"""The four Governance decision actions, each asserted on what it is supposed to mean.

Approve grants the whole proposed scope; narrowing grants only the selected subset and
supersedes anything holding it; a hold is temporary and reversible; a denial is final.
Every one of them lands in the hash-chained audit ledger with its named approver.
"""

from __future__ import annotations


def delegate(client, headers, issue, requester, key):
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
    assert response.status_code < 300, response.text
    return response.json()


def decide(client, headers, delegation_id, body, actor):
    return client.post(
        f"/v1/delegations/{delegation_id}/decision",
        headers={**headers, "X-Actor-Id": actor},
        json=body,
    )


def test_approve_grants_the_whole_proposed_scope(client, headers):
    delegation = delegate(client, headers, "PAY-4471", "chirayu-gupta", "action-approve")
    proposed = delegation["risk_assessment"]["proposed_surfaces"]
    decided = decide(
        client,
        headers,
        delegation["id"],
        {"action": "approve", "approver_id": "priyanka-mohekar", "rationale": "ok"},
        "priyanka-mohekar",
    )
    assert decided.status_code == 200
    assert decided.json()["warrant"]["scope_surfaces"] == proposed
    approval = decided.json()["approval"]
    assert approval["action"] == "approve"
    assert approval["approver_name"] == "Priyanka Mohekar"
    assert approval["rationale"] == "ok"


def test_approve_refuses_a_partial_selection_instead_of_widening_it(client, headers):
    """Unticking a surface and pressing Approve used to grant the full scope anyway."""
    delegation = delegate(client, headers, "PAY-4471", "chirayu-gupta", "action-approve-partial")
    proposed = delegation["risk_assessment"]["proposed_surfaces"]
    assert len(proposed) > 1
    refused = decide(
        client,
        headers,
        delegation["id"],
        {
            "action": "approve",
            "approver_id": "priyanka-mohekar",
            "narrowed_surfaces": proposed[:1],
        },
        "priyanka-mohekar",
    )
    assert refused.status_code == 422
    assert "narrow" in refused.json()["error"]
    # Still undecided, so the operator can pick the action they actually meant.
    assert client.get(f"/v1/delegations/{delegation['id']}").json()["status"] == (
        "awaiting_approval"
    )


def test_narrow_issues_only_the_selected_scope(client, headers):
    delegation = delegate(client, headers, "PAY-4471", "chirayu-gupta", "action-narrow")
    proposed = delegation["risk_assessment"]["proposed_surfaces"]
    decided = decide(
        client,
        headers,
        delegation["id"],
        {
            "action": "narrow",
            "approver_id": "priyanka-mohekar",
            "narrowed_surfaces": proposed[:1],
            "rationale": "smallest useful grant",
        },
        "priyanka-mohekar",
    )
    assert decided.status_code == 200
    warrant = decided.json()["warrant"]
    assert warrant["scope_surfaces"] == proposed[:1]
    assert decided.json()["approval"]["action"] == "narrow"
    # The narrowed scope, not the proposal, is what the agent may write.
    assert set(warrant["scope_surfaces"]).issubset(set(proposed))


def test_narrow_supersedes_a_warrant_already_holding_the_surface(client, headers):
    """Narrowing skipped the supersede path, so two live warrants could share a surface."""
    first = delegate(client, headers, "PAY-4471", "chirayu-gupta", "action-hold-first")
    granted = decide(
        client,
        headers,
        first["id"],
        {"action": "approve", "approver_id": "priyanka-mohekar", "rationale": "first"},
        "priyanka-mohekar",
    )
    assert granted.status_code == 200
    held_warrant = granted.json()["warrant"]["id"]
    second = delegate(client, headers, "PAY-3000", "chirayu-gupta", "action-hold-second")
    overlapping = second["risk_assessment"]["proposed_surfaces"]
    assert "services/billing/retry.py" in overlapping
    narrowed = decide(
        client,
        headers,
        second["id"],
        {
            "action": "narrow",
            "approver_id": "priyanka-mohekar",
            "narrowed_surfaces": ["services/billing/retry.py"],
            "rationale": "supersede",
        },
        "priyanka-mohekar",
    )
    assert narrowed.status_code == 200
    # A revoked warrant is 410 Gone, and its revocation reason names the supersede.
    superseded = client.get(f"/v1/warrants/{held_warrant}")
    assert superseded.status_code == 410
    assert second["id"] in superseded.json()["details"]["revoke_reason"]
    assert narrowed.json()["warrant"]["status"] == "active"


