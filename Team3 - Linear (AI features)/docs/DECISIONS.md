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

**Chosen approach:** Seed a curated FDE assignment backlog with five assignment users, cache extraction by
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

## D-ENG-019 — A protected surface is restricted per changed path, not per surface

**Context:** A session's restricted-path list was built by testing each protected surface
glob against the warrant's approved scope with the fnmatch arguments reversed
(`fnmatch(surface_glob, scope_pattern)`). Both directions were wrong. An approval
narrowed to a concrete file (`services/billing/retry.py`) never matched the surface glob
it lived under, so `services/billing/**` stayed restricted and the very file the named
owner had just approved was rejected as restricted material — every protected-surface
delegation failed after approval. A broad grant (`services/**`) matched every nested
glob, silently unlocking the irreversible `services/billing/ledger/**` surface nobody
had approved.

**Options:** Drop the restricted list and rely on the scope check alone; compare
normalised path prefixes; test whether the approved scope entry falls under the surface
glob.

**Chosen approach:** `_scope_grants_surface(scope_pattern, surface_glob)` drops a
protected surface from the restricted list only when an approved scope entry is at least
as specific as that surface — the scope entry itself must fall under the surface glob.

**Why:** It keeps the hierarchy meaningful in both directions: an approved path inside a
protected surface is writable, and a wide grant still cannot reach a nested surface with
its own owners and irreversibility. Deleting the restricted list would have made the
nested-surface protection unexpressible.

**Trade-offs:** For a single-level surface the restricted check now largely duplicates
the scope check. That redundancy is deliberate — it fails closed if scope enforcement is
ever loosened, and it distinguishes `RestrictedPathError` from an ordinary
out-of-scope diff in the audit trail.

**Revisit trigger:** Surfaces gaining semantics beyond globs (ownership by content type,
per-branch protection) would need a real matcher rather than fnmatch.

## D-ENG-020 — A session is refused when its approved scope is absent from the checkout

**Context:** A warrant's scope comes from the issue's declared surfaces, which are only
as good as the tracker's data. When none of those paths exist in `REPOSITORY_ROOT` the
session is doomed before it starts: a real agent has nothing to edit, exits cleanly, and
the session failed minutes later with `agent_failed: agent completed without producing a
reviewable diff` — naming neither the scope nor the repository. Three different causes
(wrong checkout, agent declined the work, writes landed on ignored paths) produced one
indistinguishable message.

**Options:** Leave the late failure and document it; warn but run anyway; refuse at
launch; auto-create the missing paths.

**Chosen approach:** Resolve every approved pattern against the checkout before the
session row exists. If nothing resolves, refuse with a 409 that names the unresolved
patterns, the repository root and its tracked-file count. The resolution is recorded as a
`scope_preflight` event on sessions that do launch, and an exit-zero agent that still
produces no diff is diagnosed into three distinct messages, with the evidence on an
`empty_diff_diagnosed` event.

**Why:** A session that cannot produce a reviewable diff is not a governance outcome, it
is a misconfiguration, and the operator is the only one who can fix it. Auto-creating
paths would manufacture a diff — a fake success in the one place the product must not
have one.

**Trade-offs:** A pattern is treated as resolvable when its parent directory exists, so
legitimately-new files still work; a scope naming only new files in a new directory is
refused and needs the directory created first.

**Revisit trigger:** Tracker-declared surfaces becoming validated against the repository
at issue-creation time, which would make this preflight redundant.

## D-ENG-021 — Hold (defer) is a reversible hold, not a quiet denial

**Context:** "Hold (defer)" wrote an `approvals` row and set the delegation to
`deferred`. Nothing read that status, and two independent locks — `decide()` refusing any
status other than `awaiting_approval`, and `UNIQUE(delegation_id)` on `approvals` — made
it permanent. It was Deny under a gentler label, and neither it nor a denial was visible
anywhere in the UI.

**Options:** Remove the action; make the row non-unique and allow re-decision; add an
explicit resume that lifts the hold.

**Chosen approach:** `POST /v1/delegations/{id}/resume` returns a deferred delegation to
`awaiting_approval`, gated on the same approver set as `decide()`. It deletes the hold
row and appends `approval_resumed` to the audit ledger, so the hold and the lift both
survive in the append-only record even though the current-decision row is cleared. The
recorded decision (action, approver, rationale, scope) is now returned by
`get_delegation` and rendered, and held or denied delegations carry a visible chip in the
triage queue.

**Why:** The four actions must mean what their labels say. A hold that cannot be lifted
teaches operators to deny instead, which loses the distinction the audit trail depends
on.

