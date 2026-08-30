from datetime import datetime, timedelta, timezone
from pathlib import Path

POLICY = (Path(__file__).parents[2] / "policies" / "default.v1.yaml").read_text()


def create_web(client, headers, key="conformance"):
    return client.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": "WEB-4519",
            "requester_id": "lead-web",
            "target_agent_id": "codex-cloud",
            "idempotency_key": key,
        },
    ).json()


def test_policy_lifecycle_validation_admin_and_adversarial_gate(client, headers):
    non_admin = client.post(
        "/v1/policies/simulate",
        headers={**headers, "X-Actor-ID": "engineer-demo"},
        json={"yaml_source": POLICY},
    )
    assert non_admin.status_code == 403

    invalid = client.post(
        "/v1/policies/simulate",
        headers={**headers, "X-Actor-ID": "admin-demo"},
        json={"yaml_source": "version: ["},
    )
    assert invalid.status_code == 422
    assert invalid.json()["details"][0]["line"] == 1

    unsafe = POLICY.replace("version: v1", "version: v-unsafe", 1).replace(
        "verdict: REQUIRE_APPROVAL\n    reason_codes: [INJECTION_SIGNAL]",
        "verdict: ALLOW\n    reason_codes: [INJECTION_SIGNAL]",
        1,
    )
    unsafe_simulation = client.post(
        "/v1/policies/simulate",
        headers={**headers, "X-Actor-ID": "admin-demo"},
        json={"yaml_source": unsafe, "against": "last_n_delegations", "n": 10},
    )
    assert unsafe_simulation.status_code == 409
    rejected = client.post(
        "/v1/policies",
        headers={**headers, "X-Actor-ID": "admin-demo"},
        json={"yaml_source": unsafe},
    )
    assert rejected.status_code == 409

    pending = client.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": "PAY-4471",
            "requester_id": "engineer-demo",
            "target_agent_id": "codex-cloud",
            "idempotency_key": "policy-version-pinning",
        },
    ).json()
    assert pending["decision"]["policy_version"] == "v1"
    valid = POLICY.replace("version: v1", "version: v2", 1).replace(
        "INTERNAL_MODIFICATION: [read_repo, write_files, run_tests, open_draft_pr]",
        "INTERNAL_MODIFICATION: [read_repo]",
        1,
    )
    activated = client.post(
        "/v1/policies",
        headers={**headers, "X-Actor-ID": "admin-demo"},
        json={"yaml_source": valid},
    )
    assert activated.status_code == 201
    assert activated.json()["activated"] is True
    assert len(activated.json()["sha"]) == 64
    duplicate = client.post(
        "/v1/policies",
        headers={**headers, "X-Actor-ID": "admin-demo"},
        json={"yaml_source": valid},
    )
    assert duplicate.status_code == 409

    approved = client.post(
        f"/v1/delegations/{pending['id']}/decision",
        headers=headers,
        json={"action": "approve", "approver_id": "admin-demo"},
    ).json()
    assert "write_files" in approved["warrant"]["allowed_tools"]

    create_web(client, headers, "policy-diff-source")
    v3 = POLICY.replace("version: v1", "version: v3", 1)
    simulated = client.post(
        "/v1/policies/simulate",
        headers={**headers, "X-Actor-ID": "admin-demo"},
        json={"yaml_source": v3, "against": "last_n_delegations", "n": 1},
    )
    assert simulated.status_code == 200
    assert simulated.json()["evaluated_delegations"] == 1
    assert len(simulated.json()["verdict_diffs"]) == 1


def test_gate1_failure_is_retryable_and_does_not_call_judge(client, headers):
    created = create_web(client, headers, "gate1")
    warrant = created["warrant"]
    failed = client.post(
        f"/v1/warrants/{warrant['id']}/evidence",
        headers=headers,
        json={
            "nonce": warrant["demo_nonce"],
            "files": ["services/auth/keys/signing.py"],
            "artifacts": [],
            "test_output": "",
            "claimed_criteria": [],
        },
    )
    assert failed.status_code == 422
    assert failed.json()["details"]["gate1"]["files_within_scope"] is False
    db = client.app.state.db
    row = db.one("SELECT consumed_at FROM warrants WHERE id=?", (warrant["id"],))
    assert row["consumed_at"] is None
    assert not db.one(
        "SELECT id FROM model_usage WHERE delegation_id=? AND operation='judge_evidence'",
        (created["id"],),
    )
    delegation = client.get(f"/v1/delegations/{created['id']}").json()
    assert delegation["status"] == "verification_failed"
    corrected = client.post(
        f"/v1/warrants/{warrant['id']}/evidence",
        headers=headers,
        json={
            "nonce": warrant["demo_nonce"],
            "files": warrant["scope_surfaces"],
            "artifacts": [{"type": "test", "ref": "ci://corrected"}],
            "test_output": "requested behaviour passed existing behaviour stable",
            "claimed_criteria": created["extraction"]["result"]["acceptance_criteria"],
        },
    )
    assert corrected.status_code == 200


