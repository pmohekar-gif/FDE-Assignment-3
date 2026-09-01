from warrant.triage import TriageRecommendationService


def table_counts(client):
    db = client.app.state.db
    tables = ("issues", "delegations", "audit_events", "telemetry_events")
    return {table: db.one(f"SELECT COUNT(*) AS n FROM {table}")["n"] for table in tables}


def triage_service(client):
    return TriageRecommendationService(
        client.app.state.db, client.app.state.service.retrieval
    )


def assert_bounded_contract(result):
    assert result.advisory_only is True
    assert 0 <= result.team["confidence"] <= 1
    assert result.priority["recommended"] in {"urgent", "high", "medium", "low"}
    assert 0 <= result.priority["confidence"] <= 1
    assert all(0 <= item["confidence"] <= 1 for item in result.labels)
    assert result.retrieval["mode"] in {"HYBRID", "LEXICAL_ONLY"}
    assert 0 <= result.retrieval["completeness"] <= 1


def test_payment_issue_gets_advisory_team_priority_and_label_recommendations(client):
    before = table_counts(client)

    result = triage_service(client).recommend("ws-demo", "PAY-4471")

    assert result is not None
    assert result.issue["current_team"] == "Payments"
    assert result.issue["revision"] == 1
    assert result.team["recommended"] == "Payments"
    assert result.priority["recommended"] == "high"
    assert {item["label"] for item in result.labels} >= {"bug", "customer-impact"}
    assert result.team["why"]
    assert result.priority["why"]
    assert all(item["why"] for item in result.labels)
    assert_bounded_contract(result)
    assert table_counts(client) == before


def test_security_issue_gets_urgent_security_recommendation(client):
    result = triage_service(client).recommend("ws-demo", "SEC-4502")

    assert result is not None
    assert result.priority["recommended"] == "urgent"
    assert "security" in {item["label"] for item in result.labels}
    assert_bounded_contract(result)


def test_triage_recommendation_enforces_workspace_boundary(client):
    service = triage_service(client)
    assert service.recommend("ws-demo", "DOES-NOT-EXIST") is None
    assert service.recommend("another-workspace", "PAY-4471") is None


def test_triage_recommendation_discloses_lexical_fallback(client_factory):
    client = client_factory("embedding")

    result = triage_service(client).recommend("ws-demo", "WEB-4519")

    assert result is not None
    assert result.retrieval == {
        "mode": "LEXICAL_ONLY",
        "completeness": 0.5,
        "neighbour_keys": result.retrieval["neighbour_keys"],
    }
