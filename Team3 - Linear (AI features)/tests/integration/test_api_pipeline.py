import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from warrant.config import Settings
from warrant.main import create_app
from warrant.security import sign_webhook
from warrant.seed import reset_and_seed


def openrouter_settings(tmp_path, model="minimax/minimax-m3:free"):
    return Settings(
        database_path=Path(tmp_path) / "openrouter.db",
        ai_provider="openrouter",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4.1-mini",
        webhook_secret="test-webhook-secret",
        csrf_token="test-csrf",
        warrant_ttl_minutes=240,
        allow_sufficiency_threshold=0.70,
        fixture_failure=None,
        debug=False,
        openrouter_api_key="test-openrouter-key",
        openrouter_model=model,
        provider_retry_base_ms=0,
    )


def openrouter_client(tmp_path) -> TestClient:
    settings = openrouter_settings(tmp_path)
    reset_and_seed(settings)
    return TestClient(create_app(settings))


def extraction_payload(path):
    return {
        "reproduction_present": True,
        "acceptance_criteria": ["Expected behaviour must remain stable."],
        "affected_surfaces": [path],
        "data_classes": [],
        "external_side_effects": [],
        "missing_information": [],
        "scope_estimate": "small",
        "embedded_instruction_detected": False,
        "confidence": 0.95,
    }


def openrouter_response(content, usage=True, metadata=True):
    response = {
        "model": "minimax/minimax-m3:free",
        "choices": [{"message": {"content": content}}],
    }
    if metadata:
        response["provider"] = "minimax-test-route"
    if usage:
        response["usage"] = {
            "prompt_tokens": 101,
            "completion_tokens": 29,
            "total_tokens": 130,
            "completion_tokens_details": {"reasoning_tokens": 7},
            "cost": 0.0,
        }
    return response


def create(client, headers, issue, requester="engineer-demo", key="case"):
    return client.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": issue,
            "requester_id": requester,
            "target_agent_id": "codex-cloud",
            "idempotency_key": f"{key}-{issue}",
        },
    )


def test_three_reference_scenarios_execute_real_pipeline(client, headers):
    approval = create(client, headers, "PAY-4471", key="reference").json()
    denied = create(client, headers, "SEC-4502", key="reference").json()
    allowed = create(client, headers, "WEB-4519", requester="lead-web", key="reference").json()
    assert approval["decision"]["verdict"] == "REQUIRE_APPROVAL"
    assert denied["decision"]["verdict"] == "DENY"
    assert "INJECTION_SIGNAL" in denied["decision"]["reason_codes"]
    assert allowed["decision"]["verdict"] == "ALLOW"
    assert allowed["warrant"]["status"] == "active"
    assert approval["retrieval"]["candidates"]


def test_idempotent_manual_and_signed_webhook_ingress(client, headers):
    first = create(client, headers, "WEB-4519", requester="lead-web", key="idem").json()
    second = create(client, headers, "WEB-4519", requester="lead-web", key="idem").json()
    assert first["id"] == second["id"]
    assert second["idempotent_replay"] is True

    raw = json.dumps(
        {"issue_ref": "PAY-4471", "requester_id": "engineer-demo", "target_agent_id": "codex-cloud"}
    ).encode()
    timestamp = str(time.time())
    signature = sign_webhook("test-webhook-secret", timestamp, raw)
    response = client.post(
        "/v1/hooks/tracker",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature,
            "X-Timestamp": timestamp,
            "X-Delivery-Id": "wh-001",
        },
    )
    assert response.status_code == 202
    assert response.json()["decision"]["verdict"] == "REQUIRE_APPROVAL"
    assert response.json()["risk_assessment"]["features"]["untrusted_origin"] is True
    assert response.json()["risk_assessment"]["evidence_sufficiency"] <= 0.9


def test_invalid_request_and_webhook_fail_clearly(client, headers):
    assert client.post("/v1/delegations", headers=headers, json={}).status_code == 422
    assert (
        client.post(
            "/v1/hooks/tracker", content=b"{}", headers={"X-Signature": "bad", "X-Timestamp": "0"}
        ).status_code
        == 401
    )


def test_dashboard_exposes_measured_and_not_measured_metrics(client):
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "unsafe allow count" in dashboard.text
    assert "risk class macro f1" in dashboard.text
    assert "NOT_MEASURED" in dashboard.text
    assert "of 400 synthetic issues" in dashboard.text


