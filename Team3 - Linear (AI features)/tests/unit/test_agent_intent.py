from __future__ import annotations

from datetime import datetime, timezone

import pytest

from warrant.agent import (
    CODE_INTENTS,
    DEGRADATIONS,
    PREFERRED_KINDS,
    AgentIntent,
    resolve_intent,
)
from warrant.db import Database
from warrant.schemas import AgentQuery, AgentScope

HEADERS = {"X-CSRF-Token": "test-csrf"}

# One representative question per intent. Every intent must be reachable and every
# question must produce a non-empty answer against every fixture below.
INTENT_QUERIES: dict[AgentIntent, str] = {
    AgentIntent.SUMMARY: "Summarize this for me.",
    AgentIntent.BLOCKERS: "What is blocking this?",
    AgentIntent.DECISION_RATIONALE: "What decision was made and why?",
    AgentIntent.EVIDENCE: "What evidence do we have?",
    AgentIntent.APPROVAL_STATUS: "Is this approved yet?",
    AgentIntent.SESSION_STATUS: "What is the coding session doing?",
    AgentIntent.CODE_CHANGES: "Which files changed?",
    AgentIntent.CODE_LOCATION: "Where is delegation approval enforced?",
    AgentIntent.CODE_IMPACT: "What depends on evaluate_policy?",
    AgentIntent.INVESTIGATE: "Investigate the root cause.",
    AgentIntent.GENERAL: "Tell me anything grounded you can.",
}


def test_every_documented_intent_is_reachable_from_query_text() -> None:
    scope = {"issue_id": "PAY-4471"}
    for intent, query in INTENT_QUERIES.items():
        if intent is AgentIntent.GENERAL:
            # GENERAL is the fallback: with issue context it deliberately becomes SUMMARY.
            assert resolve_intent(query, {}) is AgentIntent.GENERAL
            continue
        assert resolve_intent(query, scope) is intent, query


def test_intent_table_is_complete_and_self_consistent() -> None:
    for intent in AgentIntent:
        assert intent in INTENT_QUERIES
        assert intent in PREFERRED_KINDS
        assert intent in DEGRADATIONS or intent is AgentIntent.GENERAL


def test_code_intent_wins_over_issue_metadata_intent() -> None:
    scope = {"issue_id": "PAY-4471"}
    cases = {
        "Where is delegation approval implemented?": AgentIntent.CODE_LOCATION,
        "What files are involved in PAY-4471?": AgentIntent.CODE_LOCATION,
        "Which module handles CSRF verification?": AgentIntent.CODE_LOCATION,
        "What would break if I change evaluate_policy?": AgentIntent.CODE_IMPACT,
        "What depends on load_policy?": AgentIntent.CODE_IMPACT,
        "Which functions are involved here?": AgentIntent.CODE_LOCATION,
        "What symbols are defined for approval?": AgentIntent.CODE_LOCATION,
    }
    for query, expected in cases.items():
        assert resolve_intent(query, scope) is expected, query
        assert expected in CODE_INTENTS


def test_scope_shape_steers_resolution_when_the_text_is_ambiguous() -> None:
    assert resolve_intent("Anything useful?", {"repository_id": "local"}) is (
        AgentIntent.CODE_LOCATION
    )
    assert resolve_intent("Anything useful?", {"issue_id": "PAY-4471"}) is AgentIntent.SUMMARY
    assert resolve_intent("Anything useful?", {"coding_session_id": "cs_1"}) is (
        AgentIntent.SESSION_STATUS
    )
    assert resolve_intent("Anything useful?", {}) is AgentIntent.GENERAL


def _delegate(client, issue: str, requester: str, key: str) -> dict:
    return client.post(
        "/v1/delegations",
        headers=HEADERS,
        json={
            "issue_ref": issue,
            "requester_id": requester,
            "target_agent_id": "codex-cloud",
            "idempotency_key": key,
        },
    ).json()


