# AI Collaboration Disclosure

No provider billing data was available to any of this work. Cost is therefore
`NOT_MEASURED`, not estimated.

**Two assistants were used, in sequence.** OpenAI Codex produced the original build.
Anthropic's Claude, via the Cowork desktop client, then audited that build against its
own specification and implemented the gaps it found. An earlier revision of this file
credited Codex alone; that was inaccurate and is corrected below. The split is recorded
in detail under "Division of work" so a reviewer can attribute any part of the codebase
to the tool that actually produced it.

| Tool / model | Use | Generated contribution | Human verification required | Estimated / measured cost |
| --- | --- | --- | --- | --- |
| OpenAI Codex (GPT-5 family) | Original implementation from the specification | Read the complete Week3 dossier; generated the initial application, conformance tests, evaluation harness, CI/container assets, and first-pass documentation. Test baseline at handover: 116 passed. | Product owner/engineer must review code and claims. Executed pinned tests, lint, mypy, build, evaluation, and Compose validation. | NOT_MEASURED |
| Anthropic Claude (Opus 5, via the Cowork desktop client) | Specification-conformance audit, then gap remediation | Audited the Codex build against the original prompt and produced the gap report and remediation prompts. Then implemented: the Agent intent resolver and empty-answer fix, repository `.gitignore` enforcement and the reverse-dependency graph, broadened secret patterns, CSRF on agent/code endpoints, the runnable demo target repository, verification-check discovery, worktree/PID lifecycle handling, the mock authentication layer, the full operator-shell UI rebuild, the execution-contract and pull-request completeness work, the Bifrost gateway provider, and the Claude/Codex development hooks. Test baseline moved 116 → 220 → 261. | Same bar as Codex: every claim re-verified by running tests, lint, and a live server rather than trusting self-reports. Counts in this file were observed in pytest output, not reported by the assistant that wrote the code. | NOT_MEASURED |
| Deterministic fixture provider inside Warrant | Offline development, tests, and reliable demo replay | Extracts synthetic descriptive features and produces a simulated evidence judgement through the same schemas as a real provider. | UI permanently labels fixture mode; results are excluded from live-model quality claims. | $0 runtime inference; no external call |
| OpenAI-compatible provider inside Warrant | Optional real extraction, criterion judging, and non-authorising prose | Genuine JSON-schema constrained calls when `AI_PROVIDER=openai` and credentials are configured. | Not called or measured. Run a live evaluation before reporting quality, latency, token use, or cost. | NOT_MEASURED |
| OpenRouter MiniMax M3 provider inside Warrant | Experimental synthetic-data live check | Uses OpenRouter slug `minimax/minimax-m3:free`. This endpoint provides JSON output but not server-enforced JSON Schema, so Warrant strips common wrappers, parses JSON, and enforces the same Pydantic schemas client-side. | Use synthetic assignment data only. OpenRouter and the serving inference provider are separate processing layers; provider routing, retention, processing, DPA/ZDR, and sub-processor status must be verified before non-synthetic use. | NOT_MEASURED until `make live-check`; any $0 cost is free-endpoint/promotional evidence, not production unit economics |
| Installed Codex CLI coding runner | Optional external repository execution (a product feature, not an authoring tool) | Adapter invokes the real CLI in a Warrant-scoped isolated worktree when explicitly enabled. | A smoke was attempted, but sandbox app-server initialisation failed and an unsandboxed retry was not authorised. No successful external-agent result is claimed. `make verify-agent-cli` reported **0 flags checked** on the verifying machine, so the argv the runner builds is still unconfirmed against a real CLI. | NOT_MEASURED |
| Grid Dynamics Bifrost gateway provider inside Warrant | Optional real extraction/judging through the GD gateway | Implemented as an OpenAI-compatible `/v1/chat/completions` client with a separate virtual key and dynamic model resolution. | **Never called.** No credential was used and the gateway was never contacted; every test runs against fakes. Verify VPN access, provider routing, and retention before any non-synthetic use. | NOT_MEASURED |
| Pstack (open-pstack for Claude Code / Codex) | Requested development-time architecture/review aid | No contribution to the delivered code. It was installed on the operator's machine after the implementation was complete, so nothing in this repository was produced by it. Equivalent architecture, dependency, and security review was performed manually. | Keep Pstack out of runtime dependencies if used later. | NOT_USED |

## Division of work

**Produced by OpenAI Codex (original build, 116 tests at handover):** the FastAPI/SQLite
application skeleton; the deterministic policy interpreter and authority matrix; the
warrant, approval and scope-narrowing lifecycle; the hash-chained audit ledger and
export; hybrid FTS5 + local-vector retrieval; the fixture, OpenAI-compatible and
OpenRouter providers; the 120-case evaluation harness; the synthetic 400-issue seed; the
Slack Events adapter; the first coding-runner adapter and worktree isolation; CI,
Dockerfile and Compose assets; and the first-pass documentation set.

**Produced by Anthropic Claude (Cowork), 116 → 261 tests:** the conformance audit
(`pmohekar-verification-report.md`, `codex-gap-closure-prompts.md`); the Agent intent
resolver and the fix for the empty-answer defect; `.gitignore` enforcement on the
non-git repository path and the reverse-dependency graph behind impact analysis;
broadened secret patterns and `redact_secrets`; CSRF on the agent and code endpoints;
`demo_repo.py` and the `make demo-repo` target that makes coding sessions actually
runnable; verification-check discovery, worktree teardown, PID tracking and the
protected-branch guard; the mock authentication layer (`auth.py`, sessions and
credentials tables, login page); the complete operator-shell UI rebuild (stylesheet,
every template, and the four previously unsurfaced pages); the execution-contract work
(approval snapshot, restricted-path enforcement, live-warrant re-check, immutability
trigger); the pull-request publisher abstraction and hardened `gh` parsing; the Bifrost
gateway provider; the Claude/Codex development hooks and `verify_agent_cli.py`; and the
documentation corrections, including this one.

**Produced by neither:** all product, market, pricing, and user-research content. See the
integrity boundary below.

**Not used on the delivered code:** open-pstack. It was installed after implementation
was complete; see the table.

## Verification performed in this session

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
