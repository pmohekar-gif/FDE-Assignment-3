from datetime import datetime, timedelta, timezone

import pytest


def create(client, headers, issue, requester, key):
    return client.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": issue,
            "requester_id": requester,
            "target_agent_id": "codex-cloud",
            "idempotency_key": key,
        },
    )


def approve_payment(client, headers, key):
    created = create(client, headers, "PAY-4471", "engineer-demo", key).json()
    approved = client.post(
        f"/v1/delegations/{created['id']}/decision",
        headers=headers,
        json={
            "action": "approve",
            "approver_id": "admin-demo",
            "rationale": "failure-matrix fixture approval",
        },
    ).json()
    return created, approved["warrant"]


def evidence_for(created, warrant):
    return {
        "nonce": warrant["demo_nonce"],
        "files": warrant["scope_surfaces"],
        "artifacts": [{"type": "test", "ref": "ci://failure-matrix"}],
        "test_output": (
            "tests passed; second retry must not create another charge; "
            "existing single-charge path remains stable"
        ),
        "claimed_criteria": created["extraction"]["result"]["acceptance_criteria"],
    }


@pytest.mark.parametrize(
    "failure",
    [
        "provider_5xx",
        "malformed",
        "embedding",
        "policy_unloadable",
        "duplicate_delivery",
        "evidence_after_expiry",
        "replayed_nonce",
        "judge_unavailable",
        "audit_write_failure",
        "stale_surface_map",
    ],
)
def test_every_expressible_failure_mode_never_allows(
    client_factory, headers, monkeypatch, failure
):
    injected = failure if failure in {
        "provider_5xx",
        "malformed",
        "embedding",
        "policy_unloadable",
        "judge_unavailable",
        "stale_surface_map",
    } else None
    client = client_factory(injected)
    observed_authority = "ABORTED"

    if failure in {
        "provider_5xx",
        "malformed",
        "embedding",
        "policy_unloadable",
        "stale_surface_map",
    }:
        result = create(client, headers, "WEB-4519", "lead-web", failure).json()
        observed_authority = result["decision"]["verdict"]
        assert result["decision"]["fail_closed"] is True

    elif failure == "duplicate_delivery":
        first = create(client, headers, "PAY-4471", "engineer-demo", failure).json()
        second = create(client, headers, "PAY-4471", "engineer-demo", failure).json()
        assert second["idempotent_replay"] is True
        assert first["id"] == second["id"]
        assert len(client.app.state.db.all("SELECT id FROM delegations")) == 1
        observed_authority = second["decision"]["verdict"]

    elif failure in {"evidence_after_expiry", "replayed_nonce", "judge_unavailable"}:
        created, warrant = approve_payment(client, headers, failure)
        evidence = evidence_for(created, warrant)
        observed_authority = created["decision"]["verdict"]
        if failure == "evidence_after_expiry":
            past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
            client.app.state.db.execute(
                "UPDATE warrants SET expires_at=? WHERE id=?", (past, warrant["id"])
            )
            response = client.post(
                f"/v1/warrants/{warrant['id']}/evidence", headers=headers, json=evidence
            )
            assert response.status_code == 410
        elif failure == "replayed_nonce":
            endpoint = f"/v1/warrants/{warrant['id']}/evidence"
            assert client.post(endpoint, headers=headers, json=evidence).status_code == 200
            assert client.post(endpoint, headers=headers, json=evidence).status_code == 409
        else:
            response = client.post(
                f"/v1/warrants/{warrant['id']}/evidence", headers=headers, json=evidence
            )
            assert response.json()["verdict"] == "INCONCLUSIVE"

    elif failure == "audit_write_failure":
        def fail_audit(*args, **kwargs):
            raise RuntimeError("injected audit write failure")

        monkeypatch.setattr(client.app.state.service.audit, "append", fail_audit)
        with pytest.raises(RuntimeError, match="audit write failure"):
            create(client, headers, "PAY-4471", "engineer-demo", failure)
        assert not client.app.state.db.one("SELECT id FROM warrants LIMIT 1")

    assert observed_authority != "ALLOW"
