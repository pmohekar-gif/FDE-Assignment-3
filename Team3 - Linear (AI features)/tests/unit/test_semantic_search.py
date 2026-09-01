def table_counts(client):
    db = client.app.state.db
    tables = ("issues", "delegations", "retrieval_evidence", "audit_events", "telemetry_events")
    return {table: db.one(f"SELECT COUNT(*) AS n FROM {table}")["n"] for table in tables}


def test_exact_key_search_ranks_exact_issue_first_and_performs_no_writes(client):
    search = client.app.state.service.retrieval.search_issues
    before = table_counts(client)

    result = search("ws-demo", "PAY-4471", limit=5)

    assert result.results[0]["external_key"] == "PAY-4471"
    assert "exact_key" in result.results[0]["matched_by"]
    assert len(result.results) <= 5
    assert table_counts(client) == before


def test_search_uses_description_language_and_team_is_a_hard_filter(client):
    result = client.app.state.service.retrieval.search_issues(
        "ws-demo", "second retry must not create another charge", team="Payments", limit=10
    )

    assert any(item["external_key"] == "PAY-4471" for item in result.results)
    assert all(item["team"] == "Payments" for item in result.results)
    assert all(0 <= item["rrf_score"] <= 1 for item in result.results)
    assert all(
        set(item["matched_by"]) <= {"exact_key", "lexical", "semantic"}
        for item in result.results
    )


def test_search_enforces_workspace_boundary_and_handles_empty_query(client):
    search = client.app.state.service.retrieval.search_issues

    assert search("another-workspace", "PAY-4471").results == []
    empty = search("ws-demo", "   ")
    assert empty.results == []
    assert empty.mode == "EMPTY_QUERY"


def test_search_bounds_result_limit_and_discloses_lexical_fallback(client_factory):
    degraded = client_factory("embedding")
    search = degraded.app.state.service.retrieval.search_issues

    result = search("ws-demo", "reports empty state", limit=500)

    assert len(result.results) <= 50
    assert result.mode == "LEXICAL_ONLY"
    assert result.completeness == 0.5
