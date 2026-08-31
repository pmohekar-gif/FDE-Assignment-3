from __future__ import annotations

import json
import urllib.request

from fastapi.testclient import TestClient

from warrant.config import Settings
from warrant.main import create_app
from warrant.seed import reset_and_seed


class StubResponse:
    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self):
        return json.dumps(self.raw).encode()


def make_client(tmp_path, monkeypatch, content, include_metadata=True):
    def urlopen(request: urllib.request.Request, timeout: float):
        raw = {"choices": [{"message": {"content": json.dumps(content)}}]}
        if include_metadata:
            raw.update(
                {
                    "model": "minimax/minimax-m3:free",
                    "provider": "StubProvider",
                    "usage": {
                        "prompt_tokens": 50,
                        "completion_tokens": 20,
                        "total_tokens": 75,
                        "cost": 0.0,
                        "completion_tokens_details": {"reasoning_tokens": 5},
                    },
                }
            )
        return StubResponse(raw)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    settings = Settings(
        database_path=tmp_path / "openrouter.db",
        ai_provider="openrouter",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4.1-mini",
        webhook_secret="test",
        csrf_token="test-csrf",
        warrant_ttl_minutes=240,
        allow_sufficiency_threshold=0.7,
        fixture_failure=None,
        debug=False,
        openrouter_api_key="test-key-not-real",
        provider_retry_base_ms=0,
    )
    reset_and_seed(settings)
    return TestClient(create_app(settings))


def extraction(**extra):
    return {
        "reproduction_present": True,
        "acceptance_criteria": ["Existing behaviour remains stable"],
        "affected_surfaces": ["web/reports/EmptyState.tsx"],
        "data_classes": [],
        "external_side_effects": [],
        "missing_information": [],
        "scope_estimate": "small",
        "embedded_instruction_detected": False,
        "confidence": 0.9,
        **extra,
    }


def delegate(client):
    return client.post(
        "/v1/delegations",
        headers={"X-CSRF-Token": "test-csrf"},
        json={
            "issue_ref": "WEB-4519",
            "requester_id": "lead-web",
            "target_agent_id": "codex-cloud",
            "idempotency_key": "openrouter-test",
        },
    )


def test_unschemaed_json_still_has_deterministic_verdict_and_persists_usage(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, extraction())
    response = delegate(client)
    assert response.status_code == 201
    assert response.json()["decision"]["verdict"] == "ALLOW"
    usage = client.app.state.db.one("SELECT * FROM model_usage LIMIT 1")
    assert usage["input_tokens"] == 50
    assert usage["reasoning_tokens"] == 5
    assert usage["total_tokens"] == 75
    assert usage["reported_cost_usd"] == 0.0
    assert usage["serving_provider"] == "StubProvider"


def test_malformed_extraction_never_allows(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, {"affected_surfaces": ["web/**"]})
    response = delegate(client)
    assert response.status_code == 201
    assert response.json()["decision"]["verdict"] != "ALLOW"
    assert response.json()["extraction"]["status"] == "unavailable"


def test_missing_provider_metadata_does_not_fail_authorization(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, extraction(), include_metadata=False)
    response = delegate(client)
    assert response.status_code == 201
    assert response.json()["decision"]["verdict"] == "ALLOW"
