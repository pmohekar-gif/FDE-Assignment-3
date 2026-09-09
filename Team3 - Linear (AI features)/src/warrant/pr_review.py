import fnmatch
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from .adapters.github import GitHubAdapter
from .audit import AuditLedger
from .config import Settings
from .db import Database
from .providers import LLMProvider
from .service import Conflict, Forbidden, NotFound

log = logging.getLogger(__name__)


class GitHubPRReviewService:
    def __init__(self, settings: Settings, db: Database, provider: LLMProvider) -> None:
        self.settings = settings
        self.db = db
        self.provider = provider
        self.github = GitHubAdapter(settings)

    def _normalize_pr_filename(self, filename: str) -> str:
        """Normalize GitHub repo-root paths to this Warrant checkout's project root.

        GitHub reports paths relative to the repository root. In this assignment repo,
        the Warrant app lives under a top-level directory like
        `Team3 - Linear (AI features)/`, while Warrant scopes are written relative to
        `REPOSITORY_ROOT` inside that directory. Strip only that configured root
        basename so `Team3 - Linear (AI features)/src/warrant/main.py` can match
        `src/**`.
        """
        normalized = filename.strip().lstrip("/")
        root_name = self.settings.repository_root.name
        prefix = f"{root_name}/" if root_name else ""
        if prefix and normalized.startswith(prefix):
            return normalized[len(prefix) :]
        return normalized

    def link_pr_to_issue(
        self,
        workspace_id: str,
        actor_id: str,
        owner: str,
        repo: str,
        pull_request_number: int,
        issue_ref: str,
    ) -> dict[str, Any]:
        issue = self.db.one(
            "SELECT id FROM issues WHERE external_key=? AND workspace_id=?",
            (issue_ref, workspace_id),
        )
        if not issue:
            raise NotFound(f"Issue {issue_ref} not found in workspace")

        pr = self.github.get_pull_request(owner, repo, pull_request_number)

        # Check existing
        existing = self.db.one(
            "SELECT id, issue_id FROM github_pr_links WHERE workspace_id=? AND owner=? "
            "AND repo=? AND pull_request_number=?",
            (workspace_id, owner, repo, pull_request_number),
        )

        now = datetime.now(timezone.utc).isoformat()

        created = False
        if not existing:
            created = True
            link_id = f"link_{uuid.uuid4().hex[:12]}"
            self.db.execute(
                "INSERT INTO github_pr_links (id, workspace_id, issue_id, owner, repo, "
                "pull_request_number, pr_url, head_sha, selected_by, selected_at, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    link_id,
                    workspace_id,
                    issue["id"],
                    owner,
                    repo,
                    pull_request_number,
                    pr.html_url,
                    pr.head_sha,
                    actor_id,
                    now,
                    self.github.source,
                ),
            )

            payload = {
                "owner": owner,
                "repo": repo,
                "pull_request_number": pull_request_number,
                "issue_ref": issue_ref,
                "head_sha": pr.head_sha,
            }

            ledger = AuditLedger(self.db)
            ledger.append(
                workspace_id=workspace_id,
                event_type="github_pr_linked_to_issue",
                actor_type="user",
                actor_id=actor_id,
                subject_type="github_pr_link",
                subject_id=link_id,
                payload=payload,
            )
        else:
            if existing["issue_id"] != issue["id"]:
                raise Conflict(
                    f"PR {owner}/{repo}#{pull_request_number} is already linked "
                    "to a different issue."
                )
            link_id = existing["id"]

        return {"status": "ok", "issue_id": issue["id"], "link_id": link_id, "created": created}

    def create_review_session(
        self,
        workspace_id: str,
        actor_id: str,
        owner: str,
        repo: str,
        pull_request_number: int,
        issue_ref: str,
        source: str,
    ) -> dict[str, Any]:
        if not self.settings.github_pr_review_enabled:
            raise Forbidden("GitHub PR review is disabled")

        if self.settings.github_mode not in {"stub", "live"}:
            raise Forbidden("GitHub adapter is not configured")

        issue = self.db.one(
            "SELECT id, title, body_normalised, external_key FROM issues "
            "WHERE external_key=? AND workspace_id=?",
            (issue_ref, workspace_id),
        )
        if not issue:
            raise NotFound(f"Issue {issue_ref} not found in workspace")

        pr = self.github.get_pull_request(owner, repo, pull_request_number)
        files = self.github.get_pull_request_files(owner, repo, pull_request_number, limit=100)
        file_paths = [
            (file.filename, self._normalize_pr_filename(file.filename)) for file in files
        ]
        checks = self.github.get_pull_request_checks(owner, repo, pr.head_sha, limit=100)

        # 1. Governance checks
        authorization_gap = True
        warrant_id = None
        delegation_id = None
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()

        outside_scope_files: list[str] = []
        allowed_paths: list[str] = []
        scope_evaluated = False
        scope_configuration_error = False
        protected_surface_matches: list[dict[str, Any]] = []

        surface_rows = self.db.all(
            "SELECT glob, label, protected, security_sensitive FROM surfaces WHERE workspace_id=?",
            (workspace_id,),
        )
        for raw_path, normalized_path in file_paths:
            for surface in surface_rows:
                if (
                    fnmatch.fnmatch(normalized_path, surface["glob"])
                    or fnmatch.fnmatch(raw_path, surface["glob"])
                ) and (surface["protected"] or surface["security_sensitive"]):
                    protected_surface_matches.append(
                        {
                            "path": normalized_path,
                            "original_path": raw_path,
                            "glob": surface["glob"],
                            "label": surface["label"],
                            "protected": bool(surface["protected"]),
                            "security_sensitive": bool(surface["security_sensitive"]),
                        }
                    )

        warrant_status = "missing"
        consumed_warrant = False

        delegation = self.db.one(
            "SELECT id FROM delegations WHERE issue_id=? ORDER BY created_at DESC LIMIT 1",
            (issue["id"],),
        )
        if delegation:
            delegation_id = delegation["id"]
            warrant = self.db.one(
                "SELECT id, revoked_at, expires_at, evidence_contract_json, scope_json "
                "FROM warrants WHERE delegation_id=? ORDER BY issued_at DESC LIMIT 1",
                (delegation_id,),
            )
            if warrant:
                warrant_id = warrant["id"]
                expired = False
                warrant_status = "valid"
                if warrant["expires_at"]:
                    try:
                        exp_str = warrant["expires_at"].replace("Z", "+00:00")
                        exp_dt = datetime.fromisoformat(exp_str)
                        if exp_dt <= now_dt:
                            expired = True
                            warrant_status = "expired"
                    except ValueError:
                        pass
                
                if warrant["revoked_at"] is not None:
                    warrant_status = "revoked"

                consumed_session = self.db.one(
                    "SELECT id FROM coding_sessions "
                    "WHERE warrant_id=? AND session_kind='agent_execution'",
                    (warrant_id,),
                )
                if consumed_session:
                    consumed_warrant = True

                if warrant["revoked_at"] is None and not expired:
                    authorization_gap = False

                    # File scope check
                    try:
                        scope = json.loads(warrant["scope_json"])
                        # scope could be a list (normal) or dict
                        if isinstance(scope, list):
                            allowed_paths = scope
                        elif isinstance(scope, dict):
                            allowed_paths = scope.get("allowed_paths", [])
                        else:
                            allowed_paths = []

                        if not (
                            isinstance(allowed_paths, list)
                            and allowed_paths
                            and all(isinstance(path, str) and path for path in allowed_paths)
                        ):
                            scope_configuration_error = True
                            outside_scope_files = [normalized for _, normalized in file_paths]
                        else:
                            scope_evaluated = True
                            for raw_path, normalized_path in file_paths:
                                matched = any(
                                    fnmatch.fnmatch(normalized_path, pattern)
                                    or fnmatch.fnmatch(raw_path, pattern)
                                    for pattern in allowed_paths
                                )
                                if not matched:
                                    outside_scope_files.append(normalized_path)
                    except (ValueError, TypeError):
                        scope_configuration_error = True
                        outside_scope_files = [normalized for _, normalized in file_paths]

        checks_failed = any(
            c.conclusion in {"failure", "timed_out", "action_required"} for c in checks
        )
        checks_pending = any(c.status != "completed" for c in checks)

        if not checks:
            checks_state = "none_found"
            checks_failed = False
        else:
            if checks_failed:
                checks_state = "failed"
            elif checks_pending:
                checks_state = "pending"
            else:
                checks_state = "passed"

        scope_violation = bool(outside_scope_files) or scope_configuration_error
        if checks_failed or scope_violation:
            verdict = "FAIL"
        elif authorization_gap:
            verdict = "INCONCLUSIVE"
        elif checks_state in {"none_found", "pending"} or protected_surface_matches:
            verdict = "PASS_WITH_EXCEPTIONS"
        else:
            verdict = "PASS"

        # 2. AI Alignment Check (Deterministic for MVP)
        alignment_verdict = "INCONCLUSIVE"
        alignment_criteria: list[str] = []
        alignment_summary = (
            "AI alignment check skipped or inconclusive. "
            "A safe, bounded diff redaction pathway is required."
        )

        if authorization_gap:
            alignment_summary = "No valid Warrant authorization was found for this PR."
        elif scope_violation:
            alignment_summary = "PR changes files outside the Warrant scope."

        # 3. Create Session
        session_id = f"ses_{uuid.uuid4().hex[:12]}"

        contract_json = json.dumps({
            "pr_review": {
                "owner": owner,
                "repo": repo,
                "pull_request_number": pull_request_number,
                "issue_ref": issue_ref,
            }
        })

        human_review_checklist: list[str] = []
        if authorization_gap:
            human_review_checklist.append("No valid Warrant authorization was found")
        if scope_violation:
            human_review_checklist.append("PR changes files outside the Warrant scope")
        if protected_surface_matches:
            human_review_checklist.append(
                "Verify protected or security-sensitive surfaces changed by the PR"
            )
        if checks_state in ("failed", "none_found", "pending"):
            human_review_checklist.append("Verify CI/CD checks have passed")
        if consumed_warrant:
            human_review_checklist.append("Verify this PR belongs to the consumed agent session")

        result_json = json.dumps({
            "pre_authorized": not authorization_gap,
            "governance": {
                "verdict": verdict,
                "gap": authorization_gap,
                "scope_violation": scope_violation,
                "scope_evaluated": scope_evaluated,
                "scope_configuration_error": scope_configuration_error,
                "warrant_status": warrant_status,
                "consumed_warrant": consumed_warrant,
                "outside_scope_files": outside_scope_files,
                "changed_files": [normalized_path for _, normalized_path in file_paths],
                "original_changed_files": [raw_path for raw_path, _ in file_paths],
                "allowed_scope": allowed_paths,
                "checks_state": checks_state,
                "protected_surfaces_detected": bool(protected_surface_matches),
                "protected_surface_matches": protected_surface_matches,
                "human_review_required": bool(
                    authorization_gap
                    or scope_violation
                    or checks_failed
                    or checks_state in {"none_found", "pending"}
                    or protected_surface_matches
                ),
                "human_review_checklist": human_review_checklist,
            },
            "alignment": {
                "verdict": alignment_verdict,
                "criteria": alignment_criteria,
                "summary": alignment_summary,
            },
        })

        self.db.execute(
            "INSERT INTO coding_sessions ("
            "id, workspace_id, delegation_id, warrant_id, issue_id, requester_id, source, "
            "provider, state, repository_root, base_revision, contract_json, result_json, "
            "created_at, started_at, finished_at, session_kind"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                workspace_id,
                delegation_id,
                warrant_id,
                issue["id"],
                actor_id,
                source,
                "github-pr-review",
                "COMPLETED",
                str(self.settings.repository_root),
                pr.base_ref,
                contract_json,
                result_json,
                now,
                now,
                now,
                "github_pr_review",
            ),
        )
        
        # Log audit events
        ledger = AuditLedger(self.db)
        ledger.append(
            workspace_id=workspace_id,
            event_type="github_pr_review_started",
            actor_type="user",
            actor_id=actor_id,
            subject_type="coding_session",
            subject_id=session_id,
            payload={"session_kind": "github_pr_review", "issue_id": issue["id"]},
        )
        ledger.append(
            workspace_id=workspace_id,
            event_type="github_pr_review_completed",
            actor_type="user",
            actor_id=actor_id,
            subject_type="coding_session",
            subject_id=session_id,
            payload={"governance_gap": authorization_gap, "checks_failed": checks_failed},
        )

        return {"session_id": session_id}
