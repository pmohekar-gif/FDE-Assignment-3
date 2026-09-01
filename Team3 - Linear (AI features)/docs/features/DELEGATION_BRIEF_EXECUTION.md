# User-visible Delegation Brief

## Goal

Turn the existing `/v1/delegations/{id}/brief` capability into a clear operator-facing summary
of issue context, retrieved evidence, risk, policy verdict, warrant state, and next steps—without
allowing generated prose to grant or change authority.

## Why this feature is next

- Brief generation already exists for fixture, OpenAI-compatible, and OpenRouter providers.
- It directly supports Warrant's safe-delegation workflow.
- The current endpoint is not represented as a first-class UI workflow.
- Its non-authorising boundary exists in design but was not explicit in the response contract.

## Product contract

- Deterministic policy remains the only verdict source.
- Generated prose is explanatory and never authorising.
- Structured facts remain available even when model generation fails.
- Model and fallback paths expose the same versioned response contract.
- Missing information, scope, and warrant status remain visible rather than summarized away.

## Phase 1 — Versioned non-authorising contract

Status: complete

Deliverables:

- Add an explicit brief contract version.
- Add a machine-readable authority boundary.
- Provide a stable structured fact snapshot alongside narrative prose.
- Improve deterministic fallback next steps by verdict.
- Verify model and fallback paths cannot override the policy decision.

Checklist:

- [x] `authorising` is always false.
- [x] Decision source is explicitly `deterministic_policy`.
- [x] Prose is explicitly prohibited from changing the verdict.
- [x] Structured verdict and reasons match the delegation record.
- [x] Scope, evidence sufficiency, missing information, and warrant status are preserved.
- [x] Model and fallback paths return the same top-level contract.
- [x] Workspace isolation remains enforced.
- [x] Existing test suite passes.

## Phase 2 — Brief lifecycle and API hardening

Status: complete

Deliverables:

- Persist or cache briefs by delegation revision and prompt hash.
- Avoid repeated model cost for unchanged delegation facts.
- Add an explicit refresh operation with CSRF protection.
- Report generation time, provider/model provenance, and stale state.

Checklist:

- [x] Repeated reads reuse an unchanged brief.
- [x] Refresh is an explicit state-changing action.
- [x] Stale briefs are disclosed after evidence or decision changes.
- [x] Provider failures continue to return deterministic fallback content.
- [x] Usage and cache behavior are tested.

Briefs are persisted by delegation with issue revision, structured-fact hash, prompt hash,
provider/model provenance, source, and generation time. A normal GET returns the unchanged cache.
Changed facts make it stale; `POST /v1/delegations/{id}/brief/refresh` requires CSRF and performs
the explicit regeneration.

## Phase 3 — Delegation-page brief experience

Status: implementation complete; browser visual QA pending

Deliverables:

- Add an operator-readable brief panel to the delegation page.
- Separate deterministic facts from generated narrative visually.
- Show provenance, degradation, missing information, and next actions.
- Include loading, fallback, stale, and error states.

Checklist:

- [x] Brief is visible without reading raw JSON.
- [x] Policy verdict is visually authoritative over prose.
- [x] Model/fallback provenance is visible.
- [x] Missing information and human next steps are accessible.
- [ ] Desktop and mobile layouts are visually verified. Route, content, responsive CSS, stale,
  refresh, and fallback behavior pass automated coverage; no controllable browser was available.

## Phase 4 — Grounding evaluation and telemetry

Status: complete

Deliverables:

- Add labelled brief-grounding cases.
- Measure contradiction, unsupported-authority, and required-fact coverage.
- Record brief views/refreshes without narrative or issue-body telemetry.
- Document fixture versus live-model limitations.

Checklist:

- [x] Unsupported authority claims are a zero-tolerance evaluation gate.
- [x] Structured-fact coverage is measured.
- [x] Model and fallback paths are evaluated separately.
- [x] Telemetry stores no generated narrative or issue body.

Phase 4 uses `evaluations/brief_golden.json` with separate fixture-model and structured-fallback
cases. It reports unsupported-authority count, contradiction count, and required-fact coverage.
View/refresh telemetry contains only delegation ID, source, and stale state.

## Latest verification

Verified on 2026-09-01:

- Focused brief/API/UI/evaluation tests passed: 12.
- Full suite passed: 92 tests.
- Ruff passed for every changed Python file.
- Mypy passed for all 15 source files.
- `brief_unsupported_authority_count` = 0.
- `brief_contradiction_count` = 0.
- `brief_required_fact_coverage` = 1.0.
- Model and structured-fallback evaluation paths both passed.
- Final browser visual inspection remains pending because no browser was connected.

## Definition of done

The feature is complete when an operator can read a concise delegation brief in the UI, clearly
distinguish deterministic authority from generated explanation, understand provenance and stale
state, and see measured grounding quality without prose ever changing authorization.
