# Build Status

## Working

- Complete manual delegation pipeline over persistent fictional data.
- Signed/timestamped tracker webhook validation and delivery-id idempotency.
- Redaction and deterministic prompt-injection scoring before provider inference.
- Hybrid SQLite FTS5 + local-vector retrieval with reciprocal-rank fusion.
- Provider abstraction with labelled fixture, OpenAI JSON-Schema inference, and
  experimental OpenRouter MiniMax M3 JSON-object inference with client-side schema
  enforcement.
- Validated YAML policy interpreter: ordered/terminal/fail-closed rules, complete
  consequence × reversibility matrix, and consequence-derived tool grants.
- Immutable admin-only policy activation with line-aware 422 validation, simulation,
  and a 409 adversarial-allow guardrail.
- Policy simulation diffs the requested last N persisted delegations, orders newly
  allowed cases first, and applies the adversarial guard to simulation and activation.
- Reference scenarios: billing `REQUIRE_APPROVAL`, injected key rotation `DENY`, reversible web copy `ALLOW`.
- Human approve, deny, defer, and narrow-scope controls with backend ownership checks.
- Scoped/expiring warrant with tool allow/deny lists, evidence contract, and single-use nonce.
- Expiry sweeper and reasoned revocation path with audit events, `410 Gone`, delegation
  state changes, and conservative agent trust updates.
- Evidence return, deterministic gate 1, provider judge/abstention, and verification verdict.
- Gate-1 failures return structured 422 results, never invoke the judge, and leave the
  nonce available for a corrected evidence submission.
- Append-only, hash-chained audit ledger with integrity check and CSV/JSON export.
- Admin/owner authorization on JSON and CSV audit API exports, with non-admin access
  rejected at the service boundary.
- Optional HS256 JWT authentication for browser cookies and API bearer clients, with one
  shared demo password across seeded users, distinct database roles, required issuer,
  audience, identity, workspace, and time claims, plus immediate database-backed revocation.
- Persisted product/model telemetry, provider-reported usage/cost/routing metadata,
  schema-repair events, and Prometheus-format metrics endpoint.
- Responsive UI with explicit simulated/live provider labelling and core workflow states.
- Policy workbench containment: the authority matrix owns its horizontal scroller, the
  editor and matrix columns cannot overlap, and the layout switches to one column at
  1100px. Shared empty states use one compact type scale.
- Operator-first dashboard with a decision queue, server-side issue search/team filter,
  pagination across all 400 issues, explicit requester/agent selectors, and pinned demo
  records whose descriptions come from seed data.
- Full pre-approval authority preview, reason/rule glossary, sufficiency threshold meter,
  nine-stage persisted pipeline trace, rationale capture, scope checkboxes, and all four
  backend decision actions. Structured evidence failures remain correctable inline.
- Server-rendered policy workbench for active YAML/matrix/rules, line-aware simulation,
  persisted verdict diffs, guarded activation, and inline 409/422 results.
- Human-readable evaluation page and admin audit workspace with delegation stories,
  chain re-verification, date/agent/authority/surface/verdict filters, cursor pagination,
  and filter-preserving CSV export.
- Derived scope is intersected with declared issue scope and excludes concurrently held
  surfaces. Out-of-declared extraction surfaces remain non-authoritative but are retained
  as missing-information risk signals; a fully held scope cannot produce an empty warrant.
  Untrusted webhook origin lowers sufficiency and requires approval.
- Provider retry/repair/optional fallback and a three-consecutive-failure/60-second
  embedding circuit. Extraction through a fallback is explicitly fail-closed.
- Issue-revision/prompt-hash extraction cache, pre-rank team filtering, and explicit precedents.
- Runtime telemetry and the product dashboard report extraction cache hit rate, using
  `NOT_MEASURED` before any lookup has occurred.
- Non-authorising brief prose with a deterministic structured fallback.
- Contextual, conversation-persisting Agent answers grounded in issue/delegation/policy,
  repository, and coding-session records; responses are always advisory/non-authorising.
- Revision-aware local repository indexing and code Q&A with real file/line/snippet
  citations plus traversal, symlink, ignore, generated-file, binary, size, and secret controls.
- An external Codex runner adapter, a visible mock runner, isolated Git worktrees,
  explicit state/event history, cancellation, path-scope enforcement, verification, and
  mandatory unified-diff artifacts.
- An immutable execution contract that records the authorising approval (or an explicit
  `absent` marker when the warrant auto-allowed), derives restricted paths from the
  surface map, enforces them against runner writes, and is protected from mutation by a
  database trigger. The warrant is re-verified live immediately before the runner starts
  and again immediately before any pull-request publish; a revoked or expired warrant
  aborts with a typed `WarrantNoLongerValid` error recorded in the session timeline.
