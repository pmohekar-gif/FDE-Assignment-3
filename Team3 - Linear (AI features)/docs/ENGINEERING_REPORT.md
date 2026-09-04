# Engineering Report

## What was built

A working Warrant MVP in the Week3 directory: a modular FastAPI application with a
server-rendered original UI, durable data, synthetic demo reset, hybrid issue retrieval,
structured provider abstraction, deterministic policy, human approval/scope narrowing,
scoped warrants, evidence verification, hash-chained audit, export, telemetry,
evaluation, a contextual Agent, real-repository Code Intelligence, governed external
coding-agent adapters, Slack Events integration, and automated risk-focused tests.

## Core workflow

The verified flow is issue selection → normalisation/redaction/injection scoring → workspace-scoped lexical/vector retrieval → structured extraction → deterministic risk features → policy decision → optional human approval/narrowing → warrant → evidence → deterministic gate 1 → provider judge or abstention → verification verdict → audit and telemetry.

Three reference cases work:

- `PAY-4471`: `REQUIRE_APPROVAL`.
- `SEC-4502`: `DENY`, including `INJECTION_SIGNAL`; no warrant.
- `WEB-4519`: `ALLOW`, with automatic warrant.

The payment case was additionally verified through narrowed approval, evidence submission, `PASS`, and an intact audit chain.

The `WEB-4519` allow case was verified through a visibly simulated coding runner in an
isolated temporary Git checkout. The session preserved the original checkout, enforced
the warrant's `web/**` scope, ran `git diff --check`, persisted its event timeline, and
produced a reviewable unified diff. The same session was then queried through the Agent.

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

A real live-provider call WAS run on 2026-08-31 — 3 delegations through OpenRouter
against `minimax/minimax-m3:free`, served by GMICloud, recorded in
`evaluations/live-run-2026-08-31.json`. Two findings matter. First, verdict drift:
WEB-4519 was expected to be `ALLOW` and the live extraction produced
`REQUIRE_APPROVAL` — drift in the fail-closed direction, so no unsafe allow, but the
approval burden a live provider imposes is higher than the fixture slice suggests.
Second, latency: p50 preflight was 50,578 ms, which rules this endpoint out for an
interactive gate. Cost read $0 because the endpoint is free-tier promotional pricing and
is explicitly not comparable to a production target. p95 preflight latency and token
usage remain `NOT_MEASURED` — three calls cannot support a p95. `make live-check`
can generate a dated synthetic OpenRouter/OpenAI report; any $0 OpenRouter free-endpoint
cost is reported as promotional/free-endpoint evidence, not production unit economics.

## Agent and Code Intelligence

The contextual Agent resolves optional issue, delegation, coding-session, and repository
scope. It cites the exact stored records used, persists conversations/messages, and marks
every response `authoritative=false` and `authorising=false`. Code questions route to a
revision-aware index of the configured checkout and return real paths, line ranges,
snippets, symbols, and imports. The provider excludes secrets, ignored/generated trees,
binary/non-UTF-8/oversize content, traversal, and symlink escapes. Snippets redact
secret-like values before leaving the service.

## Coding execution and pull requests

`CodingAgentRunner` has a real Codex CLI subprocess adapter plus an
explicitly labelled mock. Real execution is disabled unless
`EXTERNAL_CODING_AGENT_ENABLED=true`. A session requires an active warrant granting both
file writes and test execution, snapshots an immutable contract, creates a fresh Git
worktree/branch, limits environment/time/output, supports cancellation, redacts logs,
and rejects out-of-scope or secret-bearing diffs before host-owned verification. A
reviewable diff artifact is mandatory. Draft PR publication additionally requires the
warrant tool grant, completed verification, an admin/owner request, the feature flag,
valid `gh` auth, and a GitHub origin; no merge path exists.

