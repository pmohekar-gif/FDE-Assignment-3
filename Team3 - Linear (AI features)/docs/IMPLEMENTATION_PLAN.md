# Implementation Plan

## Product being built

Warrant is a delegation control plane for coding-agent work. It sits between a work item and an agent, assembles evidence about the requested work, turns unstructured issue text into a validated feature set, and passes those facts to a deterministic policy engine. The engine returns `ALLOW`, `REQUIRE_APPROVAL`, or `DENY`; approved work receives a scoped, expiring warrant and an evidence contract, and returned evidence is checked before an append-only accountability record is completed. AI builds the case but never grants authority.

## Primary user

The primary user is a platform or developer-productivity lead at a 50–400 engineer organisation that already permits coding agents to make repository changes. The economic buyer is a VP Engineering or CTO; the day-to-day champion is the staff engineer or code owner who reviews agent work.

## Problem

Teams can delegate work to agents but cannot reliably answer four connected questions: whether the work should have been delegated, what the agent was allowed to touch, who authorised it, and whether the returned work satisfied the request. OAuth scopes and branch protection are too coarse or too late, while an agent transcript is not a reproducible authorisation record.

## Core workflow

1. An authenticated human or a signed tracker webhook submits a delegation request.
2. Warrant normalises and redacts the issue, scores prompt-injection indicators, and treats all issue content as untrusted data.
3. Hybrid lexical and semantic retrieval returns related issues, surface metadata, active overlapping warrants, and policy precedents.
4. A schema-bound AI provider extracts descriptive facts only: acceptance criteria, affected surfaces, data classes, side effects, missing information, and confidence.
5. Deterministic feature extraction applies the surface map, requester permissions, reversibility, sensitivity, concurrency, retrieval completeness, and provider health. Deterministic facts override model claims.
6. A pure policy engine returns `ALLOW`, `REQUIRE_APPROVAL`, or `DENY` with reason and rule codes. Failure can never produce `ALLOW`.
7. `ALLOW` creates a scoped warrant. `REQUIRE_APPROVAL` renders an evidence brief for an authorised human, who may deny, approve, or narrow but never widen scope. `DENY` records the boundary and route forward.
8. The agent returns a nonce-bound evidence bundle. Deterministic gate 1 verifies scope, expiry, nonce, artefacts, and evidence completeness; schema-bound AI gate 2 judges acceptance criteria and may abstain.
9. Every stage appends a hash-chained audit event, model usage, and value-oriented telemetry. Audit data can be filtered and exported.

## MVP

- Persistent synthetic workspace with users, agents, issues, protected surfaces, policies, delegations, decisions, warrants, approvals, evidence, model usage, and audit events.
- Manual delegation API and UI plus signed/idempotent tracker webhook ingress.
- Real hybrid retrieval over seeded work items, with workspace filtering and lexical-only degradation.
- Provider abstraction with genuine OpenAI-compatible structured inference and an explicitly labelled deterministic fixture provider for offline development and demos.
- Strict extraction and evidence-judgement schemas; malformed or unavailable model output fails closed.
- Versioned deterministic policy engine with terminal deny rules, approval rules, confidence gates, reason codes, and scope narrowing.
- Approval brief, scoped/expiring warrant, single-use nonce, evidence contract, and verification result.
- Hash-chained append-only audit ledger, integrity verification, JSON/CSV export, metrics, and model-usage telemetry.
- Synthetic demo reset, evaluation harness, unit/integration/end-to-end/failure/security tests, and one-command development entry point.

## Explicitly excluded

- A coding agent, code execution environment, sandbox, CI runner, or issue tracker.
- User-facing triage, duplicate detection, or semantic search.
- More than one tracker implementation; a live Linear installation is a post-slice integration and is not required for the offline demo.
- Real customer code, issues, credentials, telemetry, or interview data.
- SSO/SCIM, billing, enterprise IAM, multi-region/HA, Kubernetes, Kafka, Redis, or a dedicated vector database.
- AI-authored policy changes, an AI authorisation field, or an “auto-approve when confident” bypass.

## Architecture

The MVP is a modular Python monolith. FastAPI owns the HTTP/API boundary and server-rendered Jinja UI. An application service sequences normalisation, retrieval, structured extraction, deterministic features, policy, warrant lifecycle, verification, telemetry, and audit. The policy module is a pure function with no provider or persistence access. SQLite with FTS5 is the zero-dependency local persistence and lexical index; deterministic hashed embeddings provide the local semantic channel. The persistence boundary is isolated so PostgreSQL 16 + pgvector remains the deployment migration path described by the R&D specification. This is a deliberate three-week trade-off recorded in `docs/DECISIONS.md`: the working, reproducible vertical slice is prioritised while preserving the data-access seam and retrieval algorithm.

