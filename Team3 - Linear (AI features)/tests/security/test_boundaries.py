def create_payment(client, headers, key="security"):
    return client.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": "PAY-4471",
            "requester_id": "engineer-demo",
            "target_agent_id": "codex-cloud",
            "idempotency_key": key,
        },
    ).json()


def test_csrf_and_cross_tenant_resources_are_not_exposed(client):
    assert (
        client.post(
            "/v1/delegations",
            json={
                "issue_ref": "WEB-4519",
                "requester_id": "lead-web",
                "target_agent_id": "codex-cloud",
                "idempotency_key": "missing-csrf",
            },
        ).status_code
        == 400
    )
    created = client.post(
        "/v1/delegations",
        headers={"X-CSRF-Token": "test-csrf"},
        json={
            "issue_ref": "WEB-4519",
            "requester_id": "lead-web",
            "target_agent_id": "codex-cloud",
            "idempotency_key": "tenant",
        },
    ).json()
    assert (
        client.get(
            f"/v1/delegations/{created['id']}", headers={"X-Workspace-ID": "ws-other"}
        ).status_code
        == 404
    )


def test_self_approval_and_scope_widening_are_blocked(client, headers):
    created = create_payment(client, headers, "approval-boundaries")
    self_approval = client.post(
        f"/v1/delegations/{created['id']}/decision",
        headers=headers,
        json={"action": "approve", "approver_id": "engineer-demo"},
    )
    assert self_approval.status_code == 403
    widening = client.post(
        f"/v1/delegations/{created['id']}/decision",
        headers=headers,
        json={
            "action": "narrow",
            "approver_id": "admin-demo",
            "narrowed_surfaces": ["services/auth/keys/**"],
        },
    )
    assert widening.status_code == 422


def test_nonce_replay_is_rejected(client, headers):
    created = client.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": "WEB-4519",
            "requester_id": "lead-web",
            "target_agent_id": "codex-cloud",
            "idempotency_key": "nonce",
        },
    ).json()
    warrant = created["warrant"]
    body = {
        "nonce": warrant["demo_nonce"],
        "files": warrant["scope_surfaces"],
        "artifacts": [{"type": "test", "ref": "ci://fixture"}],
        "test_output": "passed requested behaviour existing behaviour stable",
        "claimed_criteria": created["extraction"]["result"]["acceptance_criteria"],
    }
    assert (
        client.post(
            f"/v1/warrants/{warrant['id']}/evidence", headers=headers, json=body
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/v1/warrants/{warrant['id']}/evidence", headers=headers, json=body
        ).status_code
        == 409
    )


def test_audit_table_rejects_mutation(client):
    service = client.app.state.service
    create_payment(client, {"X-CSRF-Token": "test-csrf"}, "audit-trigger")
    try:
        service.db.execute("UPDATE audit_events SET event_type='tampered' WHERE seq=1")
    except Exception as exc:
        assert "append-only" in str(exc)
    else:
        raise AssertionError("audit mutation unexpectedly succeeded")


def test_audit_export_requires_admin_for_json_and_csv(client):
    for suffix in ("", "?format=csv"):
        non_admin = client.get(
            f"/v1/audit{suffix}", headers={"X-Actor-ID": "engineer-demo"}
        )
        assert non_admin.status_code == 403

        admin = client.get(f"/v1/audit{suffix}", headers={"X-Actor-ID": "admin-demo"})
        assert admin.status_code == 200
        if suffix:
            assert admin.headers["content-type"].startswith("text/csv")
        else:
            assert admin.json()["chain_verified"] is True
