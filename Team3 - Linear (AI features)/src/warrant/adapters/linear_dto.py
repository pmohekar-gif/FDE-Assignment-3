"""
linear_dto.py — Minimal read-only DTO for a Linear issue imported into Warrant.

All fields are drawn from the confirmed-available schema (§6.1 of the feasibility doc).
No mutations are represented here. Raw issue description is never stored; only its
SHA-256 fingerprint is kept in the adapter metadata table.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LinearLabelDTO(BaseModel):
    id: str
    name: str
    color: Optional[str] = None


class LinearTeamDTO(BaseModel):
    id: str
    name: str
    key: str


class LinearStateDTO(BaseModel):
    id: str
    name: str
    type: str  # e.g. "started", "completed", "cancelled", "triage", "backlog"


class LinearAssigneeDTO(BaseModel):
    id: str
    name: str
    # email intentionally omitted — PII; not needed for Warrant's accountability layer


class LinearIssueDTO(BaseModel):
    """
    Minimal read-only snapshot of a Linear issue for Warrant import.
    All fields are drawn from the confirmed-available schema section (§6.1).
    No mutations are represented here.
    """

    id: str  # Linear internal UUID
    identifier: str  # Human-readable key, e.g. "ENG-123"
    title: str
    description: Optional[str] = None  # Markdown; may be None for empty issues
    url: str
    priority: int = Field(ge=0, le=4)  # 0=none,1=urgent,2=high,3=medium,4=low
    updated_at: datetime
    created_at: datetime
    team: LinearTeamDTO
    labels: list[LinearLabelDTO] = Field(default_factory=list)
    state: LinearStateDTO
    assignee: Optional[LinearAssigneeDTO] = None

    @property
    def priority_label(self) -> str:
        return {0: "none", 1: "urgent", 2: "high", 3: "medium", 4: "low"}.get(
            self.priority, "none"
        )

    def to_warrant_fields(self, body_normalised: str) -> dict:
        """
        Map Linear fields to Warrant's internal issues table columns only.

        `body_normalised` MUST be passed in by the caller after running the
        normalise_untrusted(title, description) redaction pipeline — it is NOT
        nullable in the issues table and must never be empty or None.

        Caller is responsible for:
          - idempotency check on external_key
          - serialising `labels` and `path_hints` via json.dumps() at persistence time
        """
        return {
            "external_key": self.identifier,
            "title": self.title,
            "body_normalised": body_normalised,
            "team": self.team.name,
            "labels": [label.name for label in self.labels],
            "priority": self.priority_label,
            "updated_at": self.updated_at.isoformat(),
            "path_hints": [],  # Linear issues carry no repo path context; fail toward uncertainty
        }

    def to_adapter_metadata(self) -> dict:
        """
        Extract metadata to be stored in the separate linear_issue_links table.

        Raw description text is NOT stored here to avoid duplicating potentially
        sensitive Linear issue text. Only a SHA-256 fingerprint is retained for
        deduplication and audit purposes.
        """
        description_bytes = (self.description or "").encode()
        return {
            "external_id": self.id,
            "source": "linear",
            "url": self.url,
            "external_created_at": self.created_at.isoformat(),
            "description_sha256": hashlib.sha256(description_bytes).hexdigest(),
            "state": self.state.name,
            "assignee": self.assignee.name if self.assignee else None,
            "team_key": self.team.key,
        }

    def content_fingerprint(self, body_normalised: str) -> str:
        """
        Stable SHA-256 fingerprint of all mapped issues-table fields.
        Used to detect whether a re-import carries any changes worth bumping revision for.
        """
        warrant = self.to_warrant_fields(body_normalised)
        canonical = "|".join(
            f"{k}={warrant[k]!r}" for k in sorted(warrant) if k != "updated_at"
        )
        return hashlib.sha256(canonical.encode()).hexdigest()