- A `PullRequestPublisher` abstraction (`GhPullRequestPublisher` plus a test double), so
  the outbound publish path is testable without `gh` installed, and `gh` output that
  cannot be parsed raises a typed error rather than a bare `IndexError`.
- An optional Grid Dynamics Bifrost gateway provider (`AI_PROVIDER=bifrost`) using the
  gateway's OpenAI-compatible `/v1/chat/completions` adapter, a separate virtual-key
  credential, and dynamic model resolution via `GET /v1/models` cached by key
  fingerprint. Never contacted during this build; see "Not Implemented".
- Development-time lifecycle hooks for both Claude Code and Codex (`.claude/`, `.codex/`)
  that lint after Python edits and restate the test standard on stop, plus
  `make verify-agent-cli`. See `docs/AGENT_TOOLING.md`.
- Optional draft PR publication through `gh`, gated on feature flag, auth, compatible
  origin, completed verification, reviewable diff, warrant tool scope, and admin action.
- Slack Events URL verification/app mentions with HMAC freshness, deduplication, thread
  context, Warrant identity mapping, shared Agent answers, governed start, and deep links.
- Repeatable 400-issue/12-user synthetic demo reset.
- Sentence-level fixture acceptance criteria, visibly marked residual UI truncation,
  diversified synthetic issues, and near-duplicate retrieval filtering.
- An explicit local SVG favicon removes the browser's implicit missing-asset request.
- 120-case policy evaluation plus full-pipeline and operational adversarial slices.
- Ordered CI, mypy typecheck, package build, Dockerfile, and seed/app Compose path.
- Pinned `uv.lock` and verified Makefile commands.
- Required implementation, architecture, decision, limitation, demo, AI disclosure, README, and engineering-report documentation.
- The Slack adapter is implemented. Slack is a conversational front door to the same governed delegation engine — nothing it does skips the deterministic policy checks; it either answers from evidence or routes through the same approval path as everything else."

## In Progress

- No requested conformance implementation remains in progress.

## Not Implemented

- PostgreSQL/pgvector deployment, RLS, HNSW, worker queue, and production concurrency constraints.
- Live Linear adapter. 
- A successful real Codex run in this environment. The implementation exists and
  is opt-in; the attempted Codex smoke was sandbox-blocked and an unsandboxed retry was
  not authorised. `make verify-agent-cli` now exists to check the runner's argv against a
  real CLI's `--help`, but on the verifying machine it reported **0 flags checked**: only
  `claude` was installed, and `SubprocessCodingAgentRunner` builds no argv for `claude`.
  The argv the runner constructs for `codex` therefore remains unverified against the
  real tool.
- Any live Bifrost gateway call. The provider is implemented and unit-tested entirely
  against fakes; the gateway was never contacted, no credential was used, and the
  endpoint is VPN-gated. Latency, cost, token use, and output quality are `NOT_MEASURED`
  for this path.
- Slack correctness work. The known Slack defects (investigate intent, status phrasing,
  thread misrouting, feature-flag parity, workspace-scoped deduplication, fast-ack
  decoupling, diff/PR deep links, error-code fidelity, outbound-path test coverage, and
  setup documentation) are all still open and were deliberately deferred this round.
- Broad live-model evaluation. A real credentialled OpenRouter run WAS performed on
  2026-08-31 and is recorded in `evaluations/live-run-2026-08-31.json`: 3 delegations
  against `minimax/minimax-m3:free`, served by GMICloud. It found real problems, so it is
  reported here rather than in the delivered list. See "Live-model findings" below. What
  remains not implemented is a statistically meaningful live evaluation across the full
  120-case slice.
- Production OAuth/SSO, rate limiting, OpenTelemetry traces/alerts, hosted deployment, or external audit-chain anchoring.
- Real customer interviews, user feedback, and willingness-to-pay evidence; these require authorised human research and were not fabricated.

## Known Issues

- Test suite emits one Starlette/FastAPI TestClient deprecation warning for the installed `httpx` compatibility layer; behaviour is unaffected.
- The in-app browser connection failed to initialise, so UI verification is based on template/API tests and successful local HTTP rendering, not a screenshot inspection.
- Synthetic local vectors and issues do not support a production retrieval-quality claim.
- Compose syntax validates, but the image could not be executed because the local Docker
  daemon was not running.
- `gh` is installed but not authenticated, so draft PR publication is locally unavailable.
- Pstack was requested as a development-time aid but no Pstack executable or skill was
  installed; its review discipline was applied manually and it is not a runtime dependency.

