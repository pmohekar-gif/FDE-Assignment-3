"""End-to-end regressions for the Governance -> delegation -> agent -> diff path.

These are the behaviours that were broken in the delivered build: an approved
protected-surface delegation could never produce a diff, a session whose approved scope
did not exist in the configured checkout failed late with an unexplained
`agent_failed`, and an agent that changed nothing (or only ignored files) gave the
operator no way to tell those two cases apart.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from warrant.coding import CodingAgentRunner, RunnerResult
from warrant.main import create_app
from warrant.seed import reset_and_seed

BILLING_RETRY = '''"""Checkout capture retries."""

RETRY_WINDOW_SECONDS = 5.0
'''
RETRY_BUTTON = "export const RETRY_LABEL = 'Retry payment';\n"


class SilentRunner(CodingAgentRunner):
    """Exits cleanly having changed nothing -- what a real agent does with no work to do."""

    name = "mock"
    real = False

    def is_available(self):
        return True, "test runner"

    def run(self, session_id, workspace, prompt):
        return RunnerResult(0, "nothing to change", 1)

    def cancel(self, session_id):
        return False


class HookBlockedRunner(CodingAgentRunner):
    """Reproduces a real CHIR-1104 run: an ambient Codex hook denied the prompt.

    The CLI exits 0 having changed nothing, so on the evidence the session sees this is
    indistinguishable from an agent that read the code and decided no change was needed —
    except for one line in the transcript.
    """

    name = "mock"
    real = False

    def is_available(self):
        return True, "test runner"

    def run(self, session_id, workspace, prompt):
        return RunnerResult(
            0,
            "OpenAI Codex v0.153.0\n"
            "--------\n"
            f"workdir: {workspace}\n"
            "approval: never\n"
            "--------\n"
            "hook: SessionStart\n"
            "hook: SessionStart Completed\n"
            "hook: UserPromptSubmit\n"
            "hook: UserPromptSubmit Blocked\n",
            1,
        )

    def cancel(self, session_id):
        return False


class IgnoredWriteRunner(CodingAgentRunner):
    """Writes only where the target repository's ignore rules hide the change."""

    name = "mock"
    real = False

    def is_available(self):
        return True, "test runner"

    def run(self, session_id, workspace, prompt):
        target = workspace / "web" / "generated" / "bundle.js"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("// produced by the agent\n")
        return RunnerResult(0, "wrote a generated file", 1)

    def cancel(self, session_id):
        return False


class SecretWritingRunner(CodingAgentRunner):
    """Writes a change containing both a real-looking credential and an ordinary email.

    Reproduces a real post-isolation failure: the agent produced an in-scope diff, but
    `redact_diff_content` found secret-shaped material in it and the session was refused
    outright, with no way to tell a real leak from an address in a comment.
    """

    name = "mock"
    real = False

    def is_available(self):
        return True, "test runner"

    def run(self, session_id, workspace, prompt):
        target = workspace / "web" / "reports" / "EmptyState.tsx"
        target.write_text(
            "// contact support@example.com with questions\n"
            "export const emptyState = 'No activity';\n"
            'export const apiKey = "sk_live_0123456789abcdef";\n'
        )
        return RunnerResult(0, "added a support contact and a key", 1)

    def cancel(self, session_id):
        return False


class NeighbourOfASecretRunner(CodingAgentRunner):
    """Changes one line in a file that already contains secret-shaped material.

    The demo checkout's `infra/deploy/auth.yaml` carries
    `signing_key_secret: auth-signing-key` -- a Kubernetes reference to a secret's
    *name*. Every session whose diff merely showed a line like that as context used to
    fail with `secret_assignment`, for material the agent never wrote.
    """

    name = "mock"
    real = False

    def is_available(self):
        return True, "test runner"

    def run(self, session_id, workspace, prompt):
        target = workspace / "web" / "reports" / "EmptyState.tsx"
        target.write_text(
            "const auth_token = 'preexisting-value-from-the-base-revision';\n"
            "export const emptyState = 'Create your first report';\n"
        )
        return RunnerResult(0, "changed the empty-state copy", 1)

    def cancel(self, session_id):
        return False


