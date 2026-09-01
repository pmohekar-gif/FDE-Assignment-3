def table_counts(client):
    db = client.app.state.db
    tables = ("issues", "delegations", "retrieval_evidence", "audit_events", "telemetry_events")
    return {
        table: db.one(f"SELECT COUNT(*) AS n FROM {table}")["n"]  # noqa: S608
        for table in tables
    }


def test_related_issues_endpoint_returns_bounded_advisory_contract_without_writes(client):
    before = table_counts(client)

    response = client.get("/v1/issues/PAY-4471/related?limit=3")

    assert response.status_code == 200
    body = response.json()
    assert body["source"]["external_key"] == "PAY-4471"
    assert body["retrieval"]["mode"] in {"HYBRID", "LEXICAL_ONLY"}
    assert 0 <= body["retrieval"]["completeness"] <= 1
    assert body["advisory_only"] is True
    assert 0 < len(body["suggestions"]) <= 3
    assert all(item["external_key"] != "PAY-4471" for item in body["suggestions"])
    assert all(item["team"] == "Payments" for item in body["suggestions"])
    assert all(
        item["relation"] in {"possible_duplicate", "related"}
        for item in body["suggestions"]
    )
    assert table_counts(client) == before


def test_related_issues_endpoint_validates_limit(client):
    assert client.get("/v1/issues/PAY-4471/related?limit=0").status_code == 422
    assert client.get("/v1/issues/PAY-4471/related?limit=11").status_code == 422
    assert client.get("/v1/issues/PAY-4471/related?limit=not-a-number").status_code == 422


def test_related_issues_endpoint_returns_404_inside_workspace_boundary(client):
    missing = client.get("/v1/issues/DOES-NOT-EXIST/related")
    other_workspace = client.get(
        "/v1/issues/PAY-4471/related", headers={"X-Workspace-ID": "another-workspace"}
    )

    assert missing.status_code == 404
    assert missing.json()["error"] == "issue not found"
    assert other_workspace.status_code == 404


def test_related_issues_endpoint_discloses_lexical_fallback(client_factory):
    degraded_client = client_factory("embedding")

    response = degraded_client.get("/v1/issues/WEB-4519/related?limit=2")

    assert response.status_code == 200
    assert response.json()["retrieval"] == {
        "mode": "LEXICAL_ONLY",
        "completeness": 0.5,
    }


def test_related_issue_telemetry_is_csrf_protected_and_contains_no_issue_body(client, headers):
    payload = {
        "event": "selected",
        "source_issue_ref": "PAY-4471",
        "suggested_issue_ref": "PAY-3200",
        "relation": "related",
        "rank": 1,
    }
    assert client.post("/v1/telemetry/related-issues", json=payload).status_code == 400

    response = client.post("/v1/telemetry/related-issues", headers=headers, json=payload)

    assert response.status_code == 202
    event = client.app.state.db.one(
        "SELECT name,attributes_json FROM telemetry_events "
        "WHERE name='related_issue_suggestions_selected'"
    )
    assert event is not None
    attributes = client.app.state.db.loads(event["attributes_json"])
    assert attributes == {
        "rank": 1,
        "relation": "related",
        "result_count": None,
        "source_issue_ref": "PAY-4471",
        "suggested_issue_ref": "PAY-3200",
    }
    assert "body" not in event["attributes_json"].lower()


def test_selected_telemetry_requires_a_suggested_issue(client, headers):
    response = client.post(
        "/v1/telemetry/related-issues",
        headers=headers,
        json={"event": "selected", "source_issue_ref": "PAY-4471"},
    )
    assert response.status_code == 422
