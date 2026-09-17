"""A coding session can name its own GitHub repository instead of REPOSITORY_ROOT.

The unit tests in `tests/unit/test_repo_source.py` cover the URL parser and the clone
helper in isolation. These cover the part that was actually missing before: whether the
*session* ends up running against the repository it was asked for, and whether the feature
is properly gated when it is off.

No test here reaches the network. `RepositorySource.authenticated_url` is redirected at a
local Git repository on disk, which `git clone` treats exactly like any other remote.
"""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Sibling test module, imported by name: `tests/integration` has no `__init__.py`, which is
# this suite's existing convention, so pytest puts the directory itself on `sys.path`.
from test_coding_sessions import (  # noqa: E402 - see above
    create_delegation,
    git,
    wait_for_terminal,
)

from warrant.main import create_app
from warrant.repo_source import RepositorySource
from warrant.seed import reset_and_seed


def _origin(tmp_path: Path) -> Path:
    """A real Git remote carrying the surfaces the seeded WEB-* warrants scope."""
    repo = tmp_path / "origin"
    for relative, body in (
        ("web/reports/EmptyState.tsx", "export const emptyState = 'No activity';\n"),
        ("web/reports/Table.tsx", "export const PAGE_SIZE = 25;\n"),
    ):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.test")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    return repo


def _configured_checkout(tmp_path: Path) -> Path:
    """A different, deliberately empty checkout, so REPOSITORY_ROOT cannot satisfy a scope.

    If a session silently fell back to the configured repository, the scope preflight here
    would refuse it -- which makes "it ran at all" evidence that it used the clone.
    """
    repo = tmp_path / "configured"
    repo.mkdir()
    (repo / "UNRELATED.md").write_text("not the repository under test\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.test")
    git(repo, "config", "user.name", "Test")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "unrelated")
    return repo


def _app(client, tmp_path, **overrides) -> TestClient:
    settings = replace(
        client.app.state.settings,
        database_path=tmp_path / "selection.db",
        repository_root=_configured_checkout(tmp_path),
        coding_session_root=tmp_path / "runtime",
        repository_clone_root=tmp_path / "clones",
        verification_command=("git", "diff", "--check"),
        external_coding_agent_enabled=False,
        **overrides,
    )
    reset_and_seed(settings)
    return TestClient(create_app(settings))


@pytest.fixture
def local_remote(tmp_path, monkeypatch):
    origin = _origin(tmp_path)
    monkeypatch.setattr(
        RepositorySource, "authenticated_url", lambda self, token: str(origin), raising=True
    )
    return origin


def test_a_session_runs_against_the_repository_it_named_not_the_configured_one(
    client, headers, tmp_path, local_remote
):
    app = _app(client, tmp_path, repository_clone_enabled=True)
    delegation = create_delegation(app, headers, "WEB-4519", "chirayu-gupta", "clone-allow")

    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={
            "delegation_id": delegation["id"],
            "provider": "mock",
            "source": "api",
            "repository_url": "pmohekar-gif/FDE-Assignment-3",
        },
    )

    assert started.status_code == 202
    session = wait_for_terminal(app, started.json()["id"])
    assert session["state"] == "COMPLETED"
    clone = tmp_path / "clones" / "pmohekar-gif" / "FDE-Assignment-3"
    assert Path(session["repository_root"]) == clone.resolve()
    assert Path(session["repository_root"]) != app.app.state.settings.repository_root
    assert session["diff"]["changed_files"][0]["path"] == "web/reports/EmptyState.tsx"
    # The record says which repository the work happened in and how fresh it was.
    resolved = [e for e in session["events"] if e["event_type"] == "repository_resolved"]
    assert len(resolved) == 1
    assert resolved[0]["payload"]["cloned"] is True
    assert resolved[0]["payload"]["authenticated"] is False


