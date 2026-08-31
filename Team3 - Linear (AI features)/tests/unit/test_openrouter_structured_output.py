from __future__ import annotations

import json
from pathlib import Path

import pytest

from warrant.config import Settings
from warrant.providers import OpenRouterProvider, ProviderMalformed


def settings(model: str = "minimax/minimax-m3:free", mode: str = "auto") -> Settings:
    return Settings(
        database_path=Path("/tmp/unused.db"),
        ai_provider="openrouter",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4.1-mini",
        webhook_secret="test",
        csrf_token="test",
        warrant_ttl_minutes=240,
        allow_sufficiency_threshold=0.70,
        fixture_failure=None,
        debug=False,
        openrouter_api_key="test-key",
        openrouter_model=model,
        structured_output_mode=mode,
    )


def extraction_payload(**extra):
    payload = {
        "reproduction_present": True,
        "acceptance_criteria": ["must keep behaviour stable"],
        "affected_surfaces": ["web/reports/EmptyState.tsx"],
        "data_classes": [],
        "external_side_effects": [],
        "missing_information": [],
        "scope_estimate": "small",
        "embedded_instruction_detected": False,
        "confidence": 0.91,
    }
    payload.update(extra)
    return payload


def test_json_object_mode_strips_code_fences(monkeypatch):
    provider = OpenRouterProvider(settings())

    def stub(payload):
        assert payload["response_format"] == {"type": "json_object"}
        assert "JSON_SCHEMA" in payload["messages"][0]["content"]
        return {
            "choices": [
                {"message": {"content": "```json\n" + json.dumps(extraction_payload()) + "\n```"}}
            ]
        }

    monkeypatch.setattr(provider, "_post_chat_completions", stub)
    result = provider.extract("text", ["web/reports/EmptyState.tsx"], [])
    assert result.value.affected_surfaces == ["web/reports/EmptyState.tsx"]
    assert result.structured_output_mode == "json_object"


def test_json_object_mode_rejects_unexpected_field(monkeypatch):
    provider = OpenRouterProvider(settings())

    def stub(_payload):
        return {
            "choices": [
                {"message": {"content": json.dumps(extraction_payload(authorisation="ALLOW"))}}
            ]
        }

    monkeypatch.setattr(provider, "_post_chat_completions", stub)
    with pytest.raises(ProviderMalformed):
        provider.extract("text", ["web/reports/EmptyState.tsx"], [])


def test_json_object_mode_rejects_missing_required_field(monkeypatch):
    provider = OpenRouterProvider(settings())
    payload = extraction_payload()
    del payload["reproduction_present"]

    monkeypatch.setattr(
        provider,
        "_post_chat_completions",
        lambda _payload: {"choices": [{"message": {"content": json.dumps(payload)}}]},
    )
    with pytest.raises(ProviderMalformed):
        provider.extract("text", ["web/reports/EmptyState.tsx"], [])


def test_openrouter_model_capability_is_explicit():
    assert settings().resolved_structured_output_mode == "json_object"
    assert settings(model="openai/gpt-5-mini").resolved_structured_output_mode == "none"
    assert (
        settings(model="openai/gpt-5-mini", mode="json_schema").resolved_structured_output_mode
        == "json_schema"
    )
