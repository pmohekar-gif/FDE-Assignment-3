def issue_state(client, key="PAY-4471"):
    row = client.app.state.db.one(
        "SELECT team,priority,labels_json,revision FROM issues WHERE external_key=?", (key,)
    )
    return {
        "team": row["team"],
        "priority": row["priority"],
        "labels": client.app.state.db.loads(row["labels_json"], []),
        "revision": row["revision"],
    }


def test_triage_recommendation_api_is_advisory_and_write_free(client):
    before = issue_state(client)
    audits_before = client.app.state.db.one("SELECT COUNT(*) AS n FROM audit_events")["n"]

    response = client.get("/v1/issues/PAY-4471/triage-recommendation")

    assert response.status_code == 200
    body = response.json()
    assert body["advisory_only"] is True
    assert body["team"]["recommended"] == "Payments"
    assert body["priority"]["recommended"] == "high"
    assert {item["label"] for item in body["labels"]} >= {"bug", "customer-impact"}
    assert issue_state(client) == before
    assert client.app.state.db.one("SELECT COUNT(*) AS n FROM audit_events")["n"] == audits_before


def test_triage_recommendation_api_handles_boundaries_and_degradation(client, client_factory):
    assert client.get("/v1/issues/DOES-NOT-EXIST/triage-recommendation").status_code == 404
    assert (
        client.get(
            "/v1/issues/PAY-4471/triage-recommendation",
            headers={"X-Workspace-ID": "another-workspace"},
        ).status_code
        == 404
    )
    degraded = client_factory("embedding")
    retrieval = degraded.get("/v1/issues/WEB-4519/triage-recommendation").json()["retrieval"]
    assert retrieval["mode"] == "LEXICAL_ONLY"
    assert retrieval["completeness"] == 0.5


def test_human_can_change_and_apply_triage_with_revision_and_audit(client, headers):
    before = issue_state(client)
    payload = {
        "expected_revision": before["revision"],
        "team": "Data",
        "priority": "urgent",
        "labels": ["customer-impact", "manual-review"],
    }

    response = client.post(
        "/v1/issues/PAY-4471/triage",
        headers={**headers, "X-Actor-ID": "admin-demo"},
        json=payload,
    )

    assert response.status_code == 200
    assert issue_state(client) == {
        "team": "Data",
        "priority": "urgent",
        "labels": ["customer-impact", "manual-review"],
        "revision": before["revision"] + 1,
    }
    event = client.app.state.db.one(
        "SELECT actor_id,payload_json FROM audit_events WHERE event_type='triage_applied'"
    )
    assert event["actor_id"] == "admin-demo"
    audit = client.app.state.db.loads(event["payload_json"])
    assert audit["previous"]["team"] == "Payments"
    assert audit["applied"]["team"] == "Data"
    assert audit["recommendation"]["advisory_only"] is True
    assert client.app.state.service.audit.verify("ws-demo") is True

    stale = client.post(
        "/v1/issues/PAY-4471/triage",
        headers={**headers, "X-Actor-ID": "admin-demo"},
        json=payload,
    )
    assert stale.status_code == 409


def test_triage_application_requires_csrf_and_workspace_actor(client, headers):
    payload = {
        "expected_revision": 1,
        "team": "Payments",
        "priority": "high",
        "labels": ["bug"],
    }
    assert client.post("/v1/issues/PAY-4471/triage", json=payload).status_code == 400
    assert (
        client.post(
            "/v1/issues/PAY-4471/triage",
            headers={**headers, "X-Actor-ID": "not-a-user"},
            json=payload,
        ).status_code
        == 403
    )


def test_triage_view_telemetry_contains_no_issue_body(client, headers):
    response = client.post(
        "/v1/telemetry/triage-recommendation",
        headers=headers,
        json={"issue_ref": "PAY-4471", "retrieval_mode": "HYBRID"},
    )
    assert response.status_code == 202
    event = client.app.state.db.one(
        "SELECT attributes_json FROM telemetry_events WHERE name='triage_recommendation_viewed'"
    )
    assert client.app.state.db.loads(event["attributes_json"]) == {
        "issue_ref": "PAY-4471",
        "retrieval_mode": "HYBRID",
    }
    assert "body" not in event["attributes_json"].lower()
