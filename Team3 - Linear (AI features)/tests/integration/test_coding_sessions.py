from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from warrant.coding import (
    CodingAgentRunner,
    MockCodingAgentRunner,
    MockPullRequestPublisher,
    RunnerResult,
)
from warrant.db import Database
from warrant.main import create_app
from warrant.seed import reset_and_seed

PASSING_MAKEFILE = ".PHONY: test lint\ntest:\n\t@true\nlint:\n\t@true\n"
FAILING_MAKEFILE = ".PHONY: test lint\ntest:\n\t@echo 'assertion failed'; exit 1\nlint:\n\t@true\n"


class BlockingRunner(CodingAgentRunner):
    name = "mock"
    real = False

    def __init__(self):
        self.started = threading.Event()
        self.cancelled = threading.Event()

    def is_available(self):
        return True, "test runner"

    def run(self, session_id, workspace, prompt):
        self.started.set()
        self.cancelled.wait(timeout=5)
        return RunnerResult(-15, "test cancellation", 1, cancelled=True)

    def cancel(self, session_id):
        self.cancelled.set()
        return True


class PidReportingRunner(MockCodingAgentRunner):
    """A mock that also reports an OS process id, the way a real subprocess runner does."""

    def run(self, session_id, workspace, prompt):
        self.report_process(session_id, 987654)
        return super().run(session_id, workspace, prompt)


class RestrictedPathRunner(CodingAgentRunner):
    name = "restricted"
    real = False

    def is_available(self):
        return True, "test runner"

    def run(self, session_id, workspace, prompt):
        target = workspace / "web" / "private.pem"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("restricted test material\n")
        return RunnerResult(0, "wrote a restricted file", 1)

    def cancel(self, session_id):
        return False


class NestedEnvFileRunner(CodingAgentRunner):
    """Writes a secrets file nested inside an *allowed* directory, not at the repo root.

    `BASELINE_RESTRICTED_PATHS` uses `.env*` and `**/*.pem`/`**/*.key`, but `fnmatch`
    requires a literal `/` for the `**/` prefix and forbids one for the bare `.env*`
    pattern. A `.env` written one directory below the checkout root — exactly the shape a
    real secrets leak takes — satisfies neither pattern and is expected to be rejected
    anyway, since the docstring on `BASELINE_RESTRICTED_PATHS` promises it is forbidden
    "whatever the approved scope says."
    """

    name = "nested-env"
    real = False

    def is_available(self):
        return True, "test runner"

    def run(self, session_id, workspace, prompt):
        target = workspace / "web" / ".env"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("SECRET_KEY=leaked-by-agent\n")
        return RunnerResult(0, "wrote a nested secrets file", 1)

    def cancel(self, session_id):
        return False


class NeverInvokedRunner(CodingAgentRunner):
    """Proves the abort happens before the agent is given anything to execute."""

    name = "mock"
    real = False

    def __init__(self):
        self.invocations = 0

    def is_available(self):
        return True, "test runner"

    def run(self, session_id, workspace, prompt):
        self.invocations += 1
        raise AssertionError("the runner must not be invoked under an invalid warrant")

    def cancel(self, session_id):
        return False


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def session_client(
    client, tmp_path, *, files: dict[str, str] | None = None, name="target", **overrides
):
    """A throwaway target checkout, plus a client whose repository capabilities point at it."""
    repo = tmp_path / name
    written = {"web/reports/EmptyState.tsx": "export const emptyState = 'No activity';\n"}
    written.update(files or {})
    for relative, body in written.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.test")
    git(repo, "config", "user.name", "Test")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    settings = replace(
        client.app.state.settings,
        database_path=tmp_path / f"{name}-sessions.db",
        repository_root=repo,
        coding_session_root=tmp_path / f"{name}-runtime",
        verification_command=("git", "diff", "--check"),
        external_coding_agent_enabled=False,
        **overrides,
    )
    reset_and_seed(settings)
    return TestClient(create_app(settings)), repo


def create_delegation(client, headers, issue, requester, key):
    return client.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": issue,
            "requester_id": requester,
            "target_agent_id": "codex-cloud",
            "idempotency_key": key,
        },
    ).json()


