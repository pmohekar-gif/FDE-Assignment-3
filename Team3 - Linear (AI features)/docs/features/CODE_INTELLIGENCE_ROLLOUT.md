# Code Intelligence — Rollout and Privacy Review

## Evaluation record

Date: 2026-09-07

Run `python evaluations/evaluate_code_intelligence.py` from the project environment. The
deterministic synthetic suite measures five contracts: exact-definition ranking, dependency-edge
grounding, honest no-match handling, UI/example false-positive suppression, and impact-preflight
grounding. It must report a `source_quality_pass_rate` of `1.0` before a controlled rollout.

This is a synthetic regression signal only. It does not establish live-provider quality,
production latency, cost, or customer-data safety.

## Configuration and rollback

- `CODE_INTELLIGENCE_ENABLED=true` enables the read-only surface. Set it to `false` and restart
  to remove Code Intelligence while preserving normal issue, comment, delegation, and policy
  workflows.
- `REPOSITORY_ROOT` must point to an available local checkout. A bad value yields the typed
  unavailable state; it does not stop the application.
- `REPOSITORY_MAX_FILE_BYTES` and `REPOSITORY_MAX_RESULTS` cap indexing/retrieval. Previews are
  additionally capped server-side at 120 lines and 12,000 characters.
- The configured AI provider is optional for Code Intelligence. Retrieval, citations, previews,
  and impact preflight remain deterministic; a provider can only phrase final bounded evidence.

## Privacy and telemetry review

The only Code Intelligence telemetry endpoint accepts this allow-list: event type, operation,
query length, result/source counts, cached/stale/truncated booleans, and approved failure code.
It rejects extra fields. Raw queries, raw code, prompts, source previews, filesystem roots, and
credentials are neither accepted nor stored in telemetry.

Before non-synthetic rollout, the release owner must record approval for the selected repository
scope, provider data handling, retention, incident response, and workspace authorization model.
This implementation has **not** approved a production/provider rollout; that remains a human
release gate.
