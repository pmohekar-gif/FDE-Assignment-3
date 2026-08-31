# Engineering Report

## What was built

A working Warrant MVP in the Week3 directory: a modular FastAPI application with a server-rendered original UI, durable data, synthetic demo reset, hybrid retrieval, structured provider abstraction, deterministic policy, human approval/scope narrowing, scoped warrants, evidence verification, hash-chained audit, export, telemetry, evaluation, and automated risk-focused tests.

## Core workflow

The verified flow is issue selection → normalisation/redaction/injection scoring → workspace-scoped lexical/vector retrieval → structured extraction → deterministic risk features → policy decision → optional human approval/narrowing → warrant → evidence → deterministic gate 1 → provider judge or abstention → verification verdict → audit and telemetry.

Three reference cases work:

- `PAY-4471`: `REQUIRE_APPROVAL`.
- `SEC-4502`: `DENY`, including `INJECTION_SIGNAL`; no warrant.
- `WEB-4519`: `ALLOW`, with automatic warrant.

The payment case was additionally verified through narrowed approval, evidence submission, `PASS`, and an intact audit chain.

## Architecture

The product is a modular monolith. FastAPI/Jinja own the interface, SQLite/FTS5 provides local persistence/search, a provider interface owns schema-bound inference, the service owns state transitions, a pure function owns authority, and the audit ledger owns tamper-evident accountability. Detailed diagrams and boundaries are in `docs/ARCHITECTURE.md`.

## AI implementation

`LLMProvider` has deterministic fixture, OpenAI-compatible JSON-Schema, and
OpenRouter MiniMax M3 JSON-object implementations. The OpenRouter
`minimax/minimax-m3:free` path is experimental and synthetic-data only; because that
endpoint does not enforce Warrant's JSON Schema server-side, Warrant strips common
wrappers, parses JSON, and enforces the unchanged Pydantic schemas client-side.
Extraction is closed-schema descriptive output with no authorisation field. Judging
occurs only after deterministic evidence validation and supports abstention. Provider
usage records accept nullable tokens/cost and serving-provider metadata rather than
inventing unavailable values.

No live-provider call was run. Live-model quality, cost, latency, token usage, and
MiniMax M3 free-endpoint p95 preflight latency are `NOT_MEASURED`. `make live-check`
can generate a dated synthetic OpenRouter/OpenAI report; any $0 OpenRouter free-endpoint
cost is reported as promotional/free-endpoint evidence, not production unit economics.

## Deterministic safeguards

- Authority is a pure interpreter over validated, executable YAML.
- Unknown or degraded evidence reduces autonomy.
- The matrix requires approval for irreversible internal modification and denies
  irreversible external side effects.
- Protected surfaces, sensitive data, external effects, overlap, injection, and non-ownership require approval.
- Approvers can narrow but not widen scope.
- Non-code-owner self-approval is rejected in the service layer.
- Warrant tools have explicit allow and deny lists.
- Nonces are hash-checked, single-use, and expiry-bound.
- Files outside scope fail verification before the judge runs.
- Audit update/delete is rejected by database triggers.

## Search and retrieval implementation

SQLite FTS5/BM25 supplies the lexical list. A stable local hashed-token vector plus cosine similarity supplies the offline semantic list. Reciprocal-rank fusion combines them after workspace filtering. Related items are real seeded database records, not hardcoded response objects.

Retrieval Recall@10 and MRR are `NOT_MEASURED`.

## Evaluation results

Measured 2026-08-30 against 120 synthetic, pre-labelled deterministic-policy cases:

| Metric | Actual |
| --- | ---: |
| Exact verdict accuracy | 1.0000 |
| Unsafe allow count | 0 |
| Unsafe allow rate | 0.0000 |
| Fail-closed correctness | 1.0000 |
| Adversarial non-allow rate | 1.0000 |
| Standard-slice approval burden | 0.4364 |
| Verdict distribution | 40 allow / 59 require approval / 21 deny |
| E2E pipeline safe rate | 1.0000 |
| Operational adversarial non-allow rate | 1.0000 |

These are policy results, not model/customer results. `evaluations/results.json` is the machine-readable source.

## Test results

- Unit: **21 passed**; integration/security/E2E: **32 passed**; total **53 passed**.
- Ruff lint and mypy typecheck: **passed**.
- Source distribution and wheel: **built successfully**.
- One TestClient dependency deprecation warning; no test failure.
- Coverage percentage: `NOT_MEASURED`.

## Reliability

Extraction and malformed output failure, embedding degradation, and judge failure are explicit states. All pre-flight provider/retrieval degradation reaches `REQUIRE_APPROVAL`; judge failure reaches `INCONCLUSIVE`. Idempotency, expiry, nonce replay, invalid webhook signature, and audit mutation have verified tests. There is no asynchronous queue/DLQ/worker implementation.

## Security

Secrets are environment-only; `.env` and key material are ignored. Inputs use strict schemas. Webhooks use raw-body HMAC plus timestamp. Browser mutations require CSRF. Cross-workspace lookup returns 404. Untrusted content is redacted/scored before inference. Scope widening, self-approval, nonce replay, out-of-scope files, and audit mutation are blocked in backend code/tests.

This is not a compliance-certified or production-authenticated system.

## Observability

Persisted telemetry records meaningful lifecycle events and schema-repair events.
`/metrics` publishes product counters and verdict distribution. Model usage stores
operation, provider/model, nullable token/cost fields, provider-reported cost,
reasoning/total tokens, serving provider when exposed, latency, success, repair count,
and error class. Audit records the rule/version/reasons rather than raw prompts.
OpenTelemetry tracing and alerts are not implemented.

## Performance

No controlled benchmark was run. Performance and latency are `NOT_MEASURED`.

## Known limitations

SQLite/local vectors instead of PostgreSQL/pgvector, a wholly synthetic 400-issue seed,
fixture provider by default, no live Linear adapter, synthetic local identities,
synchronous processing, and no external audit anchor. See `docs/LIMITATIONS.md`.

## What should be built next

Only after validating the problem with relevant users:

1. Migrate persistence/retrieval to PostgreSQL 16 + pgvector and add concurrency constraints/RLS.
2. Run and label a live-model extraction/judging evaluation.
3. Implement async signed webhook ACK plus worker/lease/DLQ behaviour.
4. Implement the Linear tracker adapter and delivery of approval elicitation.
5. Add bypass detection and external audit hash anchoring.

## Biggest remaining risk

The primary product risk remains the R&D dossier’s own K1/K2 question: reachable teams may not yet delegate consequential write work to agents, or may reject mandatory workflow gating. Engineering cannot validate that. Five consent-respecting interviews and observed demo reactions are still required; no customer evidence was fabricated here.
