# Linear Adapter Feasibility Spike

**Status**: SPIKE ONLY — No adapter implementation yet.  
**Author**: Engineering (FDE Assignment, Team 3)  
**Date**: 2024-09-04  
**Ticket**: Linear adapter feasibility — thin read-only import for Warrant  
**Recommendation**: **Proceed with limitations** (see §8)

---

## 1. Goal

Determine whether Warrant can perform a thin, read-only import of one Linear issue
via the official Linear GraphQL API, map it to Warrant's internal `issues` table, and
run the existing Warrant accountability layer (triage, related issues, delegation brief,
policy, warrant, audit) against it — without becoming a Linear clone and without
committing real credentials.

---

## 2. Official Documentation References

| Document | URL |
|---|---|
| Linear GraphQL API overview | https://developers.linear.app/docs/graphql/working-with-the-graphql-api |
| Authentication | https://developers.linear.app/docs/graphql/working-with-the-graphql-api/authentication |
| Rate limiting | https://developers.linear.app/docs/graphql/working-with-the-graphql-api/rate-limiting |
| Interactive GraphQL explorer (Apollo Studio) | https://studio.apollographql.com/public/Linear-API/variant/current/schema |
| SDK / TypeScript client | https://developers.linear.app/docs/sdk/getting-started |
| Terms of Service | https://linear.app/terms |
| Acceptable Use Policy | https://linear.app/legal/acceptable-use |

---

## 3. Auth Options

### 3.1 Personal API Key (recommended for this assignment)

- Generated under **Settings → API → Personal API keys** in the Linear UI.
- Sent in the request header as:

  ```
  Authorization: <YOUR_API_KEY>
  ```

  Note: **no `Bearer` prefix** for personal keys.
- Access is scoped to the workspace of the user who generated the key.
- Sufficient for a single-workspace demo/assignment import.
- **Risk**: the key inherits the user's full workspace read access. It must not be
  committed to git and must be stored in `.env` only (already `.gitignored`).

### 3.2 OAuth 2.0 (recommended for production multi-tenant use)

- Standard authorization-code flow:
  `GET https://linear.app/oauth/authorize`  →  `POST https://linear.app/oauth/token`
- Access token sent as: `Authorization: Bearer <ACCESS_TOKEN>`
- Supports scopes: `read` (sufficient for this use case), `write`, `issues:create`, etc.
- Requires registering an OAuth application in the Linear developer console.
- **For this assignment**: a personal API key is sufficient and simpler.

---

## 4. Endpoint and Request Format

```
POST https://api.linear.app/graphql
Content-Type: application/json
Authorization: <YOUR_API_KEY>

{
  "query": "<GraphQL query string>",
  "variables": { ... }
}
```

- **Single endpoint** for all operations (queries and mutations).
- Standard GraphQL-over-HTTP: POST body contains `query` and optional `variables`.
- Responses follow the GraphQL envelope: `{ "data": {...}, "errors": [...] }`.
- HTTP status is almost always `200` even for application-level errors; errors appear in
  the `errors` array, not as 4xx/5xx codes (exception: 429 for rate-limit exceeded).

---

## 5. Fetching Issues by Identifier or UUID

### 5.1 By UUID (preferred if UUID is known)

```graphql
query GetIssue($id: String!) {
  issue(id: $id) {
    id
    identifier
    title
    description
    url
    priority
    updatedAt
    createdAt
    team {
      id
      name
      key
    }
    labels {
      nodes {
        id
        name
        color
      }
    }
    state {
      id
      name
      type
    }
    assignee {
      id
      name
    }
  }
}
```

Variables: `{ "id": "<UUID>" }`

### 5.2 By Human-Readable Identifier (e.g., `ENG-123`)

No `issue(identifier: ...)` root field exists. Use the `issues` connection with a filter:

