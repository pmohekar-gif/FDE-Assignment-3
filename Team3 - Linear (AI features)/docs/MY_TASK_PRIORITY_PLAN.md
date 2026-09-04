# Assigned Feature Priority Plan

Owner slice: Skills, Loops/background automations, real Linear adapter, real GitHub
adapter, and project/cycle/update summaries.

## FDE Framing

This assignment is not asking the team to clone Linear AI. It is a Forward Deployed
Engineer exercise: understand the customer's existing workflow, connect to the tools
they already use, find the operational gap, and ship a practical wedge that works in
their environment.

For Warrant, the right positioning is:

```text
Linear remains the system of record for product and engineering work.
Warrant sits on top as the accountability and control layer for risky AI-agent
delegation.
```

That means similar feature names should have Warrant-specific behavior:

- Linear summaries tell teams what happened. Warrant summaries explain what changed,
  what authority was granted, who approved it, what evidence came back, and what still
  needs human review.
- Linear Skills run productivity workflows. Warrant Skills run governed workflows with
  audit, scope, policy, and evidence boundaries.
- Linear Loops automate work management. Warrant Loops automate accountability checks,
  stale approvals, expiring warrants, and missing evidence.
- Linear and GitHub adapters are not generic sync features. They are field connectors
  that let Warrant observe real issue and code-change context while keeping authority in
  the deterministic Warrant policy.

FDE implementation principles:

- Start with a thin real integration, not a huge platform rewrite.
- Preserve the customer's existing workflow instead of forcing a new one.
- Make the demo field-real: "Here is a Linear issue; here is how Warrant governs the
  AI-agent delegation around it."
- Build only the minimum adapter surface needed for the workflow.
- Treat every integration as untrusted input until normalized, scoped, audited, and
  policy-checked.
- Avoid product parity with Linear unless it directly supports Warrant's differentiated
  accountability layer.

## Current Codebase Baseline

Warrant is a FastAPI/Jinja/SQLite modular monolith. The product already implements a
safe coding-agent delegation workflow: issue intake, redaction, hybrid retrieval,
schema-bound AI extraction, deterministic risk assessment, YAML policy, human approval,
scoped warrants, evidence verification, telemetry, and a hash-chained audit ledger.

The existing code is organized around these seams:

- `src/warrant/main.py`: HTTP API and server-rendered UI routes.
- `src/warrant/service.py`: domain workflow, mutations, audit, telemetry, approvals,
  warrants, evidence, triage application, and delegation briefs.
- `src/warrant/retrieval.py`: hybrid search, related/duplicate suggestions, and
  delegation retrieval context.
- `src/warrant/triage.py`: advisory team/priority/label recommendations.
- `src/warrant/providers.py`: fixture, OpenAI-compatible, and OpenRouter provider paths.
- `src/warrant/db.py`: SQLite schema and migrations.
- `src/warrant/schemas.py`: Pydantic request/response contracts.
- `policies/default.v1.yaml`: deterministic authority policy.
- `docs/features/`: completed feature execution notes for triage recommendations,
  semantic search, related issues, and delegation briefs.

Already implemented adjacent features:

- Triage recommendations for team, priority, and labels.
- Related/duplicate issue suggestions.
- User-visible semantic issue search.
- Delegation briefs with a non-authorising contract, cache, refresh, telemetry, and
  grounding evaluation.
- Signed tracker-shaped webhook ingress.
- OpenRouter live-check path over synthetic data.

Still explicitly not implemented in the product docs:

- Real Linear adapter.
- Real GitHub adapter.
- External coding-agent execution.
- Background scheduler/worker system.
- Project/cycle/update summaries.
- Skills or reusable AI workflow definitions.

## Recommended Priority Order

### 1. Real Linear Adapter

Priority: first.

Why this moves to the top under the FDE framing:

- Warrant is supposed to sit on top of Linear. Without at least a thin Linear adapter,
  the product remains a strong local simulation but a weaker FDE story.
- The codebase already has a tracker-shaped signed webhook and an internal issue table,
  so the first adapter does not need to be broad.
- A narrow adapter creates the field proof: import or receive one Linear issue, then run
  existing Warrant triage, related issues, delegation, policy, warrant, and audit flows.
- This is not cloning Linear. It is connecting to Linear as the customer's system of
  record and adding Warrant's control layer around agent delegation.

Suggested MVP:

- Build the adapter as an optional boundary, not core workflow logic.
- Add `LINEAR_API_KEY` or OAuth placeholder configuration, but do not commit keys.
- Support one narrow import path:
  `POST /v1/adapters/linear/import-issue` with a Linear issue ID/key.
- Map Linear fields to the existing `issues` table:
  external key, title, description, team, labels, priority, updated timestamp, and URL.
- Re-import must be idempotent and should increment issue revision only when relevant
  fields change.
- Preserve normalized/redacted text and do not send real Linear data to OpenRouter free
  endpoint.
- Add a field-demo route or CLI command that imports one issue and immediately shows the
  Warrant workflow that can govern it.

Definition of done:

