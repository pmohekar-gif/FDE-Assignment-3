from warrant.providers import (
    LLMProvider,
    ProviderError,
    ProviderMalformed,
    ProviderResponse,
    ResilientProvider,
)
from warrant.schemas import ExtractionResult


def extraction_response() -> ProviderResponse:
    return ProviderResponse(
        value=ExtractionResult(
            reproduction_present=True,
            acceptance_criteria=["works"],
            affected_surfaces=["web/a.py"],
            data_classes=[],
            external_side_effects=[],
            missing_information=[],
            scope_estimate="small",
            embedded_instruction_detected=False,
            confidence=0.9,
        ),
        provider="spy",
        model="spy-v1",
        latency_ms=1,
        input_tokens=None,
        output_tokens=None,
        estimated_cost_usd=None,
    )


class SpyProvider(LLMProvider):
    name = "spy"
    model = "spy-v1"

    def __init__(self, failures: list[Exception]):
        self.failures = failures
        self.calls: list[str | None] = []

    def extract(self, text, path_hints, context, repair_error=None):
        self.calls.append(repair_error)
        if self.failures:
            raise self.failures.pop(0)
        return extraction_response()

    def judge(self, criteria, evidence, repair_error=None):
        raise NotImplementedError

    def brief(self, detail, repair_error=None):
        raise NotImplementedError


def test_transport_errors_retry_twice(monkeypatch):
    delays: list[float] = []
    monkeypatch.setattr("warrant.providers.time.sleep", delays.append)
    primary = SpyProvider([ProviderError("503"), ProviderError("503")])
    result = ResilientProvider(primary, base_delay_ms=1).extract("x", [], [])
    assert result.value.affected_surfaces == ["web/a.py"]
    assert len(primary.calls) == 3
    assert len(delays) == 2
    assert delays[1] > delays[0]


def test_malformed_response_gets_one_repair_with_validation_error():
    primary = SpyProvider([ProviderMalformed("field missing")])
    response = ResilientProvider(primary, base_delay_ms=0).extract("x", [], [])
    assert primary.calls == [None, "field missing"]
    assert response.schema_repair_count == 1


def test_optional_fallback_is_used_after_retry_budget(monkeypatch):
    monkeypatch.setattr("warrant.providers.time.sleep", lambda _: None)
    primary = SpyProvider([ProviderError("503")] * 3)
    fallback = SpyProvider([])
    response = ResilientProvider(primary, fallback, base_delay_ms=0).extract("x", [], [])
    assert response.provider == "fallback:spy"
    assert response.degraded is True
    assert len(primary.calls) == 3
    assert len(fallback.calls) == 1
