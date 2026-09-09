import pytest
from pydantic import ValidationError

from warrant.schemas import EvidenceSubmission, GitHubEvidenceRef
from warrant.service import InvalidEvidence, WarrantService


def test_evidence_submission_schema():
    # Test valid github_pr
    ev = EvidenceSubmission(
        nonce="A" * 16,
        files=["src/main.py"],
        artifacts=[],
        test_output="Success",
        claimed_criteria=[],
        github_pr=GitHubEvidenceRef(owner="example-org", repo="repo", pull_request_number=42),
    )
    assert ev.github_pr is not None
    assert ev.github_pr.owner == "example-org"
    assert ev.github_pr.pull_request_number == 42

    # Test missing github_pr
    ev = EvidenceSubmission(
        nonce="A" * 16,
        files=["src/main.py"],
        artifacts=[],
        test_output="Success",
        claimed_criteria=[],
    )
    assert ev.github_pr is None

    # Test invalid pull_request_number
    with pytest.raises(ValidationError):
        EvidenceSubmission(
            nonce="A" * 16,
            files=["src/main.py"],
            artifacts=[],
            test_output="Success",
            claimed_criteria=[],
            github_pr=GitHubEvidenceRef(
                owner="example-org", repo="repo", pull_request_number=int("0")
            ),
        )


@pytest.fixture
def service_and_ids(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from warrant.config import Settings
    from warrant.db import Database
    from warrant.providers import build_provider
    from warrant.retrieval import RetrievalService

    settings = Settings(
        database_path=tmp_path / "test.db",
        ai_provider="stub",
        github_mode="stub",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4.1-mini",
        webhook_secret="test",
        csrf_token="test",
        warrant_ttl_minutes=240,
        allow_sufficiency_threshold=0.70,
        fixture_failure=None,
        debug=False,
    )

    from warrant.seed import reset_and_seed

    reset_and_seed(settings)
    db = Database(settings.database_path)
    provider = build_provider(settings)
    retrieval = RetrievalService(db, embeddings_available=True)
    svc = WarrantService(db, settings, provider, retrieval)
    workspace_id = "ws-demo"
    svc.db.execute("PRAGMA foreign_keys = OFF")
    svc.db.execute("DELETE FROM issues")
    svc.db.execute("DELETE FROM delegations")
    svc.db.execute("DELETE FROM warrants")

    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    svc.db.execute(
        "INSERT INTO issues (id, workspace_id, external_key, title, body_normalised, "
        "team, priority, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("issue-pay-4471", workspace_id, "PAY-4471", "Test Issue", "Desc", "ENG", "medium", past),
    )

    svc.db.execute(
        "INSERT INTO delegations ("
        "id, workspace_id, issue_id, requester_id, target_agent_id, source, "
        "delivery_id, untrusted_origin, status, created_at, updated_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "del_test",
            workspace_id,
            "issue-pay-4471",
            "engineer-demo",
            "codex-cloud",
            "api",
            "del1",
            0,
            "open",
            past,
            past,
        ),
    )
    import hashlib

    nonce_hash = hashlib.sha256(("A" * 16).encode()).hexdigest()
    svc.db.execute(
        "INSERT INTO warrants ("
        "id, workspace_id, delegation_id, agent_id, authority_user_id, "
        "scope_json, allowed_tools_json, denied_tools_json, evidence_contract_json, "
        "nonce_hash, nonce_plain_demo, issued_at, expires_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "war_test",
            workspace_id,
            "del_test",
            "codex-cloud",
            "lead-payments",
            svc.db.dumps([]),
            svc.db.dumps([]),
            svc.db.dumps([]),
            svc.db.dumps([]),
            nonce_hash,
            "A" * 16,
            past,
            future,
        ),
    )
    return svc, workspace_id, "war_test"


def test_submit_evidence_without_github(service_and_ids):
    svc, workspace_id, warrant_id = service_and_ids
    warrant = svc.get_warrant(warrant_id, workspace_id)
    assert warrant is not None
    nonce = warrant["demo_nonce"]

    svc.db.execute(
        "UPDATE warrants SET scope_json=? WHERE id=?",
        (svc.db.dumps(["src/warrant/db.py"]), warrant_id),
    )

    evidence = EvidenceSubmission(
        nonce=nonce,
        files=["src/warrant/db.py"],
        artifacts=[{"type": "test", "ref": "ci://simulated"}],
        test_output="Passed",
        claimed_criteria=[],
    )
    result = svc.submit_evidence(warrant_id, workspace_id, evidence)
    assert result["verdict"] in ("ALLOW", "PASS", "PASS_WITH_EXCEPTIONS", "ACCEPTED", "FAIL")
    assert result["gate1"]["github_pr_attached"] is False


