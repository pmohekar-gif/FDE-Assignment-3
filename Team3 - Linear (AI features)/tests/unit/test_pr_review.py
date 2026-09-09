import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from warrant.config import Settings
from warrant.db import Database
from warrant.pr_review import GitHubPRReviewService
from warrant.providers import LLMProvider
from warrant.seed import reset_and_seed


@pytest.fixture
def mock_settings(tmp_path):
    return Settings(
        database_path=tmp_path / "test.db",
        ai_provider="fixture",
        openai_api_key="dummy",
        openai_base_url="dummy",
        openai_model="dummy",
        webhook_secret="dummy",
        csrf_token="dummy",
        warrant_ttl_minutes=1,
        allow_sufficiency_threshold=0.5,
        fixture_failure=None,
        debug=False,
        github_pr_review_enabled=True,
        github_mode="stub",
    )

@pytest.fixture
def mock_db(mock_settings):
    reset_and_seed(mock_settings)
    return Database(mock_settings.database_path)

@pytest.fixture
def mock_provider():
    return Mock(spec=LLMProvider)

@pytest.fixture
def service(mock_settings, mock_db, mock_provider):
    service = GitHubPRReviewService(mock_settings, mock_db, mock_provider)
    service.github = Mock()
    service.github.source = "github_pr"
    return service

def test_link_pr_to_issue_creates_link(service, mock_db, mock_settings):
    workspace_id = mock_settings.workspace_id
    actor_id = "user-1"
    
    mock_pr = Mock()
    mock_pr.html_url = "https://github.com/owner/repo/pull/1"
    mock_pr.head_sha = "abcdef"
    service.github.get_pull_request.return_value = mock_pr
    
    result = service.link_pr_to_issue(workspace_id, actor_id, "owner", "repo", 1, "WEB-4519")
    
    assert result["link_id"] is not None
    assert result["created"] is True
    
    link = mock_db.one("SELECT * FROM github_pr_links WHERE id=?", (result["link_id"],))
    assert link is not None
    assert link["owner"] == "owner"

def test_link_pr_to_issue_existing_link(service, mock_db, mock_settings):
    workspace_id = mock_settings.workspace_id
    actor_id = "user-1"
    
    mock_db.execute(
        "INSERT INTO github_pr_links (id, workspace_id, issue_id, owner, repo, "
        "pull_request_number, pr_url, head_sha, selected_by, selected_at, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "link-1",
            workspace_id,
            "issue-web-4519",
            "owner",
            "repo",
            1,
            "url",
            "sha",
            actor_id,
            datetime.now(timezone.utc).isoformat(),
            "github",
        ),
    )
    
    mock_pr = Mock()
    mock_pr.html_url = "https://github.com/owner/repo/pull/1"
    mock_pr.head_sha = "abcdef"
    service.github.get_pull_request.return_value = mock_pr
    
    result = service.link_pr_to_issue(workspace_id, actor_id, "owner", "repo", 1, "WEB-4519")
    assert result["link_id"] == "link-1"
    assert result["created"] is False


def test_create_review_session_strips_repository_subdir_prefix(
    service, mock_db, mock_provider, mock_settings
):
    workspace_id = mock_settings.workspace_id
    actor_id = "user-1"

    mock_db.execute(
        "INSERT INTO delegations (id, workspace_id, issue_id, status, requester_id, "
        "created_at, target_agent_id, source, delivery_id, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "delegation-prefix",
            workspace_id,
            "issue-web-4519",
            "active",
            "user-1",
            "2023-01-01T00:00:00Z",
            "agent-1",
            "ui",
            "del-prefix",
            "2023-01-01T00:00:00Z",
        ),
    )
    mock_db.execute(
        "INSERT INTO warrants (id, workspace_id, delegation_id, agent_id, authority_user_id, "
        "scope_json, allowed_tools_json, denied_tools_json, evidence_contract_json, "
        "nonce_hash, issued_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "warrant-prefix",
            workspace_id,
            "delegation-prefix",
            "agent-1",
            "user-1",
            '["src/**"]',
            "[]",
            "[]",
            "{}",
            "hash",
            "2023-01-01T00:00:00Z",
            "2099-01-01T00:00:00Z",
        ),
    )

    mock_pr = Mock()
    mock_pr.head_sha = "abcdef"
    mock_pr.base_ref = "main"
    service.github.get_pull_request.return_value = mock_pr
    mock_file = Mock()
    mock_file.filename = f"{mock_settings.repository_root.name}/src/warrant/main.py"
    service.github.get_pull_request_files.return_value = [mock_file]
    service.github.get_pull_request_checks.return_value = []

    result = service.create_review_session(
        workspace_id, actor_id, "owner", "repo", 1, "WEB-4519", "api"
    )

    session = mock_db.one("SELECT * FROM coding_sessions WHERE id=?", (result["session_id"],))
    payload = json.loads(session["result_json"])
    assert payload["governance"]["changed_files"] == ["src/warrant/main.py"]
    assert payload["governance"]["outside_scope_files"] == []


def test_create_review_session_success(service, mock_db, mock_provider, mock_settings):
    workspace_id = mock_settings.workspace_id
    actor_id = "user-1"
    
    mock_db.execute(
        "INSERT INTO delegations (id, workspace_id, issue_id, status, requester_id, "
        "created_at, target_agent_id, source, delivery_id, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "delegation-1",
            workspace_id,
            "issue-web-4519",
            "active",
            "user-1",
            "2023-01-01T00:00:00Z",
            "agent-1",
            "ui",
            "del-1",
            "2023-01-01T00:00:00Z",
        ),
    )
    
    mock_db.execute(
        "INSERT INTO warrants (id, workspace_id, delegation_id, agent_id, authority_user_id, "
        "scope_json, allowed_tools_json, denied_tools_json, evidence_contract_json, "
        "nonce_hash, issued_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "warrant-1",
            workspace_id,
            "delegation-1",
            "agent-1",
            "user-1",
            "{}",
            "[]",
            "[]",
            "{}",
            "hash",
            "2023-01-01T00:00:00Z",
            "2024-01-01T00:00:00Z",
        ),
    )
    
    mock_pr = Mock()
    mock_pr.head_sha = "abcdef"
    mock_pr.base_ref = "main"
    service.github.get_pull_request.return_value = mock_pr
    service.github.get_pull_request_files.return_value = []
    service.github.get_pull_request_checks.return_value = []
    
    result = service.create_review_session(
        workspace_id, actor_id, "owner", "repo", 1, "WEB-4519", "api"
    )
    
    assert result["session_id"].startswith("ses_")
    session = mock_db.one("SELECT * FROM coding_sessions WHERE id=?", (result["session_id"],))
    assert session is not None
    assert session["session_kind"] == "github_pr_review"
