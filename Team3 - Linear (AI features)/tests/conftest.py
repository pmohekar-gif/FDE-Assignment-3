from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from warrant.config import Settings
from warrant.main import create_app
from warrant.seed import reset_and_seed


@pytest.fixture
def client_factory(tmp_path):
    def factory(failure: str | None = None) -> TestClient:
        settings = Settings(
            database_path=tmp_path / f"warrant-{failure or 'healthy'}.db",
            ai_provider="fixture",
            openai_api_key=None,
            openai_base_url="https://api.openai.com/v1",
            openai_model="gpt-4.1-mini",
            webhook_secret="test-webhook-secret",
            csrf_token="test-csrf",
            warrant_ttl_minutes=240,
            allow_sufficiency_threshold=0.70,
            fixture_failure=failure,
            debug=False,
        )
        reset_and_seed(settings)
        return TestClient(create_app(settings))

    return factory


@pytest.fixture
def client(client_factory):
    return client_factory()


@pytest.fixture
def headers():
    return {"X-CSRF-Token": "test-csrf"}
