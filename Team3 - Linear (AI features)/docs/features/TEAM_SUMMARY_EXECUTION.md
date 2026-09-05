# Team Accountability Summary — Execution

## What This Is

A **Warrant accountability summary** — not a Linear project/cycle clone.

This endpoint aggregates delegation, warrant, approval, verification, and
risk state from Warrant's own database to give admins/owners a read-only
overview of AI-agent delegation health for a specific team.

## Endpoint Contract

### Request

```
GET /v1/summaries/team/{team}
```

```
POST /v1/summaries/team/{team}/refresh
```

| Header            | Required | Notes                              |
|-------------------|----------|------------------------------------|
| `X-Actor-ID`      | Yes      | Must resolve to an admin or owner  |
| `X-Workspace-ID`  | No       | Falls back to server default       |

For `POST /v1/summaries/team/{team}/refresh`:
- Requires `X-CSRF-Token`
- Requires `X-Actor-ID` (must be admin/owner)
- Computes non-authorising prose, updates the `team_summaries` table, appends a `team_summary_refreshed` audit event, and emits minimal telemetry.

For `GET`: No `X-CSRF-Token` required (read-only GET).

### Response (200)

```jsonc
{
  // Authority boundary — summaries never authorise anything
  "authorising": false,
  "decision_source": "deterministic_policy",
  "summary_may_change_verdict": false,

  // Team overview
  "team": "Web",
  "issue_count": 84,
  "priority_mix": { "medium": 70, "urgent": 5, "high": 9 },

  // Delegation accountability
  "recent_delegations": [
    {
      "id": "del_...",
      "status": "warrant_issued",
      "target_agent_id": "codex-cloud",
      "issue_ref": "WEB-4519",
      "created_at": "2026-09-04T..."
    }
  ],
  "delegation_count": 3,
  "verdict_counts": { "ALLOW": 2, "REQUIRE_APPROVAL": 1 },
  "pending_human_approvals": 1,
  "denied_delegations": 0,

  // Warrant state
  "active_warrants": 1,
  "expired_warrants": 0,
  "revoked_warrants": 0,
  "consumed_warrants": 1,

  // Verification health
  "failed_verifications": 0,
  "inconclusive_verifications": 0,

  // Risk surfaces
  "risky_surfaces": ["web/reports/EmptyState.tsx"],
  "protected_surfaces": [],

  // Audit chain
  "audit_chain": {
    "verified": true,
    "broken_at_seq": null
  },

  // Cache & Prose
  "facts_hash": "a1b2c3d4e5f6...",
  "prose": "This summary provides a point-in-time snapshot...",
  "prose_source": "model",
  "provider": "openai-compatible",
  "model": "gpt-4.1-mini",
  "generated_at": "2026-09-05T12:00:00+00:00",
  "cache_status": "hit",
  "refresh_required": false
}
```

### Error Responses

| Code | Condition                 |
|------|---------------------------|
| 403  | Actor is not admin/owner  |
| 404  | Team has no issues        |

## Design Decisions

### Unknown Team → 404

A team with zero issues has never existed in Warrant's context. Returning 404
is consistent with how other endpoints (`get_delegation`, `get_warrant`) handle
missing resources. This is more explicit than returning an empty-team response,
which could be confused with "team exists but has no activity."

### Authority Boundary Fields

Three top-level fields prove that summaries cannot authorise anything:

- `authorising: false` — this endpoint does not make authorisation decisions
- `decision_source: "deterministic_policy"` — the policy engine remains sole authority
- `summary_may_change_verdict: false` — viewing a summary never alters verdicts

### Telemetry Privacy

The `team_summary_viewed` telemetry event records only:

- `team` (string)
- `issue_count` (integer)
- `delegation_count` (integer)

No raw issue titles, bodies, or generated prose are stored.

## What This Is NOT

- **Not a Linear project summary** — no cycle/project sync, no GitHub data
- **Prose is strictly AI-explanatory** — AI provider only receives deterministic facts and cannot authorise actions. If it fails or is blocked (e.g., OpenRouter for real imported Linear issues), it gracefully falls back to structured prose.
- **GET does not auto-generate cache; POST refresh generates AI prose and updates cache**
- **Not a dashboard** — JSON API only, no UI
- **Not an authorisation endpoint** — summaries cannot approve/deny anything

## Files Changed

| File | Change |
|------|--------|
| `src/warrant/db.py` | Added `team_summaries` table |
| `src/warrant/schemas.py` | Added `TeamSummaryTelemetry` |
| `src/warrant/service.py` | Added `team_accountability_summary()` and `refresh_team_summary()` |
| `src/warrant/main.py` | Added `GET` and `POST /refresh` routes |
| `tests/integration/test_team_summary_api.py` | 18 integration tests (cache lifecycle, AI prose, fallback, provenance, OpenRouter guard, ChatCompletions parsing) |
| `docs/features/TEAM_SUMMARY_EXECUTION.md` | This document |
