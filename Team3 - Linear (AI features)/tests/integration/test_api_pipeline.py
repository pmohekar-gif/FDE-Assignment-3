import json
import time

from warrant.security import sign_webhook


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
