"""Bifrost gateway provider.

Every test here is offline. The Bifrost gateway is VPN-gated and needs a
tenant-issued virtual key, so `urllib.request.urlopen` is stubbed for the whole
module and no test may ever open a real socket.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from warrant.config import BIFROST_DEFAULT_BASE_URL, Settings
from warrant.providers import (
    BIFROST_MODEL_CACHE,
    BifrostProvider,
    ProviderError,
    bifrost_key_fingerprint,
    bifrost_origin,
    build_provider,
    pick_bifrost_model,
)

# Distinctive so a leak into a cache key, a cache value or an error message is
# unambiguous when asserted against.
VIRTUAL_KEY = "bfvk-SUPERSECRET-do-not-log-0123456789"
ORIGIN = "https://bifrost.evergreen.gcp.griddynamics.net"


def settings(
    *,
    api_key: str | None = VIRTUAL_KEY,
    model: str = "",
    mode: str = "auto",
    base_url: str = BIFROST_DEFAULT_BASE_URL,
    provider: str = "bifrost",
) -> Settings:
    return Settings(
        database_path=Path("/tmp/unused.db"),
        ai_provider=provider,
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4.1-mini",
        webhook_secret="test",
        csrf_token="test",
        warrant_ttl_minutes=240,
        allow_sufficiency_threshold=0.70,
        fixture_failure=None,
        debug=False,
        bifrost_api_key=api_key,
        bifrost_base_url=base_url,
        bifrost_model=model,
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


class _StubGateway:
    """Fake Bifrost gateway installed at the urlopen boundary.

    Stubbing here rather than at `_list_model_ids`/`_post_chat_completions` is
    what lets the tests assert the URLs, auth headers and timeout that would
    actually reach the network, and count catalogue round trips for the cache.
    """

    def __init__(
        self,
        model_ids: list[str] | None = None,
        *,
        content: str | None = None,
        models_error: Exception | None = None,
        chat_error: Exception | None = None,
    ) -> None:
        self.model_ids = model_ids if model_ids is not None else ["minimax-m3"]
        self.content = content if content is not None else json.dumps(extraction_payload())
        self.models_error = models_error
        self.chat_error = chat_error
        self.model_calls: list[dict] = []
        self.chat_calls: list[dict] = []

    def install(self, monkeypatch) -> "_StubGateway":
        monkeypatch.setattr(urllib.request, "urlopen", self)
        return self

    def __call__(self, request: urllib.request.Request, timeout: float):
        record = {
            "url": request.full_url,
            "headers": dict(request.header_items()),
            "method": request.get_method(),
            "timeout": timeout,
            "body": json.loads(bytes(request.data)) if request.data else None,
        }
        if request.full_url.endswith("/v1/models"):
            self.model_calls.append(record)
            if self.models_error is not None:
                raise self.models_error
            body = {"data": [{"id": model_id} for model_id in self.model_ids]}
            return _StubResponse(json.dumps(body).encode())
        if request.full_url.endswith("/chat/completions"):
            self.chat_calls.append(record)
            if self.chat_error is not None:
                raise self.chat_error
            raw = {"choices": [{"message": {"content": self.content}}], "usage": {}}
            return _StubResponse(json.dumps(raw).encode())
        raise AssertionError(f"provider reached an unexpected URL: {request.full_url}")


class _ForbiddenNetwork:
    """urlopen stub that fails the test if the provider opens any connection."""

    def __call__(self, request: urllib.request.Request, timeout: float):
        raise AssertionError(f"unexpected network call to {request.full_url}")


@pytest.fixture(autouse=True)
def _isolated_model_cache():
    """The resolved-model cache is module state; no test may inherit another's."""
    BIFROST_MODEL_CACHE.clear()
    yield
    BIFROST_MODEL_CACHE.clear()


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Default every test to a closed network; a test opts in via _StubGateway."""
    monkeypatch.setattr(urllib.request, "urlopen", _ForbiddenNetwork())


# ---------------------------------------------------------------------------
# Credential handling
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_typed_provider_error():
    """No virtual key must be a typed ProviderError naming the env var, and it
    must fail before any gateway call is attempted."""
    with pytest.raises(ProviderError) as excinfo:
        BifrostProvider(settings(api_key=None))

    message = str(excinfo.value)
    assert "BIFROST_API_KEY" in message
    assert "AI_PROVIDER=bifrost" in message
    assert "virtual key" in message.lower(), (
        f"error must say the credential is a Bifrost virtual key, got: {message}"
    )


# ---------------------------------------------------------------------------
# Dynamic model resolution
# ---------------------------------------------------------------------------


def test_auto_resolution_picks_minimax_m3_from_catalogue(monkeypatch):
    """With BIFROST_MODEL unset, the id comes from GET {origin}/v1/models."""
    gateway = _StubGateway(
        ["openai/gpt-4.1-mini", "anthropic/claude-haiku-4-5", "minimax-m3", "minimax-m2"]
    ).install(monkeypatch)

    provider = BifrostProvider(settings())

    assert provider.model == "minimax-m3"
    assert provider.model_auto_resolved is True
    assert len(gateway.model_calls) == 1
    # The catalogue lives on the gateway origin, not the /anthropic adapter.
    assert gateway.model_calls[0]["url"] == f"{ORIGIN}/v1/models"
    assert gateway.model_calls[0]["method"] == "GET"


def test_auto_resolution_accepts_vendor_prefixed_minimax_id(monkeypatch):
    """Tenants expose the model prefixed; the prefixed id must be used verbatim."""
    _StubGateway(["openai/gpt-4.1-mini", "openrouter/minimax-m3"]).install(monkeypatch)

    assert BifrostProvider(settings()).model == "openrouter/minimax-m3"


def test_pick_bifrost_model_prefers_the_exact_id():
    assert pick_bifrost_model(["openrouter/minimax-m3", "minimax-m3"]) == "minimax-m3"
    assert pick_bifrost_model(["vendor/minimax-m3"]) == "vendor/minimax-m3"
    assert pick_bifrost_model(["openai/gpt-4.1-mini", "minimax-m2"]) is None


def test_catalogue_without_minimax_raises_actionable_error(monkeypatch):
    """A key whose allow-list omits M3 is a configuration fault, not a crash."""
    _StubGateway(["openai/gpt-4.1-mini", "anthropic/claude-haiku-4-5"]).install(monkeypatch)

    with pytest.raises(ProviderError) as excinfo:
        BifrostProvider(settings())

    message = str(excinfo.value)
    assert "Minimax M3" in message
    assert "BIFROST_MODEL" in message, "error should point at the manual override"
    assert VIRTUAL_KEY not in message


def test_explicit_model_skips_resolution_entirely(monkeypatch):
    """An explicit BIFROST_MODEL is authoritative: no catalogue round trip."""
    gateway = _StubGateway().install(monkeypatch)

    provider = BifrostProvider(settings(model="minimax-m3-tenant-a"))

    assert provider.model == "minimax-m3-tenant-a"
    assert provider.model_auto_resolved is False
    assert gateway.model_calls == [], "explicit model must not query /v1/models"


# ---------------------------------------------------------------------------
# Caching — keyed by fingerprint, never by the key itself
# ---------------------------------------------------------------------------


def test_resolution_is_cached_so_second_provider_does_not_re_request(monkeypatch):
    gateway = _StubGateway(["minimax-m3"]).install(monkeypatch)

    first = BifrostProvider(settings())
    second = BifrostProvider(settings())

    assert first.model == second.model == "minimax-m3"
    assert len(gateway.model_calls) == 1, (
        f"catalogue was queried {len(gateway.model_calls)} times; the resolved "
        "model must be cached per credential"
    )


def test_cache_is_keyed_by_fingerprint_and_never_holds_the_raw_key(monkeypatch):
    _StubGateway(["minimax-m3"]).install(monkeypatch)
    BifrostProvider(settings())

    fingerprint = bifrost_key_fingerprint(VIRTUAL_KEY)
    assert BIFROST_MODEL_CACHE == {fingerprint: "minimax-m3"}
    assert VIRTUAL_KEY not in BIFROST_MODEL_CACHE
    assert VIRTUAL_KEY not in BIFROST_MODEL_CACHE.values()
    # Nothing key-adjacent anywhere in the structure, not just at the top level.
    assert VIRTUAL_KEY not in repr(BIFROST_MODEL_CACHE)
    assert fingerprint != VIRTUAL_KEY
    assert VIRTUAL_KEY not in fingerprint


def test_distinct_keys_get_distinct_cache_entries(monkeypatch):
    gateway = _StubGateway(["minimax-m3"]).install(monkeypatch)

    BifrostProvider(settings())
    gateway.model_ids = ["openrouter/minimax-m3"]
    BifrostProvider(settings(api_key="bfvk-a-different-virtual-key"))

    assert len(gateway.model_calls) == 2, "a second credential must resolve on its own"
    assert set(BIFROST_MODEL_CACHE.values()) == {"minimax-m3", "openrouter/minimax-m3"}


# ---------------------------------------------------------------------------
# Reachability: VPN-gated gateway must degrade into a typed, explanatory error
# ---------------------------------------------------------------------------


def test_unreachable_gateway_during_resolution_mentions_vpn(monkeypatch):
    """The gateway is VPN-gated; a connection failure must say so rather than
    surfacing a raw URLError."""
    gateway = _StubGateway(models_error=urllib.error.URLError("connection refused")).install(
        monkeypatch
    )

    with pytest.raises(ProviderError) as excinfo:
        BifrostProvider(settings())

    message = str(excinfo.value)
    assert "VPN" in message, f"connectivity hint missing from: {message}"
    assert "Bifrost" in message
    assert VIRTUAL_KEY not in message, "error message must never carry the virtual key"
    # Every accepted auth header shape is tried before giving up.
    assert len(gateway.model_calls) == 3


def test_unreachable_gateway_during_completion_mentions_vpn(monkeypatch):
    """A transport failure on the chat call is a typed ProviderError too."""
    _StubGateway(
        ["minimax-m3"], chat_error=urllib.error.URLError("connection refused")
    ).install(monkeypatch)
    provider = BifrostProvider(settings())

    with pytest.raises(ProviderError) as excinfo:
        provider.extract("issue text", [], [])

    message = str(excinfo.value)
    assert "VPN" in message
    assert "Bifrost" in message
    assert VIRTUAL_KEY not in message


def test_catalogue_error_is_not_a_raw_exception(monkeypatch):
    """Errors are reported by exception type only — never a raw traceback or
    request detail that could carry credential-adjacent text."""
    _StubGateway(models_error=TimeoutError("timed out")).install(monkeypatch)

    with pytest.raises(ProviderError) as excinfo:
        BifrostProvider(settings())

    assert "TimeoutError" in str(excinfo.value)
    assert not isinstance(excinfo.value, TimeoutError)


# ---------------------------------------------------------------------------
# Wire shape: OpenAI-compatible adapter on the gateway origin
# ---------------------------------------------------------------------------


def test_bifrost_origin_strips_the_anthropic_adapter():
    assert bifrost_origin(BIFROST_DEFAULT_BASE_URL) == ORIGIN
    assert bifrost_origin(f"{ORIGIN}/anthropic/") == ORIGIN
    assert bifrost_origin(f"{ORIGIN}/ANTHROPIC") == ORIGIN
    assert bifrost_origin(ORIGIN) == ORIGIN


def test_completion_uses_openai_adapter_with_bearer_auth(monkeypatch):
    gateway = _StubGateway(["minimax-m3"]).install(monkeypatch)

    response = BifrostProvider(settings()).extract("issue text", ["web/reports/x.tsx"], [])

    assert response.value.affected_surfaces == ["web/reports/EmptyState.tsx"]
    assert len(gateway.chat_calls) == 1
    call = gateway.chat_calls[0]
    assert call["url"] == f"{ORIGIN}/v1/chat/completions"
    assert call["headers"].get("Authorization") == f"Bearer {VIRTUAL_KEY}"
    assert call["timeout"] == 45
    assert call["body"]["model"] == "minimax-m3"


def test_structured_output_is_json_object_not_json_schema(monkeypatch):
    """The gateway does not enforce JSON Schema server-side, so the request must
    ask for json_object and lean on client-side Pydantic validation."""
    gateway = _StubGateway(["minimax-m3"]).install(monkeypatch)

    response = BifrostProvider(settings()).extract("issue text", [], [])

    body = gateway.chat_calls[0]["body"]
    assert body["response_format"] == {"type": "json_object"}
    assert "JSON_SCHEMA" in body["messages"][0]["content"]
    assert response.structured_output_mode == "json_object"


# ---------------------------------------------------------------------------
# Settings wiring
# ---------------------------------------------------------------------------


def test_settings_resolve_bifrost_defaults():
    auto = settings()
    assert auto.bifrost_base_url == BIFROST_DEFAULT_BASE_URL
    assert auto.live_model == ""
    assert auto.resolved_structured_output_mode == "json_object"
    assert auto.resolved_provider_timeout_seconds == 45.0

    explicit = settings(model="minimax-m3")
    assert explicit.live_model == "minimax-m3"
    assert explicit.resolved_structured_output_mode == "json_object"

    # An operator override still wins over the provider default.
    assert settings(mode="none").resolved_structured_output_mode == "none"


def test_bifrost_env_vars_are_read(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "bifrost")
    monkeypatch.setenv("BIFROST_API_KEY", VIRTUAL_KEY)
    monkeypatch.setenv("BIFROST_BASE_URL", "https://gateway.internal/anthropic")
    monkeypatch.setenv("BIFROST_MODEL", "minimax-m3")

    loaded = Settings.from_env()

    assert loaded.ai_provider == "bifrost"
    assert loaded.bifrost_api_key == VIRTUAL_KEY
    assert loaded.bifrost_base_url == "https://gateway.internal/anthropic"
    assert loaded.bifrost_model == "minimax-m3"


def test_bifrost_model_defaults_to_auto_resolve_when_unset(monkeypatch):
    monkeypatch.delenv("BIFROST_MODEL", raising=False)
    monkeypatch.delenv("BIFROST_BASE_URL", raising=False)

    loaded = Settings.from_env()

    assert loaded.bifrost_model == ""
    assert loaded.bifrost_base_url == BIFROST_DEFAULT_BASE_URL


def test_build_provider_dispatches_bifrost_and_default_stays_fixture(monkeypatch):
    _StubGateway(["minimax-m3"]).install(monkeypatch)

    resilient = build_provider(settings())
    assert resilient.name == "bifrost"
    assert isinstance(resilient.primary, BifrostProvider)

    # Bifrost is strictly opt-in: no AI_PROVIDER=bifrost, no gateway.
    assert build_provider(settings(provider="fixture")).name == "fixture"
