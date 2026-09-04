# User-visible Semantic Issue Search

## Goal

Upgrade the operator inbox from key/title substring filtering to disclosed hybrid search across
issue keys, titles, and normalised descriptions. Search is read-only and must not create a
delegation, produce authority, or influence policy without the normal governed pipeline.

## Why this feature is next

- Semantic-ish vectors and SQLite FTS are already available internally.
- The existing inbox search only applies SQL `LIKE` to issue key and title.
- It reuses the retrieval foundation without adding external credentials or adapters.
- It makes existing capability useful before tackling broader triage recommendations.

## Product contract

- Search is always scoped to the active workspace.
- Team is an optional hard filter applied before ranking.
- Exact issue keys, lexical matches, and semantic matches are fused deterministically.
- Results expose ranking evidence and retrieval degradation.
- Empty queries return no semantic results.
- Search never creates telemetry, delegations, warrants, approvals, or audit authority by itself.

## Phase 1 — Stable hybrid-search contract

Status: complete

Deliverables:

- Add a dedicated read-only `search_issues` retrieval entry point.
- Fuse exact-key, SQLite FTS, and deterministic-vector rankings.
- Support an optional hard team filter.
- Return disclosed mode, completeness, ranking scores, and match reasons.
- Bound result counts and handle empty queries safely.

Checklist:

- [x] Exact issue-key matches rank first.
- [x] Description-language queries can retrieve an issue without title substring matching.
- [x] Workspace isolation is enforced.
- [x] Optional team filtering is enforced before ranking.
- [x] Result count is bounded between 1 and 50 internally.
- [x] Empty queries return no results.
- [x] Lexical fallback mode is disclosed when embeddings are unavailable.
- [x] Search performs no database writes.
- [x] Existing test suite passes.

## Phase 2 — Read-only search API

Status: complete

Deliverables:

- Add `GET /v1/issues/search?q=...&team=...&limit=...`.
- Validate query and limit boundaries.
- Return the stable Phase 1 response contract.
- Cover invalid input, workspace isolation, team filtering, and write-free behavior.

Checklist:

- [x] API response schema is documented and tested.
- [x] Query validation rejects blank and oversized input.
- [x] Limit validation is covered.
- [x] Workspace/team isolation is tested at the HTTP boundary.
- [x] Endpoint performs no writes.

Implemented endpoint:

```text
GET /v1/issues/search?q=second+retry+must+not+create+another+charge&team=Payments&limit=10
```

The response includes the cleaned query, optional team, retrieval mode/completeness, ranked
results with match evidence, and `read_only: true`.

## Phase 3 — Inbox semantic-search experience

Status: implementation complete; browser visual QA pending

Deliverables:

- Replace the current substring-only search path with hybrid search when a query is present.
- Disclose hybrid versus lexical-only mode and result completeness.
- Show why each result matched while preserving team filter and pagination behavior.
- Include accessible loading, empty, degraded, and clear-search states.

Checklist:

- [x] Natural-language queries work from the operator inbox.
- [x] Exact issue-key lookup remains fast and predictable.
- [x] Team filtering remains a hard boundary.
- [x] Degraded retrieval is visible rather than silently hidden.
- [ ] Desktop and mobile layouts are visually verified. Route, content, and responsive CSS
  coverage pass; final interactive browser inspection is pending.

## Phase 4 — Search quality and telemetry

Status: complete

Deliverables:

- Add an explicit labelled synthetic semantic-search dataset.
- Measure recall@10 and exact-key success separately from related-issue metrics.
- Record query/result interaction telemetry without raw query text.
- Document deterministic-vector limitations and production embedding requirements.

Checklist:

- [x] Search metrics use labelled cases.
- [x] Exact-key and semantic-query slices are reported separately.
- [x] Telemetry stores no raw query or issue body.
- [x] Evaluation distinguishes synthetic measurements from production claims.

Phase 4 uses `evaluations/search_golden.json`: three exact-key cases and three natural-language
cases. It reports `exact_key_search_success` and `semantic_search_recall_at_10` separately.
Search telemetry records query length, result count, team-filter presence, selected issue key,
and rank; raw query text is never accepted by the telemetry schema.

## Latest verification

Verified on 2026-09-01:

- Focused semantic-search/UI/API/evaluation tests passed: 16.
- Full suite passed: 85 tests.
- Ruff passed for every changed Python file.
- Mypy passed for all 15 source files.
- `semantic_search_recall_at_10` = 1.0 on three labelled synthetic natural-language cases.
- `exact_key_search_success` = 1.0 on three labelled synthetic exact-key cases.
- Final browser visual inspection remains pending.

## Definition of done

The feature is complete when an operator can use natural issue language in the inbox, understand
how results were produced and whether retrieval degraded, and see labelled synthetic quality
measurements without search creating or changing any delegation authority.