def wait_for_terminal(client, session_id):
    for _ in range(100):
        session = client.get(f"/v1/coding-sessions/{session_id}").json()
        if session["state"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return session
        time.sleep(0.03)
    raise AssertionError("coding session did not reach a terminal state")


def test_policy_allowed_mock_session_uses_worktree_verifies_and_creates_diff(
    client, headers, tmp_path
):
    app, repo = session_client(client, tmp_path)
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-allow")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock", "source": "api"},
    )
    assert started.status_code == 202
    assert started.json()["source"] == "api"
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "COMPLETED"
    assert session["provider_kind"] == "mock"
    assert session["contract"]["policy_decision"]["verdict"] == "ALLOW"
    assert session["result"]["verification"]["passed"] is True
    # Nothing is discoverable in this bare checkout, so the configured fallback is used.
    assert session["contract"]["verification_source"] == "configured"
    assert [check["command"] for check in session["verification_checks"]] == [
        ["git", "diff", "--check"]
    ]
    assert session["verification_checks"][0]["exit_code"] == 0
    assert session["host_pid"] == os.getpid()
    assert session["orphaned"] is False and session["worktree_available"] is True
    assert session["diff"]["changed_files"][0]["path"] == "web/reports/EmptyState.tsx"
    assert "Simulated coding-agent output" in session["diff"]["unified_diff"]
    assert {event["event_type"] for event in session["events"]} >= {
        "session_created",
        "worktree_created",
        "agent_started",
        "verification_passed",
        "diff_generated",
        "session_completed",
    }
    assert (
        "Simulated coding-agent output"
        not in (repo / "web" / "reports" / "EmptyState.tsx").read_text()
    )
    answered = app.post(
        "/v1/agent/query",
        headers=headers,
        json={
            "query": "What changed and did verification pass?",
            "scope": {"coding_session_id": session["id"]},
        },
    )
    assert answered.status_code == 200
    assert session["id"] in answered.json()["answer"]
    assert any(source["type"] == "coding_session" for source in answered.json()["sources"])

    before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(session["worktree_path"]),
        capture_output=True,
        text=True,
    ).stdout.strip()
    unavailable_pr = app.post(
        f"/v1/coding-sessions/{session['id']}/pull-request",
        headers=headers,
        json={"actor_id": "admin-demo"},
    )
    assert unavailable_pr.status_code == 503
    # The feature flag gates the outbound path itself, not just the gh publisher: swapping in
    # a fully available publisher must not make publishing possible.
    app.app.state.coding.publisher = MockPullRequestPublisher()
    flagged_off = app.post(
        f"/v1/coding-sessions/{session['id']}/pull-request",
        headers=headers,
        json={"actor_id": "admin-demo"},
    )
    assert flagged_off.status_code == 503
    assert flagged_off.json()["error"] == "PR publishing feature flag is disabled"
    assert app.app.state.db.one("SELECT COUNT(*) AS n FROM pull_request_artifacts")["n"] == 0
    after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(session["worktree_path"]),
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert before == after


def test_denied_or_unapproved_delegation_cannot_start_coding(client, headers, tmp_path):
    app, _ = session_client(client, tmp_path)
    denied = create_delegation(app, headers, "SEC-4502", "admin-demo", "coding-deny")
    blocked = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": denied["id"], "provider": "mock"},
    )
    assert blocked.status_code == 403

    approval = create_delegation(app, headers, "PAY-4471", "engineer-demo", "coding-approval")
    blocked = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": approval["id"], "provider": "mock"},
    )
    assert blocked.status_code == 403
    assert app.app.state.db.one("SELECT COUNT(*) AS n FROM coding_sessions")["n"] == 0


