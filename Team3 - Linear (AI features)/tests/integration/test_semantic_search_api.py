def table_counts(client):
    db = client.app.state.db
    tables = ("issues", "delegations", "retrieval_evidence", "audit_events", "telemetry_events")
    return {table: db.one(f"SELECT COUNT(*) AS n FROM {table}")["n"] for table in tables}


def test_semantic_search_api_returns_ranked_read_only_contract(client):
    before = table_counts(client)

    response = client.get(
        "/v1/issues/search",
        params={"q": "second retry must not create another charge", "limit": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["read_only"] is True
    assert body["retrieval"] == {"mode": "HYBRID", "completeness": 1.0}
    assert body["results"][0]["external_key"] == "PAY-4471"
    assert len(body["results"]) <= 5
    assert table_counts(client) == before


def test_semantic_search_api_validates_query_and_limit(client):
    assert client.get("/v1/issues/search", params={"q": ""}).status_code == 422
    assert client.get("/v1/issues/search", params={"q": "x"}).status_code == 422
    assert client.get("/v1/issues/search", params={"q": "x" * 301}).status_code == 422
    assert client.get("/v1/issues/search", params={"q": "reports", "limit": 0}).status_code == 422
    assert client.get("/v1/issues/search", params={"q": "reports", "limit": 51}).status_code == 422


def test_semantic_search_api_enforces_workspace_and_team_boundaries(client):
    team = client.get(
        "/v1/issues/search", params={"q": "retry status", "team": "Data", "limit": 10}
    ).json()
    other_workspace = client.get(
        "/v1/issues/search",
        params={"q": "PAY-4471"},
        headers={"X-Workspace-ID": "another-workspace"},
    ).json()

    assert team["results"]
    assert all(item["team"] == "Data" for item in team["results"])
    assert other_workspace["results"] == []


def test_semantic_search_api_discloses_lexical_fallback(client_factory):
    client = client_factory("embedding")
    body = client.get("/v1/issues/search", params={"q": "reports empty state"}).json()

    assert body["retrieval"] == {"mode": "LEXICAL_ONLY", "completeness": 0.5}


def test_semantic_search_telemetry_is_private_and_csrf_protected(client, headers):
    payload = {
        "event": "selected",
        "query_length": 42,
        "result_count": 5,
        "team_filtered": True,
        "selected_issue_ref": "PAY-4471",
        "rank": 1,
    }
    assert client.post("/v1/telemetry/semantic-search", json=payload).status_code == 400

    response = client.post("/v1/telemetry/semantic-search", headers=headers, json=payload)

    assert response.status_code == 202
    event = client.app.state.db.one(
        "SELECT attributes_json FROM telemetry_events WHERE name='semantic_search_selected'"
    )
    assert event is not None
    attributes = client.app.state.db.loads(event["attributes_json"])
    assert attributes == {
        "query_length": 42,
        "rank": 1,
        "result_count": 5,
        "selected_issue_ref": "PAY-4471",
        "team_filtered": True,
    }
    assert "query" not in attributes


def test_selected_search_telemetry_requires_issue_and_rank(client, headers):
    response = client.post(
        "/v1/telemetry/semantic-search",
        headers=headers,
        json={
            "event": "selected",
            "query_length": 5,
            "result_count": 2,
            "team_filtered": False,
        },
    )
    assert response.status_code == 422
