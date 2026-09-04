def test_complete_customer_journey(client, headers):
    created = client.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": "PAY-4471",
            "requester_id": "engineer-demo",
            "target_agent_id": "codex-cloud",
            "idempotency_key": "e2e-payment",
        },
    ).json()
    assert created["status"] == "awaiting_approval"
    scope = created["risk_assessment"]["proposed_surfaces"][:1]
    approved = client.post(
        f"/v1/delegations/{created['id']}/decision",
        headers=headers,
        json={
            "action": "narrow",
            "approver_id": "admin-demo",
            "narrowed_surfaces": scope,
            "rationale": "Synthetic E2E approval",
        },
    ).json()
    warrant = approved["warrant"]
    assert warrant["scope_surfaces"] == scope
    verified = client.post(
        f"/v1/warrants/{warrant['id']}/evidence",
        headers=headers,
        json={
            "nonce": warrant["demo_nonce"],
            "files": scope,
            "artifacts": [{"type": "test", "ref": "ci://synthetic/e2e"}],
            "test_output": (
                "14 passed. second retry must not create another charge; "
                "existing single-charge path remains stable; regression test attached."
            ),
            "claimed_criteria": created["extraction"]["result"]["acceptance_criteria"],
        },
    )
    assert verified.status_code == 200
    assert verified.json()["verdict"] in {"PASS", "PASS_WITH_EXCEPTIONS"}
    audit_headers = {"X-Actor-ID": "admin-demo"}
    audit = client.get("/v1/audit", headers=audit_headers).json()
    assert audit["chain_verified"] is True
    assert {event["event_type"] for event in audit["events"]} >= {
        "delegation_received",
        "policy_decided",
        "warrant_issued",
        "evidence_verified",
    }
    assert (
        client.get("/v1/audit?format=csv", headers=audit_headers)
        .headers["content-type"]
        .startswith("text/csv")
    )