**Trade-offs:** `approvals` holds only the current decision, so the hold row is removed
on resume; the hash-chained ledger, not that table, is the history.

**Revisit trigger:** A requirement to show every superseded decision in the product UI
would mean making `approvals` append-only with a `current` flag.

## D-ENG-022 — Remote repository URLs stay out of Code Intelligence

**Context:** Code Intelligence indexes one configured local checkout. An obvious
extension is "paste a Git URL, index it, ask questions, attach findings to a ticket."

**Options:** Clone arbitrary URLs into a managed cache and index them; support read-only
host APIs (GitHub/GitLab contents); keep the local-checkout boundary.

**Chosen approach:** Keep the boundary (`PB-002`, `IC-002`). Code Intelligence continues
to read `REPOSITORY_ROOT`; the GitHub adapter stays a read-only pull-request evidence
proxy.

**Why:** `assignment3.md` asks for an issue workflow with triage, duplicate detection,
semantic search, or safe agent delegation — remote code search is none of those, and the
graded core is the delegation path. Accepting a user-supplied URL also adds a
server-side request surface, unbounded disk growth, third-party credential handling and
a supply-chain path into the same process that runs coding-session worktrees, in a
product whose entire claim is bounded authority. That is a security design task with its
own threat model, not a feature increment, and it would compete with the delegation flow
for the remaining time before submission.

**Trade-offs:** A demo cannot point Code Intelligence at an arbitrary public repository
without cloning it locally first and setting `REPOSITORY_ROOT` — which is one command,
and is what `make demo-repo` already does for the demo checkout.

**Revisit trigger:** A validated customer requirement for cross-repository questions,
funded with the isolation work (separate process or container for clones, disk quotas,
credential scoping, and an allow-list of hosts) that requirement implies.

## D-ENG-023 — The provider phrases an answer from the evidence, not from a summary of it

**Context:** `CODE_INTELLIGENCE_REFINEMENT_EXECUTION.md` states the provider "receives
only the final redacted, bounded evidence set". It actually received one composed
sentence containing module names and line labels — no code — so the model could only
re-word a template while the UI labelled the result "AI synthesis".

**Chosen approach:** `_provider_facts()` passes the composed summary plus the same
bounded, secret-redacted snippets the operator sees, each labelled with its citation. The
contextual Agent likewise passes its deterministic facts alongside the composed answer.
The fixture provider is now labelled "SIMULATED synthesis · deterministic fixture, no
model called" instead of "AI synthesis · fixture".

**Why:** Either the documented guarantee or the code had to change, and the guarantee is
the one worth keeping: a grounded answer must be checkable against evidence the reader
can see.

**Trade-offs:** More tokens per query when a real provider is configured. The
`ContextBudget` caps (12 snippets / 12,000 characters) already bound it.

## D-ENG-024 — A blocked agent-CLI hook is named, not blamed on the agent

**Context:** A real `CHIR-1104` session with the `codex` runner failed as
`agent completed without producing a reviewable diff: it exited cleanly and left the
approved paths unchanged`. The runner transcript showed why:

```
hook: UserPromptSubmit
hook: UserPromptSubmit Blocked
```

A `UserPromptSubmit` hook denied the prompt, so the model never received the task and the
CLI exited 0 having done nothing. This project registers only `PostToolUse` and `Stop`
hooks in `.codex/hooks.json`, so the blocking hook came from the operator's own Codex
configuration, which the session inherits because `HOME` and `CODEX_HOME` must reach the
subprocess for it to authenticate.

On the evidence a session can see, that outcome is identical to an agent that read the
code and decided no change was needed — the exit code is 0, the diff is empty, the
approved paths exist. Only one line of the transcript separates "the agent declined" from
"the agent was never asked", and they have opposite remedies.

**Options:** leave it to the operator to read the transcript; fail earlier on any hook
denial; parse the transcript and name the cause.

**Chosen approach:** `blocked_hooks()` reads the CLI's own hook lines. A denial is always
recorded as an `agent_hook_blocked` event, even when the run still produced a diff — a
`PreToolUse` the agent worked around is not a session failure, but a reviewer of a
governed run must be able to see it. When the diff is empty *and* a turn-gating hook
(`UserPromptSubmit`, `SessionStart`) was blocked, that is reported as the cause ahead of
every other explanation, together with the agent-configuration files that actually exist
on the machine.

**Why:** the empty-diff diagnosis is only useful if it points at the thing that has to
change. Naming the agent's own configuration turns an afternoon of debugging the warrant
into a one-line fix, and it keeps the product from taking the blame for an outcome it did
not cause.

