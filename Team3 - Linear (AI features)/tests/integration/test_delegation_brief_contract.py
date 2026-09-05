def create_web_delegation(client, headers, key):
    response = client.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": "WEB-4519",
            "requester_id": "lead-web",
            "target_agent_id": "codex-cloud",
            "idempotency_key": key,
        },
    )
    assert response.status_code == 201
    return response.json()


def assert_non_authorising_contract(brief, delegation):
    assert brief["brief_version"] == "v1"
    assert brief["delegation_id"] == delegation["id"]
    assert brief["issue"]["external_key"] == "WEB-4519"
    assert brief["authority_boundary"] == {
        "authorising": False,
        "decision_source": "deterministic_policy",
        "prose_may_change_verdict": False,
    }
    facts = brief["fact_snapshot"]
    assert facts["verdict"] == delegation["decision"]["verdict"]
    assert facts["reason_codes"] == delegation["decision"]["reason_codes"]
    assert facts["proposed_surfaces"] == delegation["risk_assessment"]["proposed_surfaces"]
    assert facts["evidence_sufficiency"] == delegation["risk_assessment"]["evidence_sufficiency"]
    assert facts["missing_information"] == brief["missing_information"]
    assert facts["warrant_status"] == brief["warrant"]["status"]


def test_model_brief_has_versioned_non_authorising_contract(client, headers):
    delegation = create_web_delegation(client, headers, "brief-contract-model")

    response = client.get(f"/v1/delegations/{delegation['id']}/brief")

    assert response.status_code == 200
    brief = response.json()
    assert brief["prose_source"] == "model"
    assert_non_authorising_contract(brief, delegation)


def test_fallback_brief_preserves_contract_and_verdict(client_factory, headers):
    client = client_factory("brief")
    delegation = create_web_delegation(client, headers, "brief-contract-fallback")

    response = client.get(f"/v1/delegations/{delegation['id']}/brief")

    assert response.status_code == 200
    brief = response.json()
    assert brief["prose_source"] == "structured_fallback"
    assert "issued warrant boundaries" in brief["prose"]["human_next_steps"][0]
    assert_non_authorising_contract(brief, delegation)


def test_brief_workspace_boundary_returns_not_found(client, headers):
    delegation = create_web_delegation(client, headers, "brief-contract-workspace")

    response = client.get(
        f"/v1/delegations/{delegation['id']}/brief",
        headers={"X-Workspace-ID": "another-workspace"},
    )

    assert response.status_code == 404


def test_unchanged_brief_is_cached_without_repeated_model_usage(client, headers):
    delegation = create_web_delegation(client, headers, "brief-contract-cache")

    first = client.get(f"/v1/delegations/{delegation['id']}/brief").json()
    usage_after_first = client.app.state.db.one(
        "SELECT COUNT(*) AS n FROM model_usage WHERE delegation_id=? "
        "AND operation='generate_brief'",
        (delegation["id"],),
    )["n"]
    second = client.get(f"/v1/delegations/{delegation['id']}/brief").json()
    usage_after_second = client.app.state.db.one(
        "SELECT COUNT(*) AS n FROM model_usage WHERE delegation_id=? "
        "AND operation='generate_brief'",
        (delegation["id"],),
    )["n"]

    assert first["lifecycle"]["cache_hit"] is False
    assert second["lifecycle"]["cache_hit"] is True
    assert second["lifecycle"]["stale"] is False
    assert usage_after_first == usage_after_second == 1


def test_changed_facts_mark_cache_stale_until_csrf_protected_refresh(client, headers):
    response = client.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": "PAY-4471",
            "requester_id": "engineer-demo",
            "target_agent_id": "codex-cloud",
            "idempotency_key": "brief-contract-stale",
        },
    )
    delegation = response.json()
    first = client.get(f"/v1/delegations/{delegation['id']}/brief").json()
    assert first["fact_snapshot"]["warrant_status"] is None

    decision = client.post(
        f"/v1/delegations/{delegation['id']}/decision",
        headers={**headers, "X-Actor-ID": "lead-payments"},
        json={"action": "approve", "approver_id": "lead-payments"},
    )
    assert decision.status_code == 200
    stale = client.get(f"/v1/delegations/{delegation['id']}/brief").json()
    assert stale["lifecycle"]["stale"] is True
    assert stale["lifecycle"]["refresh_required"] is True

    path = f"/v1/delegations/{delegation['id']}/brief/refresh"
    assert client.post(path).status_code == 400
    refreshed = client.post(path, headers=headers)
    assert refreshed.status_code == 200
    refreshed_body = refreshed.json()
    assert refreshed_body["lifecycle"]["stale"] is False
    assert refreshed_body["fact_snapshot"]["warrant_status"] == "active"


def test_brief_view_telemetry_contains_no_prose_or_issue_body(client, headers):
    delegation = create_web_delegation(client, headers, "brief-contract-telemetry")
    brief = client.get(f"/v1/delegations/{delegation['id']}/brief").json()
    payload = {
        "event": "viewed",
        "delegation_id": delegation["id"],
        "prose_source": brief["prose_source"],
        "stale": brief["lifecycle"]["stale"],
    }

    response = client.post("/v1/telemetry/delegation-brief", headers=headers, json=payload)

    assert response.status_code == 202
    event = client.app.state.db.one(
        "SELECT attributes_json FROM telemetry_events WHERE name='delegation_brief_viewed'"
    )
    assert event is not None
    assert client.app.state.db.loads(event["attributes_json"]) == {
        "prose_source": "model",
        "stale": False,
    }
    assert "summary" not in event["attributes_json"]
    assert "body" not in event["attributes_json"]
