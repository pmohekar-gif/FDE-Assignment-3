# Build Status

## Working

- Complete manual delegation pipeline over persistent fictional data.
- Signed/timestamped tracker webhook validation and delivery-id idempotency.
- Redaction and deterministic prompt-injection scoring before provider inference.
- Hybrid SQLite FTS5 + local-vector retrieval with reciprocal-rank fusion.
- Provider abstraction with labelled fixture and genuine OpenAI-compatible structured inference.
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
- Persisted product/model telemetry and Prometheus-format metrics endpoint.
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
- Repeatable 400-issue/12-user synthetic demo reset.
- Sentence-level fixture acceptance criteria, visibly marked residual UI truncation,
  diversified synthetic issues, and near-duplicate retrieval filtering.
- An explicit local SVG favicon removes the browser's implicit missing-asset request.
- 120-case policy evaluation plus full-pipeline and operational adversarial slices.
- Ordered CI, mypy typecheck, package build, Dockerfile, and seed/app Compose path.
- Pinned `uv.lock` and verified Makefile commands.
- Required implementation, architecture, decision, limitation, demo, AI disclosure, README, and engineering-report documentation.

## In Progress

- No requested conformance implementation remains in progress.

## Not Implemented

- PostgreSQL/pgvector deployment, RLS, HNSW, worker queue, and production concurrency constraints.
- Live Linear adapter and external coding-agent execution.
- Live-model evaluation; no API credential was provided or used.
- Production OAuth/SSO, rate limiting, OpenTelemetry traces/alerts, hosted deployment, or external audit-chain anchoring.
- Real customer interviews, user feedback, and willingness-to-pay evidence; these require authorised human research and were not fabricated.

## Known Issues

- Test suite emits one Starlette/FastAPI TestClient deprecation warning for the installed `httpx` compatibility layer; behaviour is unaffected.
- The in-app browser connection failed to initialise, so UI verification is based on template/API tests and successful local HTTP rendering, not a screenshot inspection.
- Synthetic local vectors and issues do not support a production retrieval-quality claim.
- Compose syntax validates, but the image could not be executed because the local Docker
  daemon was not running.

## Next Highest-Risk Task

- Validate the product premise with five relevant, consent-respecting platform/security users. If validation holds, the next engineering risk is migrating to PostgreSQL/pgvector and implementing the asynchronous Linear adapter without weakening the deterministic authority boundary.

## Latest Verification — 2026-08-30

- Required sequence: Ruff passed; mypy passed; 21 unit and 32
  integration/security/E2E tests passed; evaluation passed. The isolated package build
  then passed with approved package-index access; sdist and wheel are present.
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
