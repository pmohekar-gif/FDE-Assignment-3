from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from warrant.config import Settings
from warrant.main import create_app
from warrant.seed import reset_and_seed


def make_client(tmp_path: Path, *, github_mode: str) -> TestClient:
    settings = Settings(
        database_path=tmp_path / f"github-{github_mode}.db",
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
        github_mode=github_mode,
        github_token="test-token" if github_mode == "live" else None,
    )
    reset_and_seed(settings)
    return TestClient(create_app(settings))


@pytest.fixture
def github_stub_client(tmp_path) -> TestClient:
    return make_client(tmp_path, github_mode="stub")


@pytest.fixture
def github_off_client(tmp_path) -> TestClient:
    return make_client(tmp_path, github_mode="off")


def test_github_status_endpoint_reports_off_without_fetch(github_off_client):
    response = github_off_client.get(
        "/v1/adapters/github/status", headers={"X-Actor-Id": "priyanka-mohekar"}
    )
    assert response.status_code == 200
    assert response.json() == {
        "adapter_mode": "off",
        "source": "none",
        "api_base_url": "https://api.github.com",
    }


def test_github_off_pull_request_returns_503(github_off_client):
    response = github_off_client.get(
        "/v1/adapters/github/pull-request?owner=o&repo=r&number=1",
        headers={"X-Actor-Id": "priyanka-mohekar"},
    )
    assert response.status_code == 503
    assert "not configured" in response.json()["error"]


def test_github_stub_pull_request_endpoint_requires_admin(github_stub_client):
    response = github_stub_client.get(
        "/v1/adapters/github/pull-request?owner=o&repo=r&number=1",
        headers={"X-Actor-Id": "kriti-developer"},
    )
    assert response.status_code == 403


def test_github_stub_pull_request_endpoint_returns_source_label(github_stub_client):
    response = github_stub_client.get(
        "/v1/adapters/github/pull-request?owner=example&repo=repo&number=42",
        headers={"X-Actor-Id": "priyanka-mohekar"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["adapter_mode"] == "stub"
    assert data["source"] == "github-stub"
    assert data["pull_request"]["number"] == 42
    assert "body" not in data["pull_request"]


def test_github_stub_files_endpoint_omits_patches(github_stub_client):
    response = github_stub_client.get(
        "/v1/adapters/github/pull-request/files?owner=example&repo=repo&number=42",
        headers={"X-Actor-Id": "priyanka-mohekar"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "github-stub"
    assert data["files"]
    assert "patch" not in data["files"][0]


def test_github_stub_checks_endpoint_handles_limit(github_stub_client):
    response = github_stub_client.get(
        "/v1/adapters/github/pull-request/checks?owner=example&repo=repo&ref=sha&limit=1",
        headers={"X-Actor-Id": "priyanka-mohekar"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "github-stub"
    assert len(data["checks"]) == 1
    assert data["checks"][0]["status"] == "completed"