def test_openrouter_json_object_pipeline_keeps_deterministic_verdict(
    tmp_path, headers, monkeypatch
):
    def stub(self, payload):
        assert self.name == "openrouter"
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["usage"] == {"include": True}
        assert "HTTP-Referer" in self.extra_headers
        return openrouter_response(
            "Result:\n```json\n"
            + json.dumps(extraction_payload("web/reports/EmptyState.tsx"))
            + "\n```"
        )

    monkeypatch.setattr("warrant.providers.ChatCompletionsProvider._post_chat_completions", stub)
    client = openrouter_client(tmp_path)
    created = create(client, headers, "WEB-4519", requester="lead-web", key="openrouter-ok").json()
    assert created["decision"]["verdict"] == "ALLOW"
    usage = client.app.state.db.one(
        "SELECT * FROM model_usage WHERE delegation_id=?", (created["id"],)
    )
    assert usage["provider"] == "openrouter"
    assert usage["model"] == "minimax/minimax-m3:free"
    assert usage["serving_provider"] == "minimax-test-route"
    assert usage["structured_output_mode"] == "json_object"
    assert usage["input_tokens"] == 101
    assert usage["output_tokens"] == 29
    assert usage["reasoning_tokens"] == 7
    assert usage["total_tokens"] == 130
    assert usage["reported_cost_usd"] == 0.0


def test_openrouter_malformed_extraction_fails_closed_without_allow(tmp_path, headers, monkeypatch):
    malformed = json.dumps({"affected_surfaces": ["web/reports/EmptyState.tsx"]})

    monkeypatch.setattr(
        "warrant.providers.ChatCompletionsProvider._post_chat_completions",
        lambda _self, _payload: openrouter_response(malformed),
    )
    client = openrouter_client(tmp_path)
    created = create(
        client, headers, "WEB-4519", requester="lead-web", key="openrouter-malformed"
    ).json()
    assert created["decision"]["verdict"] == "REQUIRE_APPROVAL"
    assert created["decision"]["fail_closed"] is True
    assert created["risk_assessment"]["features"]["extraction_unavailable"] is True


def test_openrouter_missing_provider_metadata_does_not_block_authorization(
    tmp_path, headers, monkeypatch
):
    monkeypatch.setattr(
        "warrant.providers.ChatCompletionsProvider._post_chat_completions",
        lambda _self, _payload: openrouter_response(
            json.dumps(extraction_payload("web/reports/EmptyState.tsx")),
            usage=False,
            metadata=False,
        ),
    )
    client = openrouter_client(tmp_path)
    created = create(
        client, headers, "WEB-4519", requester="lead-web", key="openrouter-no-metadata"
    ).json()
    assert created["decision"]["verdict"] == "ALLOW"
    usage = client.app.state.db.one(
        "SELECT serving_provider,reported_cost_usd FROM model_usage WHERE delegation_id=?",
        (created["id"],),
    )
    assert usage["serving_provider"] is None
    assert usage["reported_cost_usd"] is None


def test_openrouter_schema_repair_telemetry_includes_provider_and_model(
    tmp_path, headers, monkeypatch
):
    calls = {"count": 0}

    def stub(_self, _payload):
        calls["count"] += 1
        if calls["count"] == 1:
            return openrouter_response('{"affected_surfaces":["web/reports/EmptyState.tsx"]}')
        return openrouter_response(json.dumps(extraction_payload("web/reports/EmptyState.tsx")))

    monkeypatch.setattr("warrant.providers.ChatCompletionsProvider._post_chat_completions", stub)
    client = openrouter_client(tmp_path)
    created = create(
        client, headers, "WEB-4519", requester="lead-web", key="openrouter-repair"
    ).json()
    usage = client.app.state.db.one(
        "SELECT schema_repair_count FROM model_usage WHERE delegation_id=?",
        (created["id"],),
    )
    event = client.app.state.db.one(
        "SELECT attributes_json FROM telemetry_events WHERE name='schema_repair'"
    )
    attributes = json.loads(event["attributes_json"])
    assert usage["schema_repair_count"] == 1
    assert attributes["provider"] == "openrouter"
    assert attributes["model"] == "minimax/minimax-m3:free"