def test_submit_evidence_with_github_inside_scope(service_and_ids):
    svc, workspace_id, warrant_id = service_and_ids
    warrant = svc.get_warrant(warrant_id, workspace_id)

    svc.db.execute("UPDATE warrants SET scope_json=? WHERE id=?", (svc.db.dumps(["*"]), warrant_id))

    evidence = EvidenceSubmission(
        nonce=warrant["demo_nonce"],
        files=["*"],
        artifacts=[{"type": "test", "ref": "ci://simulated"}],
        test_output="Passed",
        claimed_criteria=[],
        github_pr=GitHubEvidenceRef(owner="example-org", repo="repo", pull_request_number=42),
    )

    result = svc.submit_evidence(warrant_id, workspace_id, evidence)

    assert result["gate1"]["github_pr_attached"] is True
    assert result["gate1"]["github_files_within_scope"] is True
    assert result["gate1"]["github_checks_state"] == "passed"

    delegation = svc.get_delegation(warrant["delegation_id"], workspace_id)
    assert delegation.get("github_evidence") is not None
    assert delegation["github_evidence"]["pull_request_number"] == 42
    assert delegation["github_evidence"]["pr_url"] == "https://github.com/example-org/repo/pull/42"


def test_submit_evidence_with_github_outside_scope(service_and_ids):
    svc, workspace_id, warrant_id = service_and_ids
    warrant = svc.get_warrant(warrant_id, workspace_id)

    svc.db.execute("UPDATE warrants SET scope_json=? WHERE id=?", (svc.db.dumps([]), warrant_id))

    evidence = EvidenceSubmission(
        nonce=warrant["demo_nonce"],
        files=[],
        artifacts=[{"type": "test", "ref": "ci://simulated"}],
        test_output="Passed",
        claimed_criteria=[],
        github_pr=GitHubEvidenceRef(owner="example-org", repo="repo", pull_request_number=42),
    )

    with pytest.raises(InvalidEvidence) as exc_info:
        svc.submit_evidence(warrant_id, workspace_id, evidence)

    details = exc_info.value.details
    assert details["gate1"]["files_within_scope"] is False
    assert "src/auth.py" in details["gate1"]["outside_scope_files"]
    assert details["gate1"]["github_checks_state"] == "unverified"


def test_submit_evidence_github_fetch_failed(service_and_ids, monkeypatch):
    svc, workspace_id, warrant_id = service_and_ids
    warrant = svc.get_warrant(warrant_id, workspace_id)
    assert warrant is not None

    from warrant.adapters.github import GitHubAdapter, GitHubRequestError

    def mock_get_pull_request(*args, **kwargs):
        raise GitHubRequestError("Simulated fetch error")

    monkeypatch.setattr(GitHubAdapter, "get_pull_request", mock_get_pull_request)

    svc.db.execute(
        "UPDATE warrants SET scope_json=? WHERE id=?",
        (svc.db.dumps(["src/warrant/db.py"]), warrant_id),
    )

    evidence = EvidenceSubmission(
        nonce=warrant["demo_nonce"],
        files=["src/warrant/db.py"],
        artifacts=[{"type": "test", "ref": "ci://simulated"}],
        test_output="Passed",
        claimed_criteria=[],
        github_pr=GitHubEvidenceRef(owner="example-org", repo="repo", pull_request_number=42),
    )

    result = svc.submit_evidence(warrant_id, workspace_id, evidence)
    assert result["verdict"] == "INCONCLUSIVE"
    assert (
        "GitHub evidence could not be fetched; human review required." in result["human_check_list"]
    )


def test_github_evidence_row_and_audit(service_and_ids):
    svc, workspace_id, warrant_id = service_and_ids
    warrant = svc.get_warrant(warrant_id, workspace_id)
    svc.db.execute("UPDATE warrants SET scope_json=? WHERE id=?", (svc.db.dumps(["*"]), warrant_id))

    evidence = EvidenceSubmission(
        nonce=warrant["demo_nonce"],
        files=["*"],
        artifacts=[{"type": "test", "ref": "ci://simulated"}],
        test_output="Passed",
        claimed_criteria=[],
        github_pr=GitHubEvidenceRef(owner="example-org", repo="repo", pull_request_number=42),
    )

    svc.submit_evidence(warrant_id, workspace_id, evidence)

    snapshots = svc.db.all(
        "SELECT * FROM github_evidence_snapshots WHERE warrant_id=?", (warrant_id,)
    )
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["owner"] == "example-org"

    audit_events = svc.db.all(
        "SELECT * FROM audit_events WHERE subject_id=? AND event_type='github_evidence_attached'",
        (warrant_id,),
    )
    assert len(audit_events) == 1