def test_human_approval_is_snapshotted_in_the_execution_contract(client, headers, tmp_path):
    app, _ = session_client(client, tmp_path)
    delegation = create_delegation(
        app, headers, "PAY-4471", "engineer-demo", "coding-approved-contract"
    )
    approved = app.post(
        f"/v1/delegations/{delegation['id']}/decision",
        headers=headers,
        json={
            "action": "approve",
            "approver_id": "lead-payments",
            "rationale": "Limit the agent to billing service code.",
        },
    )
    assert approved.status_code == 200, approved.json()
    approval = app.app.state.db.one(
        "SELECT * FROM approvals WHERE delegation_id=?", (delegation["id"],)
    )

    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    assert started.status_code == 202, started.json()
    contract_approval = started.json()["contract"]["approval"]
    assert contract_approval == {
        "id": approval["id"],
        "approver_id": "lead-payments",
        "approver_name": "Samira Lind",
        "approver_role": "lead",
        "action": "approve",
        "scope_surfaces": Database.loads(approval["narrowed_scope_json"], []),
        "rationale": "Limit the agent to billing service code.",
        "decided_at": approval["decided_at"],
    }


def test_auto_allowed_sessions_record_an_explicit_absent_approval(client, headers, tmp_path):
    """A null approval cannot be told apart from a forgotten one, so ALLOW says so outright."""
    app, _ = session_client(client, tmp_path)
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-auto-allow")
    assert delegation["decision"]["verdict"] == "ALLOW"
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    assert started.status_code == 202, started.json()
    contract = started.json()["contract"]
    assert contract["approval"]["required"] is False
    assert contract["approval"]["reason"] == "auto_allow"
    assert contract["approval"]["authority"] == "system-policy"
    assert contract["approval"]["policy_decision_verdict"] == "ALLOW"
    assert contract["approval"]["decided_at"] == delegation["warrant"]["issued_at"]

    # The restricted set is derived, not hardcoded: baseline checkout material plus every
    # protected surface in the workspace map that this warrant does not grant.
    restricted = contract["restricted_paths"]
    assert {".git/**", ".env*", "**/*.pem", "**/*.key"} <= set(restricted)
    assert {"services/auth/keys/**", "services/billing/**", "infra/deploy/**"} <= set(restricted)
    assert "docs/**" not in restricted and "web/**" not in restricted


def test_restricted_paths_follow_the_surface_map_and_the_granted_scope(client, headers, tmp_path):
    app, _ = session_client(client, tmp_path)
    coding = app.app.state.coding
    ungranted = coding._restricted_paths("ws-demo", ["web/**"])
    assert "services/auth/keys/**" in ungranted and "infra/deploy/**" in ungranted
    # A protected surface the warrant actually grants stops being forbidden; everything else
    # that is protected stays forbidden.
    granted = coding._restricted_paths("ws-demo", ["services/auth/keys/**"])
    assert "services/auth/keys/**" not in granted
    assert "infra/deploy/**" in granted and "services/billing/**" in granted
    # Unprotected surfaces are never added, and the baseline never depends on the scope.
    for derived in (ungranted, granted):
        assert "docs/**" not in derived and "web/**" not in derived
        assert derived[:4] == [".git/**", ".env*", "**/*.pem", "**/*.key"]


def test_restricted_path_write_fails_even_when_the_path_is_allowed(client, headers, tmp_path):
    app, _ = session_client(client, tmp_path)
    app.app.state.coding.runners["mock"] = RestrictedPathRunner()
    app.app.state.db.execute(
        "UPDATE issues SET path_hints_json=? WHERE external_key='WEB-4519'",
        (Database.dumps(["web/private.pem"]),),
    )
    delegation = create_delegation(
        app, headers, "WEB-4519", "lead-web", "coding-restricted-path"
    )

    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    assert started.status_code == 202, started.json()
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "FAILED"
    assert session["contract"]["allowed_paths"] == ["web/private.pem"]
    assert "**/*.pem" in session["contract"]["restricted_paths"]
    assert session["error"] == "agent changed restricted files: web/private.pem"
    assert session["verification_checks"] == []


def test_baseline_restriction_should_catch_env_nested_in_an_allowed_directory(
    client, headers, tmp_path
):
    app, _ = session_client(client, tmp_path)
    app.app.state.coding.runners["mock"] = NestedEnvFileRunner()
    delegation = create_delegation(
        app, headers, "WEB-4519", "lead-web", "coding-nested-env-gap"
    )
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    assert started.status_code == 202, started.json()
    session = wait_for_terminal(app, started.json()["id"])
    # web/** is a granted surface for this delegation, so web/.env passes the allowed-paths
    # check; it must still be caught as baseline-restricted material. Today it is not.
    assert session["state"] == "FAILED"
    assert "restricted" in (session["error"] or "").casefold()


