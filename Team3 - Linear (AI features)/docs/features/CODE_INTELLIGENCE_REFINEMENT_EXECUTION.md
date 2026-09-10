# Code Intelligence Refinement — Execution Plan

## Goal

Refine Code Intelligence from a useful read-only repository search into a reliable planning
surface: users should be able to find the right code, understand why it was retrieved, inspect
the cited source safely, and identify likely impact before creating or delegating work.

The feature remains evidence-only. It must never create an issue, alter code, approve a policy,
grant a warrant, or widen delegation scope.

## Current baseline (reviewed 2026-09-07)

The current implementation already:

- indexes allowed local repository files by revision;
- extracts file path, language, module, symbols, imports, and reverse dependency edges;
- supports read-only file-path filtering and symbol-name search;
- retrieves code snippets for natural-language questions and displays file/line citations;
- can use the configured provider only to phrase already-retrieved facts;
- redacts known secrets before snippets are displayed or supplied to a provider.

Observed refinement opportunities:

- Text matches can rank UI copy, example prompts, or declarations above real definitions/call sites.
- File Explorer is metadata-only; users cannot inspect a selected file or its symbols in place.
- Citations are visible but not navigable to a bounded, redacted source preview.
- The experience does not yet convert repository evidence into a ticket/delegation planning brief.
- Misconfigured repository roots should produce a recoverable UI state rather than prevent startup.

## Product and safety contract

- The configured repository root is the only searchable source. Paths must remain contained by
  the repository provider and follow its ignore rules.
- File previews and citations are bounded, redacted, and read-only.
- Search ranking is deterministic; the provider cannot select hidden sources or invent a citation.
- A provider may summarize selected evidence but must be visibly distinguished from deterministic
  retrieval and must not receive excluded file content.
- Any future ticket/delegation interaction is a preview only. Existing issue/delegation endpoints
  remain the sole write path and preserve CSRF, authorization, confirmation, and audit checks.
- Telemetry contains metadata only; it never stores raw code, source previews, queries, or prompts.

## Phase 0 — Baseline contract and evaluation set

### Recorded baseline: retrieval flow and ranking (2026-09-07)

1. `CodeIntelligenceService.query()` refreshes or reads the persisted index for the configured
   local repository revision. The index stores only allowed paths and derived metadata
   (language, module, symbols, imports, and reverse dependency edges).
2. For dependency/impact wording with a resolvable indexed symbol, graph evidence is produced
   first: definition (`score 100`), direct call-site/importer (`score 80`), then import evidence
   (`score 70`).
3. Local text retrieval scans allowed files and ranks matching lines by term hits, path hits,
   declaration bonus (`+6`), code-file bonus (`+2`), template penalty (`-2`), and test penalty
   (`-6`). It returns at most two snippets per file and no more than the configured result limit.
4. Generic symbol/path fallback evidence has score `1`. The combined result is sorted by score,
   then path and line. Finally, `ContextBudget` limits provider/display evidence to at most
   12 snippets and 12,000 characters.
5. The optional provider receives only the final redacted, bounded evidence set to phrase an
   answer. It cannot browse the repository, choose hidden files, or perform a write.
   Enforced by `CodeIntelligenceService._provider_facts`, which passes the composed summary
   plus exactly the budgeted, already-redacted snippets shown to the operator, each labelled
   with its citation. This was previously a documented intention only: the provider used to
   receive the composed summary alone, so it could re-word a template but could not read a
   line of code. `tests/unit/test_code_synthesis_grounding.py` pins the contract in both
   directions.

Current failure behavior is not sufficient: an unavailable configured root can currently raise
during application construction. Phase 1 must replace that with a recoverable unavailable state.

### Source-quality metric

For a query that names an indexed symbol, the first citation must be that symbol's definition.
For a dependency query, the definition must precede the direct resolved importer/call-site, and
both must precede generic text, UI, test, or example matches. A false-positive case passes only
when UI/example text is not the first citation for a code-location query.

### Deliverables

- Document the current retrieval/data flow, source limits, and failure behavior.
- Define representative synthetic query cases for exact symbols, definitions, call sites,
  dependency impact, no-match, and excluded/UI-copy false positives.
- Define ranking and source-quality acceptance criteria before changing search behavior.

### Checklist

- [x] Current source types and their ranking order are documented.
- [x] The local-only, redaction, and non-authorizing boundaries are verified.
- [x] A synthetic evaluation set includes positive, negative, and dependency cases.
- [x] A source-quality metric is defined: an exact definition/call-site must outrank UI/example text.
- [x] Failure copy is specified for unavailable/unindexed repository roots.