```graphql
query GetIssueByKey($key: String!) {
  issues(filter: { identifier: { eq: $key } }) {
    nodes {
      id
      identifier
      title
      description
      url
      priority
      updatedAt
      createdAt
      team {
        id
        name
        key
      }
      labels {
        nodes {
          id
          name
          color
        }
      }
      state {
        id
        name
        type
      }
      assignee {
        id
        name
      }
    }
  }
}
```

Variables: `{ "key": "ENG-123" }`

> **Important**: `issues(filter: ...)` always returns a connection (list). The adapter
> must assert `len(nodes) == 1` and raise a clear error if 0 or >1 results come back.

---

## 6. Available Fields — Confirmed vs Uncertain

Field availability was verified via Apollo Studio introspection of the public schema (`https://studio.apollographql.com/public/Linear-API/variant/current/schema`).

### 6.1 Confirmed Available (in public schema)

| Field | GraphQL path | Warrant mapping |
|---|---|---|
| Internal UUID | `issue.id` | adapter metadata table (`external_id`) |
| Human identifier | `issue.identifier` | `external_key` |
| Title | `issue.title` | `title` |
| Description (Markdown) | `issue.description` | `body_normalised` (after redaction/normalization) |
| Team name | `issue.team.name` | `team` |
| Team key | `issue.team.key` | adapter metadata table |
| Priority (0–4 int) | `issue.priority` | `priority` (mapped) |
| Labels | `issue.labels.nodes[].name` | `labels_json` (list JSON, not CSV) |
| Issue URL | `issue.url` | adapter metadata table |
| Updated timestamp | `issue.updatedAt` (ISO 8601) | `updated_at` |
| Created timestamp | `issue.createdAt` (ISO 8601) | adapter metadata table (`external_created_at`) |
| Workflow state name | `issue.state.name` | adapter metadata table (`state`) |
| Assignee name | `issue.assignee.name` | adapter metadata table (`assignee`) |

**Priority integer mapping** (Linear convention):

| int | Label |
|---|---|
| 0 | No priority |
| 1 | Urgent |
| 2 | High |
| 3 | Medium |
| 4 | Low |

### 6.2 Uncertain / Out of Scope for MVP

| Field | Status |
|---|---|
| Assignee email | Available in schema — intentionally excluded (PII) |
| Comments / timeline | Available but out of scope for thin import |
| Attachments | Available but out of scope |
| Subscribers | Available but out of scope |
| Cycle / project membership | Available but not needed for MVP |
| Parent / child issues | Available but not needed for MVP |
| Estimate (story points) | Available (`issue.estimate`) — optional extension |
| SLA / due date | Available (`issue.dueDate`) — optional extension |

---

## 7. Rate Limits and Error Behaviour

### 7.1 Rate limits

| Auth mode | Limit |
|---|---|
| Personal API key | ~3,000,000 complexity points/hour |
| OAuth application | 1,500 complexity points/hour |

- Limits are **complexity-based**, not request-count-based.
- A simple single-issue query (as proposed) costs approximately 2–5 complexity points.
- At 1,500 pts/hour (OAuth tier), this allows roughly 300–750 single-issue
  imports per hour — negligible risk for this assignment.
- Usage is reported in response headers (`X-Complexity`, `X-RateLimit-*` family).

### 7.2 Errors

| Condition | Behaviour |
|---|---|
| Invalid or missing auth header | HTTP 401 |
| Malformed GraphQL | HTTP 200, `errors[]` in body |
| Issue not found | HTTP 200, `data.issue: null` |
| Rate limit exceeded | HTTP 429 (or 400 + error message) |
| Server error | HTTP 500 |

The adapter must check `response["errors"]` explicitly in addition to HTTP status.

---

## 8. API Usage: Permitted for This Assignment/Demo Pattern?

**Yes**, with the following constraints:

1. **Read-only queries** (no mutations) appear feasible for authorized read-only use
   under Linear's developer documentation and Terms of Service.
2. **Personal API key scope** is limited to the key-holder's workspace — there is no
   cross-workspace data risk.
3. **Assignment/demo use case** (one import, synthetic workflow demonstration) sits well
   within the personal API key quota and Linear's Acceptable Use Policy, which prohibits
   scraping or bypassing rate limits, not normal API reads.