class NewTestFileWithSyntheticTokenRunner(CodingAgentRunner):
    """Reproduces the real CHIR-1104 failure: a genuine `codex` run wrote a brand-new
    integration test for a GitHub-token-bearing adapter, and the synthetic token needed
    to exercise the auth-header code path failed the session. The file is new, so there
    is no removed/context line for `carried` to compare against -- only recognising the
    test path exempts it.
    """

    name = "mock"
    real = False

    def is_available(self):
        return True, "test runner"

    def run(self, session_id, workspace, prompt):
        target = workspace / "tests" / "integration" / "test_github_evidence.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "class FakeGitHubRequester:\n"
            "    pass\n\n"
            "class TestGithubEvidence:\n"
            "    def test_fetch(self):\n"
            '        adapter = GitHubEvidenceAdapter("acme", "roadmap", '
            'api_key="ghp_faketoken1234567890abcd", requester=FakeGitHubRequester())\n'
        )
        return RunnerResult(0, "added an integration test", 1)

    def cancel(self, session_id):
        return False


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def target_client(client, tmp_path, files: dict[str, str], name: str, **overrides):
    repo = tmp_path / name
    for relative, body in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.test")
    git(repo, "config", "user.name", "Test")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    settings = replace(
        client.app.state.settings,
        database_path=tmp_path / f"{name}.db",
        repository_root=repo,
        coding_session_root=tmp_path / f"{name}-runtime",
        verification_command=("git", "diff", "--check"),
        external_coding_agent_enabled=False,
        **overrides,
    )
    reset_and_seed(settings)
    return TestClient(create_app(settings)), repo


def delegate(app, headers, issue, requester, key):
    return app.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": issue,
            "requester_id": requester,
            "target_agent_id": "codex-cloud",
            "idempotency_key": key,
        },
    ).json()


def approve(app, headers, delegation, approver="priyanka-mohekar"):
    return app.post(
        f"/v1/delegations/{delegation['id']}/decision",
        headers={**headers, "X-Actor-Id": approver},
        json={
            "action": "approve",
            "approver_id": approver,
            "narrowed_surfaces": delegation["risk_assessment"]["proposed_surfaces"],
            "rationale": "approved for the regression test",
        },
    )


def wait_for_terminal(app, session_id):
    for _ in range(200):
        session = app.get(f"/v1/coding-sessions/{session_id}").json()
        if session["state"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            return session
        time.sleep(0.03)
    raise AssertionError("coding session did not reach a terminal state")


def test_an_approved_protected_surface_produces_a_reviewable_diff(client, headers, tmp_path):
    """The headline failure: approval on a protected surface could never yield a diff.

    `services/billing/retry.py` sits under the protected `services/billing/**` surface.
    The restricted-path list was built with the scope/glob match inverted, so the
    surface stayed restricted and the approved file was rejected as restricted material.
    """
    app, _ = target_client(
        client,
        tmp_path,
        {"services/billing/retry.py": BILLING_RETRY, "web/checkout/RetryButton.tsx": RETRY_BUTTON},
        "protected",
    )
    delegation = delegate(app, headers, "PAY-4471", "chirayu-gupta", "protected-diff")
    assert delegation["decision"]["verdict"] == "REQUIRE_APPROVAL"
    decided = approve(app, headers, delegation)
    assert decided.status_code == 200
    warrant = decided.json()["warrant"]
    assert "services/billing/retry.py" in warrant["scope_surfaces"]
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock", "source": "api"},
    )
    assert started.status_code == 202
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "COMPLETED", session["error"]
    assert session["diff"]["changed_files"], "an approved protected surface produced no diff"
    assert [item["path"] for item in session["diff"]["changed_files"]] == [
        "services/billing/retry.py"
    ]
    assert session["result"]["verification"]["passed"] is True
    # The protected surface is still recorded as restricted material for the audit trail;
    # what changed is that the approved path inside it is no longer refused.
    assert "services/billing/ledger/**" in session["contract"]["restricted_paths"]


def test_a_scope_the_checkout_does_not_contain_is_refused_at_launch(client, headers, tmp_path):
    app, _ = target_client(
        client,
        tmp_path,
        {"services/billing/retry.py": BILLING_RETRY, "web/checkout/RetryButton.tsx": RETRY_BUTTON},
        "missing-scope",
    )
    # CHIR-1103's declared surfaces live in the control plane's own tree, which this
    # target checkout does not have. Launching there could only ever fail later.
    delegation = delegate(app, headers, "CHIR-1103", "chirayu-gupta", "missing-scope")
    assert delegation["status"] == "warrant_issued"
    refused = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock", "source": "api"},
    )
    assert refused.status_code == 409
    body = refused.json()["error"]
    assert "does not exist in the configured repository" in body
    assert "src/warrant/main.py" in body
    assert str(app.app.state.settings.repository_root) in body
    # Nothing was created: no session row, so no worktree and no branch either.
    assert app.app.state.db.all("SELECT id FROM coding_sessions", ()) == []


