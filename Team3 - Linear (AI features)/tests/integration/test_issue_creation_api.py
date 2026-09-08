from __future__ import annotations

import sqlite3


def _payload(**overrides):
    payload = {
        "title": "Prevent duplicate export notifications",
        "description": "A synthetic reproduction for the new ticket workflow.",
        "team": "Data",
        "priority": "high",
        "labels": ["exports", "regression"],
        "idempotency_key": "new-ticket-request-001",
    }
    payload.update(overrides)
    return payload


def test_create_issue_persists_searches_and_audits_without_triggering_ai(client, headers):
    response = client.post(
        "/v1/issues", headers={**headers, "X-Actor-Id": "engineer-demo"}, json=_payload()
    )

    assert response.status_code == 201
    issue = response.json()["issue"]
    assert issue["external_key"].startswith("DATA-")
    assert issue["title"] == "Prevent duplicate export notifications"
    assert issue["priority"] == "high"
    assert issue["is_demo_path"] == 0
    assert response.json()["authoritative"] is False
    assert response.json()["authorising"] is False
    assert client.get(f"/issues/{issue['external_key']}").status_code == 200
    search = client.get("/v1/issues/search", params={"q": "duplicate export notifications"})
    assert search.json()["results"]
    event = client.app.state.db.one("SELECT * FROM audit_events WHERE event_type='issue_created'")
    assert event is not None
    assert client.app.state.db.one("SELECT COUNT(*) AS n FROM comment_mentions")["n"] == 0


def test_new_issue_is_first_in_the_unfiltered_triage_inbox(client, headers):
    created = client.post(
        "/v1/issues", headers={**headers, "X-Actor-Id": "engineer-demo"}, json=_payload()
    ).json()["issue"]

    page = client.get("/")
    issue_row = f'data-issue-row="{created["external_key"]}"'
    assert issue_row in page.text
    assert page.text.index(issue_row) < page.text.index('data-issue-row="PAY-4471"')


def test_create_issue_is_idempotent_and_rejects_unknown_teams(client, headers):
    request_headers = {**headers, "X-Actor-Id": "engineer-demo"}
    first = client.post("/v1/issues", headers=request_headers, json=_payload()).json()["issue"]
    duplicate = client.post("/v1/issues", headers=request_headers, json=_payload()).json()["issue"]

    assert duplicate["id"] == first["id"]
    assert duplicate["created"] is False
    invalid = client.post(
        "/v1/issues",
        headers=request_headers,
        json=_payload(team="Unknown team", idempotency_key="new-ticket-request-002"),
    )
    assert invalid.status_code == 400


def test_create_issue_requires_csrf_and_workspace_user(client):
    assert client.post("/v1/issues", json=_payload()).status_code == 400
    forbidden = client.post(
        "/v1/issues",
        headers={"X-CSRF-Token": "test-csrf", "X-Actor-Id": "not-a-user"},
        json=_payload(),
    )
    assert forbidden.status_code == 403
    cross_workspace = client.post(
        "/v1/issues",
        headers={
            "X-CSRF-Token": "test-csrf",
            "X-Actor-Id": "engineer-demo",
            "X-Workspace-Id": "another-workspace",
        },
        json=_payload(idempotency_key="new-ticket-request-003"),
    )
    assert cross_workspace.status_code == 403


def test_storage_failure_rolls_back_ticket_and_audit(client, headers, monkeypatch):
    before_issues = client.app.state.db.one("SELECT COUNT(*) AS n FROM issues")["n"]
    before_audits = client.app.state.db.one("SELECT COUNT(*) AS n FROM audit_events")["n"]

    def unavailable(*_args, **_kwargs):
        raise sqlite3.OperationalError("simulated audit storage failure")

    monkeypatch.setattr(client.app.state.service.audit, "append", unavailable)
    response = client.post(
        "/v1/issues", headers={**headers, "X-Actor-Id": "engineer-demo"}, json=_payload()
    )

    assert response.status_code == 503
    assert "no ticket was created" in response.json()["error"]
    assert client.app.state.db.one("SELECT COUNT(*) AS n FROM issues")["n"] == before_issues
    assert client.app.state.db.one("SELECT COUNT(*) AS n FROM audit_events")["n"] == before_audits


def test_new_issue_supports_comments_without_starting_authority_work(client, headers):
    request_headers = {**headers, "X-Actor-Id": "engineer-demo"}
    before = client.app.state.db.one(
        "SELECT (SELECT COUNT(*) FROM delegations) AS delegations, "
        "(SELECT COUNT(*) FROM warrants) AS warrants"
    )
    created = client.post("/v1/issues", headers=request_headers, json=_payload()).json()["issue"]
    issue_ref = created["external_key"]
    normal = client.post(
        f"/v1/issues/{issue_ref}/comments",
        headers=request_headers,
        json={
            "body": "I reproduced this in the synthetic workspace.",
            "idempotency_key": "new-issue-comment-001",
        },
    )
    assert normal.status_code == 201
    assert normal.json()["mention"] is None
    mention_request = client.post(
        f"/v1/issues/{issue_ref}/comments",
        headers=request_headers,
        json={
            "body": "@Warrant summarize the issue context",
            "idempotency_key": "new-issue-comment-002",
        },
    )
    mention = mention_request.json()["mention"]
    completed = client.post(
        f"/v1/comment-mentions/{mention['id']}/process", headers=request_headers
    ).json()
    assert completed["state"] == "completed"
    assert completed["provider"] == "fixture"
    comments = client.get(
        f"/v1/issues/{issue_ref}/comments", headers={"X-Actor-Id": "engineer-demo"}
    ).json()["comments"]
    assert len(comments) == 3
    after = client.app.state.db.one(
        "SELECT (SELECT COUNT(*) FROM delegations) AS delegations, "
        "(SELECT COUNT(*) FROM warrants) AS warrants"
    )
    assert after == before


def test_new_issue_preserves_warrant_rate_limit_and_comment_audit(client, headers):
    request_headers = {**headers, "X-Actor-Id": "engineer-demo"}
    issue = client.post("/v1/issues", headers=request_headers, json=_payload()).json()["issue"]
    for index in range(20):
        response = client.post(
            f"/v1/issues/{issue['external_key']}/comments",
            headers=request_headers,
            json={
                "body": "@Warrant check the new ticket",
                "idempotency_key": f"new-ticket-rate-{index:02d}",
            },
        )
        assert response.status_code == 201
    limited = client.post(
        f"/v1/issues/{issue['external_key']}/comments",
        headers=request_headers,
        json={"body": "@Warrant one more request", "idempotency_key": "new-ticket-rate-limit"},
    )
    assert limited.status_code == 400
    assert "rate limit" in limited.json()["error"]
    assert client.app.state.db.one(
        "SELECT COUNT(*) AS n FROM audit_events WHERE event_type='comment_created'"
    )["n"] == 20
