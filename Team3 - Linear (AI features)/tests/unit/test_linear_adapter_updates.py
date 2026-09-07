from __future__ import annotations

from pathlib import Path
from typing import Any

from warrant.adapters.linear import LinearAdapter
from warrant.config import Settings


def settings(*, mode: str = "live") -> Settings:
    return Settings(
        database_path=Path("/tmp/unused-linear-updates.db"),
        ai_provider="fixture",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4.1-mini",
        webhook_secret="test",
        csrf_token="test",
        warrant_ttl_minutes=240,
        allow_sufficiency_threshold=0.70,
        fixture_failure=None,
        debug=False,
        linear_mode=mode,
        linear_api_key="lin-test-key" if mode == "live" else None,
        linear_api_base_url="https://linear.test/graphql",
    )


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


def _issue(identifier: str, updated_at: str = "2024-09-01T12:00:00.000Z") -> dict[str, Any]:
    return {
        "id": f"linear-{identifier}",
        "identifier": identifier,
        "title": "Fix memory leak",
        "description": "Acceptance criteria: stable memory use.",
        "url": f"https://linear.test/{identifier}",
        "priority": 2,
        "updatedAt": updated_at,
        "createdAt": "2024-08-28T09:00:00.000Z",
        "team": {"id": "team-eng", "name": "Engineering", "key": "ENG"},
        "labels": {"nodes": [{"id": "label-bug", "name": "bug", "color": "#f00"}]},
        "state": {"id": "state-started", "name": "In Progress", "type": "started"},
        "assignee": {"id": "user-alice", "name": "Alice"},
    }


def test_fetch_updated_issues_builds_bounded_filtered_graphql_request(monkeypatch):
    calls: list[dict[str, Any]] = []

    def post(url, *, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return _Response({"data": {"issues": {"nodes": [_issue("ENG-101")]}}})

    monkeypatch.setattr("warrant.adapters.linear.httpx.post", post)

    adapter = LinearAdapter(settings())
    issues = adapter.fetch_updated_issues(
        since=_issue_datetime("2024-09-01T11:58:00+00:00"), limit=10, team_key="ENG"
    )

    assert [issue.identifier for issue in issues] == ["ENG-101"]
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == "https://linear.test/graphql"
    assert call["headers"]["Authorization"] == "lin-test-key"
    assert "description" not in call["json"]["query"]
    assert call["json"]["variables"] == {
        "limit": 10,
        "filter": {
            "updatedAt": {"gt": "2024-09-01T11:58:00Z"},
            "team": {"key": {"eq": "ENG"}},
        },
    }


def test_fetch_updated_issues_parses_empty_connection(monkeypatch):
    def post(url, *, headers, json, timeout):
        return _Response({"data": {"issues": {"nodes": []}}})

    monkeypatch.setattr("warrant.adapters.linear.httpx.post", post)

    assert LinearAdapter(settings()).fetch_updated_issues(limit=5) == []


def _issue_datetime(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)