def test_a_resolvable_scope_records_the_preflight_on_the_timeline(client, headers, tmp_path):
    app, _ = target_client(
        client,
        tmp_path,
        {"web/reports/EmptyState.tsx": "export const emptyState = 'No activity';\n"},
        "preflight",
    )
    delegation = delegate(app, headers, "WEB-4519", "chirayu-gupta", "preflight")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock", "source": "api"},
    )
    session = wait_for_terminal(app, started.json()["id"])
    preflight = [
        event for event in session["events"] if event["event_type"] == "scope_preflight"
    ]
    assert len(preflight) == 1
    payload = preflight[0]["payload"]
    assert payload["unresolved"] == []
    assert payload["resolved"] == {"web/reports/EmptyState.tsx": ["web/reports/EmptyState.tsx"]}
    assert payload["tracked_file_count"] >= 1


def test_an_agent_that_changes_nothing_is_diagnosed_not_just_reported(client, headers, tmp_path):
    app, _ = target_client(
        client,
        tmp_path,
        {"web/reports/EmptyState.tsx": "export const emptyState = 'No activity';\n"},
        "silent",
    )
    app.app.state.coding.runners["mock"] = SilentRunner()
    delegation = delegate(app, headers, "WEB-4519", "chirayu-gupta", "silent")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock", "source": "api"},
    )
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "FAILED"
    assert "left the approved paths unchanged" in session["error"]
    assert "web/reports/EmptyState.tsx" in session["error"]
    diagnosed = [
        event for event in session["events"] if event["event_type"] == "empty_diff_diagnosed"
    ]
    assert len(diagnosed) == 1
    assert diagnosed[0]["payload"]["paths_present_in_checkout"] == ["web/reports/EmptyState.tsx"]
    assert diagnosed[0]["payload"]["ignored_writes"] == []


def test_a_hook_that_blocked_the_prompt_is_named_as_the_cause(client, headers, tmp_path):
    """The reported CHIR-1104 failure: blamed on the agent, caused by the agent's config."""
    app, _ = target_client(
        client,
        tmp_path,
        {"web/reports/EmptyState.tsx": "export const emptyState = 'No activity';\n"},
        "hook-blocked",
    )
    app.app.state.coding.runners["mock"] = HookBlockedRunner()
    delegation = delegate(app, headers, "WEB-4519", "chirayu-gupta", "hook-blocked")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock", "source": "api"},
    )
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "FAILED"
    assert "never received the task" in session["error"]
    assert "UserPromptSubmit" in session["error"]
    # All three mechanisms are named, because "Blocked" is consistent with each: a
    # content denial, a hook that failed for want of an environment variable, and a
    # guard that refuses the unattended `--ask-for-approval never` run.
    assert "both when it denies and when it merely fails" in session["error"]
    assert "CODING_AGENT_ENV_PASSTHROUGH" in session["error"]
    assert "--ask-for-approval never" in session["error"]
    # It must not be reported as the agent declining, nor as a scope problem.
    assert "left the approved paths unchanged" not in session["error"]
    assert "does not own the scope" not in session["error"]
    blocked = [event for event in session["events"] if event["event_type"] == "agent_hook_blocked"]
    assert len(blocked) == 1
    assert blocked[0]["payload"]["hooks"] == ["UserPromptSubmit"]
    assert blocked[0]["payload"]["turn_gating"] == ["UserPromptSubmit"]
    diagnosed = [
        event for event in session["events"] if event["event_type"] == "empty_diff_diagnosed"
    ]
    assert diagnosed[0]["payload"]["turn_gating_hooks_blocked"] == ["UserPromptSubmit"]
    # A completed SessionStart in the same transcript is not counted as a denial.
    assert "SessionStart" not in blocked[0]["payload"]["hooks"]


def test_a_write_the_repository_ignores_is_named_as_the_reason(client, headers, tmp_path):
    app, _ = target_client(
        client,
        tmp_path,
        {
            "web/reports/EmptyState.tsx": "export const emptyState = 'No activity';\n",
            ".gitignore": "web/generated/\n",
        },
        "ignored",
    )
    app.app.state.coding.runners["mock"] = IgnoredWriteRunner()
    delegation = delegate(app, headers, "WEB-4519", "chirayu-gupta", "ignored")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock", "source": "api"},
    )
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "FAILED"
    assert "the target repository ignores" in session["error"]
    assert "web/generated/" in session["error"]
    diagnosed = [
        event for event in session["events"] if event["event_type"] == "empty_diff_diagnosed"
    ]
    assert diagnosed and diagnosed[0]["payload"]["ignored_writes"]


