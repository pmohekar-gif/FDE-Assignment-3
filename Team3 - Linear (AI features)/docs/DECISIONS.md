# Engineering Decisions

## D-ENG-001 — Preserve Warrant as the selected product

**Context:** The R&D document considers five candidates and explicitly recommends Warrant.

**Options:** Build triage/dedupe/search; build one rejected candidate; build the Warrant MVP.

**Chosen approach:** Build the Warrant delegation → policy → warrant → verification → ledger workflow.

**Why:** It preserves the selected customer outcome and differentiated integrity boundary.

**Trade-offs:** More lifecycle/state work than a recommendation-only feature.

**Revisit trigger:** Only validated primary research firing the dossier’s stated kill criteria.

## D-ENG-002 — Deterministic authority, schema-bound AI evidence

**Context:** Untrusted issue text can manipulate probabilistic outputs, while permission must be reproducible.

**Options:** Model verdict; hybrid score; deterministic verdict over extracted evidence.

**Chosen approach:** The provider schemas have no authorising field; a pure function produces every verdict.

**Why:** Injection resistance, explainable rule IDs, replayability, and objective evaluation.

**Trade-offs:** Policies require explicit maintenance and can be conservative.

**Revisit trigger:** Never for authority. Additional model features may remain advisory.

## D-ENG-003 — Fail closed, except fail hard when audit cannot record

**Context:** Provider, retrieval, policy, and judge dependencies can fail.

**Options:** Fail open; reject every failure; escalate uncertainty to a human.

**Chosen approach:** Degradation resolves to `REQUIRE_APPROVAL`; evidence judging resolves to `INCONCLUSIVE`. Audit-write failure aborts.

**Why:** No failure increases autonomy, while non-critical provider outages do not stop all work.

**Trade-offs:** Infrastructure failures can increase approval burden.

**Revisit trigger:** Reduce the underlying failure rate; never introduce a permissive fallback.

## D-ENG-004 — SQLite/FTS5 local adapter before PostgreSQL/pgvector

**Context:** The dossier proposes PostgreSQL 16 + pgvector. The inspected Week3 directory had no application scaffold, database service, installed PostgreSQL client library, or deployment configuration. A verified end-to-end slice was the highest-priority requirement.

**Options:** Block implementation on PostgreSQL; fake retrieval; implement a real local persistence/retrieval adapter behind a seam.

**Chosen approach:** SQLite with FTS5, real persistence, stable local vectors, cosine ranking, and RRF. Keep database access isolated.

**Why:** It provides a one-command, offline, testable product path now without pretending unimplemented pgvector behaviour exists.

**Trade-offs:** No PostgreSQL RLS, `SKIP LOCKED`, HNSW, or production-grade concurrent warrant constraint is claimed. Local vectors are not hosted embeddings.

**Revisit trigger:** Live integration work, more than one worker, >10k issues, production tenant isolation, or retrieval-quality tuning.

## D-ENG-005 — Jinja + vanilla JavaScript, no SPA build

**Context:** The product needs one decision workspace, one evidence-return interaction, and one audit ledger.

**Options:** React/Vite SPA; server-rendered templates; API-only.

**Chosen approach:** Server-rendered Jinja with hand-written CSS and small fetch-based interactions.

**Why:** One process, no Node runtime/cache in the submission, and presentation-ready state transitions.

**Trade-offs:** Less component tooling and no client-side router.

**Revisit trigger:** User evidence shows approval-screen interaction, rather than the decision model, blocks adoption.

## D-ENG-006 — Fixture provider is a labelled fallback, not fake AI evidence

**Context:** API credentials may be unavailable in evaluation and demos must be reliable.

**Options:** Hardcode model responses silently; require a key; separate fixture and real providers.

**Chosen approach:** Default to a deterministic fixture with a persistent on-screen `SIMULATED / FIXTURE AI` label. Implement an OpenAI-compatible provider for real structured inference.

**Why:** Reproducible demos without misrepresenting simulation.

**Trade-offs:** Fixture extraction/judging quality says nothing about live model quality.

**Revisit trigger:** A configured live provider and a separately labelled live evaluation run.

## D-ENG-007 — Build a self-contained policy evaluation harness

**Context:** The assignment must ship machine-readable evaluation evidence without external accounts.

**Options:** External evaluation platform; local deterministic CLI.

**Chosen approach:** 120 fixed, synthetic, pre-labelled cases with JSON and Markdown reports and an unsafe-allow exit gate.

**Why:** Reproducibility and direct measurement of the hardest guarantee.