## AI responsibilities

- Extract descriptive facts from untrusted issue text into a closed schema.
- Generate an embedding in real-provider mode when configured; the offline provider supplies deterministic local vectors and is labelled fixture mode.
- Judge each acceptance criterion against a structurally valid evidence bundle, cite evidence, and abstain when support is insufficient.
- Optionally compose human-readable prose without changing a verdict, scope, or evidence contract.

## Deterministic responsibilities

Authentication context, tenant scoping, webhook HMAC/timestamp validation, idempotency, redaction, injection scoring, retrieval fusion, metadata filtering, surface matching, consequence/reversibility classification, evidence sufficiency, policy verdict, approver resolution, self-approval prevention, scope intersection, expiry, nonce consumption, gate-1 verification, audit hashing, timestamps, telemetry, state transitions, and all failure fallbacks.

## Data model

The implemented entities are `workspace`, `user`, `agent_identity`, `issue`, `surface`, `policy_document`, `delegation_request`, `retrieval_evidence`, `extraction_result`, `risk_assessment`, `policy_decision`, `approval`, `warrant`, `evidence_bundle`, `verification_verdict`, `audit_event`, `model_usage`, and `telemetry_event`. Every customer-owned record carries `workspace_id`; cross-workspace lookup returns 404.

## APIs

- `POST /v1/hooks/tracker` — signed, timestamped, idempotent webhook ingress.
- `POST /v1/delegations` — manual/demo delegation.
- `GET /v1/delegations/{id}` and `/brief` — inspect the complete decision and evidence.
- `POST /v1/delegations/{id}/decision` — authorised approve/deny/narrow/defer action.
- `GET /v1/warrants/{id}` — inspect enforceable scope and contract.
- `POST /v1/warrants/{id}/evidence` — nonce-bound evidence return and two-gate verification.
- `GET /v1/audit` — filter/export ledger with integrity status.
- `GET /v1/evaluations`, `/metrics`, `/healthz` — evaluation and operational surfaces.

## Risks

- **Unsafe allow:** mitigated by pure terminal policy rules, deterministic overrides, unknown-as-risk, and an evaluation gate on unsafe allows.
- **Fixture mode mistaken for live AI:** mitigated by a persistent UI/API mode label and separate provider implementations; fixture runs are never reported as live-model evidence.
- **Prompt injection:** mitigated structurally by schemas with no authorising field, deterministic injection features, and policy outside the model path.
- **Local database differs from the proposed Postgres deployment:** mitigated by a narrow repository boundary and explicitly documented migration trigger. PostgreSQL/pgvector concurrency and RLS claims are not made for this build.
- **Audit integrity without an external trust anchor:** the hash chain detects in-database mutation but a fully privileged operator could rewrite the whole chain. Export anchoring is future work.
- **Bypass outside Warrant:** the product cannot stop a user from invoking an agent through another channel. The limitation is stated in the UI and documentation.

## Evaluation

The evaluation CLI runs labelled standard, boundary, adversarial, and degraded cases through the real deterministic policy implementation. It reports exact verdict accuracy, unsafe-allow count/rate, fail-closed correctness, injection correctness, and approval burden to JSON and Markdown. Separate tests cover retrieval relevance, provider schema failure, API/database integration, complete workflow, nonce replay, cross-tenant access, self-approval, scope widening, and injection attempts. Fixture-provider results are labelled simulated; no live-model accuracy or cost is claimed unless a live run actually occurs.

## Implementation sequence

1. Write this plan and build status before production code.
2. Create the package, central configuration, schemas, migrations, seed data, and persistence boundary.
3. Build policy first, with unit tests for terminal rules and failure monotonicity.
4. Implement normalisation, hybrid retrieval, provider gateway, risk features, and the delegation orchestrator.
5. Expose the manual/API vertical slice and approval UI.
6. Add warrant issuance, evidence return, verification, audit integrity, and export.
7. Add telemetry, evaluation, security/failure tests, and demo reset.
8. Refine the UI and required documentation.
9. Verify setup, tests, evaluation, demo reset, failure paths, and repository hygiene from a clean application state.