def test_revoking_the_warrant_mid_flight_aborts_before_the_runner(client, headers, tmp_path):
    app, _ = session_client(client, tmp_path, files={"Makefile": PASSING_MAKEFILE})
    coding = app.app.state.coding
    runner = NeverInvokedRunner()
    coding.runners["mock"] = runner
    # Hold the executor between worktree preparation and the pre-run warrant re-check, so
    # the revocation lands inside the window the re-check exists to close.
    prepared, release = threading.Event(), threading.Event()
    prepare_worktree = coding._prepare_worktree

    def gated(session):
        worktree = prepare_worktree(session)
        prepared.set()
        release.wait(timeout=10)
        return worktree

    coding._prepare_worktree = gated
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-revoke-midflight")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    assert started.status_code == 202, started.json()
    assert prepared.wait(timeout=10)
    app.app.state.service.revoke_warrant(
        delegation["warrant"]["id"], "ws-demo", "admin-demo", "revoked mid-flight"
    )
    release.set()

    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "FAILED"
    assert session["error"] == "the authorising warrant was revoked; agent_run aborted"
    assert runner.invocations == 0
    assert session["diff"] is None and session["verification_checks"] == []
    failure = next(
        event for event in session["events"] if event["event_type"] == "warrant_recheck_failed"
    )
    assert failure["payload"]["stage"] == "agent_run"
    assert failure["payload"]["reason"] == "the authorising warrant was revoked"
    assert failure["payload"]["warrant_id"] == delegation["warrant"]["id"]


def test_an_expired_warrant_aborts_the_session_before_the_runner(client, headers, tmp_path):
    app, _ = session_client(client, tmp_path, files={"Makefile": PASSING_MAKEFILE})
    coding = app.app.state.coding
    runner = NeverInvokedRunner()
    coding.runners["mock"] = runner
    prepared, release = threading.Event(), threading.Event()
    prepare_worktree = coding._prepare_worktree

    def gated(session):
        worktree = prepare_worktree(session)
        prepared.set()
        release.wait(timeout=10)
        return worktree

    coding._prepare_worktree = gated
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-expire-midflight")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    assert started.status_code == 202, started.json()
    assert prepared.wait(timeout=10)
    app.app.state.db.execute(
        "UPDATE warrants SET expires_at=? WHERE id=?",
        (
            (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            delegation["warrant"]["id"],
        ),
    )
    release.set()

    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "FAILED"
    assert session["error"] == "the authorising warrant has expired; agent_run aborted"
    assert runner.invocations == 0


def test_real_runner_and_pr_publisher_are_explicitly_gated(client, headers, tmp_path):
    app, _ = session_client(client, tmp_path)
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-real-gate")
    real = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "codex"},
    )
    assert real.status_code == 403
    assert "disabled" in real.json()["error"]