def test_hold_defers_without_denying_and_can_be_lifted(client, headers):
    delegation = delegate(client, headers, "PAY-4471", "chirayu-gupta", "action-hold")
    held = decide(
        client,
        headers,
        delegation["id"],
        {
            "action": "defer",
            "approver_id": "priyanka-mohekar",
            "rationale": "waiting on the owner",
        },
        "priyanka-mohekar",
    )
    assert held.status_code == 200
    assert held.json()["status"] == "deferred"
    assert held.json()["warrant"] is None
    assert held.json()["resumable"] is True
    assert held.json()["approval"]["action"] == "defer"
    assert held.json()["approval"]["rationale"] == "waiting on the owner"
    # A hold is not a decision anyone can act around while it stands.
    blocked = decide(
        client,
        headers,
        delegation["id"],
        {"action": "approve", "approver_id": "priyanka-mohekar"},
        "priyanka-mohekar",
    )
    assert blocked.status_code == 409
    resumed = client.post(
        f"/v1/delegations/{delegation['id']}/resume",
        headers={**headers, "X-Actor-Id": "priyanka-mohekar"},
        json={"actor_id": "priyanka-mohekar", "note": "owner replied"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "awaiting_approval"
    assert resumed.json()["approval"] is None
    assert resumed.json()["resumable"] is False
    # And the delegation is genuinely decidable again, with its policy work intact.
    approved = decide(
        client,
        headers,
        delegation["id"],
        {"action": "approve", "approver_id": "priyanka-mohekar", "rationale": "cleared"},
        "priyanka-mohekar",
    )
    assert approved.status_code == 200
    assert approved.json()["warrant"]["scope_surfaces"] == (
        delegation["risk_assessment"]["proposed_surfaces"]
    )


def test_resume_requires_an_approver_and_a_held_delegation(client, headers):
    delegation = delegate(client, headers, "PAY-4471", "chirayu-gupta", "action-resume-gate")
    not_held = client.post(
        f"/v1/delegations/{delegation['id']}/resume",
        headers={**headers, "X-Actor-Id": "priyanka-mohekar"},
        json={"actor_id": "priyanka-mohekar"},
    )
    assert not_held.status_code == 409
    assert "deferred" in not_held.json()["error"]
    decide(
        client,
        headers,
        delegation["id"],
        {"action": "defer", "approver_id": "priyanka-mohekar"},
        "priyanka-mohekar",
    )
    outsider = client.post(
        f"/v1/delegations/{delegation['id']}/resume",
        headers={**headers, "X-Actor-Id": "gaurav-yadav-archive"},
        json={"actor_id": "gaurav-yadav-archive"},
    )
    assert outsider.status_code == 403
    no_csrf = client.post(
        f"/v1/delegations/{delegation['id']}/resume",
        headers={"X-Actor-Id": "priyanka-mohekar"},
        json={"actor_id": "priyanka-mohekar"},
    )
    assert no_csrf.status_code == 400


def test_deny_is_final(client, headers):
    delegation = delegate(client, headers, "PAY-4471", "chirayu-gupta", "action-deny")
    denied = decide(
        client,
        headers,
        delegation["id"],
        {"action": "deny", "approver_id": "priyanka-mohekar", "rationale": "not this quarter"},
        "priyanka-mohekar",
    )
    assert denied.status_code == 200
    assert denied.json()["status"] == "denied_by_human"
    assert denied.json()["warrant"] is None
    assert denied.json()["approval"]["action"] == "deny"
    assert denied.json()["resumable"] is False
    reopened = client.post(
        f"/v1/delegations/{delegation['id']}/resume",
        headers={**headers, "X-Actor-Id": "priyanka-mohekar"},
        json={"actor_id": "priyanka-mohekar"},
    )
    assert reopened.status_code == 409


def test_every_authorising_decision_reaches_the_audit_ledger(client, headers):
    """approve and narrow emitted no approval event, so the rationale that granted
    authority was missing from the hash-chained ledger."""
    recorded: dict[str, str] = {}
    for index, (issue, action, extra) in enumerate(
        [
            ("PAY-4471", "approve", {}),
            ("PAY-3000", "narrow", {"narrowed_surfaces": ["services/billing/retry.py"]}),
        ]
    ):
        delegation = delegate(client, headers, issue, "chirayu-gupta", f"audit-{index}")
        response = decide(
            client,
            headers,
            delegation["id"],
            {
                "action": action,
                "approver_id": "priyanka-mohekar",
                "rationale": f"{action} rationale",
                **extra,
            },
            "priyanka-mohekar",
        )
        assert response.status_code == 200, response.text
        recorded[action] = delegation["id"]

    rows = client.app.state.db.all(
        "SELECT event_type,subject_id,payload_json FROM audit_events "
        "WHERE event_type LIKE 'approval_%'",
        (),
    )
    by_type = {row["event_type"]: row for row in rows}
    assert "approval_approve" in by_type
    assert "approval_narrow" in by_type
    assert "approve rationale" in by_type["approval_approve"]["payload_json"]
    assert "narrow rationale" in by_type["approval_narrow"]["payload_json"]
    # The ledger stays verifiable with the extra entries in it.
    verified = client.app.state.service.audit.verify_detail(
        client.app.state.settings.workspace_id
    )
    assert verified["verified"] is True
