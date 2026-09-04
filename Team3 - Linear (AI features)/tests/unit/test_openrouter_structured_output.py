from __future__ import annotations

import io
import json
import urllib.request
from pathlib import Path

import pytest

from warrant.config import Settings
from warrant.providers import OpenRouterProvider, ProviderMalformed, tolerant_json_loads


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


class _StubResponse(io.BytesIO):
    """Minimal context-manager wrapper around BytesIO for urlopen stubs."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def _stub_urlopen(monkeypatch, content: str, **metadata):
    """Patch urllib.request.urlopen and capture the request the provider builds.

    Stubbing at urlopen (rather than _post_chat_completions) is the only way to
    assert that the 45-second timeout and HTTP-Referer/X-Title attribution headers
    actually reach the network boundary.
    """
    captured: dict = {}

    def open_(request: urllib.request.Request, timeout: float):
        captured["payload"] = json.loads(bytes(request.data or b"{}"))
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        raw = {
            "choices": [{"message": {"content": content}}],
            "usage": metadata.get("usage", {}),
            "model": metadata.get("model"),
            "provider": metadata.get("provider"),
        }
        return _StubResponse(json.dumps(raw).encode())

    monkeypatch.setattr(urllib.request, "urlopen", open_)
    return captured


# ---------------------------------------------------------------------------
# Wire-level: timeout and attribution headers
# ---------------------------------------------------------------------------


def test_timeout_and_attribution_headers_reach_wire(monkeypatch):
    """The 45s timeout and HTTP-Referer/X-Title headers must reach urlopen.

    Stubbing at _post_chat_completions would silently swallow these properties;
    only a urlopen-level stub can assert they are wired through.
    """
    captured = _stub_urlopen(monkeypatch, json.dumps(extraction_payload()))
    OpenRouterProvider(settings()).extract("issue text", [], [])

    assert captured["timeout"] == 45, (
        f"Expected 45s timeout for openrouter, got {captured['timeout']}"
    )
    headers = captured["headers"]
    assert "Http-referer" in headers, "HTTP-Referer attribution header was not sent"
    assert headers.get("X-title") == "Warrant Synthetic Live Check", (
        f"X-Title header mismatch: {headers.get('X-title')}"
    )


# ---------------------------------------------------------------------------
# Wire-level: prose-with-trailing-brace does not burn a repair
# ---------------------------------------------------------------------------


def test_tolerant_json_loads_prose_trailing_brace_no_repair():
    """tolerant_json_loads must handle a trailing prose brace without repair.

    The old first-{ to last-} slice would produce invalid JSON when the model
    emits 'Here is the result: {...} See note {above}.' raw_decode stops at
    the first complete JSON value so the trailing brace is ignored and no
    schema-repair round-trip is needed.
    """
    valid = extraction_payload()
    # Simulate a model that appends prose containing a brace after the JSON
    prose_suffix = " Note: confidence may vary {see docs}."
    content = json.dumps(valid) + prose_suffix
    parsed = tolerant_json_loads(content)
    assert parsed["scope_estimate"] == "small"
    assert parsed["confidence"] == 0.91


# ---------------------------------------------------------------------------
# Existing higher-level schema tests (kept for regression coverage)
# ---------------------------------------------------------------------------


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
