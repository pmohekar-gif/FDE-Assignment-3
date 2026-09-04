# Limitations

## Product boundaries

- Warrant controls only work routed through it. It cannot physically prevent a human or another integration from delegating directly to an agent.
- It does not execute agents, clone repositories, run tests, merge pull requests, deploy, migrate, rotate secrets, or delete data.
- It is not an issue tracker and does not expose triage, duplicate detection, or semantic search as products.
- A thin optional read-only Linear issue import exists, but OAuth, writeback, webhooks, projects, and cycles are not implemented. Real Linear data must not go to OpenRouter.

## Data and scale

- By default, all seeded demo/evaluation data is fictional and synthetic. If `LINEAR_MODE=live` is enabled, the optional live Linear import can store authorized Linear issue title/description after normalization/redaction in local SQLite for the accountability workflow. No Linear API keys are stored, raw descriptions are not stored in adapter metadata/audit/telemetry, and real Linear-imported data must not be sent to OpenRouter. No customer code, repository credentials, interviews, or telemetry were used.
- The seed has 400 issues and 12 users, but all are synthetic; scale parity does not
  establish retrieval quality or user value.
- Evaluation labels are synthetic policy labels. They do not constitute user or customer evidence.
- `verdict_accuracy` on the standard, boundary, adversarial, and degraded slices is a
  policy-interpreter conformance check, not a product-quality measure: the cases are
  authored in the same feature vocabulary consumed by the interpreter. The synthetic
  fixture-backed E2E pipeline slice is the only end-to-end signal in the current run.
- Standard-slice approval burden is 0.4364 against the §24 target of at most 0.35 and
  exceeds K3's 0.40 kill threshold. The current policy trades approval burden for
  fail-closed strictness. Resolving that trade requires user evidence about whether the
  burden is acceptable; it must not be hidden by a unilateral policy relaxation.
- No production-scale concurrency, load, latency, or cost measurement has run.

## AI and retrieval

- Fixture mode is deterministic simulation. It is useful for workflow, safety, and demo testing, not for measuring language-model quality.
- The committed default remains fixture mode. The experimental live path is
  `AI_PROVIDER=openrouter` with MiniMax M3, slug `minimax/minimax-m3:free`, and base URL
  `https://openrouter.ai/api/v1`. It is restricted to synthetic assignment data; never
  point it at real customer issues, code, credentials, or telemetry.
- For the configured MiniMax M3 free endpoint, OpenRouter supports JSON output but does
  not enforce Warrant's JSON Schema server-side. Client-side Pydantic validation with
  `extra="forbid"` is therefore the structured-output enforcement boundary. Parsed JSON
  that fails schema validation is rejected as malformed and fails closed.
- OpenRouter and the serving inference provider are separate processing layers.
  OpenRouter may route to different serving providers, and provider-specific retention
  and processing behaviour must be checked before any non-synthetic use. The dossier
  §26 target claims "no training use · zero retention where offered · named in the
  sub-processor list"; the current free OpenRouter configuration is not claimed to
  satisfy that requirement unless the exact serving-provider path is verified.
- MiniMax M3 advertises a 1,048,576-token context window, but this MVP has not measured
  live extraction F1, judge precision, token use, cost, or latency. MiniMax M3
  free-endpoint p95 preflight latency against the §24 `<12s` target is `NOT_MEASURED`.
  If `make live-check` later measures p95 above target, it must be reported as a
  finding rather than hidden by changing the target.
- The `minimax/minimax-m3:free` endpoint currently reports $0 input/output pricing, but
  free-endpoint availability, rate limits, provider routing, and pricing may change.
  Reported $0 inference cost is promotional/free-endpoint economics and does not
  establish production unit economics or satisfy the `<$0.06` production target.
- If non-synthetic data is ever needed, investigate and explicitly configure OpenRouter
  provider routing controls such as provider allowlists, `data_collection: "deny"`,
  and/or ZDR requirements. Do not silently enable controls that cause automatic fallback
  or a model change.
- Local semantic retrieval uses stable hashed token vectors, not a hosted embedding
  model. Retrieval Recall@K and MRR are `NOT_MEASURED`.
- The fixture evidence judge uses token overlap and is intentionally labelled simulated.
- Provider retry, one structured repair, opt-in fixture fallback, and an in-process
  embedding circuit breaker are implemented. Fallback extraction requires human
  approval; fallback judging cannot return an unqualified pass. Circuit state is not
  shared across replicas.

## Persistence and security

- SQLite replaces the proposed PostgreSQL/pgvector deployment for the current local MVP. PostgreSQL RLS, HNSW, `SKIP LOCKED`, advisory locks, and partial unique constraints are not implemented or claimed.
- Workspace isolation is enforced in repository queries and tests, not by database RLS.
- Local authentication uses synthetic identity headers/context and a demo CSRF token, not OAuth, SSO, MFA, or production sessions.
- The default webhook/CSRF values are intentionally insecure local defaults; deployment must replace them.
- Fixture mode stores a plaintext demo nonce so the browser can simulate agent evidence. Live-provider mode does not store it. Production would deliver the nonce once to an authenticated agent and never expose it in a human UI.
- Hash chaining plus mutation-blocking triggers detect normal in-database edits but do not protect against a fully privileged operator replacing the database and recomputing every hash. No external hash anchor exists.
- Rate limiting, encryption at rest, TLS termination, dependency scanning in CI, and a formal retention/purge job are not implemented.

## Reliability and observability

- Failure tests cover provider 5xx, malformed output, embeddings, unloadable policy,
  duplicate delivery, expired evidence, replay, judge outage, audit-write failure, and
  stale surface maps. They are local adapter simulations, not production chaos tests.
- Telemetry is persisted and `/metrics` exposes counters, but OpenTelemetry traces, dashboards, alerts, circuit-breaker timing, a dead-letter queue, and worker leases are not implemented.
- The application is a synchronous single process. The signed webhook performs processing before returning rather than acknowledging and queueing within a dedicated worker.
- UI routes and core interactions were HTTP-render tested. Screenshot-level visual verification was attempted but the available in-app browser could not initialise; no visual screenshot claim is made.

## Testing and packaging

- Latest test result: 53 passed with one Starlette/FastAPI TestClient deprecation warning
  about the current `httpx` compatibility layer.
- Tests run against a real SQLite file, not PostgreSQL.
- Compose configuration validates. `docker build` and `docker compose up --build` were
  each attempted once, but both stopped because the local Docker daemon was not running.
  Image build and container runtime are `NOT_MEASURED`; hosted deployment is not claimed.

## Commercial and research evidence

- No user interviews, willingness-to-pay evidence, customer trials, or customer feedback were created by this implementation work.
- Pricing, market size, and positioning remain hypotheses in the R&D document.
- No claim is made that this MVP meets SOC 2, ISO 27001, GDPR, HIPAA, or another compliance standard.