**Trade-offs:** It measures policy correctness, not extraction/retrieval/model/customer value.

**Revisit trigger:** A labelled live-model dataset or >1,000 cases requiring collaborative annotation.

## D-ENG-008 — Hash chain plus database mutation triggers

**Context:** Every terminal decision needs an inspectable record.

**Options:** Conventional logs; append-only rows; append-only rows plus external anchoring.

**Chosen approach:** Canonical JSON SHA-256 chain and triggers blocking row update/delete.

**Why:** Cheap, testable tamper evidence appropriate to the MVP.

**Trade-offs:** A privileged operator could rewrite the whole database and recompute the chain.

**Revisit trigger:** External auditor usage or production retention requirements; add periodic external hash anchoring.

## D-ENG-009 — YAML is executable policy, not policy-shaped documentation

**Context:** The initial MVP stored YAML but duplicated its logic in Python branches.

**Chosen approach:** Load and validate YAML outside the decision function, then pass the
closed policy object into a pure interpreter for ordered rules, terminal/fail-closed
flags, complete risk matrix, threshold, and tool grants. Invalid or version-mismatched policy returns
`REQUIRE_APPROVAL / POLICY_UNAVAILABLE`.

**Why:** A policy edit now changes runtime output and the persisted SHA identifies the
exact authorising input. Model schemas still contain no verdict or grant field.

**Trade-offs:** The condition language is intentionally small and typed rather than an
arbitrary expression evaluator.

**Revisit trigger:** Add typed operators only with policy conformance tests; never embed
general code execution in policy documents.

**Live-inference amendment:** The experimental `AI_PROVIDER=openrouter` path uses the
named MiniMax M3 slug `minimax/minimax-m3:free` only for synthetic assignment data,
because no assignment inference budget is available and the endpoint currently has free
access. Compared with an unnamed endpoint, the model identity is explicit. What remains
unresolved is the serving path: OpenRouter and the serving inference provider are
separate processing layers, OpenRouter may route to different providers, and retention
or processing policies can differ. Warrant mitigates this by keeping the deterministic
policy engine authoritative; the model cannot produce an authorisation, widen scope,
grant tools, extend expiry, or consume a nonce. Before non-synthetic use, provider
routing, retention, sub-processor, DPA/ZDR, and `data_collection: "deny"` compatibility
must be explicitly verified.

## D-ENG-010 — Failed evidence checks reduce trust without consuming retry authority

**Context:** Consuming a nonce on a structural evidence error prevents an agent from
correcting the submission, while ignoring the failure would hide operational risk.

**Chosen approach:** Gate-1 failures return structured 422 output, skip the model judge,
set `verification_failed`, retain the nonce, append audit evidence, and reduce the
agent's verified pass rate. Completed gate-2 outcomes consume the nonce.

**Why:** Failure cannot increase autonomy, but a correct resubmission remains possible.

**Trade-offs:** The current trust decrement is a transparent heuristic, not a calibrated
production reputation model.

**Revisit trigger:** Replace the heuristic only after labelled operational data exists.

## D-ENG-011 — Bounded provider recovery, lexical circuit fallback

**Context:** Transient providers and embeddings must not expand authority or create
unbounded request latency. The OpenRouter MiniMax M3 free endpoint supports JSON output
but not server-enforced JSON Schema for this configuration.

**Chosen approach:** Provider transport calls receive two exponential-backoff retries
with jitter; malformed structured output receives one repair attempt carrying the
validation error; an explicit fallback may run only after that budget. OpenAI defaults
to `json_schema`; the configured `minimax/minimax-m3:free` capability defaults to
`json_object`, inlines the schema in the system prompt, strips common wrappers before
parsing, and still validates with the same Pydantic `extra="forbid"` schemas. Three
embedding failures in 60 seconds open a 60-second lexical-only circuit.

**Why:** Recovery is bounded, observable, and monotonic: fallback extraction is marked
degraded and requires approval, while fallback judging can produce at most
`PASS_WITH_EXCEPTIONS`. Every exhausted path reaches human approval or inconclusive
verification.

**Trade-offs:** Circuit state is process-local and the fixture fallback is unsuitable as
live-model quality evidence. OpenRouter free-endpoint pricing, availability, rate
limits, routing, and serving-provider data handling may change; reported $0 cost is
free-endpoint evidence, not production unit economics.

**Revisit trigger:** Multiple replicas, non-synthetic data, measured provider SLOs, or a
paid live-model evaluation; move circuit state and retry budgets into shared operational
infrastructure without changing policy semantics.

