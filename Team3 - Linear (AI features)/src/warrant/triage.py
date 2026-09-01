from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

from .db import Database
from .retrieval import RetrievalService

Priority = Literal["urgent", "high", "medium", "low"]


@dataclass(frozen=True)
class TriageRecommendation:
    issue: dict[str, Any]
    team: dict[str, Any]
    priority: dict[str, Any]
    labels: list[dict[str, Any]]
    retrieval: dict[str, Any]
    advisory_only: bool = True


class TriageRecommendationService:
    def __init__(self, db: Database, retrieval: RetrievalService):
        self.db = db
        self.retrieval = retrieval

    def recommend(self, workspace_id: str, issue_ref: str) -> TriageRecommendation | None:
        issue = self.db.one(
            "SELECT id,external_key,title,body_normalised,team,labels_json,priority,revision "
            "FROM issues WHERE workspace_id=? AND external_key=?",
            (workspace_id, issue_ref),
        )
        if issue is None:
            return None

        current_labels = Database.loads(issue["labels_json"], [])
        available_teams = [
            row["team"]
            for row in self.db.all(
                "SELECT DISTINCT team FROM issues WHERE workspace_id=? ORDER BY team",
                (workspace_id,),
            )
        ]
        query = f"{issue['title']} {issue['body_normalised']}"
        search = self.retrieval.search_issues(workspace_id, query, limit=15)
        neighbours = [item for item in search.results if item["issue_id"] != issue["id"]]

        team_scores: dict[str, float] = defaultdict(float)
        if issue["team"].lower() not in {"inbox", "untriaged", "unknown"}:
            team_scores[issue["team"]] += 2.0
        for rank, neighbour in enumerate(neighbours, start=1):
            team_scores[neighbour["team"]] += 1.0 / (rank + 2)
        ranked_teams = sorted(team_scores.items(), key=lambda item: item[1], reverse=True)
        total_team_score = sum(score for _, score in ranked_teams) or 1.0
        recommended_team, top_team_score = ranked_teams[0]
        alternatives = [
            {"team": team, "confidence": round(score / total_team_score, 3)}
            for team, score in ranked_teams[1:4]
        ]

        corpus = f"{issue['title']} {issue['body_normalised']}".lower()
        derived_labels: dict[str, tuple[float, str]] = {}

        def suggest(label: str, confidence: float, reason: str) -> None:
            existing = derived_labels.get(label)
            if existing is None or confidence > existing[0]:
                derived_labels[label] = (confidence, reason)

        if any(term in corpus for term in ("security", "signing key", "auth", "secret")):
            suggest("security", 0.95, "security-sensitive language in the issue")
        if any(term in corpus for term in ("urgent", "expired", "outage", "data loss")):
            suggest("urgent", 0.9, "time-critical or severe-impact language in the issue")
        if any(
            term in corpus
            for term in ("error", "incorrect", "duplicate", "missing", "stale", "timeout")
        ):
            suggest("bug", 0.82, "failure or incorrect-behaviour language in the issue")
        if any(term in corpus for term in ("customer", "double-charge", "another charge")):
            suggest("customer-impact", 0.92, "explicit customer or financial impact")
        if any(term in corpus for term in ("copy", "misleading", "unclear", "label")):
            suggest("copy", 0.8, "user-facing language or content change")

        for label in current_labels:
            if label not in {"synthetic", "small"}:
                suggest(label, 0.75, "already present on the issue")
        for neighbour in neighbours[:5]:
            row = self.db.one("SELECT labels_json FROM issues WHERE id=?", (neighbour["issue_id"],))
            for label in Database.loads(row["labels_json"], []) if row else []:
                if label not in {"synthetic", "small"}:
                    suggest(label, 0.6, "shared by a highly ranked similar issue")

        recommended_labels = [
            {"label": label, "confidence": confidence, "why": reason}
            for label, (confidence, reason) in sorted(
                derived_labels.items(), key=lambda item: item[1][0], reverse=True
            )[:5]
        ]

        label_names = {item["label"] for item in recommended_labels}
        if "security" in label_names or "urgent" in label_names:
            priority: Priority = "urgent"
            priority_confidence = 0.95
            priority_reason = "security-sensitive or time-critical signals require immediate triage"
        elif "customer-impact" in label_names:
            priority = "high"
            priority_confidence = 0.9
            priority_reason = "explicit customer or financial impact"
        elif "bug" in label_names:
            priority = "medium"
            priority_confidence = 0.78
            priority_reason = "incorrect behavior is present without an urgent-impact signal"
        else:
            priority = "low"
            priority_confidence = 0.7
            priority_reason = "no urgent, security, customer-impact, or defect signal was found"

        return TriageRecommendation(
            issue={
                "issue_id": issue["id"],
                "external_key": issue["external_key"],
                "title": issue["title"],
                "current_team": issue["team"],
                "current_labels": current_labels,
                "current_priority": issue["priority"],
                "revision": issue["revision"],
            },
            team={
                "recommended": recommended_team,
                "confidence": round(top_team_score / total_team_score, 3),
                "why": "current ownership plus teams of the highest-ranked similar issues",
                "alternatives": alternatives,
                "available_teams": available_teams,
            },
            priority={
                "recommended": priority,
                "confidence": priority_confidence,
                "why": priority_reason,
            },
            labels=recommended_labels,
            retrieval={
                "mode": search.mode,
                "completeness": search.completeness,
                "neighbour_keys": [item["external_key"] for item in neighbours[:5]],
            },
        )
