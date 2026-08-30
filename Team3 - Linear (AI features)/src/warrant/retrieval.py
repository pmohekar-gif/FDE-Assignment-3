from __future__ import annotations

import fnmatch
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .db import Database
from .security import cosine, stable_vector


@dataclass(frozen=True)
class RetrievalResult:
    mode: str
    completeness: float
    candidates: list[dict[str, Any]]
    surfaces: list[dict[str, Any]]
    overlaps: list[dict[str, Any]]


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores


def titles_are_near_duplicates(left: str, right: str, threshold: float = 0.8) -> bool:
    """Treat case/punctuation variants and high-overlap titles as one visible result."""
    left_tokens = set(re.findall(r"[a-z0-9]+", left.lower()))
    right_tokens = set(re.findall(r"[a-z0-9]+", right.lower()))
    if not left_tokens or not right_tokens:
        return left.strip().lower() == right.strip().lower()
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens) >= threshold


class RetrievalService:
    def __init__(self, db: Database, embeddings_available: bool = True):
        self.db = db
        self.embeddings_available = embeddings_available
        self.embedding_failures: deque[float] = deque()
        self.embedding_circuit_open_until = 0.0

    def _record_embedding_failure(self) -> None:
        now = time.monotonic()
        self.embedding_failures.append(now)
        while self.embedding_failures and now - self.embedding_failures[0] > 60:
            self.embedding_failures.popleft()
        if len(self.embedding_failures) >= 3:
            self.embedding_circuit_open_until = now + 60

    @property
    def embedding_circuit_open(self) -> bool:
        return time.monotonic() < self.embedding_circuit_open_until

    def retrieve(self, workspace_id: str, issue: dict[str, Any], top_k: int = 8) -> RetrievalResult:
        query_text = f"{issue['title']} {issue['body_normalised']}"
        terms = re.findall(r"[a-z0-9]{3,}", query_text.lower())[:12]
        lexical_ids: list[str] = []
        if terms:
            match = " OR ".join(f'"{term}"' for term in terms)
            try:
                rows = self.db.all(
                    "SELECT f.issue_id, bm25(issues_fts) AS score FROM issues_fts f "
                    "JOIN issues i ON i.id=f.issue_id "
                    "WHERE f.workspace_id=? AND i.team=? AND issues_fts MATCH ? "
                    "ORDER BY score LIMIT 20",
                    (workspace_id, issue["team"], match),
                )
                lexical_ids = [row["issue_id"] for row in rows if row["issue_id"] != issue["id"]]
            except Exception:
                lexical_ids = []

        # Team is a hard metadata filter before either ranking strategy. Cross-team
        # records are useful only when explicitly modelled as precedents, not as
        # accidental lexical neighbours.
        all_issues = self.db.all(
            "SELECT id,title,body_normalised,external_key,team FROM issues "
            "WHERE workspace_id=? AND id<>? AND team=?",
            (workspace_id, issue["id"], issue["team"]),
        )
        semantic_ids: list[str] = []
        semantic_scores: dict[str, float] = {}
        mode, completeness = "HYBRID", 1.0
        if self.embeddings_available and not self.embedding_circuit_open:
            try:
                query_vector = stable_vector(query_text)
                ranked = sorted(
                    all_issues,
                    key=lambda row: cosine(
                        query_vector, stable_vector(f"{row['title']} {row['body_normalised']}")
                    ),
                    reverse=True,
                )
                semantic_ids = [row["id"] for row in ranked[:20]]
                semantic_scores = {
                    row["id"]: cosine(
                        query_vector, stable_vector(f"{row['title']} {row['body_normalised']}")
                    )
                    for row in ranked[:20]
                }
                self.embedding_failures.clear()
            except Exception:
                self._record_embedding_failure()
                mode, completeness = "LEXICAL_ONLY", 0.5
        else:
            mode, completeness = "LEXICAL_ONLY", 0.5

        fused = reciprocal_rank_fusion([lexical_ids, semantic_ids])
        by_id = {row["id"]: row for row in all_issues}
        candidate_ids = [
            item_id
            for item_id in sorted(fused, key=lambda value: fused[value], reverse=True)
            if item_id in by_id
        ]
        candidates: list[dict[str, Any]] = []
        for item_id in candidate_ids:
            row = by_id[item_id]
            if any(
                titles_are_near_duplicates(row["title"], candidate["title"])
                for candidate in candidates
            ):
                continue
            candidates.append(
                {
                    "issue_id": item_id,
                    "external_key": row["external_key"],
                    "title": row["title"],
                    "team": row["team"],
                    "rrf_score": round(fused[item_id], 5),
                    "semantic_score": round(semantic_scores.get(item_id, 0), 3),
                    "why": "shared issue language and affected domain",
                    "kind": "similar_issue",
                }
            )
            if len(candidates) >= top_k:
                break

        precedents = self.db.all(
            "SELECT d.id AS delegation_id,i.external_key,i.title,i.team,p.result_json "
            "FROM delegations d JOIN issues i ON i.id=d.issue_id "
            "JOIN policy_decisions p ON p.delegation_id=d.id "
            "WHERE d.workspace_id=? AND i.team=? AND i.id<>? "
            "ORDER BY d.updated_at DESC LIMIT 3",
            (workspace_id, issue["team"], issue["id"]),
        )
        for precedent in precedents:
            decision = Database.loads(precedent["result_json"], {})
            if any(
                titles_are_near_duplicates(precedent["title"], candidate["title"])
                for candidate in candidates
            ):
                continue
            candidates.append(
                {
                    "issue_id": precedent["external_key"],
                    "external_key": precedent["external_key"],
                    "title": precedent["title"],
                    "team": precedent["team"],
                    "rrf_score": 0,
                    "semantic_score": 0,
                    "why": f"prior deterministic {decision.get('verdict', 'UNKNOWN')} decision",
                    "kind": "policy_precedent",
                    "delegation_id": precedent["delegation_id"],
                }
            )

        surfaces = self.db.all("SELECT * FROM surfaces WHERE workspace_id=?", (workspace_id,))
        hints = Database.loads(issue.get("path_hints_json"), [])
        matched = [
            {**surface, "data_classes": Database.loads(surface["data_classes_json"], [])}
            for surface in surfaces
            if any(fnmatch.fnmatch(hint, surface["glob"]) for hint in hints)
        ]
        overlaps = self.find_overlaps(workspace_id, hints)
        return RetrievalResult(mode, completeness, candidates, matched, overlaps)

    def find_overlaps(
        self, workspace_id: str, proposed_surfaces: list[str]
    ) -> list[dict[str, Any]]:
        """Resolve active scope conflicts from derived surfaces, not issue hints alone."""
        now = datetime.now(timezone.utc).isoformat()
        active = self.db.all(
            "SELECT id,scope_json,agent_id,expires_at FROM warrants "
            "WHERE workspace_id=? AND consumed_at IS NULL AND revoked_at IS NULL AND expires_at>?",
            (workspace_id, now),
        )
        overlaps: list[dict[str, Any]] = []
        for warrant in active:
            for held in Database.loads(warrant["scope_json"], []):
                if any(
                    fnmatch.fnmatch(surface, held) or fnmatch.fnmatch(held, surface)
                    for surface in proposed_surfaces
                ):
                    overlaps.append(
                        {
                            "warrant_id": warrant["id"],
                            "surface": held,
                            "agent_id": warrant["agent_id"],
                        }
                    )
        return overlaps