**Trade-offs:** the detection depends on Codex's transcript format. It is deliberately
narrow — a `hook: <Name> Blocked` line — and a format change degrades to the previous
generic message rather than to a wrong one. `SessionStart Completed` in the same
transcript is not treated as a denial, which is asserted by test.

**Revisit trigger:** running the agent with an isolated `CODEX_HOME` (`IC-004`), which
would make ambient hooks unreachable and this detection a backstop rather than the
primary diagnosis.

## D-ENG-025 — `CODING_AGENT_ISOLATED_HOME`: give governed sessions their own CODEX_HOME

**Context:** `D-ENG-024`'s diagnostic (`scripts/diagnose_agent_hooks.py --run`) was built
to tell apart a hook that fails (missing environment variable) from one that denies on
purpose. Run against this project's operator's real configuration, it did its job: every
registered hook exited 0, so the block was deliberate — but the denying `UserPromptSubmit`
hook, read from `~/.codex/hooks.json`, turned out to belong to an unrelated project (its
`if [ -f ... ]` guard names a path under a different repository entirely on the operator's
machine). `CODING_AGENT_ENV_PASSTHROUGH` cannot fix that: the hook is not failing for want
of a variable, and it has no logic this project controls or should be editing.

**Options:** (a) leave it to the operator to find and disable the foreign hook by hand;
(b) refuse to launch `codex` with an inherited `HOME`/`CODEX_HOME` at all, breaking
authentication for every operator; (c) give each governed session a private `CODEX_HOME`
that carries just enough of the real one to authenticate and pick the right model, without
the hooks.

**Chosen approach:** (c), gated behind `CODING_AGENT_ISOLATED_HOME` (default off, so
existing deployments are unaffected). `prepare_isolated_agent_home()` copies `auth.json`
verbatim and copies `config.toml` with its `[hooks...]` tables textually stripped
(`strip_hooks_table()`) — not a full TOML parse-and-rewrite, because this project has no
other need for a TOML writer and a targeted textual removal is easier to verify correct.
`hooks.json` is not copied at all. The private home is a sibling of the session's worktree,
never inside it, so it cannot be picked up by the diff or the scope checks that read the
worktree; `_teardown_session` removes it alongside the worktree.

**Why:** a governed session's approval already comes from the warrant, recorded and
audited, with `--ask-for-approval never` because that recorded approval *is* the
authorization. A hook belonging to some other tool on the operator's machine has no
standing to add a second, silent approval gate on top of that — and unlike the CLI's own
approval prompt, its refusal is not even visible as a decision, only as an empty diff.

**Trade-offs:** this only isolates `~/.codex`. A hook registered by an MCP server, a
system-wide shell profile, or anything else Codex loads outside its home directory is
still in force; `agent_config_locations()` and the diagnostic script's output remain the
way to find those. Copying `auth.json` duplicates a live credential on disk per session
(cleaned up with the worktree); this is judged acceptable because the same file already
sits unencrypted in the operator's home directory.

**Revisit trigger:** a Codex release that reads hooks from somewhere other than
`$CODEX_HOME/{hooks.json,config.toml}`, which would need a corresponding change to what
`prepare_isolated_agent_home()` leaves behind.

## D-ENG-026 — Fixed `.codex/hooks.json`'s own path resolution

