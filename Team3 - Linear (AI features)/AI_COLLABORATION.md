# AI Collaboration Disclosure

No provider billing data was available to any of this work. Cost is therefore
`NOT_MEASURED`, not estimated.

**Three passes were used, in sequence.** OpenAI Codex produced the original build. A
second, specification-conformance and remediation pass then audited that build against
its own specification and implemented the gaps it found. A third, defect-remediation
pass on 2026-09-10 fixed the post-approval execution failures, the Governance decision
actions, and the Code Intelligence grounding claim. An earlier revision of this file
credited Codex alone; that was inaccurate and is corrected below. The split is recorded
in detail under "Division of work" so a reviewer can attribute any part of the codebase
to the pass that actually produced it.

**What the application itself records, and what it does not.** The `model_usage` table
records one row per provider call the *product* makes — operation, provider, model, input
/output/reasoning tokens, reported and estimated cost, latency, success and error class —
and `telemetry_events` plus the hash-chained `audit_events` ledger record the surrounding
workflow. Those tables describe Warrant's own inference, not the assistants that wrote
Warrant. No authoring-assistant activity is written to any product table, audit event,
evaluation artifact or generated evidence file, and none should be: the ledger is
evidence about governed delegations, and polluting it with development-time tooling would
make it evidence about nothing. Authoring-tool disclosure lives in this file, which is
what `assignment3.md` asks for ("model/tool use, verification, and total AI spend").

| Tool / model | Use | Generated contribution | Human verification required | Estimated / measured cost |
| --- | --- | --- | --- | --- |
| OpenAI Codex (GPT-5 family) | Original implementation from the specification | Read the complete Week3 dossier; generated the initial application, conformance tests, evaluation harness, CI/container assets, and first-pass documentation. Test baseline at handover: 116 passed. | Product owner/engineer must review code and claims. Executed pinned tests, lint, mypy, build, evaluation, and Compose validation. | NOT_MEASURED |
| Specification-conformance and remediation pass | Specification-conformance audit, then gap remediation | Audited the Codex build against the original prompt and produced the gap report and remediation prompts. Then implemented: the Agent intent resolver and empty-answer fix, repository `.gitignore` enforcement and the reverse-dependency graph, broadened secret patterns, CSRF on agent/code endpoints, the runnable demo target repository, verification-check discovery, worktree/PID lifecycle handling, the mock authentication layer, the full operator-shell UI rebuild, the execution-contract and pull-request completeness work, the Bifrost gateway provider, and the Codex development hooks. Test baseline moved 116 → 220 → 261 during this pass. The suite stood at 388 passed / 1 skipped when the defect-remediation pass began; the 261 → 388 growth is not attributed here because it was not observed in either pass recorded above. | Same bar as Codex: every claim re-verified by running tests, lint, and a live server rather than trusting self-reports. Counts in this file were observed in pytest output, not reported by the assistant that wrote the code. | NOT_MEASURED |
| Deterministic fixture provider inside Warrant | Offline development, tests, and reliable demo replay | Extracts synthetic descriptive features and produces a simulated evidence judgement through the same schemas as a real provider. | UI permanently labels fixture mode; results are excluded from live-model quality claims. | $0 runtime inference; no external call |
| OpenAI-compatible provider inside Warrant | Optional real extraction, criterion judging, and non-authorising prose | Genuine JSON-schema constrained calls when `AI_PROVIDER=openai` and credentials are configured. | Not called or measured. Run a live evaluation before reporting quality, latency, token use, or cost. | NOT_MEASURED |
| OpenRouter MiniMax M3 provider inside Warrant | Experimental synthetic-data live check | Uses OpenRouter slug `minimax/minimax-m3:free`. This endpoint provides JSON output but not server-enforced JSON Schema, so Warrant strips common wrappers, parses JSON, and enforces the same Pydantic schemas client-side. | Use synthetic assignment data only. OpenRouter and the serving inference provider are separate processing layers; provider routing, retention, processing, DPA/ZDR, and sub-processor status must be verified before non-synthetic use. | NOT_MEASURED until `make live-check`; any $0 cost is free-endpoint/promotional evidence, not production unit economics |
| Installed Codex CLI coding runner | Optional external repository execution (a product feature, not an authoring tool) | Adapter invokes the real CLI in a Warrant-scoped isolated worktree when explicitly enabled. | A smoke was attempted, but sandbox app-server initialisation failed and an unsandboxed retry was not authorised. No successful external-agent result is claimed. `make verify-agent-cli` reported **0 flags checked** on the verifying machine, so the argv the runner builds is still unconfirmed against a real CLI. | NOT_MEASURED |
| Grid Dynamics Bifrost gateway provider inside Warrant | Optional real extraction/judging through the GD gateway | Implemented as an OpenAI-compatible `/v1/chat/completions` client with a separate virtual key and dynamic model resolution. | **Never called.** No credential was used and the gateway was never contacted; every test runs against fakes. Verify VPN access, provider routing, and retention before any non-synthetic use. | NOT_MEASURED |
| Defect-remediation pass (2026-09-10) | Post-approval execution failures, the four Governance decision actions, and Code Intelligence grounding | Diagnosed and fixed the reversed protected-surface scope match that made every approved protected-surface session fail; the card-PAN false positive on Git's `index` metadata line; the missing scope-existence preflight and the undiagnosable empty-diff failure; a resumable Hold (defer) with the recorded decision surfaced in the UI; the supersede path for narrowing; approval audit events for approve/narrow; provider grounding on real snippets; the demo checkout deriving one labelled file per seeded path hint. Added 41 regression tests (388 → 429 passing) and cleared the pre-existing lint (49 findings) and mypy (41 findings) backlog. | Every fix reproduced as a failing case first, then re-run: 13 seeded tickets driven end to end through approval, execution, diff and verification; `ruff check src tests` and `mypy src/warrant` both clean; full suite re-run. Counts below were read from pytest output. | NOT_MEASURED |
| Pstack (open-pstack for Codex) | Requested development-time architecture/review aid | No contribution to the delivered code. It was installed on the operator's machine after the implementation was complete, so nothing in this repository was produced by it. Equivalent architecture, dependency, and security review was performed manually. | Keep Pstack out of runtime dependencies if used later. | NOT_USED |

