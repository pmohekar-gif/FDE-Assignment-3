import pytest
from fastapi.testclient import TestClient

from warrant.config import Settings
from warrant.main import create_app
from warrant.seed import reset_and_seed


@pytest.fixture
def stub_client(tmp_path) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "linear.db",
        ai_provider="fixture",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4.1-mini",
        webhook_secret="test-webhook-secret",
        csrf_token="test-csrf",
        warrant_ttl_minutes=240,
        allow_sufficiency_threshold=0.70,
        fixture_failure=None,
        debug=False,
        linear_mode="stub",
    )
    reset_and_seed(settings)
    return TestClient(create_app(settings))


@pytest.fixture
def openrouter_client(tmp_path) -> TestClient:
    settings = Settings(
        database_path=tmp_path / "or.db",
        ai_provider="openrouter",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4.1-mini",
        openrouter_api_key="test-key",
        webhook_secret="test-webhook-secret",
        csrf_token="test-csrf",
        warrant_ttl_minutes=240,
        allow_sufficiency_threshold=0.70,
        fixture_failure=None,
        debug=False,
        linear_mode="stub",
    )
    reset_and_seed(settings)
    return TestClient(create_app(settings))


def test_import_fresh_issue(stub_client):
    headers = {"X-CSRF-Token": "test-csrf", "X-Actor-Id": "admin-demo"}
    response = stub_client.post(
        "/v1/adapters/linear/import-issue",
        headers=headers,
        json={"ref": "ENG-999"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["outcome"] == "created"
    assert data["issue_ref"] == "ENG-999"
    assert data["revision"] == 1
    assert data["is_stub"] is True
    
    # Verify FTS searchability
    search = stub_client.get("/v1/issues/search?q=memory leak")
    assert search.status_code == 200
    refs = [r["external_key"] for r in search.json()["results"]]
    assert "ENG-999" in refs


def test_reimport_unchanged(stub_client):
    headers = {"X-CSRF-Token": "test-csrf", "X-Actor-Id": "admin-demo"}
    
    # First import
    res1 = stub_client.post(
        "/v1/adapters/linear/import-issue", headers=headers, json={"ref": "ENG-888"}
    )
    assert res1.status_code == 201
    
    # Second import (identical stub payload)
    res2 = stub_client.post(
        "/v1/adapters/linear/import-issue", headers=headers, json={"ref": "ENG-888"}
    )
    assert res2.status_code == 200
    data = res2.json()
    assert data["outcome"] == "unchanged"
    assert data["revision"] == 1
    assert data["audit_event_id"] is None


def test_reimport_changed(stub_client):
    from unittest.mock import patch

    from warrant.adapters.linear_fixture import STUB_LINEAR_ISSUE

    headers = {"X-CSRF-Token": "test-csrf", "X-Actor-Id": "admin-demo"}
    
    # First import
    res1 = stub_client.post(
        "/v1/adapters/linear/import-issue", headers=headers, json={"ref": "ENG-777"}
    )
    assert res1.status_code == 201
    
    # Second import (changed payload)
    changed_stub = dict(STUB_LINEAR_ISSUE)
    changed_stub["title"] = "Updated title"
    
    with patch("warrant.adapters.linear.STUB_LINEAR_ISSUE", changed_stub):
        res2 = stub_client.post(
            "/v1/adapters/linear/import-issue", headers=headers, json={"ref": "ENG-777"}
        )
        assert res2.status_code == 200
        data = res2.json()
        assert data["outcome"] == "updated"
        assert data["revision"] == 2
        assert data["audit_event_id"] is not None

        # Verify FTS update
        search = stub_client.get("/v1/issues/search?q=Updated")
        assert search.status_code == 200
        assert "ENG-777" in [r["external_key"] for r in search.json()["results"]]


def test_collision(stub_client):
    # PAY-4471 is a pre-seeded synthetic issue
    headers = {"X-CSRF-Token": "test-csrf", "X-Actor-Id": "admin-demo"}
    response = stub_client.post(
        "/v1/adapters/linear/import-issue",
        headers=headers,
        json={"ref": "PAY-4471"},
    )
    assert response.status_code == 409
    assert "already exists and is not a Linear import" in response.json()["error"]


def test_collision_same_external_id(stub_client):
    from unittest.mock import patch

    from warrant.adapters.linear import LinearAdapter

    headers = {"X-CSRF-Token": "test-csrf", "X-Actor-Id": "admin-demo"}
    
    # 1. Import ENG-101
    res1 = stub_client.post(
        "/v1/adapters/linear/import-issue", headers=headers, json={"ref": "ENG-101"}
    )
    assert res1.status_code == 201

    # 2. Mock LinearAdapter.fetch_issue to return ENG-102 but with the same external_id as ENG-101
    original_fetch = LinearAdapter.fetch_issue
    def mock_fetch(self, ref):
        dto = original_fetch(self, ref)
        if ref == "ENG-102":
            dto.id = original_fetch(self, "ENG-101").id
        return dto

    with patch.object(LinearAdapter, "fetch_issue", autospec=True, side_effect=mock_fetch):
        res2 = stub_client.post(
            "/v1/adapters/linear/import-issue", headers=headers, json={"ref": "ENG-102"}
        )
    
    assert res2.status_code == 409
    assert "already linked to a different key" in res2.json()["error"]


def test_collision_different_external_id(stub_client):
    from unittest.mock import patch

    from warrant.adapters.linear import LinearAdapter

    headers = {"X-CSRF-Token": "test-csrf", "X-Actor-Id": "admin-demo"}
    
    # 1. Import ENG-103
    res1 = stub_client.post(
        "/v1/adapters/linear/import-issue", headers=headers, json={"ref": "ENG-103"}
    )
    assert res1.status_code == 201

    # 2. Re-import ENG-103 but Linear returns a DIFFERENT external ID for it
    original_fetch = LinearAdapter.fetch_issue
    def mock_fetch(self, ref):
        dto = original_fetch(self, ref)
        if ref == "ENG-103":
            dto.id = "some-new-id"
        return dto

    with patch.object(LinearAdapter, "fetch_issue", autospec=True, side_effect=mock_fetch):
        res2 = stub_client.post(
            "/v1/adapters/linear/import-issue", headers=headers, json={"ref": "ENG-103"}
        )
    
    assert res2.status_code == 409
    assert "linked to a different Linear issue ID" in res2.json()["error"]


def test_non_admin_rejected(stub_client):
    headers = {"X-CSRF-Token": "test-csrf", "X-Actor-Id": "engineer-demo"}
    response = stub_client.post(
        "/v1/adapters/linear/import-issue",
        headers=headers,
        json={"ref": "ENG-999"},
    )
    assert response.status_code == 403


def test_missing_csrf(stub_client):
    headers = {"X-Actor-Id": "admin-demo"}
    response = stub_client.post(
        "/v1/adapters/linear/import-issue",
        headers=headers,
        json={"ref": "ENG-999"},
    )
    assert response.status_code == 400


def test_openrouter_guard(openrouter_client):
    headers = {"X-CSRF-Token": "test-csrf", "X-Actor-Id": "admin-demo"}
    
    # 1. Import issue
    res1 = openrouter_client.post(
        "/v1/adapters/linear/import-issue", headers=headers, json={"ref": "ENG-777"}
    )
    assert res1.status_code == 201
    
    # 2. Try to delegate it (OpenRouter provider is active)
    res2 = openrouter_client.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": "ENG-777",
            "requester_id": "engineer-demo",
            "target_agent_id": "codex-cloud",
            "idempotency_key": "test-guard-key",
        }
    )
    assert res2.status_code == 403
    assert "blocked when AI_PROVIDER=openrouter" in res2.json()["error"]


def test_config_off(tmp_path):
    settings = Settings(
        database_path=tmp_path / "off.db",
        ai_provider="fixture",
        openai_api_key=None,
        openai_base_url="",
        openai_model="",
        webhook_secret="test",
        csrf_token="test",
        warrant_ttl_minutes=240,
        allow_sufficiency_threshold=0.70,
        fixture_failure=None,
        debug=False,
        linear_mode="off",
    )
    reset_and_seed(settings)
    client = TestClient(create_app(settings))
    
    headers = {"X-CSRF-Token": "test", "X-Actor-Id": "admin-demo"}
    response = client.post(
        "/v1/adapters/linear/import-issue",
        headers=headers,
        json={"ref": "ENG-999"},
    )
    assert response.status_code == 503
    assert "not configured" in response.json()["error"]