def _completed_session(client, delegation: dict) -> str:
    """Insert a terminal coding session plus diff artifact, without running an agent."""
    db = client.app.state.db
    now = datetime.now(timezone.utc).isoformat()
    session_id = "cs_fixture_complete"
    issue = db.one(
        "SELECT issue_id FROM delegations WHERE id=?",
        (delegation["id"],),
    )
    db.execute(
        "INSERT INTO coding_sessions "
        "(id,workspace_id,delegation_id,warrant_id,issue_id,requester_id,source,provider,state,"
        "repository_root,base_revision,branch_name,worktree_path,contract_json,result_json,"
        "error,created_at,started_at,finished_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            session_id,
            "ws-demo",
            delegation["id"],
            delegation["warrant"]["id"],
            issue["issue_id"],
            "lead-web",
            "api",
            "mock",
            "COMPLETED",
            "/tmp/fixture-root",
            "base-revision",
            "warrant/fixture",
            "/tmp/fixture-worktree",
            Database.dumps({"scope_surfaces": delegation["warrant"]["scope_surfaces"]}),
            Database.dumps({"summary": "fixture run"}),
            None,
            now,
            now,
            now,
        ),
    )
    db.execute(
        "INSERT INTO coding_session_events VALUES (?,?,?,?,?,?)",
        (
            "cse_fixture_1",
            session_id,
            1,
            "session_completed",
            Database.dumps({"state": "COMPLETED"}),
            now,
        ),
    )
    db.execute(
        "INSERT INTO diff_artifacts VALUES (?,?,?,?,?,?,?,?,?)",
        (
            "diff_fixture_1",
            session_id,
            "base-revision",
            None,
            Database.dumps(
                [{"path": "web/reports/EmptyState.tsx", "additions": 3, "deletions": 1}]
            ),
            3,
            1,
            "--- fixture diff ---",
            now,
        ),
    )
    return session_id


@pytest.fixture
def agent_fixtures(client):
    """Three scopes: no delegation, an awaiting-approval delegation, a completed session."""
    awaiting = _delegate(client, "PAY-4471", "engineer-demo", "intent-awaiting")
    assert awaiting["decision"]["verdict"] == "REQUIRE_APPROVAL"
    allowed = _delegate(client, "WEB-4519", "lead-web", "intent-allowed")
    session_id = _completed_session(client, allowed)
    return {
        "no_delegation": AgentScope(issue_id="SEC-4502"),
        "awaiting_approval": AgentScope(issue_id="PAY-4471"),
        "completed_session": AgentScope(coding_session_id=session_id),
    }


def test_no_intent_ever_returns_an_empty_answer_on_any_fixture(client, agent_fixtures) -> None:
    agent = client.app.state.agent
    for name, scope in agent_fixtures.items():
        for intent, query in INTENT_QUERIES.items():
            result = agent.query("ws-demo", AgentQuery(query=query, scope=scope))
            assert result["answer"].strip(), f"{name}/{intent.value} returned an empty answer"
            assert result["authoritative"] is False
            assert result["authorising"] is False
            assert result["sources"]


def test_a_missing_delegation_degrades_explicitly_instead_of_answering_nothing(
    client, agent_fixtures
) -> None:
    agent = client.app.state.agent
    result = agent.query(
        "ws-demo",
        AgentQuery(
            query="What evidence do we have and why does this require approval?",
            scope=agent_fixtures["no_delegation"],
        ),
    )
    assert result["degraded"] is True
    assert result["intent"] == AgentIntent.EVIDENCE.value
    assert "SEC-4502 has no delegation yet" in result["answer"]
    assert "SEC-4502 —" in result["answer"]


def test_an_awaiting_approval_delegation_answers_from_delegation_facts(
    client, agent_fixtures
) -> None:
    agent = client.app.state.agent
    result = agent.query(
        "ws-demo",
        AgentQuery(
            query="What evidence do we have and why does this require approval?",
            scope=agent_fixtures["awaiting_approval"],
        ),
    )
    assert result["degraded"] is False
    assert "REQUIRE_APPROVAL" in result["answer"]
    assert "Evidence sufficiency is" in result["answer"]


def test_a_completed_session_answers_code_change_questions_from_the_diff(
    client, agent_fixtures
) -> None:
    agent = client.app.state.agent
    result = agent.query(
        "ws-demo",
        AgentQuery(query="Which files changed?", scope=agent_fixtures["completed_session"]),
    )
    assert result["intent"] == AgentIntent.CODE_CHANGES.value
    assert "web/reports/EmptyState.tsx" in result["answer"]
    assert result["degraded"] is False


def test_an_unknown_repository_id_is_rejected_before_any_retrieval(client) -> None:
    from warrant.service import NotFound

    agent = client.app.state.agent
    with pytest.raises(NotFound):
        agent.query(
            "ws-demo",
            AgentQuery(
                query="Where is approval enforced?",
                scope=AgentScope(issue_id="PAY-4471", repository_id="bogus-repository"),
            ),
        )