## Division of work

**Produced by OpenAI Codex (original build, 116 tests at handover):** the FastAPI/SQLite
application skeleton; the deterministic policy interpreter and authority matrix; the
warrant, approval and scope-narrowing lifecycle; the hash-chained audit ledger and
export; hybrid FTS5 + local-vector retrieval; the fixture, OpenAI-compatible and
OpenRouter providers; the 120-case evaluation harness; the synthetic 400-issue seed; the
Slack Events adapter; the first coding-runner adapter and worktree isolation; CI,
Dockerfile and Compose assets; and the first-pass documentation set.

**Produced in the specification-conformance and remediation pass, 116 → 261 tests:** the
conformance audit (`pmohekar-verification-report.md`, `codex-gap-closure-prompts.md`);
the Agent intent resolver and the fix for the empty-answer defect; `.gitignore`
enforcement on the non-git repository path and the reverse-dependency graph behind
impact analysis; broadened secret patterns and `redact_secrets`; CSRF on the agent and
code endpoints; `demo_repo.py` and the `make demo-repo` target that makes coding
sessions actually runnable; verification-check discovery, worktree teardown, PID
tracking and the protected-branch guard; the mock authentication layer (`auth.py`,
sessions and credentials tables, login page); the complete operator-shell UI rebuild
(stylesheet, every template, and the four previously unsurfaced pages); the
execution-contract work (approval snapshot, restricted-path enforcement, live-warrant
re-check, immutability trigger); the pull-request publisher abstraction and hardened
`gh` parsing; the Bifrost gateway provider; the Codex development hooks and
`verify_agent_cli.py`; and the documentation corrections, including this one.

**Produced in the defect-remediation pass (2026-09-10), 388 → 444 tests:** the
protected-surface scope fix in `_scope_grants_surface`; `redact_diff_content`, which scans
hunk bodies instead of Git metadata; `_scope_preflight`/`_assert_scope_exists` and the
`scope_preflight` event; `_diagnose_empty_diff` and the `empty_diff_diagnosed` event; the
simulated runner's in-scope target selection and language-aware note; `resume_delegation`
and `POST /v1/delegations/{id}/resume`; the approve-selection guard, the supersede path
for narrowing, and the `approval_approve`/`approval_narrow` audit events; the recorded
decision on `get_delegation` and its UI panel and queue chips;
`CodeIntelligenceService._provider_facts` and the Agent's fact hand-off; the
answerable-example and fixture-labelling corrections on the Code Intelligence page;
`derived_placeholders()` in `demo_repo.py`; the Codex-only tooling documentation; the
lint/type backlog clearance; `blocked_hooks`/`agent_config_locations` and the
`agent_hook_blocked` event; `CODING_AGENT_ISOLATED_HOME`, `prepare_isolated_agent_home`
and `strip_hooks_table`; the `.codex/hooks.json` path-resolution fix; and
`_diagnose_secret_redaction` and the `diff_secrets_redacted` event, which name which
secret pattern fired and whether it is a broad or a high-confidence one instead of
failing a session with no way to tell the two apart. Test files added:
`test_coding_scope_and_diff.py`, `test_code_synthesis_grounding.py`,
`test_governed_session_recovery.py`, `test_delegation_actions.py`,
`test_agent_hook_diagnostic.py`.

