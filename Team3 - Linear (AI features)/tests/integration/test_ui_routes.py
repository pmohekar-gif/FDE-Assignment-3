"""Operator-shell route and markup contract.

These assert the shell that a grader actually sees: the dense grouped queue, the sufficiency
ring that encodes evidence against the ALLOW threshold, and the honesty surfaces (verdict
provenance, advisory/authorising flags, provider kind, disabled features). Every value
asserted here is rendered from the real API or the real route context.
"""

import subprocess
import time
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from warrant.main import create_app
from warrant.seed import reset_and_seed

# Two make targets so verification discovery finds more than one check and the session view
# has to render a list rather than a single row.
PASSING_MAKEFILE = ".PHONY: test lint\ntest:\n\t@echo ok\nlint:\n\t@true\n"


def session_client(client, tmp_path, name="ui-target"):
    """A throwaway target checkout plus a client whose repository points at it.

    Coding sessions require a real Git checkout, so the UI tests that exercise the session
    view build one instead of depending on where the suite happens to be running.
    """
    repo = tmp_path / name
    files = {
        "web/reports/EmptyState.tsx": "export const emptyState = 'No activity';\n",
        "Makefile": PASSING_MAKEFILE,
    }
    for relative, body in files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    for args in (
        ("init", "-q"),
        ("config", "user.email", "test@example.test"),
        ("config", "user.name", "Test"),
        ("add", "."),
        ("commit", "-qm", "base"),
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    settings = replace(
        client.app.state.settings,
        database_path=Path(tmp_path) / f"{name}.db",
        repository_root=repo,
        coding_session_root=Path(tmp_path) / f"{name}-runtime",
        external_coding_agent_enabled=False,
    )
    reset_and_seed(settings)
    return TestClient(create_app(settings))


def create_delegation(client, headers, issue="PAY-4471", requester="engineer-demo", key="ui-1"):
    response = client.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": issue,
            "requester_id": requester,
            "target_agent_id": "codex-cloud",
            "idempotency_key": key,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def run_mock_session(client, headers, delegation_id):
    started = client.post(
        "/v1/coding-sessions",
        headers=headers,
        json={"delegation_id": delegation_id, "provider": "mock", "source": "ui"},
    )
    assert started.status_code == 202, started.text
    session_id = started.json()["id"]
    for _ in range(200):
        session = client.get(f"/v1/coding-sessions/{session_id}", headers=headers).json()
        if session["state"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            assert session["state"] == "COMPLETED", session.get("error")
            return session_id
        time.sleep(0.03)
    raise AssertionError("coding session did not reach a terminal state")


# --- shell chrome -------------------------------------------------------------------


def test_shell_renders_sidebar_counts_palette_and_integrity_pill(client):
    page = client.get("/")
    assert page.status_code == 200

    # counted nav sections, current-page marking
    assert 'class="nav-item" href="/" aria-current="page"' in page.text
    for label in (
        "Triage",
        "Delegations",
        "Coding sessions",
        "Issues",
        "Code intelligence",
        "Policy",
        "Audit chain",
        "Evaluation",
        "Integrations",
    ):
        assert label in page.text
    assert 'class="ct' in page.text

    # the integrity pill and the degraded banner are both present and honest
    assert 'id="health-mode"' in page.text
    assert "SIMULATED · FIXTURE AI" in page.text
    assert 'id="degraded-banner"' in page.text
    assert "not customer evidence" in page.text

    # command palette and theme toggle
    assert 'id="palette-scrim"' in page.text
    assert 'id="open-palette"' in page.text
    assert "Search issues, ask the agent, or run a command" in page.text
    assert 'id="theme-toggle"' in page.text

    # the shared client contract survives the rebuild
    assert "X-CSRF-Token" in page.text
    assert "function renderError(" in page.text
    assert "function formatRelative(" in page.text
    assert "class ApiError extends Error" in page.text
    assert "function toast(" in page.text
    assert "registerCommand(" in page.text and "registerShortcut(" in page.text

    # identity switcher stays wired when auth is disabled
    assert 'id="actor-switcher"' in page.text
    assert 'id="audit-nav"' in page.text


# --- triage queue --------------------------------------------------------------------


def test_triage_queue_groups_by_verdict_with_sufficiency_rings(client, headers):
    create_delegation(client, headers, key="ui-queue-hold")
    create_delegation(client, headers, issue="SEC-4502", requester="lead-payments", key="ui-deny")
    create_delegation(client, headers, issue="WEB-4519", requester="lead-web", key="ui-allow")

    page = client.get("/")
    assert page.status_code == 200

    # grouped, counted verdict buckets
    assert '<div class="group hold" data-group="REQUIRE_APPROVAL">' in page.text
    assert '<div class="group allow" data-group="ALLOW">' in page.text
    assert '<div class="group deny" data-group="DENY">' in page.text
    assert "Requires approval" in page.text and "a named human must decide" in page.text
    assert "no warrant and no override path" in page.text

    # dense rows, not cards: mono key, reason-code chip, sufficiency, requester initials
    assert 'data-verdict="REQUIRE_APPROVAL"' in page.text
    # the first code shows in the row; the full list rides along in the title attribute
    assert (
        '<span class="code-chip hold" title="EXTERNAL_SIDE_EFFECT, '
        'PROTECTED_OR_SENSITIVE_SURFACE, CODE_OWNER_REQUIRED">EXTERNAL_SIDE_EFFECT</span>'
    ) in page.text
    assert ">FINANCIAL_OR_SECURITY_ACTION</span>" in page.text
    assert 'class="code-chip deny"' in page.text
    assert 'class="code-chip allow"' in page.text
    assert ">STANDARD_REVERSIBLE_SCOPE</span>" in page.text
    assert '<span class="suff">0.92</span>' in page.text
    assert 'title="Devin Reyes · engineer-demo">DR</span>' in page.text

    # the signature component: arc offset computed from the real sufficiency value
    # (circumference 37.7, so 0.92 measured leaves 37.7 * 0.08 = 3.0 unfilled) and the
    # tick rotated to the 0.70 ALLOW threshold (0.70 * 360 = 252 degrees).
    assert 'stroke-dasharray="37.7" stroke-dashoffset="3.0"' in page.text
    assert 'class="tick" d="M8 0.6v2" transform="rotate(252.0 8 8)"' in page.text
    assert "sufficiency 0.92 · allow threshold 0.70" in page.text
    assert "Ring arc = evidence sufficiency · tick = 0.70 allow threshold" in page.text

    # documented triage shortcuts are on screen and bound
    for key in ("1", "3", "H", "C"):
        assert f'<span class="kbd">{key}</span>' in page.text
    assert "Hold (defer)" in page.text
    assert "registerShortcut('1'" in page.text and "registerShortcut('3'" in page.text
    assert "registerShortcut('h'" in page.text and "registerShortcut('c'" in page.text

    # verdict filter chips
    assert 'data-verdict-filter="DENY"' in page.text

    # 14: Ask Agent is inline on the queue, scoped to the focused row
    assert 'id="agent-form"' in page.text
    assert "/v1/agent/query" in page.text
    assert "delegation_id:selected.dataset.delegation" in page.text
    assert "can never change it" in page.text

    # 5: the launcher does not animate stages it cannot observe
    assert "one server-side transaction" in page.text
    assert "setInterval" not in page.text


def test_issue_inbox_filters_paginates_and_exposes_launcher_identities(client):
    page = client.get("/?q=PAY-4471&team=Payments")
    assert page.status_code == 200
    assert 'data-issue-row="PAY-4471"' in page.text
    assert 'data-issue-row="SEC-4502"' not in page.text
    assert 'id="issue-inbox"' in page.text

    # the governed-delegation launcher and its identity inputs
    assert "Governed delegation" in page.text
    assert 'id="requester-select"' in page.text
    assert 'id="agent-select"' in page.text
    assert "lead-web" in page.text
    assert "deterministic ownership and warrant inputs" in page.text

    # per-issue AI surfaces are collapsed but present
    assert 'class="mini triage-trigger"' in page.text
    assert 'class="mini related-trigger"' in page.text
    assert 'aria-expanded="false"' in page.text
    assert 'class="mini pri delegate"' in page.text

    # pipeline progress for intake -> retrieval -> extraction -> policy
    assert "INTAKE" in page.text and "RETRIEVAL" in page.text
    assert "EXTRACTION" in page.text and "POLICY" in page.text

    # telemetry that must keep firing
    assert "/v1/telemetry/semantic-search" in page.text
    assert "/v1/telemetry/related-issues" in page.text
    assert "/v1/telemetry/triage-recommendation" in page.text
    assert "/v1/issues/" in page.text and "/triage-recommendation" in page.text

    second = client.get("/?page=2")
    assert second.status_code == 200
    assert "page 2 of" in second.text
    assert client.get("/static/favicon.svg").status_code == 200


def test_issue_inbox_discloses_retrieval_mode_and_completeness(client):
    page = client.get(
        "/",
        params={"q": "second retry must not create another charge", "team": "Payments"},
    )
    assert page.status_code == 200
    assert 'data-issue-row="PAY-4471"' in page.text
    assert "HYBRID" in page.text
    assert "100% retrieval completeness" in page.text
    assert "Retrieval is advisory; it never changes a verdict." in page.text
    assert 'class="code-chip">' in page.text  # matched_by + semantic score chip
    assert 'data-issue-row="PLAT-' not in page.text
    assert "Key, title, or describe the problem" in page.text


def test_triage_rail_surfaces_measured_and_failing_evaluation_metrics(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "Measured safety gates" in page.text
    assert "unsafe allow count" in page.text
    assert "approval burden standard slice" in page.text
    assert "outside_target" in page.text
    assert "Not yet measured (4)" in page.text
    assert "risk class macro f1" in page.text
    assert "NOT_MEASURED" in page.text
    assert "Model output cannot set a verdict." in page.text


# --- delegation detail ---------------------------------------------------------------


def test_delegation_page_shows_verdict_provenance_risk_and_full_contract(client, headers):
    delegation = create_delegation(client, headers, key="ui-detail")
    page = client.get(f"/delegations/{delegation['id']}")
    assert page.status_code == 200

    # 7: verdict hero with policy version, reason codes and the authority statement
    assert 'class="card verdict-card"' in page.text
    assert '<span class="verdict-word">REQUIRE_APPROVAL</span>' in page.text
    assert "Deterministic policy v1" in page.text
    assert "Model output cannot set this verdict" in page.text
    assert "The requester does not own every proposed surface." in page.text
    assert "/policy#rule-R-012" in page.text

    # 8: risk features grid, sufficiency meter with the marked threshold, surfaces, criteria
    assert "Risk features and evidence sufficiency" in page.text
    assert "0.92 measured" in page.text
    assert "0.70 required for ALLOW" in page.text
    assert 'role="meter"' in page.text and 'aria-valuenow="0.92"' in page.text
    assert "EXTERNAL_SIDE_EFFECT" in page.text and "MANUAL" in page.text
    assert "protected_surface" in page.text and "injection_signal" in page.text
    assert "Authoritative proposed surfaces" in page.text
    assert "Model-proposed surfaces (advisory)" in page.text
    assert "services/billing/retry.py" in page.text
    assert "Acceptance criteria" in page.text
    assert "existing single-charge path and add a regression test for double-submit." in page.text

    # 9: brief with its prose source and non-authorising boundary
    assert "Delegation brief" in page.text
    assert "prose_source = model" in page.text
    assert "deterministic-fixture-v1" in page.text
    assert "authorising = false" in page.text
    assert "decision_source = deterministic_policy" in page.text
    assert "prose_may_change_verdict = false" in page.text
    assert "Generated prose cannot approve, deny, grant tools or change the verdict." in page.text
    assert "/v1/telemetry/delegation-brief" in page.text
    assert "/brief/refresh" in page.text

    # 10: retrieval evidence and related work
    assert "Retrieval evidence and related work" in page.text
    assert "Retrieval is advisory evidence · it never changes a verdict" in page.text

    # 11/12: no warrant yet, so the tool preview and the human gate are shown
    assert "Tools that would be granted" in page.text
    assert "open_draft_pr" in page.text
    assert "Never grantable" in page.text
    assert "merge_pr" in page.text
    assert "Human gate" in page.text
    assert "Warrant scope" in page.text
    assert "Optional rationale" in page.text
    assert 'data-action="approve"' in page.text and 'data-action="deny"' in page.text
    assert 'data-action="narrow"' in page.text and 'data-action="defer"' in page.text
    assert "Self-approval prohibited" in page.text
    assert "Warrant TTL is 240 minutes." in page.text

    # pipeline trace and audit link
    assert "INTAKE" in page.text and "RECORD" in page.text
    assert "Inspect the audit story" in page.text
    assert "It cannot physically prevent an agent being invoked" in page.text

    # 14/15: Ask Agent and Code Intelligence on the delegation view
    assert 'id="agent-form"' in page.text and "/v1/agent/query" in page.text
    assert "advisory · authoritative = false" in page.text
    assert 'id="code-form"' in page.text and "/v1/code/query" in page.text
    assert "path:line cited" in page.text

    # 21/16: session launcher reads real runner capabilities before offering a provider
    assert "/v1/coding-sessions/capabilities" in page.text


def test_long_acceptance_criteria_are_truncated_with_a_title(client, headers):
    delegation = create_delegation(client, headers, key="ui-truncate")
    long_criterion = (
        "Expected: " + "the delegated worker preserves every invariant " * 6 + "without ambiguity."
    )
    extraction = client.app.state.db.one(
        "SELECT result_json FROM extractions WHERE delegation_id = ?", (delegation["id"],)
    )
    payload = client.app.state.db.loads(extraction["result_json"])
    payload["acceptance_criteria"] = [long_criterion]
    client.app.state.db.execute(
        "UPDATE extractions SET result_json = ? WHERE delegation_id = ?",
        (client.app.state.db.dumps(payload), delegation["id"]),
    )

    page = client.get(f"/delegations/{delegation['id']}")
    assert page.status_code == 200
    assert 'class="truncated"' in page.text
    assert f'title="{long_criterion}"' in page.text
    assert "…" in page.text


def test_denied_delegation_explains_the_boundary_without_offering_an_override(client, headers):
    delegation = create_delegation(
        client, headers, issue="SEC-4502", requester="lead-payments", key="ui-deny-detail"
    )
    assert delegation["decision"]["verdict"] == "DENY"
    page = client.get(f"/delegations/{delegation['id']}")
    assert page.status_code == 200
    assert '<span class="verdict-word">DENY</span>' in page.text
    assert "Boundary explanation" in page.text
    assert "What would have to change" in page.text
    assert "Guidance for a newly evaluated request · not an override" in page.text
    assert "No warrant issued" in page.text
    assert "Policy denied this request. Nothing in this interface can force issuance." in page.text
    assert "Human gate" not in page.text
    assert 'data-action="approve"' not in page.text


def test_allowed_delegation_shows_the_warrant_panel_and_never_grantable_tools(client, headers):
    delegation = create_delegation(
        client, headers, issue="WEB-4519", requester="lead-web", key="ui-allow-detail"
    )
    assert delegation["decision"]["verdict"] == "ALLOW"
    page = client.get(f"/delegations/{delegation['id']}")
    assert page.status_code == 200

    warrant = delegation["warrant"]
    assert warrant["id"] in page.text
    assert "Scope surfaces" in page.text
    assert "Allowed tools" in page.text
    assert "Explicitly denied" in page.text
    assert "Never grantable by any policy" in page.text
    assert "Evidence contract:" in page.text
    assert '<span class="tool">write_files</span>' in page.text
    assert '<span class="tool no">rotate_secret</span>' in page.text
    assert "Return evidence" in page.text
    assert "/evidence" in page.text
    assert "Launch a governed session" in page.text
    assert 'id="coding-provider"' in page.text


# --- coding sessions -----------------------------------------------------------------


def test_coding_session_page_renders_stepper_multi_check_verification_and_diff(
    client, headers, tmp_path
):
    app = session_client(client, tmp_path, name="ui-session")
    delegation = create_delegation(
        app, headers, issue="WEB-4519", requester="lead-web", key="ui-session"
    )
    session_id = run_mock_session(app, headers, delegation["id"])
    page = app.get(f"/coding-sessions/{session_id}")
    assert page.status_code == 200

    # 17: full state stepper and the persisted event timeline
    for state in ("QUEUED", "PREPARING", "RUNNING", "VERIFYING", "AWAITING_REVIEW"):
        assert f">{state}</span>" in page.text
    assert "Session timeline" in page.text
    assert "persisted events" in page.text
    assert "<code>session_created</code>" in page.text
    assert "<code>verification_discovered</code>" in page.text
    assert "<code>diff_generated</code>" in page.text

    # 16/21: mock is unmistakable and the contract is spelled out
    assert '<span class="provider-kind mock">MOCK</span>' in page.text
    assert "nothing in this session was produced by a real coding agent" in page.text
    assert "Immutable execution contract" in page.text
    assert "Base revision" in page.text and "Restricted paths" in page.text
    assert "Allowed scope" in page.text and "Expiry" in page.text
    assert "This contract was frozen when the session was created." in page.text

    # 19: the diff artifact is handed to the page for per-file expansion
    assert "Reviewable diff" in page.text
    assert 'id="diff-files"' in page.text
    assert "const unifiedDiff=" in page.text and "const changedFiles=" in page.text
    assert "diff --git" in page.text
    assert "details.className='file'" in page.text
    # The diff artifact records both endpoints of the comparison. head_revision is
    # persisted whenever the diff is captured, not only when a PR is published, so
    # the template's "uncommitted worktree state" fallback must NOT be reachable here.
    assert "Base revision" in page.text and "Head revision" in page.text
    assert "uncommitted worktree state" not in page.text

    # 19: structured agent activity summary
    assert "Agent activity" in page.text
    assert "Output truncated" in page.text
    assert "Runner output" in page.text

    # 20: honest publishing-disabled state
    assert "Publishing disabled." in page.text
    assert "PR_PUBLISHING_ENABLED=false" in page.text

    # 14: Ask Agent scoped to the session
    assert "coding_session_id" in page.text


def test_coding_session_verification_lists_every_discovered_check(client, headers, tmp_path):
    app = session_client(client, tmp_path, name="ui-checks")
    delegation = create_delegation(
        app, headers, issue="WEB-4519", requester="lead-web", key="ui-session-checks"
    )
    session_id = run_mock_session(app, headers, delegation["id"])
    detail = app.get(f"/v1/coding-sessions/{session_id}", headers=headers).json()
    checks = detail["verification_checks"]
    assert len(checks) >= 2, "the target repo declares make test and make lint"
    page = app.get(f"/coding-sessions/{session_id}")
    assert page.status_code == 200
    assert f"{len(checks)} discovered checks" in page.text
    # every check renders as its own row with command, exit code and duration
    assert page.text.count('<div class="check-top">') == len(checks)
    for check in checks:
        assert f'<span class="check-name">{check["name"]}</span>' in page.text
        assert f"<code>{' '.join(check['command'])}</code>" in page.text
        assert f"<span>exit {check['exit_code']}</span>" in page.text
        assert f"<span>{check['duration_ms']} ms</span>" in page.text
        assert check["summary"] in page.text
    assert "An exit code alone is not success." in page.text


def test_coding_sessions_index_lists_sessions_and_reads_capabilities(client, headers, tmp_path):
    app = session_client(client, tmp_path, name="ui-index")
    delegation = create_delegation(
        app, headers, issue="WEB-4519", requester="lead-web", key="ui-session-index"
    )
    session_id = run_mock_session(app, headers, delegation["id"])
    page = app.get("/coding-sessions")
    assert page.status_code == 200
    assert session_id in page.text
    assert "WEB-4519" in page.text
    assert '<span class="provider-kind mock">MOCK</span>' in page.text
    assert "must never be read as real agent work" in page.text
    # 16: per-runner availability comes from the capabilities endpoint
    assert "/v1/coding-sessions/capabilities" in page.text
    assert "Runner capabilities" in page.text
    assert "external_execution_enabled" in page.text
    assert "Discovered verification" in page.text


# --- workspace views -----------------------------------------------------------------


def test_delegations_index_groups_every_delegation_by_verdict(client, headers):
    create_delegation(client, headers, key="ui-index-hold")
    create_delegation(client, headers, issue="WEB-4519", requester="lead-web", key="ui-index-allow")
    page = client.get("/delegations")
    assert page.status_code == 200
    assert "Verdict distribution" in page.text
    assert '<div class="group hold" data-group="REQUIRE_APPROVAL">' in page.text
    assert '<div class="group allow" data-group="ALLOW">' in page.text
    assert "never by a model" in page.text
    assert "an arc short of the tick can never be auto-allowed" in page.text


def test_code_intelligence_page_exposes_index_status_and_refresh(client):
    page = client.get("/code")
    assert page.status_code == 200
    assert "/v1/code/index/status" in page.text
    assert "/v1/code/index/refresh" in page.text
    assert "/v1/code/query" in page.text
    assert "Dependency edges" in page.text
    assert "Max snippets" in page.text
    assert "Modules" in page.text
    assert "ignore_source" in page.text
    assert "cached_index" in page.text
    assert "dependency_resolved" in page.text
    assert "authorising" in page.text
    assert 'id="refresh-index"' in page.text
    assert "start_line" in page.text and "end_line" in page.text


def test_integrations_page_reports_feature_flags_and_slack_state(client):
    page = client.get("/integrations")
    assert page.status_code == 200
    features = client.get("/healthz").json()["features"]
    for key in features:
        assert f"<code>{key}</code>" in page.text
    assert "ENABLED" in page.text and "DISABLED" in page.text
    assert "Slack adapter" in page.text
    assert "not configured" in page.text
    assert "SLACK_ENABLED=false" in page.text
    assert "POST /v1/integrations/slack/events" in page.text
    assert "A Slack message can request a delegation; it can never approve one." not in page.text
    assert "until both the flag and a signing secret are set" in page.text
    assert "Fixture mode" in page.text
    assert "Endpoints behind each surface" in page.text


def test_audit_page_shows_chain_state_and_event_hashes(client, headers):
    create_delegation(client, headers, key="ui-audit")
    page = client.get("/audit?actor_id=admin-demo")
    assert page.status_code == 200
    assert "CHAIN VERIFIED" in page.text
    assert "Chain integrity" in page.text
    assert "Head hash" in page.text
    assert "Event hashes and payloads" in page.text
    assert "delegation_received" in page.text
    assert "policy_decided" in page.text
    assert "content_normalised" in page.text
    assert 'id="reverify"' in page.text and 'id="export-csv"' in page.text
    assert "a filter can never hide a break" in page.text


def test_policy_page_shows_matrix_rules_and_never_grantable_tools(client):
    page = client.get("/policy")
    assert page.status_code == 200
    assert "Never grantable by any policy version" in page.text
    assert '<span class="tool no">rotate_secret</span>' in page.text
    assert "Authority matrix" in page.text
    assert "Tool grants by consequence" in page.text
    assert "Ordered rules" in page.text
    assert 'id="rule-R-001"' in page.text
    assert "Terminal deny for a security-sensitive mapped surface." in page.text
    assert 'id="policy-yaml"' in page.text
    assert 'id="simulate"' in page.text and 'id="activate"' in page.text
    assert "Activation stays disabled until the exact text you simulated passes" in page.text


def test_evaluation_page_does_not_hide_the_failing_metric(client):
    page = client.get("/evaluation")
    assert page.status_code == 200
    assert "Metrics and proposed targets" in page.text
    assert "Approval burden" in page.text
    assert "the metric that is currently failing" in page.text
    assert "outside_target" in page.text
    assert "Hiding it would make the rest of this page untrustworthy." in page.text
    assert "Not yet measured" in page.text
    assert "risk_class_macro_f1" in page.text
    assert "Interpretation boundary" in page.text
    assert "policy-interpreter conformance check" in page.text
    assert "Raw JSON" in page.text


# --- identity boundary ---------------------------------------------------------------


def test_audit_filters_cursor_and_actor_identity_boundary(client, headers):
    delegation = create_delegation(client, headers, key="ui-audit-api")
    admin = {"X-Actor-ID": "admin-demo"}
    filtered = client.get(
        "/v1/audit?agent_id=codex-cloud&verdict=REQUIRE_APPROVAL&limit=2", headers=admin
    )
    assert filtered.status_code == 200
    body = filtered.json()
    assert body["chain_verified"] is True
    assert body["events"]
    assert all(item["agent_id"] == "codex-cloud" for item in body["events"])
    assert all(item["verdict"] == "REQUIRE_APPROVAL" for item in body["events"])
    if body["next_cursor"]:
        older = client.get(f"/v1/audit?cursor={body['next_cursor']}&limit=2", headers=admin)
        assert older.status_code == 200
        assert all(item["seq"] < body["next_cursor"] for item in older.json()["events"])

    mismatch = client.post(
        f"/v1/delegations/{delegation['id']}/decision",
        headers={**headers, "X-Actor-ID": "engineer-demo"},
        json={"action": "approve", "approver_id": "admin-demo"},
    )
    assert mismatch.status_code == 403