**Context:** Running `scripts/diagnose_agent_hooks.py --run` against this project's own
`PostToolUse`/`Stop` hooks (registered in this repo's `.codex/hooks.json`, not the
operator's global one) returned `EXIT 127: No such file or directory`, for a path one
directory shallower than where the scripts actually live. The hooks resolved their own
script location with `$(git rev-parse --show-toplevel 2>/dev/null || pwd)`, and this
repository is a subdirectory of a larger Git checkout (the assignment's multi-team
monorepo) rather than its own repository root — so `git rev-parse --show-toplevel`, run
outside a governed session's isolated worktree, resolved to the monorepo root instead of
this project's own directory.

**Chosen approach:** replaced `$(git rev-parse --show-toplevel 2>/dev/null || pwd)` with
plain `$(pwd)` in both hook commands. Codex invokes a project's hooks with its working
directory already set to that project (the same `cwd` a governed session's worktree gets
via `--cd`), so `pwd` is both simpler and correct in both places `git rev-parse` was
trying to cover.

**Why:** this project's own lint-on-edit and stop-reminder hooks were silently inert for
any interactive `codex` session run directly against this checkout (as opposed to a
governed session's isolated worktree, where the worktree's own toplevel happened to make
the old command work by accident). A hook that always fails is worse than no hook: it
still costs the timeout on every matching tool call.

**Trade-offs:** none identified; `pwd` is strictly more predictable here than resolving a
Git toplevel that may not be this directory.

## D-ENG-027 — Name which secret pattern fired, instead of a dead-end refusal

**Context:** Once `D-ENG-025` isolated a governed session from an unrelated project's
ambient hook, a real `codex` run produced an in-scope diff that then hit a second gate:
`_execute` raised `CodingAgentError("diff contains secret-like material and was
redacted")` whenever `redact_diff_content` found anything, ending the session as
`FAILED` with no further detail. `security.SECRET_PATTERNS` includes `email` and
`card_pan`, both deliberately broad (the module's own comment: high-confidence shapes
are ordered first specifically so these two cannot consume part of a real credential) —
an address in a code comment or a long ordinary number is enough to trip either one. The
diff was already safe by the time this fired: `redact_diff_content` had replaced the
matched text with `[REDACTED:KIND]` before the row was ever written to
`diff_artifacts`. Refusing the session anyway threw away a reviewable, already-redacted
diff over a message that gave no way to tell a real leak from an ordinary comment
without re-running the agent and reading raw output by hand — the same shape of problem
`D-ENG-024` solved for hook denials.

**Options:** (a) leave the message as-is and let the operator read the (already
redacted) diff by hand to judge; (b) stop failing the session at all once the content is
redacted, since the stored artifact is safe; (c) keep failing the session, but name which
pattern(s) fired and whether each is a broad or a high-confidence one.

**Chosen approach:** (c). `redact_diff_content` now returns the distinct pattern names
that matched alongside the count (never the matched text). `_diagnose_secret_redaction`
turns that into a message that names each kind and classifies it: `email`/`card_pan` are
flagged as "not by itself evidence of a leak," anything else (`pem_block`,
`connection_string`, `jwt`, `secret_assignment`, `bearer`, `api_key`) as "worth treating
as a real leak until shown otherwise." A `diff_secrets_redacted` event records the kinds
and count on the session timeline before the failure, alongside `agent_hook_blocked` and
`empty_diff_diagnosed` in the same amber styling.

**Why:** the security posture is unchanged — a session that trips a secret pattern still
ends `FAILED`, and the matched text is still never stored or shown anywhere. What changed
is that the operator no longer has to guess which of eight very different patterns fired,
or whether it is worth an escalation, from an unqualified sentence. Option (b) was set
aside deliberately: this project's own hook-blocking incident showed the cost of an
agent-facing gate silently downgrading from "block" to "warn" without a specific,
evidenced reason, and a secret-pattern hit is exactly the kind of event a delegation
control plane should keep failing closed on rather than waving through by default.

**Trade-offs:** the broad/narrow split is a judgment call baked into this project, not
`security.py`'s. If a future pattern is added there without updating
`BROAD_SECRET_KINDS`, it defaults to being treated as high-confidence, which is the
safer failure direction.

**Revisit trigger:** a pattern proves noisy enough in practice (`secret_assignment` is
the next most likely candidate, since it matches on a variable's *name* rather than the
shape of its value) to move into `BROAD_SECRET_KINDS`, or an operator asks for (b) --
completing with a warning instead of failing -- once real-world false-positive rates are
known.

## D-ENG-028 — A secret already in the file is not the agent's leak

**Context:** `D-ENG-027`'s revisit trigger fired within the day, but the cause was not
pattern noise. Repeat real sessions kept failing on `secret_assignment`, and the source
was the demo checkout itself: `demo_repo.py` writes
`infra/deploy/auth.yaml` containing `signing_key_secret: auth-signing-key` — a
Kubernetes-style reference to a secret's *name*, which is exactly the sort of thing that
belongs in deploy config and is not a credential. `redact_diff_content` scanned every
hunk body line, so a diff that merely showed that line as **context** around the agent's
real change failed the session. The agent had written nothing secret, and could not have
avoided the failure except by not touching the file.

This is the same class of defect as the Git-metadata false positive (`D-ENG-024`'s
neighbour): scanning material the agent did not author, then blaming the agent for it.

**Options:** (a) move `secret_assignment` into `BROAD_SECRET_KINDS` so it reports but
reads as low-confidence — treats a provenance bug as a confidence problem and weakens
detection of real assigned credentials; (b) exclude the demo file's specific line —
fixes one checkout and nothing else; (c) track provenance and fail only on secrets the
agent actually introduced.

**Chosen approach:** (c). `redact_diff_content` now returns a `DiffRedaction` splitting
matches into `introduced` and `carried`. A match counts as introduced only when it
appears on an added line **and** its identical text does not appear on a removed or
context line of the same diff. Only `introduced` fails the session. `carried` is still
redacted in the stored artifact and still recorded on the timeline as
`diff_secrets_redacted`, attributed to the file rather than to the agent.

**Why:** the guarantee worth having is "a governed session cannot introduce a
credential", not "a governed session cannot run near one". The second is not a security
property; it is an availability bug that makes whole directories undelegatable, and it
punishes the agent for the repository's existing contents.

**Trade-offs:** provenance is inferred from the diff alone rather than by reading the
base revision, which keeps the function pure and cheap. The removed-or-context
comparison is what makes a whole-file rewrite (which re-adds unchanged content as `+`
lines) read correctly as carried rather than introduced. The residual gap: if an agent
adds a credential whose exact text also happens to appear on a removed line, it reads as
carried — but that text was already in the file by definition, so nothing new leaked.

**Revisit trigger:** a case where introduced-vs-carried needs the base revision rather
than the diff — for example scanning a file the diff does not touch at all — at which
point this moves from a pure function to something that reads the checkout.

## D-ENG-029 — A synthetic secret in a new test is not the agent's leak either

**Context:** `D-ENG-028` closed the case where a match was pre-existing in a *modified*
file. The same real `CHIR-1104` run, driven by an actual `codex` process against the
production checkout, then failed on a different file: a brand-new
`tests/integration/test_github_evidence.py`, whose `FakeGitHubRequester` test double
takes a synthetic, PAT-shaped token to exercise `GitHubEvidenceAdapter`'s auth-header
handling. A new file has no removed or context line — every line is an addition — so
`introduced`-vs-`carried` cannot exempt it; the match reads as introduced by
construction, whichever file it lands in.

This is not a one-off. This project's *own* test suite does the identical thing
throughout `tests/unit/test_coding_scope_and_diff.py` — `sk_live_0123456789abcdef`,
`hunter2-actually-a-real-value`, `ghp_faketoken1234567890abcd` — because exercising
credential-handling code honestly requires a credential-shaped value somewhere. Any
ticket whose implementation needs a new test for auth-adjacent code was going to hit
this.

**Options:** (a) lower `secret_assignment`/`api_key` to `BROAD_SECRET_KINDS` so they
report without failing — weakens detection of a real credential landing anywhere,
including production code, to fix a test-only problem; (b) require every new test to
reuse an existing fixture constant instead of a literal — not something this project can
enforce on an external agent's writing style; (c) recognise the file's *path* as a test,
and exempt matches added there the same way `carried` exempts pre-existing ones.

**Chosen approach:** (c). `TEST_PATH` recognises this project's own convention
(`tests/unit/test_*.py`, `tests/integration/test_*.py`) plus the common conventions of
other stacks (`*.test.ts`, `*.spec.tsx`, `*_test.go`, a `test`/`tests`/`__tests__`
directory segment). `redact_diff_content` tracks the current file from each diff's own
`diff --git a/<old> b/<new>` header as it scans, and a match added under a recognised
test path is counted as `test_fixture` rather than `introduced` -- still redacted in the
stored artifact, still recorded on the timeline, never blocking. A test proves the
narrowness deliberately: the identical token outside a test path still fails.

**Why:** the guarantee worth having is still "a governed session cannot introduce a
credential into the product," not "a governed session cannot write a test that needs a
realistic-looking one." Path-based recognition is coarse compared to understanding that
a string never leaves an in-memory test double, but it is auditable, it is what this
project's own test-writing convention already satisfies, and — unlike a content
heuristic keyed on the word "fake" or "test" appearing in the value — it cannot be
defeated by an agent simply choosing a token that doesn't spell out its own fakeness.

**Trade-offs:** a test file that copy-pastes a *real* credential into a fixture is
exempted just as readily as a synthetic one — this trades a narrow blind spot (secrets
belong in tests even less than elsewhere) for not blocking the overwhelming common case
of legitimate test-writing. `carried` and `test_fixture` are deliberately reported as
separate counts on the timeline rather than merged, so a reviewer can tell "this was
already there" from "this is a new test fixture" without re-reading the diff.

**Revisit trigger:** a real credential is found to have been introduced through a test
path in practice, at which point the exemption should require the value to appear
inside a test-double/mock construct specifically, not merely inside a test-path file.
