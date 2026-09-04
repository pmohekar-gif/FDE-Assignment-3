"""
linear.py — Read-only Linear issue import adapter for Warrant.

Supports two modes controlled exclusively by LINEAR_MODE:
  "stub" — returns STUB_LINEAR_ISSUE for any ref (offline demo / CI)
  "live" — makes a real HTTPS POST to the Linear GraphQL API

Mode "off" (default) means the adapter is not configured; the import endpoint
will raise AdapterConfigError if called, but app startup is unaffected.

Authentication for live mode: Personal API Key in the Authorization header
(no Bearer prefix). See §3.1 of LINEAR_ADAPTER_FEASIBILITY.md.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import httpx

from ..config import Settings
from ..service import DomainError, NotFound
from .linear_dto import (
    LinearAssigneeDTO,
    LinearIssueDTO,
    LinearLabelDTO,
    LinearStateDTO,
    LinearTeamDTO,
)
from .linear_fixture import STUB_LINEAR_ISSUE

# UUID pattern — matches Linear's internal UUID format
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)

# GraphQL query: fetch by internal UUID or human-readable key (e.g. "ENG-123")
_QUERY_BY_ID = """
query WarrantImportIssueById($id: String!) {
  issue(id: $id) {
    id identifier title description url priority updatedAt createdAt
    team { id name key }
    labels { nodes { id name color } }
    state { id name type }
    assignee { id name }
  }
}
"""

_REQUEST_TIMEOUT = 15.0  # seconds


class AdapterConfigError(DomainError):
    """Raised when the Linear adapter is called but not properly configured."""

    status_code = 503


class LinearIssueNotFoundError(NotFound):
    """Raised when the requested Linear issue does not exist in the workspace."""


def _parse_dto(raw: dict[str, Any], source_label: str) -> LinearIssueDTO:
    """Convert a raw Linear API issue node dict into a typed LinearIssueDTO."""
    labels_nodes = (raw.get("labels") or {}).get("nodes", [])
    assignee_raw = raw.get("assignee")
    state_raw = raw.get("state") or {}
    team_raw = raw.get("team") or {}

    return LinearIssueDTO(
        id=raw["id"],
        identifier=raw["identifier"],
        title=raw["title"],
        description=raw.get("description"),
        url=raw["url"],
        priority=int(raw.get("priority") or 0),
        updated_at=datetime.fromisoformat(
            raw["updatedAt"].replace("Z", "+00:00")
        ),
        created_at=datetime.fromisoformat(
            raw["createdAt"].replace("Z", "+00:00")
        ),
        team=LinearTeamDTO(
            id=team_raw.get("id", ""),
            name=team_raw.get("name", ""),
            key=team_raw.get("key", ""),
        ),
        labels=[
            LinearLabelDTO(
                id=lbl.get("id", ""),
                name=lbl.get("name", ""),
                color=lbl.get("color"),
            )
            for lbl in labels_nodes
        ],
        state=LinearStateDTO(
            id=state_raw.get("id", ""),
            name=state_raw.get("name", ""),
            type=state_raw.get("type", ""),
        ),
        assignee=LinearAssigneeDTO(
            id=assignee_raw["id"],
            name=assignee_raw["name"],
        )
        if assignee_raw
        else None,
    )


class LinearAdapter:
    """
    Read-only Linear issue importer. Call `fetch_issue(ref)` to obtain a
    `LinearIssueDTO`. The adapter enforces its own mode validation lazily
    (only when fetch_issue is called) so the application starts cleanly
    when LINEAR_MODE is "off" or unconfigured.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch_issue(self, ref: str) -> LinearIssueDTO:
        """
        Fetch a Linear issue by UUID or human-readable key (e.g. "ENG-123").

        Raises:
            AdapterConfigError: if mode is "off" or "live" without an API key.
            LinearIssueNotFoundError: if the issue does not exist.
        """
        mode = self._settings.linear_mode
        if mode == "off":
            raise AdapterConfigError(
                "Linear adapter is not configured. "
                "Set LINEAR_MODE=stub or LINEAR_MODE=live."
            )
        if mode == "stub":
            return self._fetch_stub(ref)
        if mode == "live":
            if not self._settings.linear_api_key:
                raise AdapterConfigError(
                    "LINEAR_MODE=live requires LINEAR_API_KEY to be set."
                )
            return self._fetch_live(ref)
        raise AdapterConfigError(
            f"Unknown LINEAR_MODE={mode!r}. Must be 'off', 'stub', or 'live'."
        )

    # ------------------------------------------------------------------
    # Stub mode
    # ------------------------------------------------------------------

    def _fetch_stub(self, ref: str) -> LinearIssueDTO:
        """Return the static stub fixture for any ref in stub mode."""
        import hashlib

        stub = dict(STUB_LINEAR_ISSUE)
        if ref:
            # Override identifier and id so they match the requested ref
            # for clarity and avoid collisions
            stub["identifier"] = ref
            stub["id"] = f"stub-uuid-{hashlib.md5(ref.encode()).hexdigest()}"
        # Mark source clearly in the identifier title prefix
        if not stub["title"].startswith("[SIMULATED]"):
            stub["title"] = f"[SIMULATED] {stub['title']}"
        return _parse_dto(stub, source_label="linear-stub")

    # ------------------------------------------------------------------
    # Live mode
    # ------------------------------------------------------------------

    def _fetch_live(self, ref: str) -> LinearIssueDTO:
        """Fetch a real Linear issue via the GraphQL API."""
        query = _QUERY_BY_ID
        variables: dict[str, str] = {"id": ref}

        try:
            response = httpx.post(
                self._settings.linear_api_base_url,
                headers={
                    "Content-Type": "application/json",
                    # Personal API key: no "Bearer" prefix (§3.1 of feasibility doc)
                    "Authorization": self._settings.linear_api_key or "",
                },
                json={"query": query, "variables": variables},
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AdapterConfigError(
                f"Linear API request failed: {type(exc).__name__}: {exc}"
            ) from exc

        payload = response.json()
        errors = payload.get("errors")
        if errors:
            raise AdapterConfigError(
                f"Linear GraphQL errors: {errors[0].get('message', errors)}"
            )

        data = payload.get("data") or {}
        node = data.get("issue")
        if not node:
            raise LinearIssueNotFoundError(
                f"Linear issue {ref!r} was not found."
            )

        return _parse_dto(node, source_label="linear")