- One Linear issue can be imported into Warrant without weakening workspace boundaries.
- Imported issues can use existing triage/search/related/delegation workflows.
- Re-import behavior is deterministic and revision-safe.
- Tests use HTTP stubs only; no test makes a real Linear network call.
- Docs clearly state data-handling rules and limitations.

Estimated effort: medium-high if scoped to import only; high if webhook sync is added.

Main files to touch:

- New `src/warrant/adapters/linear.py`
- `src/warrant/config.py`
- `src/warrant/db.py`
- `src/warrant/main.py`
- `src/warrant/security.py` if webhook verification differs.
- Adapter tests with HTTP stubs only; no real network calls in tests.

### 2. Project/Cycle/Update Summaries

Priority: second.

Why this is easiest:

- It can reuse the existing `delegation_brief` pattern: versioned response contract,
  generated prose plus structured facts, deterministic fallback, cache/stale state, and
  telemetry that excludes raw content.
- It does not require external credentials, OAuth, webhook subscriptions, or a worker
  queue.
- Seed data already has teams, issues, priorities, labels, delegations, warrants,
  verification results, telemetry, and audit events. That is enough for synthetic
  project/team update summaries.
- It fits the current architecture without weakening the authority boundary.
- After the Linear adapter, the summary can be shown as a Warrant layer over imported
  Linear work instead of as a standalone Linear-like summary clone.

Suggested MVP:

- Add a read-only summary endpoint:
  `GET /v1/summaries/team/{team}` or `GET /v1/projects/{team}/summary`.
- Summarize current issue counts, priority mix, recent delegation verdicts, open
  approval queue, risky surfaces, expired/revoked warrants, and evidence failures.
- Include Warrant-specific sections:
  pending human approvals, active warrants, missing evidence, scope conflicts,
  policy-denied work, and audit-chain status.
- Return both a structured fact snapshot and generated/fallback prose.
- Add a simple dashboard panel for "Team update summary".
- Add telemetry for summary viewed/refreshed, without storing generated prose or issue
  bodies.
- Add synthetic evaluation that checks for unsupported authority claims and required
  fact coverage, similar to delegation brief evaluation.

Definition of done:

- A user can generate a team/project-style update from existing Warrant data.
- The response makes clear that prose is explanatory only.
- Summary generation is cached or refreshable.
- Tests prove no summary can change policy, approval, warrant, or issue state.

Estimated effort: low to medium.

Main files to touch:

- `src/warrant/schemas.py`
- `src/warrant/service.py`
- `src/warrant/main.py`
- `src/warrant/templates/dashboard.html` or a new template
- `src/warrant/providers.py` only if a new provider method is needed; preferably reuse
  `brief()` with a summary-specific prompt wrapper if the contract remains compatible.
- `src/warrant/db.py` if summaries are cached.
- `evaluations/` and `tests/`

### 3. Real GitHub Adapter

Priority: third.

Why this moves ahead of Skills/Loops:

- Warrant's unique value is safe coding-agent delegation. For that, GitHub metadata is
  more differentiating than generic workflow automation.
- The current product uses synthetic `path_hints` and static `policies/surfaces.yaml`.
  A read-only GitHub adapter can make ownership and scope evidence feel field-real.
- This should still be carefully scoped: start with CODEOWNERS and PR/diff metadata, not
  merge/deploy actions.

Suggested MVP:

- Start with read-only repository metadata.
- Add `GITHUB_TOKEN` and repository config.
- Parse CODEOWNERS or import a simple path-owner mapping into governed surfaces.
- Add a way to attach a PR/diff reference to an evidence submission.
- Verify changed files against warrant scope before the evidence judge runs.
- Do not implement merge, deploy, secret rotation, or branch changes.

Definition of done:

- Warrant can map real repo paths to owners/protected surfaces from GitHub metadata.
- Evidence can include a PR/diff reference and changed files are checked against warrant
  scope.
- Tests use stubs/fixtures only.
- No GitHub write action is available.

Estimated effort: high.

Main files to touch:

- New `src/warrant/adapters/github.py`
- `src/warrant/config.py`
- `src/warrant/db.py`
- `src/warrant/service.py`
- `src/warrant/main.py`
- `policies/surfaces.yaml` migration logic or replacement/import path
- Tests for CODEOWNERS parsing, scope checking, token absence, API failure, and no
  write permissions.

### 4. Skills

Priority: fourth.

Why this comes after adapters and summaries:

- A "skill" is best represented as a reusable workflow definition. Project/update
  summaries provide the first concrete workflow to wrap as a skill.
- The codebase already has several workflow-like actions: related issues, semantic
  search, triage recommendation, delegation brief, and live-check. Skills can unify
  these behind named reusable recipes.
- Skills can begin as local YAML/JSON definitions instead of external integrations.
- Under the FDE framing, Skills should package Warrant-specific field workflows, not copy
  Linear's generic productivity skills.

Suggested MVP:

- Add a `skills/` config folder or `skills` table.
- Define a small stable skill contract:
  id, name, description, inputs, allowed operation, output contract, safety boundary,
  enabled flag.
- Ship two built-in skills:
  `weekly_warrant_update` and `review_agent_delegation_candidate`.
