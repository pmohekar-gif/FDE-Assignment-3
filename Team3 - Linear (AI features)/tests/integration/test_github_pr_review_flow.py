from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from warrant.config import Settings
from warrant.db import Database
from warrant.main import create_app
from warrant.seed import reset_and_seed


def _settings(root: Path, *, enabled: bool = True, github_mode: str = "stub") -> Settings:
    return Settings(
        database_path=root / "warrant.db",
        ai_provider="fixture",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4.1-mini",
        webhook_secret="test-webhook-secret",
        csrf_token="test-csrf",
        warrant_ttl_minutes=240,
        allow_sufficiency_threshold=0.70,
        fixture_failure=None,
        debug=False,
        github_mode=github_mode,
        github_pr_review_enabled=enabled,
    )


def _client(settings: Settings) -> TestClient:
    reset_and_seed(settings)
    return TestClient(create_app(settings), raise_server_exceptions=False)


def _headers() -> dict[str, str]:
    return {"X-Actor-Id": "priyanka-mohekar", "X-Csrf-Token": "test-csrf"}


def _create_review(client: TestClient, issue_ref: str = "WEB-4519"):
    return client.post(
        "/v1/coding-sessions/github-pr-review",
        json={
            "owner": "example-org",
            "repo": "repo",
            "pull_request_number": 42,
            "issue_ref": issue_ref,
            "source": "ui",
        },
        headers=_headers(),
    )


def test_github_integration_page_uses_single_pr_url_input(tmp_path):
    settings = _settings(tmp_path)
    client = _client(settings)

    response = client.get("/integrations/github", headers={"X-Actor-Id": "priyanka-mohekar"})

    assert response.status_code == 200
    assert "pr-url-input" in response.text
    assert "https://github.com/owner/repo/pull/123" in response.text
    assert "id=\"pr-owner\"" not in response.text
    assert "id=\"pr-repo\"" not in response.text
    assert "id=\"pr-number\"" not in response.text
    assert "issue-search" in response.text
    assert "list=\"issue-options\"" in response.text
    assert "id=\"review-issue-ref\"" in response.text
    assert "type=\"hidden\" id=\"review-issue-ref\"" in response.text
    assert "<select id=\"review-issue-ref\"" not in response.text


def test_pr_review_without_delegation_is_post_hoc_and_renders(tmp_path):
    settings = _settings(tmp_path)
    client = _client(settings)

    response = _create_review(client)

    assert response.status_code == 202
    session_id = response.json()["session_id"]
    api_response = client.get(f"/v1/coding-sessions/{session_id}", headers=_headers())
    assert api_response.status_code == 200
    session = api_response.json()
    assert session["session_kind"] == "github_pr_review"
    assert session["provider_kind"] == "external_review"
    assert session["delegation_id"] is None
    assert session["warrant_id"] is None
    assert session["result"]["pre_authorized"] is False
    assert session["result"]["governance"]["gap"] is True

    page = client.get(f"/coding-sessions/{session_id}", headers={"X-Actor-Id": "priyanka-mohekar"})
    assert page.status_code == 200
    assert "Warrant evaluated this external PR but did not launch an agent" in page.text
    assert "/delegations/None" not in page.text


def test_pr_review_feature_and_adapter_flags_fail_closed(tmp_path):
    disabled = _settings(tmp_path / "disabled", enabled=False)
    client = _client(disabled)
    response = _create_review(client)
    assert response.status_code == 403
    assert response.json()["type"] == "Forbidden"

    off = _settings(tmp_path / "off", enabled=True, github_mode="off")
    client = _client(off)
    response = _create_review(client)
    assert response.status_code == 403
    assert response.json()["type"] == "Forbidden"


def test_pr_link_rejects_same_pr_for_different_issue(tmp_path):
    settings = _settings(tmp_path)
    client = _client(settings)
    payload = {
        "owner": "example-org",
        "repo": "repo",
        "pull_request_number": 42,
        "issue_ref": "WEB-4519",
    }

    first = client.post("/v1/integrations/github/pr-link", json=payload, headers=_headers())
    assert first.status_code == 200
    second = client.post(
        "/v1/integrations/github/pr-link",
        json={**payload, "issue_ref": "PAY-4471"},
        headers=_headers(),
    )
    assert second.status_code == 409
    assert second.json()["type"] == "Conflict"


def test_pr_review_can_share_warrant_with_agent_execution(tmp_path):
    settings = _settings(tmp_path)
    client = _client(settings)
    db = Database(settings.database_path)
    now = "2026-01-01T00:00:00+00:00"
    db.execute(
        "INSERT INTO delegations ("
        "id, workspace_id, issue_id, requester_id, target_agent_id, source, delivery_id, "
        "untrusted_origin, status, created_at, updated_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "dlg-existing",
            settings.workspace_id,
            "issue-web-4519",
            "priyanka-mohekar",
            "codex-cloud",
            "ui",
            "existing-delivery",
            0,
            "warrant_issued",
            now,
            now,
        ),
    )
    db.execute(
        "INSERT INTO warrants ("
        "id, workspace_id, delegation_id, agent_id, authority_user_id, scope_json, "
        "allowed_tools_json, denied_tools_json, evidence_contract_json, nonce_hash, "
        "issued_at, expires_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "war-existing",
            settings.workspace_id,
            "dlg-existing",
            "codex-cloud",
            "priyanka-mohekar",
            json.dumps(["*"]),
            "[]",
            "[]",
            "[]",
            "hash",
            now,
            "2027-01-01T00:00:00+00:00",
        ),
    )
    db.execute(
        "INSERT INTO coding_sessions ("
        "id, workspace_id, delegation_id, warrant_id, issue_id, requester_id, source, "
        "provider, state, repository_root, base_revision, contract_json, created_at, "
        "session_kind"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "ses-agent-existing",
            settings.workspace_id,
            "dlg-existing",
            "war-existing",
            "issue-web-4519",
            "priyanka-mohekar",
            "ui",
            "mock",
            "COMPLETED",
            "/tmp/repo",
            "main",
            "{}",
            now,
            "agent_execution",
        ),
    )

    response = _create_review(client)

    assert response.status_code == 202
    session = client.get(
        f"/v1/coding-sessions/{response.json()['session_id']}", headers=_headers()
    ).json()
    assert session["warrant_id"] == "war-existing"
    assert session["result"]["pre_authorized"] is True
    assert session["result"]["governance"]["consumed_warrant"] is True
    assert session["result"]["governance"]["verdict"] == "PASS"