def test_expiry_sweeper_and_revocation_are_audited(client, headers):
    created = create_web(client, headers, "expiry")
    warrant = created["warrant"]
    db = client.app.state.db
    before = db.one("SELECT verified_pass_rate FROM agents WHERE id='codex-cloud'")[
        "verified_pass_rate"
    ]
    expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    db.execute("UPDATE warrants SET expires_at=? WHERE id=?", (expired, warrant["id"]))
    assert client.get(f"/v1/warrants/{warrant['id']}").status_code == 410
    assert db.one("SELECT expired_at FROM warrants WHERE id=?", (warrant["id"],))["expired_at"]
    after = db.one("SELECT verified_pass_rate FROM agents WHERE id='codex-cloud'")[
        "verified_pass_rate"
    ]
    assert after < before
    events = client.get(
        "/v1/audit", headers={"X-Actor-ID": "admin-demo"}
    ).json()["events"]
    assert any(event["event_type"] == "warrant_expired" for event in events)

    active = create_web(client, headers, "revocation")["warrant"]
    revoked = client.post(
        f"/v1/warrants/{active['id']}/revoke",
        headers=headers,
        json={"actor_id": "admin-demo", "reason": "scope no longer needed"},
    )
    assert revoked.status_code == 200
    gone = client.get(f"/v1/warrants/{active['id']}")
    assert gone.status_code == 410
    assert gone.json()["details"]["revoke_reason"] == "scope no longer needed"
    persisted = db.one("SELECT revoke_reason FROM warrants WHERE id=?", (active["id"],))
    assert persisted["revoke_reason"] == "scope no longer needed"


def test_tool_grants_come_from_policy_and_never_grant_forbidden_tools(client, headers):
    warrant = create_web(client, headers, "tools")["warrant"]
    assert warrant["allowed_tools"] == [
        "read_repo",
        "write_files",
        "run_tests",
        "open_draft_pr",
    ]
    assert set(warrant["allowed_tools"]).isdisjoint(warrant["denied_tools"])
    assert {"merge_pr", "deploy", "delete_data"} <= set(warrant["denied_tools"])


def test_extraction_cache_is_keyed_by_issue_revision_and_prompt(client, headers):
    first = create_web(client, headers, "cache-first")
    second = create_web(client, headers, "cache-second")
    assert first["extraction"]["status"] == "ok"
    assert second["extraction"]["status"] == "cached"
    assert second["risk_assessment"]["proposed_surfaces"] == []
    assert second["retrieval"]["overlaps"]
    usages = client.app.state.db.all(
        "SELECT id FROM model_usage WHERE operation='extract_delegation_facts'"
    )
    assert len(usages) == 1
    assert "warrant_extraction_cache_hit_rate 0.5000" in client.get("/metrics").text


def test_fully_concurrent_scope_requires_approval_and_cannot_issue_empty_warrant(
    client, headers
):
    first = create_web(client, headers, "concurrency-holder")
    assert first["warrant"] is not None

    blocked = create_web(client, headers, "concurrency-blocked")
    assert blocked["status"] == "awaiting_approval"
    assert blocked["warrant"] is None
    assert blocked["risk_assessment"]["proposed_surfaces"] == []
    assert "SCOPE_FULLY_HELD_BY_CONCURRENT_WARRANT" in blocked["decision"]["reason_codes"]

    attempted_approval = client.post(
        f"/v1/delegations/{blocked['id']}/decision",
        headers=headers,
        json={"action": "approve", "approver_id": "admin-demo"},
    )
    assert attempted_approval.status_code == 409
    assert (
        client.app.state.db.one(
            "SELECT COUNT(*) AS count FROM warrants WHERE delegation_id=?",
            (blocked["id"],),
        )["count"]
        == 0
    )


def test_retrieval_filters_by_team_and_includes_policy_precedents(client, headers):
    create_web(client, headers, "precedent-source")
    result = client.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": "WEB-3001",
            "requester_id": "lead-web",
            "target_agent_id": "codex-cloud",
            "idempotency_key": "precedent-target",
        },
    ).json()
    candidates = result["retrieval"]["candidates"]
    assert all(candidate["team"] == "Web" for candidate in candidates)
    assert any(candidate["kind"] == "policy_precedent" for candidate in candidates)


def test_brief_uses_non_authorising_prose_with_structured_fallback(
    client, client_factory, headers
):
    created = create_web(client, headers, "brief-model")
    brief = client.get(f"/v1/delegations/{created['id']}/brief").json()
    assert brief["prose_source"] == "model"
    assert brief["verdict"] == created["decision"]
    assert "summary" in brief["prose"]

    failed_client = client_factory("all")
    failed = create_web(failed_client, headers, "brief-fallback")
    fallback = failed_client.get(f"/v1/delegations/{failed['id']}/brief").json()
    assert fallback["prose_source"] == "structured_fallback"
    assert fallback["verdict"]["verdict"] != "ALLOW"