## Next Highest-Risk Task

- Validate the product premise with five relevant, consent-respecting platform/security users. If validation holds, the next engineering risk is migrating to PostgreSQL/pgvector and implementing the asynchronous Linear adapter without weakening the deterministic authority boundary.

## Live-model findings — 2026-08-31 (`evaluations/live-run-2026-08-31.json`)

- **Verdict drift.** WEB-4519 expected `ALLOW`; the live run produced `REQUIRE_APPROVAL`.
  The drift is in the fail-closed direction, so no unsafe allow occurred and the
  deterministic policy still held — but live extraction raises approval burden above what
  the fixture slice measures.
- **Latency.** p50 preflight 50,578 ms across three calls (49.1s / 50.6s / 70.4s). That
  disqualifies this free endpoint from an interactive gate. p95 is `NOT_MEASURED`; three
  calls cannot support one.
- **Cost.** $0 measured, explicitly `NOT_COMPARABLE_TO_PRODUCTION_TARGET` — free-endpoint
  promotional economics, not unit economics.
- **Routing.** OpenRouter and the serving provider (GMICloud) are separate processing
  layers; serving-provider retention behaviour must be verified before any non-synthetic
  data is sent.

## Latest Verification — 2026-09-04

- Ruff passed. **261 tests passed and 1 opt-in real-Codex test skipped** (unit 129,
  integration 118, security 13, e2e 1). mypy was NOT re-run: the verifying environment
  had no mypy installed, so the typecheck result is stale as of 2026-08-30.
- Counts were confirmed file-by-file rather than in one run. The sandbox used for
  verification timed out on whole-directory runs, so `tests/unit` and `tests/integration`
  were executed in named batches and the per-file summaries added up. Every file was
  observed passing; no count below was inferred.
- Closed this round: the execution contract now records a real approval snapshot
  (including an explicit `absent` marker for auto-allow, instead of an ambiguous null),
  `restricted_paths` is derived from the surface map and actually enforced, the warrant
  is re-checked live before the runner starts and again before any PR publish,
  `contract_json` is protected by an update-rejecting trigger, `head_revision` is
  persisted whenever a diff is captured rather than only on publish, and `gh` output
  parsing raises a typed `PullRequestPublishError` instead of a bare `IndexError`.
- One existing UI test was changed deliberately:
  `test_coding_session_page_renders_stepper_multi_check_verification_and_diff` asserted
  the template's `"uncommitted worktree state"` fallback, which only rendered because
  `head_revision` was always NULL. That bug is fixed, so the assertion was inverted to
  require the fallback is now unreachable. The test was not weakened.

## Latest Verification — 2026-09-03

- Ruff and mypy passed; **223 tests passed and 1 opt-in real-Codex test skipped** (unit 100,
  integration 109, security 13, e2e 1). mypy was NOT re-run in this session: the
  verifying environment had no mypy installed, so the typecheck result is stale.
- The worktree-retention test exposed a terminal-state visibility race: `COMPLETED`
  became observable immediately before retention cleanup. Cleanup now reserves the new
  terminal slot before publishing the state, and selection/removal is serialized. The
  focused lifecycle checks and subsequent full suite pass.
- Evaluation and package verification below are from the 2026-08-30 run and were not
  re-executed.
- `make eval`: 120 policy cases, 0 unsafe allows, 100% fail-closed correctness,
  100% E2E safe rate, and 100% operational-adversarial non-allow rate.
- Standard-slice approval burden is 0.4364: outside the ≤0.35 target and above K3's
  0.40 threshold. It is reported but is not a build-failing gate.
- `docker compose config -q`: passed. `docker build` and `docker compose up --build`
  were each attempted once and both reported that the local daemon was unavailable;
  image build and container runtime remain `NOT_MEASURED`.
- Seed implementation: 400 issues, 12 users, 3 agents, 6 governed surfaces.
- Automated verification covered the policy overflow/1100px CSS contract, shared empty
  typography, sentence-level criteria, long-criterion ellipsis/title behaviour,
  retrieval title/score diversity and near-duplicate removal, and the favicon's 200
  response. Live HTTP checks returned 200 for `/`, `/policy`, `/static/app.css`, and
  `/static/favicon.svg`; the exercised server log contained no 404.
- Browser-rendered verification: **none**. The in-app browser reported `No browser is
  available`, so the requested 1280px, 1440px, and 1920px visual checks, the below-1100px
  stacked layout inspection, and screenshot/click-through inspection were not performed.
  Those visual behaviours are verified by CSS and automated tests only; no screenshot
  claim is made.