### Exit criterion

A developer can change retrieval ranking without guessing what counts as a better result.

## Phase 1 — Repository configuration resilience

### Deliverables

- Validate the configured repository root at startup and expose a recoverable unavailable state.
- Show the configured root, revision state, and a clear repair instruction in the UI without
  exposing filesystem paths outside the configured repository boundary.
- Ensure refresh/query/file/symbol endpoints fail safely and consistently when unavailable.

### Checklist

- [x] An unavailable root does not crash application startup.
- [x] Every Code Intelligence endpoint returns a typed safe failure while unavailable.
- [x] The UI explains how to configure `REPOSITORY_ROOT` and does not expose sensitive paths.
- [x] Tests cover a missing root, disabled feature, and successful configured root.

### Exit criterion

Code Intelligence configuration errors are visible and recoverable without affecting unrelated
Warrant workflows.

## Phase 2 — Retrieval quality and grounding

### Deliverables

- Rank exact symbol definitions and resolved dependency/call-site edges above generic text matches.
- Down-rank UI templates, example queries, and documentation-only matches for code-location
  questions while retaining them for explicit documentation queries.
- Attach machine-readable source reasons and ranking tiers to every citation.
- Add deterministic evaluation cases and tests for the ranking contract.

### Checklist

- [x] Exact symbol definitions rank ahead of unrelated text containing the query phrase.
- [x] Dependency queries show resolved definition/import/call-site edges when available.
- [x] Generic matches remain available only after stronger evidence.
- [x] A no-match result is explicit and has no invented location.
- [x] All selected provider facts are derived from the final bounded citation set.
- [x] Evaluation and integration tests cover positive, negative, and regression cases.

### Exit criterion

The first citations shown for supported queries are useful code evidence, not UI copy or an
unrelated declaration.

## Phase 3 — Source navigation and file inspection

### Deliverables

- Make citations and File Explorer rows open a bounded, redacted source preview.
- Show selected file metadata, indexed symbols, imports, and known dependents.
- Add a constrained “Ask about this file/symbol” shortcut that scopes a normal Code Intelligence
  query; it must not inject untrusted file text directly from the browser.

### Checklist

- [x] File/path lookup is repository-contained and follows ignore rules.
- [x] Preview size and line windows are server-bounded and redacted.
- [x] The UI clearly labels selected source, revision, and unavailable/stale state.
- [x] Symbol/dependency metadata is obtained from the persisted index, not client input.
- [x] Tests cover traversal attempts, excluded files, redaction, bounds, and valid previews.

### Exit criterion

A user can move from a result to inspect the relevant safe code context without leaving Warrant.

## Phase 4 — Repository impact preflight

### Deliverables

- Add a read-only impact preview for a selected file or symbol: definitions, direct dependents,
  related paths, and suggested verification areas.
- Let users copy/open a prefilled issue-comment or delegation-draft context containing citations.
- Keep every output advisory; a human must still create/review/confirm any ticket or delegation.

### Checklist

- [x] Impact derives only from current indexed evidence and labels stale/unresolved state.
- [x] Preview does not create or mutate an issue, delegation, policy, or warrant.
- [x] Any handoff includes citations and a context revision, never raw hidden prompts.
- [x] Tests prove crafted client data cannot turn the preview into a write.

### Exit criterion

Users can turn repository evidence into a better-scoped human-reviewed work request.

## Phase 5 — Evaluation, observability, and rollout

### Deliverables

- Expand synthetic golden cases and report ranking/source-quality metrics.
- Record metadata-only usage and safe failure telemetry.
- Verify desktop/mobile UI states and document configuration, privacy, and rollback behavior.

### Checklist

- [x] Golden cases measure exact-symbol, impact, no-match, and false-positive suppression.
- [x] No raw query, code, prompt, or source preview appears in telemetry/audit metadata.
- [x] UI shows loading, empty, unavailable, stale, and error states.
- [x] Workspace feature disablement leaves ordinary Warrant workflows unaffected.
- [x] Production/provider/privacy review is recorded before non-synthetic rollout.

### Exit criterion

The refinement is measurable, safe to disable, and ready for a controlled rollout.

## Implementation order

```text
Phase 0 contract/evaluations
  -> Phase 1 safe configuration state
  -> Phase 2 ranking quality
  -> Phase 3 previews/navigation
  -> Phase 4 impact preflight
  -> Phase 5 evaluation and rollout
```

No phase starts until its predecessor checklist has been verified.