def test_github_checks_failed(service_and_ids, monkeypatch):
    svc, workspace_id, warrant_id = service_and_ids
    warrant = svc.get_warrant(warrant_id, workspace_id)
    svc.db.execute("UPDATE warrants SET scope_json=? WHERE id=?", (svc.db.dumps(["*"]), warrant_id))

    from warrant.adapters.github import GitHubAdapter
    from warrant.adapters.github_dto import GitHubCheckRunDTO

    def mock_get_pull_request_checks(*args, **kwargs):
        return [
            GitHubCheckRunDTO(
                id=1,
                name="test",
                status="completed",
                conclusion="failure",
                started_at="2024-01-01T00:00:00Z",
                html_url="http://test",
            )
        ]

    monkeypatch.setattr(GitHubAdapter, "get_pull_request_checks", mock_get_pull_request_checks)

    evidence = EvidenceSubmission(
        nonce=warrant["demo_nonce"],
        files=["*"],
        artifacts=[{"type": "test", "ref": "ci://simulated"}],
        test_output="Passed",
        claimed_criteria=[],
        github_pr=GitHubEvidenceRef(owner="example-org", repo="repo", pull_request_number=42),
    )

    result = svc.submit_evidence(warrant_id, workspace_id, evidence)
    assert result["verdict"] == "FAIL"
    assert result["gate1"]["github_checks_state"] == "failed"


def test_github_checks_pending(service_and_ids, monkeypatch):
    svc, workspace_id, warrant_id = service_and_ids
    warrant = svc.get_warrant(warrant_id, workspace_id)
    svc.db.execute("UPDATE warrants SET scope_json=? WHERE id=?", (svc.db.dumps(["*"]), warrant_id))

    from warrant.adapters.github import GitHubAdapter
    from warrant.adapters.github_dto import GitHubCheckRunDTO

    def mock_get_pull_request_checks(*args, **kwargs):
        return [
            GitHubCheckRunDTO(
                id=1,
                name="test",
                status="in_progress",
                conclusion=None,
                started_at="2024-01-01T00:00:00Z",
                html_url="http://test",
            )
        ]

    monkeypatch.setattr(GitHubAdapter, "get_pull_request_checks", mock_get_pull_request_checks)

    evidence = EvidenceSubmission(
        nonce=warrant["demo_nonce"],
        files=["*"],
        artifacts=[{"type": "test", "ref": "ci://simulated"}],
        test_output="Passed",
        claimed_criteria=[],
        github_pr=GitHubEvidenceRef(owner="example-org", repo="repo", pull_request_number=42),
    )

    result = svc.submit_evidence(warrant_id, workspace_id, evidence)
    assert result["verdict"] == "PASS_WITH_EXCEPTIONS"
    assert result["gate1"]["github_checks_state"] == "pending"


def test_github_checks_none_found(service_and_ids, monkeypatch):
    svc, workspace_id, warrant_id = service_and_ids
    warrant = svc.get_warrant(warrant_id, workspace_id)
    svc.db.execute("UPDATE warrants SET scope_json=? WHERE id=?", (svc.db.dumps(["*"]), warrant_id))

    from warrant.adapters.github import GitHubAdapter

    def mock_get_pull_request_checks(*args, **kwargs):
        return []

    monkeypatch.setattr(GitHubAdapter, "get_pull_request_checks", mock_get_pull_request_checks)

    evidence = EvidenceSubmission(
        nonce=warrant["demo_nonce"],
        files=["*"],
        artifacts=[{"type": "test", "ref": "ci://simulated"}],
        test_output="Passed",
        claimed_criteria=[],
        github_pr=GitHubEvidenceRef(owner="example-org", repo="repo", pull_request_number=42),
    )

    result = svc.submit_evidence(warrant_id, workspace_id, evidence)
    assert result["verdict"] == "PASS_WITH_EXCEPTIONS"
    assert result["gate1"]["github_checks_state"] == "none_found"


