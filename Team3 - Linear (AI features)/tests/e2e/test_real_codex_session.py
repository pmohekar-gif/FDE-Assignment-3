from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from warrant.main import create_app
from warrant.seed import reset_and_seed


@pytest.mark.skipif(
    os.getenv("RUN_REAL_CODEX") != "1" or not shutil.which("codex"),
    reason="explicit real Codex smoke test is disabled or Codex is unavailable",
)
def test_real_codex_executes_in_isolated_worktree_and_returns_verified_diff(client, tmp_path):
    repository = tmp_path / "real-codex-target"
    target = repository / "web" / "reports" / "EmptyState.tsx"
    target.parent.mkdir(parents=True)
    target.write_text("export const emptyState = 'No activity';\n")
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=repository, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repository, check=True)
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repository, check=True)
    settings = replace(
        client.app.state.settings,
        database_path=tmp_path / "real-codex.db",
        repository_root=repository,
        coding_session_root=tmp_path / "real-runtime",
        verification_command=("git", "diff", "--check"),
        external_coding_agent_enabled=True,
        coding_agent_provider="codex",
        coding_agent_timeout_seconds=180,
    )
    reset_and_seed(settings)
    app = TestClient(create_app(settings))
    headers = {"X-CSRF-Token": settings.csrf_token}
    delegation = app.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": "WEB-4519",
            "requester_id": "lead-web",
            "target_agent_id": "codex-cloud",
            "idempotency_key": "real-codex-e2e",
        },
    ).json()
    started = app.post(
        "/v1/coding-sessions",
        headers=headers,
        json={
            "delegation_id": delegation["id"],
            "provider": "codex",
            "source": "api",
            "requested_outcome": (
                "Change web/reports/EmptyState.tsx so emptyState is exactly "
                "'Create your first report'. Change no other file."
            ),
        },
    )
    assert started.status_code == 202
    session_id = started.json()["id"]
    for _ in range(400):
        session = app.get(f"/v1/coding-sessions/{session_id}").json()
        if session["state"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            break
        time.sleep(0.5)
    else:
        raise AssertionError("real Codex session did not complete")
    assert session["state"] == "COMPLETED", session.get("error")
    assert session["provider_kind"] == "real"
    assert session["result"]["verification"]["passed"] is True
    assert [item["path"] for item in session["diff"]["changed_files"]] == [
        "web/reports/EmptyState.tsx"
    ]
    assert "Create your first report" in session["diff"]["unified_diff"]
    assert target.read_text() == "export const emptyState = 'No activity';\n"
