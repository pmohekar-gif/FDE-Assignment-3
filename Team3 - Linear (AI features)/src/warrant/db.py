from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS workspaces (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, policy_version_active TEXT NOT NULL,
  settings_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, display_name TEXT NOT NULL,
  role TEXT NOT NULL, code_owner_paths_json TEXT NOT NULL DEFAULT '[]',
  FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);
CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, name TEXT NOT NULL, vendor TEXT NOT NULL,
  status TEXT NOT NULL, verified_pass_rate REAL NOT NULL DEFAULT 0,
  FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);
CREATE TABLE IF NOT EXISTS issues (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, external_key TEXT NOT NULL,
  title TEXT NOT NULL, body_normalised TEXT NOT NULL, team TEXT NOT NULL,
  labels_json TEXT NOT NULL DEFAULT '[]', path_hints_json TEXT NOT NULL DEFAULT '[]',
  priority TEXT NOT NULL DEFAULT 'medium',
  revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL,
  demo_note TEXT NOT NULL DEFAULT '', is_demo_path INTEGER NOT NULL DEFAULT 0,
  UNIQUE(workspace_id, external_key), FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS issues_fts USING fts5(
  issue_id UNINDEXED, workspace_id UNINDEXED, title, body, tokenize='porter unicode61'
);
CREATE TABLE IF NOT EXISTS surfaces (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, glob TEXT NOT NULL, label TEXT NOT NULL,
  protected INTEGER NOT NULL, irreversible INTEGER NOT NULL, security_sensitive INTEGER NOT NULL,
  data_classes_json TEXT NOT NULL, owner_ids_json TEXT NOT NULL,
  FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);
CREATE TABLE IF NOT EXISTS policies (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, version TEXT NOT NULL, sha256 TEXT NOT NULL,
  yaml_source TEXT NOT NULL, activated_at TEXT NOT NULL,
  UNIQUE(workspace_id, version), FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);
CREATE TABLE IF NOT EXISTS delegations (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, issue_id TEXT NOT NULL,
  requester_id TEXT NOT NULL,
  target_agent_id TEXT NOT NULL, source TEXT NOT NULL, delivery_id TEXT NOT NULL,
  untrusted_origin INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL, UNIQUE(workspace_id, delivery_id),
  FOREIGN KEY(workspace_id) REFERENCES workspaces(id), FOREIGN KEY(issue_id) REFERENCES issues(id)
);
CREATE TABLE IF NOT EXISTS retrieval_evidence (
  delegation_id TEXT PRIMARY KEY, mode TEXT NOT NULL, completeness REAL NOT NULL,
  candidates_json TEXT NOT NULL, overlaps_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extractions (
  delegation_id TEXT PRIMARY KEY, status TEXT NOT NULL, result_json TEXT,
  provider TEXT NOT NULL, model TEXT NOT NULL, prompt_hash TEXT NOT NULL,
  latency_ms INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extraction_cache (
  issue_id TEXT NOT NULL, issue_revision INTEGER NOT NULL, prompt_hash TEXT NOT NULL,
  result_json TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY(issue_id, issue_revision, prompt_hash)
);
CREATE TABLE IF NOT EXISTS risk_assessments (
  delegation_id TEXT PRIMARY KEY, result_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS policy_decisions (
  delegation_id TEXT PRIMARY KEY, result_json TEXT NOT NULL, decided_at TEXT NOT NULL,
  latency_ms INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY, delegation_id TEXT NOT NULL, approver_id TEXT NOT NULL,
  action TEXT NOT NULL, narrowed_scope_json TEXT NOT NULL, rationale TEXT,
  decided_at TEXT NOT NULL, UNIQUE(delegation_id)
);
CREATE TABLE IF NOT EXISTS warrants (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, delegation_id TEXT NOT NULL UNIQUE,
  agent_id TEXT NOT NULL, authority_user_id TEXT NOT NULL, scope_json TEXT NOT NULL,
  allowed_tools_json TEXT NOT NULL, denied_tools_json TEXT NOT NULL,
  evidence_contract_json TEXT NOT NULL, nonce_hash TEXT NOT NULL, nonce_plain_demo TEXT,
  issued_at TEXT NOT NULL, expires_at TEXT NOT NULL, consumed_at TEXT, revoked_at TEXT,
  expired_at TEXT, revoke_reason TEXT,
  FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);
CREATE TABLE IF NOT EXISTS evidence_bundles (
  id TEXT PRIMARY KEY, warrant_id TEXT NOT NULL UNIQUE, bundle_json TEXT NOT NULL,
  bundle_hash TEXT NOT NULL, submitted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verification_verdicts (
  bundle_id TEXT PRIMARY KEY, verdict TEXT NOT NULL, gate1_json TEXT NOT NULL,
  gate2_json TEXT, human_checks_json TEXT NOT NULL, provider TEXT,
  latency_ms INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, seq INTEGER NOT NULL,
  event_type TEXT NOT NULL, actor_type TEXT NOT NULL, actor_id TEXT NOT NULL,
  subject_type TEXT NOT NULL, subject_id TEXT NOT NULL, payload_json TEXT NOT NULL,
  prev_hash TEXT NOT NULL, hash TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(workspace_id, seq)
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END;
CREATE TABLE IF NOT EXISTS model_usage (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, delegation_id TEXT NOT NULL,
  operation TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
  input_tokens INTEGER, output_tokens INTEGER, estimated_cost_usd REAL,
  latency_ms INTEGER NOT NULL, success INTEGER NOT NULL, error_class TEXT,
  reasoning_tokens INTEGER, total_tokens INTEGER, reported_cost_usd REAL,
  serving_provider TEXT, structured_output_mode TEXT,
  schema_repair_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS telemetry_events (
  id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, name TEXT NOT NULL,
  subject_id TEXT, attributes_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS delegation_briefs (
  delegation_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, issue_revision INTEGER NOT NULL,
  facts_hash TEXT NOT NULL, prompt_hash TEXT NOT NULL, response_json TEXT NOT NULL,
  prose_source TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);
CREATE INDEX IF NOT EXISTS idx_delegations_workspace ON delegations(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_warrants_workspace ON warrants(workspace_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_audit_workspace ON audit_events(workspace_id, seq);
CREATE INDEX IF NOT EXISTS idx_telemetry_name ON telemetry_events(workspace_id, name);
CREATE INDEX IF NOT EXISTS idx_extraction_cache_issue ON extraction_cache(issue_id, issue_revision);
CREATE INDEX IF NOT EXISTS idx_briefs_workspace ON delegation_briefs(workspace_id, generated_at);
CREATE TABLE IF NOT EXISTS linear_issue_links (
  issue_id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  external_id TEXT NOT NULL,
  external_key TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'linear',
  url TEXT NOT NULL,
  external_created_at TEXT NOT NULL,
  description_sha256 TEXT NOT NULL,
  state TEXT NOT NULL,
  assignee TEXT,
  team_key TEXT NOT NULL,
  imported_at TEXT NOT NULL,
  FOREIGN KEY(issue_id) REFERENCES issues(id)
);
CREATE INDEX IF NOT EXISTS idx_linear_links_workspace
  ON linear_issue_links(workspace_id, external_key);
CREATE UNIQUE INDEX IF NOT EXISTS idx_linear_links_unique_external
  ON linear_issue_links(workspace_id, external_id);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def migrate(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(warrants)").fetchall()
            }
            for name in ("expired_at", "revoke_reason"):
                if name not in columns:
                    connection.execute(f"ALTER TABLE warrants ADD COLUMN {name} TEXT")
            issue_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(issues)").fetchall()
            }
            if "demo_note" not in issue_columns:
                connection.execute(
                    "ALTER TABLE issues ADD COLUMN demo_note TEXT NOT NULL DEFAULT ''"
                )
            if "is_demo_path" not in issue_columns:
                connection.execute(
                    "ALTER TABLE issues ADD COLUMN is_demo_path INTEGER NOT NULL DEFAULT 0"
                )
            if "priority" not in issue_columns:
                connection.execute(
                    "ALTER TABLE issues ADD COLUMN priority TEXT NOT NULL DEFAULT 'medium'"
                )
            usage_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(model_usage)").fetchall()
            }
            usage_additions = {
                "reasoning_tokens": "INTEGER",
                "total_tokens": "INTEGER",
                "reported_cost_usd": "REAL",
                "serving_provider": "TEXT",
                "structured_output_mode": "TEXT",
                "schema_repair_count": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, definition in usage_additions.items():
                if name not in usage_columns:
                    connection.execute(f"ALTER TABLE model_usage ADD COLUMN {name} {definition}")
            # linear_issue_links is created via SCHEMA above; no ALTER needed

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        with self.connect() as connection:
            connection.execute(sql, params)

    def one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(sql, params).fetchone()
            return dict(row) if row else None

    def all(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(sql, params).fetchall()]

    @staticmethod
    def dumps(value: Any) -> str:
        return json.dumps(value, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def loads(value: str | None, default: Any = None) -> Any:
        if value is None:
            return default
        return json.loads(value)