def test_api_submit_evidence_with_github(service_and_ids):
    from fastapi.testclient import TestClient

    from warrant.main import create_app

    svc, workspace_id, warrant_id = service_and_ids
    warrant = svc.get_warrant(warrant_id, workspace_id)
    svc.db.execute("UPDATE warrants SET scope_json=? WHERE id=?", (svc.db.dumps(["*"]), warrant_id))

    app = create_app(svc.settings, auto_seed=False)
    # inject the existing db and service so we don't recreate them
    app.state.db = svc.db

    # We must patch the dependency in the app if it recreates WarrantService,
    # but the API endpoints initialize it from request.app.state.settings, etc.
    # Actually, it's better to just use the test client with the settings
    client = TestClient(app)

    payload = {
        "nonce": warrant["demo_nonce"],
        "files": ["src/auth.py"],
        "artifacts": [{"type": "test", "ref": "ci://simulated"}],
        "test_output": "Passed",
        "claimed_criteria": [],
        "github_pr": {"owner": "example-org", "repo": "repo", "pull_request_number": 42},
    }

    # Needs auth headers or disable auth in settings?
    # settings.auth_enabled is False by default in tests? Let's check.
    # In test fixture we didn't set auth_enabled.

    response = client.post(
        f"/v1/warrants/{warrant_id}/evidence",
        json=payload,
        headers={"X-Workspace-Id": workspace_id, "X-Csrf-Token": "test"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "verdict" in data
    assert "gate1" in data
    assert data["gate1"]["github_pr_attached"] is True


def test_github_evidence_snapshot_immutability_triggers(service_and_ids):
    import sqlite3

    import pytest

    svc, workspace_id, warrant_id = service_and_ids

    # Insert a dummy snapshot manually
    snapshot_id = svc.new_id("ghs")
    bundle_id = svc.new_id("evb")

    svc.db.execute(
        "INSERT INTO github_evidence_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            snapshot_id,
            workspace_id,
            warrant_id,
            None,
            "owner",
            "repo",
            1,
            "http://url",
            "open",
            0,
            0,
            "main",
            "sha",
            "[]",
            "[]",
            "{}",
            svc.now(),
        ),
    )

    # 1. Update of changed_files_json fails
    with pytest.raises(sqlite3.IntegrityError, match="github evidence snapshots are immutable"):
        svc.db.execute(
            "UPDATE github_evidence_snapshots SET changed_files_json=? WHERE id=?",
            ("[{}]", snapshot_id),
        )

    # 2. Delete snapshot fails
    with pytest.raises(sqlite3.IntegrityError, match="github evidence snapshots cannot be deleted"):
        svc.db.execute("DELETE FROM github_evidence_snapshots WHERE id=?", (snapshot_id,))

    # 3. Second update of evidence_bundle_id fails
    # First update should succeed
    svc.db.execute(
        "UPDATE github_evidence_snapshots SET evidence_bundle_id=? WHERE id=?",
        (bundle_id, snapshot_id),
    )

    # Second update should fail
    with pytest.raises(
        sqlite3.IntegrityError, match="github evidence snapshot bundle_id can only be set once"
    ):
        svc.db.execute(
            "UPDATE github_evidence_snapshots SET evidence_bundle_id=? WHERE id=?",
            ("new_bundle", snapshot_id),
        )


def test_github_evidence_skipped_judge_telemetry(service_and_ids, monkeypatch):
    svc, workspace_id, warrant_id = service_and_ids
    warrant = svc.get_warrant(warrant_id, workspace_id)
    svc.db.execute("UPDATE warrants SET scope_json=? WHERE id=?", (svc.db.dumps(["*"]), warrant_id))

    from warrant.adapters.github import GitHubAdapter
    from warrant.adapters.github_dto import GitHubCheckRunDTO

    def mock_get_pull_request_checks(*args, **kwargs):
        return [
            GitHubCheckRunDTO(
                id=1,
                name="test",
                status="completed",
                conclusion="failure",
                started_at="2024-01-01T00:00:00Z",
                html_url="http://test",
            )
        ]

    monkeypatch.setattr(GitHubAdapter, "get_pull_request_checks", mock_get_pull_request_checks)

    from warrant.schemas import EvidenceSubmission, GitHubEvidenceRef

    evidence = EvidenceSubmission(
        nonce=warrant["demo_nonce"],
        files=["*"],
        artifacts=[{"type": "test", "ref": "ci://simulated"}],
        test_output="Passed",
        claimed_criteria=[],
        github_pr=GitHubEvidenceRef(owner="example-org", repo="repo", pull_request_number=42),
    )

    result = svc.submit_evidence(warrant_id, workspace_id, evidence)
    assert result["verdict"] == "FAIL"

    telemetry = svc.db.all(
        "SELECT * FROM model_usage WHERE operation='judge_evidence' AND delegation_id=?",
        (warrant["delegation_id"],),
    )
    assert len(telemetry) == 0

    # Assert verification_verdicts.provider == 'not_run' and gate2_json IS NULL
    verdicts = svc.db.all(
        "SELECT * FROM verification_verdicts WHERE bundle_id IN "
        "(SELECT id FROM evidence_bundles WHERE warrant_id=?)",
        (warrant_id,),
    )
    assert len(verdicts) > 0
    assert verdicts[0]["provider"] == "not_run"
    assert verdicts[0]["gate2_json"] is None