4. **No real customer data** may be sent to OpenRouter or stored beyond Warrant's
   local SQLite database (already enforced by `MY_TASK_PRIORITY_PLAN.md` and the
   `.env` data-handling rules).
5. **The adapter must never commit a real API key** — `.env` is `.gitignored` and the
   `.env.example` uses `replace-me` placeholders.

---

## 9. Minimal DTO (Python / Pydantic)

> SPIKE ONLY — not yet implemented; subject to review approval.
> Proposed file: `src/warrant/adapters/linear_dto.py`

```python
from __future__ import annotations
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
    id: str                           # Linear internal UUID
    identifier: str                   # Human-readable key, e.g. "ENG-123"
    title: str
    description: Optional[str] = None # Markdown; may be None for empty issues
    url: str
    priority: int = Field(ge=0, le=4) # 0=none,1=urgent,2=high,3=medium,4=low
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
        Map Linear fields to Warrant's internal issues table columns.
        `body_normalised` must be passed in by the caller after running the
        normalise_untrusted(title, description) redaction pipeline — it is NOT
        nullable in the issues table and must never be empty or None.
        Caller is responsible for idempotency check on external_key.
        Implementation should call json.dumps() on labels and path_hints
        at persistence time.
        """
        return {
            "external_key": self.identifier,
            "title": self.title,
            "body_normalised": body_normalised,
            "team": self.team.name,
            "labels": [label.name for label in self.labels],
            "priority": self.priority_label,
            "updated_at": self.updated_at.isoformat(),
            "path_hints": [],  # Linear has no path context; fail toward uncertainty
        }

    def to_adapter_metadata(self) -> dict:
        """
        Extract metadata to be stored in the separate adapter metadata table.
        Raw description text is NOT stored here to avoid duplicating sensitive
        Linear issue text. Only a SHA-256 fingerprint is kept for dedup/audit.
        """
        import hashlib
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
```

### 9.1 Path-Hint Strategy

- Linear issues do not naturally provide repo path hints.
- The MVP default must be: `path_hints_json=[]` unless explicit safe hints are present.
- Empty/unknown path hints should fail toward approval/uncertainty, not auto-allow.
- If parsing paths from description is proposed, it must be conservative and documented.

---

## 10. Minimal GraphQL Query (Production-Ready Shape)

```graphql
# Fetch by UUID — use when the internal ID is already known.
query WarrantImportIssueById($id: String!) {
  issue(id: $id) {
    id
    identifier
    title
    description
    url
    priority
    updatedAt
    createdAt
    team { id name key }
    labels { nodes { id name color } }
    state { id name type }
    assignee { id name }
  }
}

# Fetch by human-readable key — use when only "ENG-123" style ID is known.
query WarrantImportIssueByKey($key: String!) {
  issues(filter: { identifier: { eq: $key } }) {
    nodes {
      id
      identifier
      title
      description
      url
      priority
      updatedAt
      createdAt
      team { id name key }
      labels { nodes { id name color } }
      state { id name type }
      assignee { id name }
    }
  }
}
```

**Complexity estimate**: approximately 2–4 points per call (well within both personal
and OAuth tiers).

---

## 11. Privacy and Data-Handling Constraints

1. **Assignee email must not be fetched or stored** — it is PII and is not needed for
   Warrant's accountability layer.
2. **Description must be redacted** before being passed to any AI provider (same
   redaction path as existing internal issues — already implemented in `service.py`).
3. **No Linear data must be sent to the OpenRouter free endpoint** — `MY_TASK_PRIORITY_PLAN.md`
   already mandates this; the adapter must enforce it by marking imported issues with
   `source=linear` and blocking all OpenRouter calls for Linear-imported customer data.
4. **The API key must live only in `.env`** — never in code, logs, or test fixtures.
5. **Tests must use HTTP stubs only** — no real network calls in the test suite.
6. **Audit payload minimization** — no raw issue description, no API key, and no full customer text in audit/telemetry logs.