def test_cancellation_requires_an_authorized_actor(client, headers, tmp_path):
    app, _ = session_client(client, tmp_path)
    runner = BlockingRunner()
    app.app.state.coding.runners["mock"] = runner
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-cancel")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock", "source": "slack"},
    )
    assert started.status_code == 202
    assert started.json()["source"] == "api"
    assert runner.started.wait(timeout=2)

    denied = app.post(
        f"/v1/coding-sessions/{started.json()['id']}/cancel",
        headers=headers,
        json={"actor_id": "engineer-platform"},
    )
    assert denied.status_code == 403

    cancelled = app.post(
        f"/v1/coding-sessions/{started.json()['id']}/cancel",
        headers=headers,
        json={"actor_id": "lead-web"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "CANCELLED"
    dispatched = next(
        event for event in cancelled.json()["events"] if event["event_type"] == "cancel_dispatched"
    )
    assert dispatched["payload"]["runner_cancelled"] is True
    assert dispatched["payload"]["recorded_host_pid"] == os.getpid()


def test_discovery_runs_every_discovered_check_and_records_each_result(client, headers, tmp_path):
    app, _ = session_client(client, tmp_path, files={"Makefile": PASSING_MAKEFILE})
    capabilities = app.get("/v1/coding-sessions/capabilities").json()
    assert capabilities["verification"]["source"] == "makefile"
    assert [check["command"] for check in capabilities["verification"]["checks"]] == [
        ["make", "test"],
        ["make", "lint"],
    ]
    assert capabilities["git_checkout"]["available"] is True

    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-discovery")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    assert started.status_code == 202
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "COMPLETED", session["error"]
    assert session["contract"]["verification_source"] == "makefile"
    assert [check["command"] for check in session["contract"]["verification_checks"]] == [
        ["make", "test"],
        ["make", "lint"],
    ]
    recorded = session["verification_checks"]
    assert [
        (item["name"], item["command"], item["exit_code"], item["passed"]) for item in recorded
    ] == [
        ("test", ["make", "test"], 0, 1),
        ("lint", ["make", "lint"], 0, 1),
    ]
    assert all(item["duration_ms"] >= 0 and item["summary"] for item in recorded)
    assert [item["name"] for item in session["result"]["verification"]["checks"]] == [
        "test",
        "lint",
    ]
    assert session["result"]["verification"]["passed"] is True
    completed = [
        event["payload"]
        for event in session["events"]
        if event["event_type"] == "verification_check_completed"
    ]
    assert [item["command"] for item in completed] == [["make", "test"], ["make", "lint"]]


def test_a_failing_required_check_fails_the_session_despite_a_clean_agent_exit(
    client, headers, tmp_path
):
    app, _ = session_client(client, tmp_path, files={"Makefile": FAILING_MAKEFILE})
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-check-fails")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    assert started.status_code == 202
    session = wait_for_terminal(app, started.json()["id"])
    # The agent exited 0 and produced an in-scope diff; the gate still refuses the session.
    assert session["state"] == "FAILED"
    assert session["result"]["runner"]["exit_code"] == 0
    assert session["diff"]["changed_files"][0]["path"] == "web/reports/EmptyState.tsx"
    assert "verification failed" in session["error"]
    assert session["result"]["verification"]["passed"] is False
    failed = [item for item in session["verification_checks"] if not item["passed"]]
    # `make` reports a failed recipe as exit 2; what matters is that it is not 0.
    assert [item["name"] for item in failed] == ["test"]
    assert failed[0]["exit_code"] not in (0, None)
    assert "assertion failed" in failed[0]["output"]
    assert {event["event_type"] for event in session["events"]} >= {"verification_failed"}
    assert "session_completed" not in {event["event_type"] for event in session["events"]}


def test_branch_carries_the_issue_key_and_title_slug(client, headers, tmp_path):
    app, _ = session_client(client, tmp_path, files={"Makefile": PASSING_MAKEFILE})
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-branch-name")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    assert started.status_code == 202
    assert started.json()["branch_name"] == "agent/web-4519-reports-empty-state-copy-is-misleading"


def test_an_existing_branch_is_uniquified_instead_of_being_reused(client, headers, tmp_path):
    app, repo = session_client(client, tmp_path, files={"Makefile": PASSING_MAKEFILE})
    derived = "agent/web-4519-reports-empty-state-copy-is-misleading"
    git(repo, "branch", derived)
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-branch-taken")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    assert started.status_code == 202
    branch = started.json()["branch_name"]
    assert branch != derived and branch.startswith(f"{derived}-")
    assert wait_for_terminal(app, started.json()["id"])["state"] == "COMPLETED"


def test_protected_branch_guard_refuses_the_targets_checked_out_branch(client, headers, tmp_path):
    app, repo = session_client(client, tmp_path, files={"Makefile": PASSING_MAKEFILE})
    coding = app.app.state.coding
    derived = "agent/web-4519-reports-empty-state-copy-is-misleading"
    # Make the branch this session would derive the repository's live checkout.
    git(repo, "switch", "-q", "-c", derived)
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-protected")
    blocked = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"] == (
        f"protected branch '{derived}' cannot be used for coding sessions"
    )
    assert app.app.state.db.one("SELECT COUNT(*) AS n FROM coding_sessions")["n"] == 0

    # The configured protected names are enforced on the derived ref and on its leaf.
    for name in ("main", "agent/main", "production"):
        try:
            coding._assert_branch_writable(name)
        except Exception as exc:  # noqa: BLE001 - the typed refusal is what is asserted
            assert type(exc).__name__ == "Forbidden"
        else:
            raise AssertionError(f"{name} must be refused")


def test_terminal_worktrees_and_branches_are_reclaimed_beyond_retention(client, headers, tmp_path):
    app, repo = session_client(
        client,
        tmp_path,
        files={
            "Makefile": PASSING_MAKEFILE,
            "web/reports/Table.tsx": "export const PAGE_SIZE = 25;\n",
        },
        coding_session_retention=1,
    )
    sessions = []
    # Two different owned, reversible web issues, so both reach ALLOW on their own merits.
    for issue in ("WEB-4519", "WEB-3001"):
        delegation = create_delegation(app, headers, issue, "lead-web", f"coding-retention-{issue}")
        started = app.post(
            "/v1/coding-sessions",
            headers=headers,
            json={"delegation_id": delegation["id"], "provider": "mock"},
        )
        assert started.status_code == 202, started.json()
        sessions.append(wait_for_terminal(app, started.json()["id"]))
    assert [session["state"] for session in sessions] == ["COMPLETED", "COMPLETED"]
    assert sessions[0]["branch_name"] != sessions[1]["branch_name"]

    oldest = app.get(f"/v1/coding-sessions/{sessions[0]['id']}").json()
    newest = app.get(f"/v1/coding-sessions/{sessions[1]['id']}").json()
    assert oldest["worktree_removed_at"] is not None
    assert not Path(oldest["worktree_path"]).exists()
    assert oldest["worktree_available"] is False
    assert newest["worktree_removed_at"] is None
    assert Path(newest["worktree_path"]).exists() and newest["worktree_available"] is True
    branches = subprocess.run(
        ["git", "branch", "--format=%(refname:short)"],
        cwd=repo,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert sessions[0]["branch_name"] not in branches
    assert sessions[1]["branch_name"] in branches
    removal = next(event for event in oldest["events"] if event["event_type"] == "worktree_removed")
    assert removal["payload"]["branch_deleted"] is True

    # A reclaimed worktree cannot silently publish a PR from stale content.
    refused = app.post(
        f"/v1/coding-sessions/{sessions[0]['id']}/pull-request",
        headers=headers,
        json={"actor_id": "admin-demo"},
    )
    assert refused.status_code == 503
    assert "reclaimed by retention" in refused.json()["error"]


def test_the_diff_records_its_head_revision_without_publishing_a_pull_request(
    client, headers, tmp_path
):
    app, _ = session_client(client, tmp_path, files={"Makefile": PASSING_MAKEFILE})
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-head-revision")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    assert started.status_code == 202, started.json()
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "COMPLETED", session["error"]
    assert session["pull_request"] is None
    head = session["diff"]["head_revision"]
    # The revision the diff was actually taken against, resolved from the worktree itself.
    assert head is not None and len(head) == 40
    resolved = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(session["worktree_path"]),
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head == resolved == session["base_revision"]


def test_draft_pull_requests_go_through_the_publisher_abstraction(client, headers, tmp_path):
    app, _ = session_client(
        client, tmp_path, files={"Makefile": PASSING_MAKEFILE}, pr_publishing_enabled=True
    )
    publisher = MockPullRequestPublisher()
    app.app.state.coding.publisher = publisher
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-pr-publish")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    assert started.status_code == 202, started.json()
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "COMPLETED", session["error"]
    uncommitted_head = session["diff"]["head_revision"]

    published = app.post(
        f"/v1/coding-sessions/{session['id']}/pull-request",
        headers=headers,
        json={"actor_id": "admin-demo"},
    )
    assert published.status_code == 200, published.json()
    artifact = published.json()
    assert artifact["provider"] == "mock-pr"
    assert artifact["number"] == 1 and artifact["state"] == "draft"
    assert artifact["url"] == "https://example.invalid/simulated/pull/1"
    assert len(publisher.created) == 1
    assert publisher.get_pull_request(Path(session["worktree_path"]), session["branch_name"])

    after = app.get(f"/v1/coding-sessions/{session['id']}").json()
    assert after["pull_request"]["url"] == artifact["url"]
    # The commit that carries the reviewed diff replaces the pre-commit head revision.
    assert after["diff"]["head_revision"] != uncommitted_head
    assert len(after["diff"]["head_revision"]) == 40
    rechecked = [
        event["payload"]["stage"]
        for event in after["events"]
        if event["event_type"] == "warrant_rechecked"
    ]
    assert rechecked == ["agent_run", "pr_publish"]


def test_reviewers_and_base_branch_travel_from_the_request_to_the_publisher(
    client, headers, tmp_path
):
    app, _ = session_client(
        client,
        tmp_path,
        files={"Makefile": PASSING_MAKEFILE},
        pr_publishing_enabled=True,
        pr_base_branch="main",
        pr_reviewers=("configured-default",),
    )
    publisher = MockPullRequestPublisher()
    app.app.state.coding.publisher = publisher
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-pr-reviewers")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "COMPLETED", session["error"]

    published = app.post(
        f"/v1/coding-sessions/{session['id']}/pull-request",
        headers=headers,
        json={
            "actor_id": "admin-demo",
            "reviewers": ["teammate-one", "acme/reviewers"],
            "base": "release/2.1",
        },
    )
    assert published.status_code == 200, published.json()
    artifact = published.json()
    # The per-request values win over the configured defaults.
    assert artifact["reviewers"] == ["teammate-one", "acme/reviewers"]
    assert artifact["base"] == "release/2.1"
    assert artifact["reviewer_error"] is None
    assert publisher.base == "release/2.1"
    assert publisher.created[0].reviewers == ("teammate-one", "acme/reviewers")
    # Who was asked to review is recorded on the timeline, where it is auditable.
    after = app.get(f"/v1/coding-sessions/{session['id']}").json()
    created_event = next(e for e in after["events"] if e["event_type"] == "pr_created")
    assert created_event["payload"]["reviewers"] == ["teammate-one", "acme/reviewers"]
    assert created_event["payload"]["base"] == "release/2.1"


def test_configured_default_reviewers_apply_when_the_request_omits_them(
    client, headers, tmp_path
):
    app, _ = session_client(
        client,
        tmp_path,
        files={"Makefile": PASSING_MAKEFILE},
        pr_publishing_enabled=True,
        pr_reviewers=("configured-default", "acme/platform"),
    )
    publisher = MockPullRequestPublisher()
    app.app.state.coding.publisher = publisher
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-pr-defaults")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "COMPLETED", session["error"]

    published = app.post(
        f"/v1/coding-sessions/{session['id']}/pull-request",
        headers=headers,
        json={"actor_id": "admin-demo"},
    )
    assert published.status_code == 200, published.json()
    assert published.json()["reviewers"] == ["configured-default", "acme/platform"]
    # No base configured and none requested: the repository's own default branch is used,
    # which is what gh does when it is given no --base at all.
    assert published.json()["base"] == "repository default"


def test_a_reviewer_handle_shaped_like_a_flag_is_refused_by_the_api(client, headers, tmp_path):
    app, _ = session_client(
        client, tmp_path, files={"Makefile": PASSING_MAKEFILE}, pr_publishing_enabled=True
    )
    publisher = MockPullRequestPublisher()
    app.app.state.coding.publisher = publisher
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-pr-badhandle")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "COMPLETED", session["error"]

    refused = app.post(
        f"/v1/coding-sessions/{session['id']}/pull-request",
        headers=headers,
        json={"actor_id": "admin-demo", "reviewers": ["--repo=someone-else/repo"]},
    )
    assert refused.status_code == 503
    assert "not a valid GitHub username" in refused.json()["error"]
    # Nothing was published and nothing was recorded.
    assert publisher.created == []
    assert app.app.state.db.one("SELECT COUNT(*) AS n FROM pull_request_artifacts")["n"] == 0


def test_pull_request_publishing_refuses_a_revoked_warrant(client, headers, tmp_path):
    app, _ = session_client(
        client, tmp_path, files={"Makefile": PASSING_MAKEFILE}, pr_publishing_enabled=True
    )
    publisher = MockPullRequestPublisher()
    app.app.state.coding.publisher = publisher
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-pr-revoked")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    assert started.status_code == 202, started.json()
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "COMPLETED", session["error"]
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(session["worktree_path"]),
        capture_output=True,
        text=True,
    ).stdout.strip()

    app.app.state.service.revoke_warrant(
        delegation["warrant"]["id"], "ws-demo", "admin-demo", "revoked before publishing"
    )
    refused = app.post(
        f"/v1/coding-sessions/{session['id']}/pull-request",
        headers=headers,
        json={"actor_id": "admin-demo"},
    )
    assert refused.status_code == 503
    assert refused.json()["type"] == "WarrantNoLongerValid"
    assert refused.json()["error"] == "the authorising warrant was revoked; pr_publish aborted"
    # Nothing was committed, nothing was published, nothing was recorded.
    assert publisher.created == []
    assert app.app.state.db.one("SELECT COUNT(*) AS n FROM pull_request_artifacts")["n"] == 0
    after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(session["worktree_path"]),
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert before == after
    failure = next(
        event
        for event in app.get(f"/v1/coding-sessions/{session['id']}").json()["events"]
        if event["event_type"] == "warrant_recheck_failed"
    )
    assert failure["payload"]["stage"] == "pr_publish"


def test_the_agent_process_id_reaches_the_session_row(client, headers, tmp_path):
    app, _ = session_client(client, tmp_path, files={"Makefile": PASSING_MAKEFILE})
    app.app.state.coding.runners["mock"] = PidReportingRunner()
    delegation = create_delegation(app, headers, "WEB-4519", "lead-web", "coding-pid")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock"},
    )
    assert started.status_code == 202
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "COMPLETED", session["error"]
    assert session["agent_pid"] == 987654
    assert session["host_pid"] == os.getpid()
    recorded = next(
        event for event in session["events"] if event["event_type"] == "agent_process_started"
    )
    assert recorded["payload"] == {"agent_pid": 987654, "host_pid": os.getpid()}


