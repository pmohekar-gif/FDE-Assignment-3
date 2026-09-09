import sqlite3

import pytest

from warrant.db import Database


def _insert_session(
    db: Database,
    session_id: str,
    *,
    delegation_id: str | None = None,
    warrant_id: str | None = None,
    session_kind: str = "github_pr_review",
) -> None:
    db.execute(
        "INSERT INTO coding_sessions ("
        "id, workspace_id, delegation_id, warrant_id, issue_id, requester_id, source, "
        "provider, state, repository_root, base_revision, contract_json, created_at, "
        "session_kind"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            "ws_1",
            delegation_id,
            warrant_id,
            "iss_1",
            "usr_1",
            "system",
            "dummy",
            "COMPLETED",
            "/repo",
            "main",
            "{}",
            "2024-01-01T00:00:00Z",
            session_kind,
        ),
    )


def test_coding_session_contract_is_immutable(tmp_path):
    """The coding-session execution contract remains immutable after migration."""
    db = Database(tmp_path / "test.sqlite3")
    db.migrate()
    _insert_session(db, "ses_1")

    with pytest.raises(
        sqlite3.IntegrityError,
        match="coding-session execution contract is immutable",
    ):
        db.execute(
            "UPDATE coding_sessions SET contract_json = ? WHERE id = ?",
            ('{"mutated": true}', "ses_1"),
        )

    db.execute("UPDATE coding_sessions SET state = 'FAILED' WHERE id = 'ses_1'")
    row = db.one("SELECT state, contract_json FROM coding_sessions WHERE id = 'ses_1'")
    assert row == {"state": "FAILED", "contract_json": "{}"}


def test_agent_execution_warrant_unique_but_pr_reviews_can_share(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.migrate()

    index = db.one(
        "SELECT sql FROM sqlite_master WHERE type='index' "
        "AND name='idx_coding_sessions_unique_agent_warrant'"
    )
    assert index is not None
    assert "session_kind='agent_execution'" in index["sql"]

    _insert_session(
        db,
        "ses_agent_1",
        delegation_id="dlg_1",
        warrant_id="war_1",
        session_kind="agent_execution",
    )
    with pytest.raises(sqlite3.IntegrityError):
        _insert_session(
            db,
            "ses_agent_2",
            delegation_id="dlg_1",
            warrant_id="war_1",
            session_kind="agent_execution",
        )

    _insert_session(
        db,
        "ses_review_1",
        delegation_id="dlg_1",
        warrant_id="war_1",
        session_kind="github_pr_review",
    )
    _insert_session(
        db,
        "ses_review_2",
        delegation_id="dlg_1",
        warrant_id="war_1",
        session_kind="github_pr_review",
    )


def test_agent_execution_requires_real_delegation_and_warrant_ids(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.migrate()

    with pytest.raises(sqlite3.IntegrityError):
        _insert_session(db, "ses_bad", session_kind="agent_execution")


def test_old_strict_coding_sessions_schema_migrates(tmp_path):
    db = Database(tmp_path / "legacy.sqlite3")
    with db.connect() as connection:
        connection.executescript(
            """
            CREATE TABLE coding_sessions (
              id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, delegation_id TEXT NOT NULL,
              warrant_id TEXT NOT NULL, issue_id TEXT NOT NULL, requester_id TEXT NOT NULL,
              source TEXT NOT NULL, provider TEXT NOT NULL, state TEXT NOT NULL,
              repository_root TEXT NOT NULL, base_revision TEXT NOT NULL, branch_name TEXT,
              worktree_path TEXT, contract_json TEXT NOT NULL, result_json TEXT,
              error TEXT, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
              agent_pid INTEGER, host_pid INTEGER, worktree_removed_at TEXT,
              UNIQUE(warrant_id)
            );
            INSERT INTO coding_sessions (
              id, workspace_id, delegation_id, warrant_id, issue_id, requester_id, source,
              provider, state, repository_root, base_revision, contract_json, created_at
            ) VALUES (
              'ses_legacy', 'ws_1', 'dlg_1', 'war_1', 'iss_1', 'usr_1', 'ui',
              'mock', 'COMPLETED', '/repo', 'main', '{}', '2024-01-01T00:00:00Z'
            );
            """
        )

    db.migrate()

    columns = {
        row["name"]: row
        for row in db.all("PRAGMA table_info(coding_sessions)")
    }
    assert columns["delegation_id"]["notnull"] == 0
    assert columns["warrant_id"]["notnull"] == 0
    assert columns["session_kind"]["dflt_value"] == "'agent_execution'"
    assert db.one("SELECT session_kind FROM coding_sessions WHERE id='ses_legacy'") == {
        "session_kind": "agent_execution"
    }

    with pytest.raises(
        sqlite3.IntegrityError,
        match="coding-session execution contract is immutable",
    ):
        db.execute(
            "UPDATE coding_sessions SET contract_json = ? WHERE id = ?",
            ('{"mutated": true}', "ses_legacy"),
        )

    with pytest.raises(sqlite3.IntegrityError):
        _insert_session(
            db,
            "ses_agent_duplicate",
            delegation_id="dlg_1",
            warrant_id="war_1",
            session_kind="agent_execution",
        )
    _insert_session(
        db,
        "ses_review_after_migration",
        delegation_id="dlg_1",
        warrant_id="war_1",
        session_kind="github_pr_review",
    )
