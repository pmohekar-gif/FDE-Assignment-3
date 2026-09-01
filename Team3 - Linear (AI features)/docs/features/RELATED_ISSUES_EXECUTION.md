# User-visible Related and Duplicate Issue Suggestions

## Goal

Expose Warrant's existing hybrid retrieval as a read-only operator feature that helps a user
spot likely duplicate and related work before starting a governed delegation.

This feature is advisory only. A suggestion must never create, close, merge, or delegate an
issue, and retrieval confidence must never grant authority.

## Why this feature is first

- The hybrid SQLite FTS + deterministic-vector retrieval already exists.
- It completes a visible product loop without requiring Linear, GitHub, or agent credentials.
- The work is read-only and does not weaken Warrant's policy boundary.
- Each phase is independently testable and useful.

## Product contract

- Suggestions are restricted to the current workspace and issue team.
- The source issue is never returned as its own suggestion.
- Results distinguish `possible_duplicate` from `related`.
- Every result includes an operator-readable reason and bounded confidence score.
- Retrieval mode and completeness are disclosed; lexical fallback remains visible.
- Suggestions never authorize work or bypass the normal delegation pipeline.

## Phase 1 — Stable retrieval contract

Status: complete

Deliverables:

- Add a dedicated read-only `suggest_related` retrieval entry point.
- Resolve issues by external key within the workspace boundary.
- Add deterministic relationship classification and confidence.
- Preserve existing delegation retrieval behaviour.
- Cover workspace/team isolation, ordering, and missing-issue behaviour with tests.

Checklist:

- [x] Source issue is excluded.
- [x] Cross-team results are excluded.
- [x] Result count is bounded.
- [x] Relation is either `possible_duplicate` or `related`.
- [x] Confidence stays between 0 and 1.
- [x] Retrieval mode and completeness are returned.
- [x] Unknown issue keys return no result rather than leaking another workspace.
- [x] Existing test suite passes.

## Phase 2 — Read-only API

Status: complete

Deliverables:

- Add `GET /v1/issues/{issue_ref}/related`.
- Validate `limit` with a small server-side maximum.
- Return 404 for an unknown issue in the active workspace.
- Add API contract and failure-path tests.

Checklist:

- [x] Endpoint performs no writes.
- [x] Workspace boundary is enforced server-side.
- [x] Limit validation is covered.
- [x] Response schema is documented and tested.
- [x] Fallback mode is visible to clients.

Implemented response contract:

```json
{
  "source": {
    "issue_id": "issue-pay-4471",
    "external_key": "PAY-4471",
    "title": "Checkout double-charges when retry is pressed twice",
    "team": "Payments"
  },
  "retrieval": {"mode": "HYBRID", "completeness": 1.0},
  "suggestions": [],
  "advisory_only": true
}
```

Verification commands:

```bash
.venv/bin/pytest -q tests/integration/test_related_issues_api.py
.venv/bin/pytest -q
```

## Phase 3 — Dashboard interaction

Status: implementation complete; browser visual QA pending

Deliverables:

- Add a “Find related” action to issue cards.
- Render an accessible inline suggestion panel with key, title, relation, reason, and confidence.
- Link policy precedents to their delegation detail when available.
- Include loading, empty, degraded, and error states.

Checklist:

- [x] Suggestions are visible before delegation.
- [x] The normal delegation action remains distinct.
- [x] Keyboard and screen-reader states are usable.
- [x] Duplicate language is explicitly advisory.
- [x] Desktop layout visually verified from the 2026-09-01 localhost screenshot: disclosure,
  duplicate/related labels, confidence, reasons, and distinct delegation action render correctly.
- [ ] Mobile layout is visually verified at approximately 390px. Automated responsive CSS and
  route coverage pass; the browser was unavailable for independent mobile interaction testing.

## Phase 4 — Quality and evaluation hardening

Status: complete

Deliverables:

- Add a small labelled synthetic retrieval set.
- Measure recall@10 and possible-duplicate precision.
- Record suggestion views/selections as non-authorising telemetry.
- Document thresholds, limitations, and fallback behaviour.

Checklist:

- [x] Metrics use labelled examples rather than anecdotal screenshots.
- [x] Threshold changes are regression-tested.
- [x] Evaluation output distinguishes measured values from targets.
- [x] No telemetry contains raw issue bodies or secrets.

Phase 4 uses `evaluations/retrieval_golden.json`, a four-query synthetic labelled set. The
evaluation reports recall@10 and possible-duplicate precision separately and identifies this
small synthetic dataset as a limitation. UI telemetry records only issue keys, relation, rank,
and result count through a separate CSRF-protected endpoint.

## Latest verification

Verified on 2026-09-01:

- Ruff passed for every changed Python file.
- Mypy passed for all 15 source files.
- Full suite passed: 73 tests.
- Evaluation regenerated with retrieval recall@10 = 1.0 and possible-duplicate precision = 1.0
  on the documented four-query synthetic dataset.
- Persisted related-issue telemetry includes views and selections; a content scan found no issue
  body, bearer, or token-like fields.
- Desktop rendering passed from the supplied localhost screenshot.
- Mobile visual inspection remains pending because no controllable browser was available.

## Definition of done

The feature is complete when an operator can request related issues from the dashboard before
delegation, understand why each item was suggested and how reliable retrieval was, and the
labelled evaluation shows its measured quality without changing any authorization decision.