**Produced by neither:** all product, market, pricing, and user-research content. See the
integrity boundary below.

**Not used on the delivered code:** open-pstack. It was installed after implementation
was complete; see the table.

## Verification performed on 2026-09-10 (defect-remediation pass)

- **444 tests passed and 1 opt-in real-Codex test skipped** (unit 213, integration 218,
  security 13, e2e 1 collected; the real-Codex e2e test is skipped unless
  `RUN_REAL_CODEX=1` and the CLI is present). Interpreter: CPython 3.10 on Linux, which
  is below the `requires-python = ">=3.11"` floor, so `uv sync` was bypassed and the
  suite was run against pip-installed pinned dependency ranges with `PYTHONPATH=src`.
  **Re-run `make check` on a 3.11+ interpreter before submitting** to confirm the counts
  under the project's own toolchain.
- `ruff check src tests`: clean. It previously reported 62 findings (49 in `seed.py`,
  13 in tests), so `make lint` — and therefore `make check` — was failing in the
  delivered build. `seed.py` was reformatted only; the seeded issue data was proved
  byte-identical before and after by comparing the parsed literals.
- `mypy src/warrant`: clean. It previously reported 41 errors in 4 files and the
  disclosure recorded the last passing run as 2026-08-30. Two of those errors were real
  robustness defects (a mention whose issue row is missing raised a `TypeError` instead
  of a 404; the comment-assist path read attributes off whatever the provider returned
  without checking the schema).
- 13 seeded tickets (PAY-4471, CHIR-1103, CHIR-1104, CHIR-1105, GAU-3101, GAU-3103,
  GAU-3204, PRI-2102, PRI-2103, KRIT-4102, WEB-4519, WEB-3001, PLAT-4104) were driven
  end to end against the generated demo checkout: delegation, deterministic policy,
  named approval where required, warrant issue, simulated coding session, worktree diff,
  host verification. All 13 reached `COMPLETED` with a non-empty diff on a file inside
  the approved scope. Before the fixes, the protected-surface ticket failed on a
  restricted path and the control-plane-scoped tickets failed with the reported
  `agent_failed` message.
- No real external coding-agent (`codex`) session was executed in this pass; the runner's
  argv and gates are covered by tests and by `make verify-agent-cli`, and the real-agent
  smoke remains the separate opt-in e2e test.
- `make eval`, `docker compose config`, and browser screenshot review were not re-run in
  this pass; the results below are from 2026-09-04 and are unchanged by these fixes only
  insofar as no evaluation input was modified.

## Verification performed in the earlier remediation session

- R&D source-of-truth reviewed across all 45 sections, including the interactive scenario data embedded in JavaScript.
- Ruff passed; **261 tests passed and 1 opt-in real-Codex test skipped** as of
  2026-09-04 (unit 129, integration 118, security 13, e2e 1). mypy last passed on
  2026-08-30 and was not re-run since; that result is stale.
- Repository/coding verification covered path traversal, symlink escape, secret/binary/
  generated-file exclusion, revision cache, real line citations, runner argv/environment,
  worktree isolation, warrant/approval gates, mandatory diffs, host verification, Slack
  signatures/deduplication, and non-authorising Agent session Q&A.
- `make eval`: 120 policy cases plus six E2E/operational slices; 0 unsafe allows and
  100% safe E2E/operational rates.
- `docker compose config -q`: passed. Image execution was not verified because the
  local Docker daemon was not running.
- Healthy smoke flow: `REQUIRE_APPROVAL`, `DENY`, and `ALLOW` reference scenarios all produced intended verdicts.
- Complete smoke flow: approval with narrowed scope, warrant, evidence return, verification, and audit-chain check completed.
- Dependency versions resolved and pinned in `uv.lock`.
- Visual browser verification was attempted but the in-app browser connection could not initialise; no screenshot-level verification is claimed.

## Integrity boundary

AI assistance did not generate users, interviews, quotes, willingness-to-pay evidence, customer feedback, live-model scores, latency numbers, cost numbers, or compliance claims. No such evidence exists in this implementation.

Every number in this file was observed in real command output. Where an assistant
reported a result that could not be reproduced, the reproduced result was recorded
instead. Two findings are reported here specifically because they are unflattering: the
one live-model run produced verdict drift and a 50.6-second p50 latency, and the
external-agent CLI check verified zero flags. Neither was omitted to make the build look
finished.

MiniMax M3's experimental free endpoint is not a committed reliability dependency. Its
current free status, availability, rate limits, and serving-provider routing may change.
The shipped default remains the labelled deterministic fixture.