- `weekly_warrant_update` calls the project/team accountability summary path.
- `review_agent_delegation_candidate` calls triage recommendation, related issues,
  semantic search, and Warrant policy preview, but remains advisory until the existing
  delegation endpoint is explicitly used.
- If the Linear/GitHub adapters exist, skill inputs can reference imported Linear issues
  and GitHub-derived scope metadata.
- Add `GET /v1/skills` and `POST /v1/skills/{id}/run`.
- Persist skill runs for audit/telemetry.

Definition of done:

- A user can run a named reusable workflow without remembering endpoint details.
- Skill output remains advisory unless it enters an existing explicit mutation path.
- Skill runs are auditable and workspace-scoped.

Estimated effort: medium.

Main files to touch:

- New `src/warrant/skills.py`
- `src/warrant/schemas.py`
- `src/warrant/service.py`
- `src/warrant/main.py`
- `src/warrant/db.py`
- New docs under `docs/features/`
- Tests for read-only behavior, workspace isolation, bad input, and audit events.

### 5. Loops / Background Automations

Priority: fifth.

Why this should not be first:

- The current app is synchronous and single-process. There is no scheduler, queue,
  lease table, worker process, retry queue, or background-job observability.
- Automations are easier and safer once Skills exist, because a loop can run a named
  skill on a schedule or event trigger.
- Real background execution creates reliability and duplicate-run risks that need
  idempotency, locks, and audit records.
- Warrant Loops should be accountability loops, not generic Linear automations.

Suggested MVP:

- Start with in-process, manually triggered automation runs rather than a daemon.
- Add tables for `automation_definitions` and `automation_runs`.
- Define supported triggers:
  `manual`, `new_issue`, `daily_digest`.
- Define supported actions by referencing skill IDs, not arbitrary Python functions.
- Seed one Warrant-specific loop:
  `daily_warrant_review`, which reports stale approvals, expiring warrants, missing
  evidence, failed verification, and high-risk denied delegations.
- Add `POST /v1/automations/{id}/run` for deterministic local demo execution.
- Add `make run-automations` or a CLI that executes due automations once.
- Only after that, add a lightweight scheduler loop if required.

Definition of done:

- An automation can run a skill idempotently and record a run result.
- Duplicate runs are prevented by an idempotency key or run window.
- Every automation action is audited.
- Failures do not change issue/delegation authority silently.

Estimated effort: medium to high.

Main files to touch:

- New `src/warrant/automations.py`
- New CLI module, possibly `src/warrant/automation_runner.py`
- `src/warrant/db.py`
- `src/warrant/main.py`
- `src/warrant/service.py`
- Tests for duplicate prevention, failed runs, audit, and no-authority side effects.

## Overall Priority Table

| Rank | Task | Effort | Risk | Reuses Existing Code | Product Value |
| --- | --- | --- | --- | --- | --- |
| 1 | Real Linear adapter | Medium-high | High | Webhook/intake, issue schema | Proves Warrant sits on top of Linear |
| 2 | Project/cycle/update summaries | Low-medium | Low | Delegation brief, telemetry, evaluation | High demo value with Warrant differentiation |
| 3 | Real GitHub adapter | High | High | Surface map, scope/evidence gates | Makes coding-agent control field-real |
| 4 | Skills | Medium | Medium | Summaries, triage, related, search | Packages Warrant workflows |
| 5 | Loops/background automations | Medium-high | Medium-high | Skills, telemetry, audit | Automates accountability checks |

## Suggested Implementation Sequence For Your Work

1. Add a narrow Linear import adapter so Warrant can sit on top of a real or stubbed
   Linear issue.
2. Build project/team summaries that emphasize Warrant's accountability layer rather
   than generic progress summaries.
3. Add read-only GitHub metadata import, starting with CODEOWNERS/surface mapping and
   changed-file evidence checks.
4. Wrap adapter-backed summaries and issue-review flows into a minimal Skills system.
5. Add manually runnable automation loops that execute those skills with idempotency and
   audit.

This order is less "easiest first" and more FDE-real: connect to the incumbent system,
show Warrant's differentiated value, then automate the repeatable field workflow. The
scope should remain intentionally narrow so integration risk does not swallow the whole
assignment.

## Recommended Scope For This Assignment Window

If time is limited, ship a thin Linear adapter and project/update summaries completely,
then make GitHub a read-only CODEOWNERS parser or documented stub. Add Skills/Loops only
around the completed Warrant-specific flows.

Minimum strong submission slice:

- Linear issue import with stubbed tests and clear data-handling rules.
- Warrant-specific project/team update summaries.
- One reusable skill that runs the summary or delegation-candidate review.
- Honest GitHub and automation plans with risks and API contract sketches.

Ambitious submission slice:

- Everything above.
- GitHub CODEOWNERS parser with fixture-based tests.
- One manually triggered accountability loop, such as `daily_warrant_review`.

Avoid:

- Sending real customer data to OpenRouter's free endpoint.
- Adding background jobs without idempotency and audit.
- Giving GitHub write permissions.
- Letting summaries, skills, or loops create authority outside the existing policy and
  warrant workflow.