The contract is now genuinely complete rather than partially symbolic. It records the
approval that authorised the session — approver, timestamp, and narrowed scope — and
where a warrant auto-allowed with no human in the loop it records that explicitly
instead of leaving a null that cannot be distinguished from an omission.
`restricted_paths` is derived from the surface map intersected with the granted scope
and is enforced against every write, so a path that is inside the warrant's scope but
inside a restricted surface still fails with a typed `RestrictedPathError`. Because a
warrant can be revoked while a session runs, the warrant is re-verified immediately
before the runner is invoked and again immediately before any publish; either check
failing aborts with `WarrantNoLongerValid` and writes that fact to the event timeline. A
database trigger rejects any `UPDATE` of `contract_json`, so "immutable" is enforced by
the store rather than by convention.

Publication goes through a `PullRequestPublisher` abstraction with a `gh`-backed
implementation and a test double, which makes the outbound path testable on machines
without `gh`. `gh` output that cannot be parsed into a URL and number raises a typed
`PullRequestPublishError` instead of the bare `IndexError` it used to, so a malformed
response can never be recorded as a successful publish. `head_revision` is persisted
whenever a diff is captured, not only when a PR is published, so every diff artifact
names both endpoints of its comparison.

A real Codex smoke was attempted. The authenticated CLI was present, but its in-process
app-server client failed under the execution sandbox (`Operation not permitted`). The
requested unsandboxed retry was rejected, so no successful real-agent run is claimed.
The gated real-run E2E test remains available via `RUN_REAL_CODEX=1` in an authorised
environment. `gh` was present but unauthenticated, so PR publication was not exercised.

## Slack

The Slack Events endpoint verifies raw-body v0 HMAC signatures and five-minute freshness,
deduplicates event IDs, ignores bots/unsupported events, fetches bounded thread context,
and replies through the Web API when a bot token exists. Q&A reuses the same Agent.
Status reads the same session records. `start coding` maps Slack identities, creates or
reuses a Warrant delegation, stops on deny/approval, and only launches after an active
warrant. Local integration tests use signed events; no real workspace was connected.

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

- Total: **261 passed, 1 skipped** across unit, integration, security, and E2E suites
  (unit 129, integration 118, security 13, e2e 1). The only skip is the explicit opt-in
  real-Codex smoke. Counts were gathered per-file because whole-directory runs exceeded
  the verifying sandbox's timeout; every file was observed passing.
- Ruff lint: **passed**. mypy last passed 2026-08-30 and was not re-run; that result is
  stale.
- Source distribution and wheel: **built successfully**.
- One TestClient dependency deprecation warning; no test failure.
- Coverage percentage: `NOT_MEASURED`.

## Reliability

Extraction and malformed output failure, embedding degradation, and judge failure are explicit states. All pre-flight provider/retrieval degradation reaches `REQUIRE_APPROVAL`; judge failure reaches `INCONCLUSIVE`. Idempotency, expiry, nonce replay, invalid tracker/Slack signatures, repository escapes, coding scope violations, runner environment/argv, and audit mutation have verified tests. Coding sessions use local background threads; there is no durable asynchronous queue/DLQ/worker implementation.

## Security

Secrets are environment-only; `.env` and key material are ignored. Inputs use strict schemas. Webhooks use raw-body HMAC plus timestamp. Browser mutations require CSRF. Cross-workspace lookup returns 404. Untrusted content is redacted/scored before inference. Scope widening, self-approval, nonce replay, repository traversal/symlink escape, out-of-scope coding diffs, secret-like artifacts, unauthorised cancellation, and audit mutation are blocked in backend code/tests.

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
in-process execution state, no verified real Slack/Codex/PR run, and no external
audit anchor. See `docs/LIMITATIONS.md`.

## What should be built next

Only after validating the problem with relevant users:

1. Migrate persistence/retrieval to PostgreSQL 16 + pgvector and add concurrency constraints/RLS.
2. Run and label a live-model extraction/judging evaluation.
3. Implement async signed webhook ACK plus worker/lease/DLQ behaviour.
4. Implement the Linear tracker adapter and delivery of approval elicitation.
5. Add bypass detection and external audit hash anchoring.

## Biggest remaining risk

The primary product risk remains the R&D dossier’s own K1/K2 question: reachable teams may not yet delegate consequential write work to agents, or may reject mandatory workflow gating. Engineering cannot validate that. Five consent-respecting interviews and observed demo reactions are still required; no customer evidence was fabricated here.