def test_sessions_orphaned_by_a_restart_are_failed_with_their_recorded_pids(
    client, headers, tmp_path
):
    app, _ = session_client(client, tmp_path, files={"Makefile": PASSING_MAKEFILE})
    coding = app.app.state.coding
    db = app.app.state.db
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO coding_sessions "
        "(id,workspace_id,delegation_id,warrant_id,issue_id,requester_id,source,provider,state,"
        "repository_root,base_revision,branch_name,worktree_path,contract_json,created_at,"
        "agent_pid,host_pid) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "ses_orphan",
            "ws-demo",
            "dlg_orphan",
            "wrt_orphan",
            "issue-web-4519",
            "lead-web",
            "api",
            "mock",
            "RUNNING",
            str(coding.repository.root),
            "HEAD",
            "agent/web-4519-orphan",
            str(tmp_path / "target-runtime" / "ses_orphan"),
            Database.dumps({"allowed_paths": ["web/**"]}),
            now,
            424242,
            os.getpid() + 100_000,
        ),
    )
    assert coding.reconcile_orphaned_sessions() == ["ses_orphan"]
    orphaned = coding.get("ses_orphan", "ws-demo")
    assert orphaned["state"] == "FAILED"
    assert "orphaned by a server restart" in orphaned["error"]
    assert "424242" in orphaned["error"]
    event = next(item for item in orphaned["events"] if item["event_type"] == "session_orphaned")
    assert event["payload"]["agent_pid"] == 424242
    assert event["payload"]["host_pid"] == os.getpid()
    # Idempotent: a second pass finds nothing left to reconcile.
    assert coding.reconcile_orphaned_sessions() == []