def test_a_synthetic_token_in_a_new_integration_test_does_not_fail_the_session(
    client, headers, tmp_path
):
    """The real repeat failure, reproduced with the actual failing ticket: CHIR-1104's
    scope covers `tests/integration/test_github_evidence.py`, and a real `codex` run
    wrote exactly that file with a synthetic GitHub token to test the adapter's
    auth-header handling. The file is brand new -- no removed/context line for
    `carried` to compare against -- so this only passes if the test-path exemption
    fires.
    """
    app, _ = target_client(
        client,
        tmp_path,
        {
            "src/warrant/adapters/github.py": "SURFACE = 'src/warrant/adapters/github.py'\n",
            "src/warrant/pr_review.py": "SURFACE = 'src/warrant/pr_review.py'\n",
        },
        "synthetic-token",
    )
    app.app.state.coding.runners["mock"] = NewTestFileWithSyntheticTokenRunner()
    delegation = delegate(app, headers, "CHIR-1104", "chirayu-gupta", "synthetic-token")
    if delegation["status"] == "awaiting_approval":
        decided = approve(app, headers, delegation)
        assert decided.status_code == 200, decided.text
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock", "source": "api"},
    )
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "COMPLETED", session["error"]
    assert "ghp_faketoken1234567890abcd" not in session["diff"]["unified_diff"]
    assert "REDACTED" in session["diff"]["unified_diff"]
    redacted = [
        event for event in session["events"] if event["event_type"] == "diff_secrets_redacted"
    ]
    assert len(redacted) == 1
    assert redacted[0]["payload"]["redactions"] == 0, "must not be blamed on the agent"
    assert redacted[0]["payload"]["test_fixture"] >= 1


def test_a_secret_already_in_the_file_does_not_fail_the_session(client, headers, tmp_path):
    """The reported repeat failure: `secret_assignment` on a line the agent never wrote.

    The base revision already contains a credential-shaped line. The agent changes a
    different line in the same file, so that line appears in the diff as context. The
    session must complete -- and must still record that redaction happened.
    """
    app, _ = target_client(
        client,
        tmp_path,
        {
            "web/reports/EmptyState.tsx": (
                "const auth_token = 'preexisting-value-from-the-base-revision';\n"
                "export const emptyState = 'No activity';\n"
            )
        },
        "carried-secret",
    )
    app.app.state.coding.runners["mock"] = NeighbourOfASecretRunner()
    delegation = delegate(app, headers, "WEB-4519", "chirayu-gupta", "carried-secret")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock", "source": "api"},
    )
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "COMPLETED", session["error"]
    assert session["diff"]["changed_files"], "the agent's real change must survive"
    # The pre-existing value is still scrubbed from what gets stored...
    assert "preexisting-value-from-the-base-revision" not in session["diff"]["unified_diff"]
    assert "REDACTED" in session["diff"]["unified_diff"]
    # ...and the redaction is on the timeline, attributed to the file rather than the agent.
    redacted = [
        event for event in session["events"] if event["event_type"] == "diff_secrets_redacted"
    ]
    assert len(redacted) == 1
    assert redacted[0]["payload"]["redactions"] == 0, "nothing was introduced by the agent"
    assert redacted[0]["payload"]["carried"] >= 1
    assert redacted[0]["payload"]["carried_kinds"] == ["secret_assignment"]


def test_secret_shaped_content_names_which_pattern_fired_and_why_it_matters(
    client, headers, tmp_path
):
    """A real post-isolation failure: the diff was in scope, but contained an email
    address and something shaped like a live API key. The session must say which is
    which, never repeat the matched text, and record the event on the timeline even
    though the diff itself (already redacted) is safe.
    """
    app, _ = target_client(
        client,
        tmp_path,
        {"web/reports/EmptyState.tsx": "export const emptyState = 'No activity';\n"},
        "secret-shaped",
    )
    app.app.state.coding.runners["mock"] = SecretWritingRunner()
    delegation = delegate(app, headers, "WEB-4519", "chirayu-gupta", "secret-shaped")
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation["id"], "provider": "mock", "source": "api"},
    )
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "FAILED"
    assert "sk_live_0123456789abcdef" not in session["error"]
    assert "support@example.com" not in session["error"]
    # secret_assignment (a credential-named variable assigned a value) matches the key
    # line first, per SECRET_PATTERNS' own ordering, before api_key gets a chance at it.
    assert "secret_assignment" in session["error"]
    assert "email" in session["error"]
    assert "real leak" in session["error"]
    assert "not by itself evidence" in session["error"]
    redacted = [
        event for event in session["events"] if event["event_type"] == "diff_secrets_redacted"
    ]
    assert len(redacted) == 1
    assert set(redacted[0]["payload"]["kinds"]) == {"secret_assignment", "email"}
    assert redacted[0]["payload"]["redactions"] >= 2
    # The stored diff is still there for review, with the match replaced, not the diff
    # itself thrown away.
    assert "sk_live_0123456789abcdef" not in session["diff"]["unified_diff"]
    assert "REDACTED" in session["diff"]["unified_diff"]
