def create(client, headers, issue="WEB-4519", requester="lead-web"):
    return client.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": issue,
            "requester_id": requester,
            "target_agent_id": "codex-cloud",
            "idempotency_key": f"agent-{issue}-{requester}",
        },
    ).json()


def ask(client, headers, query, scope, conversation_id=None):
    body = {"query": query, "scope": scope}
    if conversation_id:
        body["conversation_id"] = conversation_id
    return client.post("/v1/agent/query", headers=headers, json=body)


def test_agent_answers_issue_and_delegation_questions_without_authority(client, headers):
    delegation = create(client, headers)
    response = ask(
        client,
        headers,
        "Summarize this issue and explain what is blocking it.",
        {"delegation_id": delegation["id"]},
    )
    assert response.status_code == 200
    answer = response.json()
    assert "WEB-4519" in answer["answer"]
    assert answer["authoritative"] is False
    assert answer["authorising"] is False
    assert answer["intent"] == "BLOCKERS"
    assert {item["type"] for item in answer["sources"]} >= {
        "issue",
        "delegation",
        "policy_decision",
    }


def test_agent_supports_conversation_and_repository_grounding(client, headers):
    delegation = create(client, headers, requester="lead-web")
    first = ask(
        client,
        headers,
        "Where is delegation approval enforced in code?",
        {"delegation_id": delegation["id"], "repository_id": "local"},
    ).json()
    assert any(item["type"] == "code" and item["start_line"] >= 1 for item in first["sources"])
    second = ask(
        client,
        headers,
        "What decision has already been made?",
        {"delegation_id": delegation["id"]},
        conversation_id=first["conversation_id"],
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == first["conversation_id"]
    assert second.json()["intent"] == "DECISION_RATIONALE"


def test_agent_never_returns_an_empty_answer_for_the_reproduced_questions(client, headers):
    """The four live-reproduced questions that used to return HTTP 200 with answer ''."""
    reproduced = (
        ("What evidence do we have and why does this require approval?", "EVIDENCE"),
        ("Where is delegation approval enforced?", "CODE_LOCATION"),
        ("What files are involved in this issue?", "CODE_LOCATION"),
        ("Summarize this issue and explain what is blocking it.", "BLOCKERS"),
    )
    for query, intent in reproduced:
        response = ask(client, headers, query, {"issue_id": "PAY-4471"})
        assert response.status_code == 200
        body = response.json()
        assert body["answer"].strip(), f"{query!r} returned an empty answer"
        assert body["intent"] == intent
        assert body["authoritative"] is False
        assert body["authorising"] is False


def test_agent_code_intents_reach_code_intelligence_even_with_an_issue_in_scope(client, headers):
    for query in (
        "Where is delegation approval implemented?",
        "What files are involved in PAY-4471?",
        "Which module handles CSRF verification?",
        "What would break if I change evaluate_policy?",
    ):
        body = ask(client, headers, query, {"issue_id": "PAY-4471"}).json()
        assert body["intent"] in {"CODE_LOCATION", "CODE_IMPACT"}, query
        assert any(item["type"] == "code" for item in body["sources"]), query


def test_agent_investigate_returns_issue_facts_plus_repository_evidence(client, headers):
    body = ask(
        client, headers, "Investigate PAY-4471 and find the root cause.", {"issue_id": "PAY-4471"}
    ).json()
    assert body["intent"] == "INVESTIGATE"
    types = {item["type"] for item in body["sources"]}
    assert "issue" in types
    assert "code" in types
    assert "PAY-4471" in body["answer"]


def test_agent_rejects_an_unknown_repository_id_in_scope(client, headers):
    response = ask(
        client,
        headers,
        "Where is approval enforced?",
        {"issue_id": "PAY-4471", "repository_id": "not-a-real-repository"},
    )
    assert response.status_code == 404
    assert response.json()["error"] == "repository not found"


def test_agent_and_code_queries_require_a_csrf_token(client, headers):
    assert (
        client.post(
            "/v1/agent/query",
            json={"query": "Summarize this issue.", "scope": {"issue_id": "PAY-4471"}},
        ).status_code
        == 400
    )
    assert (
        client.post("/v1/code/query", json={"query": "Where is approval enforced?"}).status_code
        == 400
    )
    assert (
        ask(client, headers, "Summarize this issue.", {"issue_id": "PAY-4471"}).status_code == 200
    )


def test_agent_response_records_its_context_budget(client, headers):
    body = ask(
        client, headers, "Where is delegation approval enforced?", {"issue_id": "PAY-4471"}
    ).json()
    context = body["context"]
    assert context["answer_chars"] <= context["max_answer_chars"]
    assert context["source_count"] <= context["max_sources"]
    assert context["answer_truncated"] is False


def test_code_query_and_index_status_return_repository_revision_and_sources(client, headers):
    before = client.get("/v1/code/index/status").json()
    assert before["authoritative"] is False
    assert before["authorising"] is False
    assert before["ignore_source"] in {"git", "gitignore", "denylist"}
    response = client.post(
        "/v1/code/query", headers=headers, json={"query": "Where is delegation approval enforced?"}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["revision"]
    assert result["sources"]
    assert result["authoritative"] is False
    assert result["authorising"] is False
    assert result["ignore_source"] == before["ignore_source"]
    assert all(
        source["path"] and source["start_line"] <= source["end_line"]
        for source in result["sources"]
    )
    after = client.get("/v1/code/index/status").json()
    assert after["indexed"] is True
    assert before["revision"] == after["revision"]
    assert after["context_budget"]["max_snippets"] >= 1


def test_code_query_answers_impact_from_real_importer_edges(client, headers):
    result = client.post(
        "/v1/code/query",
        headers=headers,
        json={"query": "What depends on evaluate_policy?", "limit": 12},
    ).json()
    assert result["dependency_resolved"] is True
    paths = {source["path"] for source in result["sources"]}
    assert "src/warrant/policy.py" in paths
    assert "src/warrant/service.py" in paths, "the real importer must outrank plain text hits"
    assert any(source["edge"] == "definition" for source in result["sources"])
    assert any(source["edge"] in {"import", "call_site"} for source in result["sources"])
    assert "src/warrant/service.py" in result["answer"]


def test_code_query_admits_when_a_symbol_cannot_be_resolved(client, headers):
    result = client.post(
        "/v1/code/query",
        headers=headers,
        json={"query": "What depends on zzz_not_a_real_symbol?"},
    ).json()
    assert result["dependency_resolved"] is False
    assert "could not resolve" in result["answer"]
    assert "text matches" in result["answer"]
