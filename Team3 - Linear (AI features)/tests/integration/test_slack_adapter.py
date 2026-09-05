from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import replace

from fastapi.testclient import TestClient

from warrant.main import create_app
from warrant.seed import reset_and_seed


def slack_client(client, tmp_path):
    settings = replace(
        client.app.state.settings,
        database_path=tmp_path / "slack.db",
        slack_enabled=True,
        slack_signing_secret="slack-test-secret",
        slack_bot_token=None,
        slack_user_map={"U123": "engineer-demo"},
    )
    reset_and_seed(settings)
    return TestClient(create_app(settings))


def signed_headers(raw: bytes, timestamp: str | None = None):
    timestamp = timestamp or str(int(time.time()))
    base = b"v0:" + timestamp.encode() + b":" + raw
    signature = "v0=" + hmac.new(b"slack-test-secret", base, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
    }


def test_slack_url_verification_requires_a_valid_signature(client, tmp_path):
    slack = slack_client(client, tmp_path)
    raw = json.dumps({"type": "url_verification", "challenge": "challenge-value"}).encode()
    assert slack.post("/v1/integrations/slack/events", content=raw).status_code == 401
    valid = slack.post("/v1/integrations/slack/events", content=raw, headers=signed_headers(raw))
    assert valid.json() == {"challenge": "challenge-value"}


def test_slack_mention_reuses_agent_and_deduplicates_event(client, tmp_path):
    slack = slack_client(client, tmp_path)
    payload = {
        "type": "event_callback",
        "event_id": "Ev-agent-1",
        "event": {
            "type": "app_mention",
            "user": "engineer-web",
            "channel": "C123",
            "ts": "111.222",
            "text": "<@BOT> summarize WEB-4519",
        },
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    first = slack.post("/v1/integrations/slack/events", content=raw, headers=signed_headers(raw))
    second = slack.post("/v1/integrations/slack/events", content=raw, headers=signed_headers(raw))
    assert first.status_code == 200
    assert "WEB-4519" in first.json()["reply"]["text"]
    assert "cannot authorise work" in first.json()["reply"]["text"]
    assert second.json()["deduplicated"] is True


def test_slack_start_coding_enters_policy_and_stops_for_approval(client, tmp_path):
    slack = slack_client(client, tmp_path)
    payload = {
        "type": "event_callback",
        "event_id": "Ev-code-1",
        "event": {
            "type": "app_mention",
            "user": "U123",
            "channel": "C123",
            "ts": "333.444",
            "text": "<@BOT> start coding PAY-4471",
        },
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    response = slack.post("/v1/integrations/slack/events", content=raw, headers=signed_headers(raw))
    assert response.status_code == 200
    assert "Approval is required" in response.json()["reply"]["text"]
    assert slack.app.state.db.one("SELECT COUNT(*) AS n FROM coding_sessions")["n"] == 0


def test_slack_rejects_expired_and_invalid_signatures(client, tmp_path):
    slack = slack_client(client, tmp_path)
    raw = b'{"type":"event_callback","event_id":"Ev-old","event":{}}'
    old = str(int(time.time()) - 301)
    assert (
        slack.post(
            "/v1/integrations/slack/events", content=raw, headers=signed_headers(raw, old)
        ).status_code
        == 401
    )
    headers = signed_headers(raw)
    headers["X-Slack-Signature"] = "v0=bad"
    assert (
        slack.post("/v1/integrations/slack/events", content=raw, headers=headers).status_code == 401
    )