## D-ENG-012 — Synthetic scale and delivery evidence remain explicitly local

**Context:** The conformance target asks for approximately 400 issues, a runnable
container path, and CI, but no live tracker, PostgreSQL, or hosted runtime is authorised.

**Chosen approach:** Seed 400 fictional issues/12 fictional users, cache extraction by
issue revision and prompt hash, ship ordered CI plus Docker/Compose, and retain SQLite.

**Why:** This proves local workflow and packaging behavior without fabricating a live
integration, production performance, or customer evidence.

**Trade-offs:** Docker runtime verification remains pending because the local daemon was
unavailable; all production quality/latency/cost metrics remain `NOT_MEASURED`.

**Revisit trigger:** An authorised deployment environment and live integration scope.

## D-ENG-013 — Scope discrepancies reduce autonomy without widening authority

**Context:** An extractor may identify a surface outside issue-declared path hints, or
concurrency subtraction may remove every otherwise valid proposed surface.

**Chosen approach:** Keep authority bounded to extracted ∩ declared scope, retain every
dropped extraction surface as missing-information evidence, and require human review.
When a concurrent warrant holds the whole bounded scope, emit the distinct
`SCOPE_FULLY_HELD_BY_CONCURRENT_WARRANT` reason and refuse empty-scope warrant issuance.

**Why:** Model output cannot widen authority, but security-relevant discrepancies cannot
silently disappear. No failure or conflict increases autonomy.

**Trade-offs:** Strict review and concurrency rules increase the measured approval
burden; a fully blocked delegation must be submitted for fresh evaluation after the
conflict clears.

**Revisit trigger:** Production concurrency work may add a safe re-evaluation workflow,
but it must re-run risk and policy rather than resurrect a stale approval.

## D-ENG-014 — One contextual Agent, zero delegated authority

**Chosen approach:** A single Agent service grounds answers in workspace records,
repository citations, and coding-session artifacts. It persists conversation turns but
cannot approve, issue a warrant, or start execution from a Q&A call.

**Why:** Users get context across issue, policy, code, and execution without creating a
probabilistic permission path. The deterministic Warrant service remains authoritative.

**Trade-offs:** Answers are extractive/deterministic in offline mode rather than a broad
general-purpose model experience.

## D-ENG-015 — Real repository adapter with revision cache

**Chosen approach:** Index the configured checkout directly behind a provider interface,
cache metadata by Git/tree revision, and return bounded file/line snippets. Do not copy
full repository bodies into the database.

**Why:** It provides genuine code grounding with a replaceable seam and a smaller data
retention surface. Path canonicalisation and exclusions are enforced by the provider.

**Trade-offs:** This implementation is local-only and uses lightweight symbol/import/text
analysis rather than a remote SCM API or compiler-grade semantic graph.

## D-ENG-016 — Warrant-gated agents in isolated worktrees

**Chosen approach:** Invoke the installed Codex CLI directly with argv arrays only
after an active warrant. Run in a unique Git worktree, cap time/output/environment,
enforce diff paths after execution, run host-owned verification, and persist the state
machine and mandatory diff. Keep real execution off by default.

**Why:** The external agent receives a concrete contract while the host retains the
authoritative scope, verification, artifact, cancellation, and audit controls.

**Trade-offs:** CLI authentication/sandbox support is environment-specific. In this
workspace, the real Codex smoke could not initialize inside the host sandbox, and an
unsandboxed retry was not authorised; only the adapter and gated test are claimed.

## D-ENG-017 — Slack is an adapter into Warrant, not an alternate workflow

**Chosen approach:** Verify/deduplicate Slack Events, map Slack identities explicitly,
reuse Agent Q&A, and route `start coding` through delegation, deterministic policy,
approval, warrant, and coding-session services.

**Why:** Channel convenience cannot bypass governance. Missing approval produces a deep
link, not execution.

**Trade-offs:** The adapter is locally contract-tested but a real Slack workspace/token
was not available for end-to-end delivery verification.

## D-ENG-018 — Pstack remains development-time only

**Chosen approach:** Do not introduce Pstack into application imports, startup, or
deployment. The requested Pstack-assisted workflow was checked, but no executable or
skill was present, so architecture review, dependency tracing, and security validation
were performed manually.

**Why:** The application must remain independently runnable and the implementation report
must not imply a tool was used when it was unavailable.

**Revisit trigger:** A future development environment provides Pstack; it may assist
analysis and review but still must not become a runtime dependency.
