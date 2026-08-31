from __future__ import annotations

import io
import json
import urllib.request

import pytest

from warrant.config import Settings
from warrant.providers import (
    OpenAICompatibleProvider,
    ProviderMalformed,
    structured_output_mode_for,
)


def settings(tmp_path, model: str = "minimax/minimax-m3:free") -> Settings:
    return Settings(
        database_path=tmp_path / "test.db",
        ai_provider="openrouter",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4.1-mini",
        webhook_secret="test",
        csrf_token="test",
        warrant_ttl_minutes=240,
        allow_sufficiency_threshold=0.7,
        fixture_failure=None,
        debug=False,
        openrouter_api_key="test-key-not-real",
        openrouter_model=model,
    )


class StubResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def stub_urlopen(monkeypatch, content: str, **metadata):
    captured = {}

    def open_(request: urllib.request.Request, timeout: float):
        captured["payload"] = json.loads(request.data or b"{}")
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        raw = {
            "choices": [{"message": {"content": content}}],
            "usage": metadata.get("usage", {}),
            "model": metadata.get("model"),
            "provider": metadata.get("provider"),
        }
        return StubResponse(json.dumps(raw).encode())

    monkeypatch.setattr(urllib.request, "urlopen", open_)
    return captured


def valid_extraction(**extra):
    return {
        "reproduction_present": True,
        "acceptance_criteria": ["works"],
        "affected_surfaces": ["web/a.py"],
        "data_classes": [],
        "external_side_effects": [],
        "missing_information": [],
        "scope_estimate": "small",
        "embedded_instruction_detected": False,
        "confidence": 0.9,
        **extra,
    }


def test_json_object_strips_fences_but_forbids_unexpected_field(monkeypatch, tmp_path):
    content = "Result follows:\n```json\n" + json.dumps(valid_extraction(surprise=True)) + "\n```"
    captured = stub_urlopen(monkeypatch, content)
    provider = OpenAICompatibleProvider(settings(tmp_path))
    with pytest.raises(ProviderMalformed):
        provider.extract("issue", [], [])
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert "required JSON Schema" in captured["payload"]["messages"][0]["content"]


def test_json_object_rejects_missing_required_field(monkeypatch, tmp_path):
    value = valid_extraction()
    del value["scope_estimate"]
    stub_urlopen(monkeypatch, json.dumps(value))
    with pytest.raises(ProviderMalformed):
        OpenAICompatibleProvider(settings(tmp_path)).extract("issue", [], [])


def test_parsed_invalid_json_never_returns_partial_result(monkeypatch, tmp_path):
    stub_urlopen(monkeypatch, '{"affected_surfaces":["web/a.py"]}')
    with pytest.raises(ProviderMalformed):
        OpenAICompatibleProvider(settings(tmp_path)).extract("issue", [], [])


def test_capability_is_explicit_per_model():
    assert structured_output_mode_for("openrouter", "minimax/minimax-m3:free") == "json_object"
    assert structured_output_mode_for("openrouter", "some/schema-model") == "none"
    assert structured_output_mode_for("openai", "gpt-4.1-mini") == "json_schema"
    assert structured_output_mode_for("openrouter", "other", "json_schema") == "json_schema"


def test_usage_routing_and_attribution_are_captured(monkeypatch, tmp_path):
    captured = stub_urlopen(
        monkeypatch,
        json.dumps(valid_extraction()),
        model="minimax/minimax-m3:free",
        provider="SyntheticStub",
        usage={
            "prompt_tokens": 101,
            "completion_tokens": 22,
            "total_tokens": 130,
            "cost": 0.0,
            "completion_tokens_details": {"reasoning_tokens": 7},
        },
    )
    response = OpenAICompatibleProvider(settings(tmp_path)).extract("issue", [], [])
    assert (
        response.input_tokens,
        response.output_tokens,
        response.reasoning_tokens,
    ) == (101, 22, 7)
    assert response.total_tokens == 130
    assert response.reported_cost_usd == 0.0
    assert response.serving_provider == "SyntheticStub"
    assert captured["timeout"] == 45
    assert captured["headers"]["Http-referer"]
    assert captured["headers"]["X-title"] == "Warrant"
