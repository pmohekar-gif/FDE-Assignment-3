from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from warrant.adapters.github import (
    AdapterConfigError,
    GitHubAdapter,
    GitHubNotFoundError,
    GitHubRequestError,
)
from warrant.config import Settings


def make_settings(**kwargs):
    base = dict(
        database_path=Path("/tmp/unused.db"),
        ai_provider="fixture",
        webhook_secret="secret",
        csrf_token="token",
        warrant_ttl_minutes=60,
        allow_sufficiency_threshold=0.8,
        fixture_failure=None,
        debug=False,
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4o",
    )
    base.update(kwargs)
    return Settings(**base)


@pytest.fixture
def github_stub_settings():
    return make_settings(
        github_mode="stub",
        github_token="fake-token",
        github_api_base_url="https://api.github.com",
    )


@pytest.fixture
def github_live_settings():
    return make_settings(
        github_mode="live",
        github_token="fake-token",
        github_api_base_url="https://api.github.com",
    )


@pytest.fixture
def github_off_settings():
    return make_settings(github_mode="off")


def test_github_adapter_off(github_off_settings):
    adapter = GitHubAdapter(github_off_settings)
    with pytest.raises(AdapterConfigError):
        adapter.get_pull_request("owner", "repo", 1)


def test_github_adapter_live_no_token():
    settings = make_settings(github_mode="live", github_token=None)
    adapter = GitHubAdapter(settings)
    with pytest.raises(AdapterConfigError):
        adapter.get_pull_request("owner", "repo", 1)


def test_github_stub_mode(github_stub_settings):
    adapter = GitHubAdapter(github_stub_settings)

    pr = adapter.get_pull_request("test-owner", "test-repo", 99)
    assert pr.number == 99
    assert "test-owner" in pr.html_url
    assert "test-repo" in pr.html_url
    assert pr.title.startswith("[SIMULATED]")

    files = adapter.get_pull_request_files("test-owner", "test-repo", 99)
    assert len(files) == 2
    assert files[0].filename == "src/auth.py"
    assert not hasattr(files[0], "patch")

    checks = adapter.get_pull_request_checks("test-owner", "test-repo", "some-sha")
    assert len(checks) == 2
    assert checks[0].name == "lint"


@patch("httpx.get")
def test_github_live_mode_success(mock_get, github_live_settings):
    adapter = GitHubAdapter(github_live_settings)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": 111,
        "number": 1,
        "html_url": "https://github.com/owner/repo/pull/1",
        "state": "open",
        "draft": False,
        "merged": False,
        "base": {"ref": "main"},
        "head": {"sha": "sha123"},
        "title": "Test PR",
        "body": "must not be mapped",
    }
    mock_get.return_value = mock_response

    pr = adapter.get_pull_request("owner", "repo", 1)
    assert pr.id == 111
    assert pr.title == "Test PR"
    assert not hasattr(pr, "body")
    mock_get.assert_called_once()
    assert mock_get.call_args.args[0] == "https://api.github.com/repos/owner/repo/pulls/1"
    headers = mock_get.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer fake-token"
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"


@patch("httpx.get")
def test_github_files_strip_patch_content_and_bound_limit(mock_get, github_live_settings):
    adapter = GitHubAdapter(github_live_settings)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "filename": "src/auth.py",
            "status": "modified",
            "additions": 3,
            "deletions": 1,
            "patch": "secret code diff must not be returned",
        }
    ]
    mock_get.return_value = mock_response

    files = adapter.get_pull_request_files("owner", "repo", 1, limit=500)

    assert mock_get.call_args.args[0].endswith("/pulls/1/files?per_page=100")
    assert files[0].model_dump() == {
        "filename": "src/auth.py",
        "status": "modified",
        "additions": 3,
        "deletions": 1,
    }


@patch("httpx.get")
def test_github_checks_handle_empty_response(mock_get, github_live_settings):
    adapter = GitHubAdapter(github_live_settings)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"total_count": 0, "check_runs": []}
    mock_get.return_value = mock_response

    assert adapter.get_pull_request_checks("owner", "repo", "sha123") == []


def test_github_live_rejects_unsafe_base_url():
    settings = make_settings(
        github_mode="live",
        github_token="fake-token",
        github_api_base_url="http://127.0.0.1:8000",
    )
    with pytest.raises(AdapterConfigError):
        GitHubAdapter(settings).get_pull_request("owner", "repo", 1)


def test_github_rejects_path_injection(github_live_settings):
    adapter = GitHubAdapter(github_live_settings)
    with pytest.raises(GitHubRequestError):
        adapter.get_pull_request("owner/evil", "repo", 1)


@patch("httpx.get")
def test_github_live_mode_not_found(mock_get, github_live_settings):
    adapter = GitHubAdapter(github_live_settings)

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_get.return_value = mock_response

    with pytest.raises(GitHubNotFoundError):
        adapter.get_pull_request("owner", "repo", 1)


@patch("httpx.get")
def test_github_live_mode_http_error(mock_get, github_live_settings):
    adapter = GitHubAdapter(github_live_settings)

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = httpx.HTTPError("Server error")
    mock_get.return_value = mock_response

    with pytest.raises(AdapterConfigError):
        adapter.get_pull_request("owner", "repo", 1)
