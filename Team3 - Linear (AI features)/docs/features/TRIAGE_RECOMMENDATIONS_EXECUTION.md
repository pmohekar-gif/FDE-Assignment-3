# AI-assisted Triage Recommendations

## Goal

Recommend a team, priority, and labels for an existing or imported issue before it enters the
Warrant delegation pipeline. Recommendations are advisory: a human may accept or change them,
and no recommendation grants agent authority.

## Target workflow

```text
Import issue
  ↓
Detect duplicates
  ↓
Suggest team, priority, and labels
  ↓
Run Warrant delegation policy
  ↓
Human approves or changes the decision
  ↓
Audit everything
```

Duplicate detection and the Warrant policy/approval/audit stages already exist. Issue import is a
separate future feature. This plan completes the missing triage-recommendation stage first.

## Product contract

- Recommendations never modify the issue automatically.
- Team recommendation uses workspace-scoped retrieval evidence and existing metadata.
- Priority and labels include explicit reasons and bounded confidence.
- Current values remain visible so a human can compare before accepting anything.
- Retrieval degradation is disclosed.
- Triage recommendations do not affect Warrant policy until explicitly accepted and persisted.

## Phase 1 — Stable advisory recommendation contract

Status: complete

Deliverables:

- Add a read-only triage service for team, priority, and label recommendations.
- Use hybrid search neighbours plus deterministic issue signals.
- Return current values, recommendations, alternatives, reasons, and confidence.
- Preserve workspace isolation and expose retrieval completeness.

Checklist:

- [x] Team recommendation includes confidence, reason, and alternatives.
- [x] Priority is one of `urgent`, `high`, `medium`, or `low`.
- [x] Label recommendations include confidence and reason.
- [x] Existing team, labels, and revision remain visible.
- [x] Confidence values stay between 0 and 1.
- [x] Retrieval mode and completeness are disclosed.
- [x] Unknown/cross-workspace issues return no recommendation.
- [x] Recommendation generation performs no database writes.
- [x] Existing test suite passes.

## Phase 2 — Read-only recommendation API

Status: complete

Deliverables:

- Add `GET /v1/issues/{issue_ref}/triage-recommendation`.
- Return the Phase 1 contract without modifying the issue.
- Cover workspace boundaries, degraded retrieval, and write-free behavior.

Checklist:

- [x] Response schema is documented and tested.
- [x] Unknown issue behavior is explicit (`404`).
- [x] Retrieval degradation is visible through `mode` and `completeness`.
- [x] Endpoint performs no writes.

## Phase 3 — Human review and application workflow

Status: implementation complete; visual browser verification pending

Deliverables:

- Add a triage recommendation panel before governed delegation.
- Allow a human to accept or change team, priority, and labels.
- Persist accepted values with optimistic revision checks.
- Audit original recommendation and final human decision.

Checklist:

- [x] Recommendations and current values are visually distinct.
- [x] Human changes are supported before persistence.
- [x] Stale issue revisions are rejected with `409`.
- [x] Nothing is applied without an explicit confirmation action.
- [x] Applied triage decisions are auditable as `triage_applied` events.
- [ ] Desktop and mobile layouts are verified.

## Phase 4 — Triage quality evaluation

Status: complete

Deliverables:

- Add labelled synthetic team, priority, and label cases.
- Measure team accuracy, priority macro-F1, and label precision/recall.
- Record views/accepts/changes without raw issue-body telemetry.
- Document fixture and synthetic-data limitations.

Checklist:

- [x] Each recommendation dimension is measured separately.
- [x] Human acceptance and override rates are diagnostic, not truth labels.
- [x] Evaluation distinguishes synthetic results from production quality.
- [x] Telemetry stores no raw issue body, recommendation prose, or labels.

## Operator verification

1. Restart the app so the issue-priority migration and new routes are loaded.
2. Open the Inbox and click **Review AI triage** on an issue card.
3. Compare current values with the suggested team, priority, labels, reasons, and confidence.
4. Change at least one value, confirm the checkbox, and click **Apply triage decision**.
5. Open **Audit** and verify a `triage_applied` event records both the recommendation and the
   human's final values.
6. Run `.venv/bin/warrant-eval` and inspect the four `triage_*` metrics on the Evaluation page.

The labelled evaluation uses only three synthetic demo issues. Passing those targets is a local
regression signal, not proof of production routing quality.

## Definition of done

The feature is complete when a human can review, accept, or change team/priority/label
recommendations before delegation, every applied decision is revision-safe and audited, and
labelled evaluation reports each recommendation dimension without influencing authority.