---

## 12. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Schema drift (Linear silently removes fields) | Low–Medium | Medium | Pin to confirmed fields only; DTO validates with Pydantic; add schema smoke-test fixture |
| Issue not found (key typo or wrong workspace) | Medium | Low | Raise `LinearIssueNotFoundError`; surface in API response with clear message |
| Rate limit hit during demo | Very Low | Low | Single-issue import costs ~2–4 pts; 1,500 pts/hr is enormous headroom |
| API key accidentally committed | Low | High | `.env` is `.gitignored`; `.env.example` uses `replace-me`; CI should lint for key patterns |
| Real issue data sent to OpenRouter | Low | High | Enforce `source=linear` guard in provider dispatch path; block all OpenRouter for imported customer data |
| Markdown description contains PII | Medium | Medium | Run existing redaction path before any AI call; treat imported text as untrusted input |
| Linear auth format changes | Very Low | Medium | Auth is a single header injection; trivial to patch |
| `issues(filter)` returns >1 result for identifier | Very Low | Low | Assert `len(nodes) == 1`; raise on ambiguity |

---

## 13. Stub / Demo Fallback

If a real Linear API key is unavailable (CI, offline demo, reviewer without a Linear
workspace), the adapter should fall back to a **static fixture**:

```python
# src/warrant/adapters/linear_fixture.py
# STUB for offline demo / CI — clearly labelled as SIMULATED

STUB_LINEAR_ISSUE = {
    "id": "stub-uuid-0000-0000-0000-000000000001",
    "identifier": "ENG-001",
    "title": "[SIMULATED] Fix memory leak in agent runner",
    "description": (
        "Profiler shows 40 MB/h growth under sustained load. "
        "Traced to the embedding cache not being evicted on context flush."
    ),
    "url": "https://linear.app/example-org/issue/ENG-001",
    "priority": 2,
    "updatedAt": "2026-09-01T12:00:00.000Z",
    "createdAt": "2026-08-28T09:00:00.000Z",
    "team": {"id": "team-stub-001", "name": "Engineering", "key": "ENG"},
    "labels": {"nodes": [{"id": "lbl-001", "name": "bug", "color": "#eb5757"}]},
    "state": {"id": "state-001", "name": "In Progress", "type": "started"},
    "assignee": {"id": "user-001", "name": "Alice"},
}
```

The `import-issue` endpoint should detect an explicit `LINEAR_MODE=stub` (preferred over
`LINEAR_API_KEY=stub`) and return the fixture data, clearly marking it as
`"source": "linear-stub"` in the adapter metadata/link table and the API response.
Do not implicitly use a stub because `AI_PROVIDER=fixture` — these are independent systems.
Missing or invalid Linear config should return a clear adapter config error, not silently
fall back to stub data.

---

## 14. Recommendation

> **Proceed with limitations.**

The thin read-only import path **appears feasible for authorized read-only use** under the existing Linear GraphQL
API:

- All required fields (`id`, `identifier`, `title`, `description`, `team`, `labels`,
  `priority`, `url`, `updatedAt`) are confirmed available in the public schema.
- Personal API key auth is trivial to implement and sufficient for a single-workspace
  demo.
- A single-issue query costs approximately 2–4 complexity points — negligible against
  any rate-limit tier.
- The API use appears consistent with Linear's permitted developer and integration use.
- The DTO, query shape, and field mapping are well-defined and ready for implementation.

**Limitations to carry forward into implementation**:

1. Fetch-by-identifier requires the `issues(filter: ...)` path — no direct root field
   exists for human-readable identifiers.
2. Assignee email must be excluded from the query and never stored.
3. Description must enter the existing redaction pipeline before any AI provider call.
4. A real `LINEAR_API_KEY` must never be committed; tests must use stubs only.
5. OAuth is deferred to a future hardening step; personal API key is used for the
   assignment window.

**Do not implement the adapter until this spike is reviewed and approved.**
