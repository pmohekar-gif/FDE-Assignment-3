from __future__ import annotations

# ruff: noqa: E501

def _headers() -> dict[str, str]:
    return {"X-CSRF-Token": "test-csrf", "X-Actor-Id": "engineer-demo"}


def _create(client, body: str, key: str = "comment-key-001"):
    return client.post(
        "/v1/issues/WEB-4519/comments",
        headers=_headers(),
        json={"body": body, "idempotency_key": key},
    )


def test_normal_comment_is_not_an_ai_run(client):
    response = _create(client, "A normal implementation update.")
    assert response.status_code == 201
    assert response.json()["mention"] is None
    assert client.app.state.db.one("SELECT COUNT(*) AS n FROM comment_mentions")["n"] == 0
    listed = client.get("/v1/issues/WEB-4519/comments", headers={"X-Actor-Id": "engineer-demo"})
    assert listed.status_code == 200
    assert listed.headers["cache-control"] == "no-store"
    assert [comment["body_normalised"] for comment in listed.json()["comments"]] == [
        "A normal implementation update."
    ]


def test_mention_is_token_bound_idempotent_and_grounded(client):
    response = _create(client, "@Warrant summarize blockers", "comment-key-002")
    assert response.status_code == 201
    mention = response.json()["mention"]
    assert mention["state"] == "working"
    duplicate = _create(client, "@Warrant summarize blockers", "comment-key-002")
    assert duplicate.status_code == 201
    assert duplicate.json()["mention"]["id"] == mention["id"]
    done = client.post(f"/v1/comment-mentions/{mention['id']}/process", headers=_headers())
    assert done.status_code == 200
    payload = done.json()
    assert payload["state"] == "completed"
    assert payload["provider"] == "fixture"
    assert payload["citations"]
    assert _create(client, "mail@warrant.example is not a mention", "comment-key-003").json()["mention"] is None


def test_comment_ownership_and_request_delete_cascades_agent_reply(client):
    created = _create(client, "@Warrant what is blocked?", "comment-key-004").json()
    mention = created["mention"]
    client.post(f"/v1/comment-mentions/{mention['id']}/process", headers=_headers())
    comment_id = created["comment"]["id"]
    denied = client.delete(
        f"/v1/comments/{comment_id}",
        headers={"X-CSRF-Token": "test-csrf", "X-Actor-Id": "admin-demo"},
    )
    assert denied.status_code == 404
    removed = client.delete(f"/v1/comments/{comment_id}", headers=_headers())
    assert removed.status_code == 204
    assert client.app.state.db.one("SELECT deleted_at FROM comments WHERE id=?", (mention["assistant_comment_id"],))["deleted_at"]
    assert client.get(f"/v1/comment-mentions/{mention['id']}", headers=_headers()).json()["assistant_comment"] is None


def test_provider_failure_keeps_request_and_marks_agent_failure(client_factory):
    client = client_factory("comment_assist")
    created = _create(client, "@Warrant summarize", "comment-key-005").json()
    response = client.post(f"/v1/comment-mentions/{created['mention']['id']}/process", headers=_headers())
    assert response.status_code == 200
    assert response.json()["state"] == "failed"
    assert "could not complete" in response.json()["assistant_comment"]["body_normalised"]


def test_dotenv_is_loaded_without_overriding_process_environment(tmp_path, monkeypatch):
    from warrant import config

    dotenv = tmp_path / ".env"
    dotenv.write_text("AI_PROVIDER=openrouter\nOPENROUTER_MODEL=minimax/minimax-m3:free\n")
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    config._load_dotenv(dotenv)
    assert config.Settings.from_env().ai_provider == "openrouter"