def test_the_branch_and_worktree_are_created_in_the_clone_leaving_the_remote_untouched(
    client, headers, tmp_path, local_remote
):
    app = _app(client, tmp_path, repository_clone_enabled=True)
    delegation = create_delegation(app, headers, "WEB-4519", "chirayu-gupta", "clone-isolation")

    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={
            "delegation_id": delegation["id"],
            "provider": "mock",
            "source": "api",
            "repository_url": "https://github.com/pmohekar-gif/FDE-Assignment-3.git",
        },
    )
    session = wait_for_terminal(app, started.json()["id"])

    assert session["state"] == "COMPLETED"
    branches = subprocess.run(
        ["git", "branch", "--list", session["branch_name"]],
        cwd=local_remote,
        capture_output=True,
        text=True,
    ).stdout
    assert branches.strip() == "", "the agent's branch must not appear on the remote"
    assert (
        "Simulated coding-agent output"
        not in (local_remote / "web" / "reports" / "EmptyState.tsx").read_text()
    )


def test_a_second_session_reuses_the_clone_rather_than_cloning_again(
    client, headers, tmp_path, local_remote
):
    app = _app(client, tmp_path, repository_clone_enabled=True)
    # Two *different* issues on non-overlapping surfaces. Reusing one issue would be
    # refused by the concurrent-overlapping-scope rule before it ever reached the clone,
    # so the test would pass for the wrong reason.
    for index, (issue, key) in enumerate(
        (("WEB-4519", "clone-first"), ("WEB-3001", "clone-second"))
    ):
        delegation = create_delegation(app, headers, issue, "chirayu-gupta", key)
        started = app.post(
            "/v1/coding-sessions",
            headers=headers,
            json={
                "delegation_id": delegation["id"],
                "provider": "mock",
                "source": "api",
                "repository_url": "pmohekar-gif/FDE-Assignment-3",
            },
        )
        assert started.status_code == 202, started.json()
        session = wait_for_terminal(app, started.json()["id"])
        assert session["state"] == "COMPLETED"
        resolved = [e for e in session["events"] if e["event_type"] == "repository_resolved"][0]
        assert resolved["payload"]["cloned"] is (index == 0)


def test_the_feature_flag_gates_it_and_the_refusal_names_the_setting(
    client, headers, tmp_path, local_remote
):
    app = _app(client, tmp_path, repository_clone_enabled=False)
    delegation = create_delegation(app, headers, "WEB-4519", "chirayu-gupta", "clone-disabled")

    refused = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={
            "delegation_id": delegation["id"],
            "provider": "mock",
            "source": "api",
            "repository_url": "pmohekar-gif/FDE-Assignment-3",
        },
    )

    assert refused.status_code == 403
    assert "REPOSITORY_CLONE_ENABLED" in refused.json()["error"]
    assert not (tmp_path / "clones").exists(), "a disabled feature must not clone anything"


@pytest.mark.parametrize(
    "hostile",
    [
        "https://gitlab.com/owner/repo",
        "https://user:ghp_secret@github.com/owner/repo",
        "-upload-pack/repo",
        "not a repository",
    ],
)
def test_a_hostile_repository_url_is_a_request_error_not_a_server_error(
    client, headers, tmp_path, local_remote, hostile
):
    """400, not 503: the caller must supply something different, and a 503 would blame the
    configured checkout for a problem with the request."""
    app = _app(client, tmp_path, repository_clone_enabled=True)
    delegation = create_delegation(
        app, headers, "WEB-4519", "chirayu-gupta", f"bad-{hash(hostile)}"
    )

    refused = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={
            "delegation_id": delegation["id"],
            "provider": "mock",
            "source": "api",
            "repository_url": hostile,
        },
    )

    assert refused.status_code == 400, refused.json()
    assert refused.json()["type"] == "RepositoryCloneError"


def test_omitting_the_url_still_uses_the_configured_checkout(client, headers, tmp_path):
    """The behaviour that existed before this feature is the behaviour with no URL."""
    app = _app(client, tmp_path, repository_clone_enabled=True)
    capabilities = app.get("/v1/coding-sessions/capabilities").json()

    assert capabilities["repository_selection"]["enabled"] is True
    assert capabilities["git_checkout"]["root"] == str(
        app.app.state.settings.repository_root
    )
