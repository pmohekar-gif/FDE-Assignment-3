# AI in Comments (`@Warrant`) — Linear-Agent-Referenced Execution Plan

## Linear product reference (reviewed 2026-09-04)

This plan uses Linear's public documentation as a **product-behaviour reference**, not as a
claim about Linear's internal implementation. The relevant reference is
[Linear Agent](https://linear.app/docs/linear-agent), supported by its
[comments](https://linear.app/docs/comment-on-issues),
[agents](https://linear.app/docs/agents-in-linear), and
[AI credits](https://linear.app/docs/ai-credits) documentation.

Linear documents the following behaviour:

- The agent can be reached in a dedicated chat, keyboard shortcut, or by mentioning it in any
  comment; comments are therefore an in-context entry point, not a separate chatbot.
- It uses workspace context—issues, projects, teams, history, comments, documents, and their
  relationships—to answer questions, summarize activity, and make updates.
- It operates within the invoking user's existing permissions: it can only reference or modify
  content that user may access.
- In comments, it is positioned to help produce visible, ready-to-post output: status updates,
  concise progress summaries, action items, and decision recaps. The documented examples also
  include rewriting text and identifying blockers.
- The broader agent is documented as able to create/update issues, projects, milestones, and
  initiatives, and to post, edit, and delete **its own** comments. Workspace admins/owners can
  control whether it is enabled; workspace and personal guidance tailor its behaviour.
- Linear also exposes reusable skills and MCP-backed external context as separate, administered
  capabilities. Usage-based work is controlled with workspace credit balances and spend limits.

Warrant should copy the user experience and product controls that make sense—mention in context,
visible agent identity, permission-scoped context, progress, workspace enablement, guidance, and
traceable agent-owned comments. It should not assume undocumented Linear internals such as its
prompt format, model routing, databases, queues, or authorization code.

## Decision and product boundary

Build `@Warrant` as an **explicitly invoked issue-discussion agent**, modelled on Linear Agent in
comments. A person writes `@Warrant summarize the decisions and propose next steps`; Warrant
creates a visible assistant response in the same thread, using permission-scoped issue, thread,
and workspace context. It shows progress while it works, identifies its sources and uncertainty,
and persists its output as an agent-owned comment.

The Warrant MVP is deliberately **draft-first**, not full Linear parity: it can answer,
summarize, find related issues, rewrite user-supplied text, and propose structured changes. Later
phases may permit narrowly-scoped agent mutations that are separately policy-checked and audited.
It may never autonomously change a delegation decision, grant a warrant, widen scope, or bypass
human approval. This keeps Warrant's defining rule intact: AI supplies evidence and prose;
deterministic code supplies authority.

## Linear-inspired interaction model for Warrant

The interaction to reproduce is small and useful:

1. A user mentions `@Warrant` in an issue comment and optionally asks a natural-language question.
2. Warrant posts a distinct, persisted “working” agent comment, gathers only the context the
   invoking user may access, and updates that comment to the final result.
3. The assistant can answer, summarize, rewrite supplied text, surface blockers/action items,
   retrieve related issues, and create a deterministic preview for a triage or delegation draft.
4. The thread preserves the user request, agent identity, run status, context revision, provider
   provenance, citations, cost/usage metadata, and any later action taken.
5. A workspace owner can disable the feature; workspace/personal guidance controls tone and
   output conventions. These controls precede reusable skills or external integrations.

Do not begin by implementing autonomous issue creation, assignment, status changes, external
messages, or an open-ended agent tool loop. Those are later, separately authorised capabilities.

## Current-project fit

This repository already supplies most of the safe AI infrastructure:

| Existing capability | Reuse for comments |
| --- | --- |
| `LLMProvider` with fixture and structured-output providers | Add a closed `comment_assist()` operation; retain provider validation and repair behaviour. |
| `security.py`, FastAPI dependencies, CSRF checks | Authenticate the author, scope every read/write by workspace, and protect comment/action POSTs. |
| Normalisation/redaction and injection signals | Treat comments, quoted text, and AI instructions as untrusted input before inference. |
| `retrieval.py` and triage/related-issue services | Supply permission-filtered related issues; do not let the model invent issue IDs. |
| SQLite migration seam in `db.py` | Add comments, assistant runs, citations, and idempotency tables/indexes. |
| Audit and model-usage records | Record mention receipt, generation state, accepted action, and provider metadata without raw prompts. |
| Jinja issue/delegation UI | Add an issue detail page with a chronological thread and composer. |

What is missing is the issue-comment domain model, user-facing issue detail route, mention parser,
assistant orchestration, action-confirmation flow, evaluation data, and tests.

## Requirements to agree before coding

Answer these during product/design review; each answer should be recorded in the feature PR.

### Product requirements checklist

- [ ] Which issue roles can invoke `@Warrant`? (Recommended MVP: all workspace members who can view the issue.)
- [ ] Is the assistant mentioned as `@Warrant` or a workspace-configurable alias? Do not present
  Warrant as `@Linear`; that is Linear's product identity.
- [ ] Which MVP intents ship: answer question, summarize, extract decisions/action items,
  suggest related issues, triage draft, delegation draft?
- [ ] Should a mention with no text show a command menu or default to a concise issue summary?
- [ ] May the assistant read only the current issue thread, or also workspace-visible related issues?
- [ ] Are assistant answers public to all issue viewers, or can a requester have private drafts?
- [ ] What is the response-time target and acceptable “still working” behaviour?
- [ ] What copy explains fixture/demo mode versus a live provider?

### Permission and safety checklist

- [ ] Define a single `can_view_issue(actor, issue)` check and use it for context, comment reads,
  citations, and proposed actions.
- [ ] Never send comments/attachments a requester cannot read to the provider.
- [ ] Strip or redact secrets and personal data using the existing normalisation pipeline.
- [ ] Detect prompt-injection phrases, quote them as untrusted data, and downgrade to a
  non-actionable response when the signal is high.
- [ ] Keep the output schema free of authority fields (`verdict`, `approved`, `tool_grant`,
  `status_to_apply`, and arbitrary tool calls).
- [ ] Require CSRF plus explicit confirmation for every write; enforce permissions server-side.
- [ ] Rate limit mention creation per workspace/user and cap request/context/output sizes.
- [ ] Do not allow the assistant to impersonate a person; use a distinct assistant identity.
- [ ] Provide deletion/redaction behaviour for comments and ensure removed content is excluded
  from future context.
- [ ] Decide retention, provider-data handling, export, and audit requirements before live data.

### Quality and operations checklist

- [ ] Define grounded-answer acceptance: citations resolve to permitted current context and no
  unsupported factual claim is allowed in the evaluation set.
- [ ] Define latency, error, cost-per-mention, and rate-limit budgets.
- [ ] Record only metadata in telemetry/audit—never raw comment bodies or full prompts.
- [ ] Establish support behaviour for provider timeout, malformed output, deleted source comment,
  and duplicate webhook/client submission.
- [ ] Prepare representative synthetic examples, including ambiguous requests and prompt injection.

## MVP scope and non-goals

### In scope

- Top-level issue comments and assistant replies (threaded replies can follow after the MVP).
- Mention detection that runs only on newly submitted comments, with an agent-owned working and
  final comment, like Linear's in-context agent interaction.
- Closed intents: `answer`, `summarize`, `rewrite`, `extract_action_items`, `blockers`,
  `related_issues`, `triage_draft`, and `delegation_draft`.
- Context limited to the current issue plus access-filtered retrieval results.
- Citation-backed assistant messages, draft action cards, retry/error states, and audit/usage records.
- Fixture-mode implementation and a structured live-provider path.

### Explicitly out of scope

- Autonomous tool use, external integrations, background agents, or arbitrary actions.
- AI-created policy/warrant decisions, approvals, scope widening, or evidence verification overrides.
- Attachments, rich-text collaboration, direct messages, and cross-workspace context.
- Streaming tokens in Phase 1 (show a pending assistant reply instead).

## Phase plan

### Phase 0 — Linear-reference product contract (1–2 days)

Status: complete (implementation defaults recorded 2026-09-04)

Deliverables:

- Resolve the requirement checklists above with product, security, and platform owners.
- Write a versioned API/output contract and UX wireframe for empty, pending, answered, blocked,
  and failed states.
- Select the initial intents and response limits.
- Define Warrant guidance: workspace default plus optional personal preferences, with workspace
  rules taking precedence. Define owner-only feature enable/disable and usage/spend controls.
- Create synthetic evaluation examples before prompt/provider work begins.

Checklist:

- [ ] MVP alias (`@Warrant` recommended), roles, visibility, and intent list are approved.
- [ ] Mutation boundary and confirmation UX are approved.
- [ ] Context sources and per-source limits are documented.
- [ ] Agent identity, working-state comment, edit/retry behaviour, and agent-comment deletion
  policy are specified.
- [ ] Workspace enablement, guidance precedence, and per-workspace/per-user usage limits are specified.
- [ ] Data-retention/provider review is complete for the selected environment.
- [ ] Success metrics and a launch/rollback owner are named.

Exit criterion: a developer can implement from the API contract without guessing product or
permission behaviour.

### Phase 0 outcome — Warrant v1 contract

The following decisions are now the implementation baseline. They deliberately reproduce the
documented Linear Agent-in-comments interaction while using Warrant terminology and preserving
Warrant's non-authorising boundary.

| Decision | Warrant v1 implementation default |
| --- | --- |
| Agent identity | `@Warrant`; it is a separate `agent` author, never a human user or `@Linear`. |
| Who may invoke it | Any user with permission to view the issue. The server resolves all context as that user. |
| Feature enablement | Disabled only by a workspace owner/admin through `agent_settings.enabled`; enabled by default in the synthetic demo workspace. |
| Comment visibility | Public to everyone who can view the issue. Private assistant conversations are not part of v1. |
| Supported intents | Answer, summarize, rewrite supplied text, extract action items, identify blockers, related issues, triage draft, delegation draft. |
| No-text mention | Reply with a concise issue state/blocker summary; do not open an autonomous chat. |
| Context | Current issue, up to 30 most recent visible non-deleted comments, current deterministic issue/delegation facts, and at most five access-filtered related issues. |
| Guidance | Workspace guidance applies first; a user's personal style preference may refine tone but cannot weaken workspace rules. |
| Progress | Create one visible agent-owned `working` comment, then update that same record to `completed` or `failed`. No token streaming in v1. |
| Writes | V1 creates/updates only the agent's own response comment. Triage/delegation are previews that require an explicit human confirmation in Phase 3. |
| Usage control | Enforce 20 mentions/user/hour and 100/workspace/hour; hard-limit 2,000 response characters and record provider cost where available. |
| Failure behaviour | Preserve the human comment; mark the agent comment `failed` with a retry control. A failure never produces a guessed answer or action. |

#### Versioned API contract

`POST /v1/issues/{issue_ref}/comments` accepts the following closed request. The client does not
tell the server whether a mention exists; the server normalises `body`, extracts the mention, and
creates the run atomically with the comment.

```json
{
  "body": "@Warrant summarize blockers and next steps",
  "parent_comment_id": null,
  "idempotency_key": "client-generated-uuid"
}
```

Success returns `201` with the persisted human comment and, only for a valid mention, the
agent-owned working comment and its run reference:

```json
{
  "comment": {"id": "cmt_…", "author_type": "user", "status": "completed"},
  "mention": {
    "id": "mnt_…",
    "state": "working",
    "assistant_comment_id": "cmt_…",
    "poll_url": "/v1/comment-mentions/mnt_…"
  }
}
```

`GET /v1/comment-mentions/{id}` returns the `working`, `completed`, or `failed` run state. A
completed response includes the assistant comment, provider provenance, generated-at timestamp,
and citations. It must never expose the raw provider prompt, hidden context, another workspace's
record, or a write-capable model tool call.

#### Acceptance criteria for Phase 1

- The workspace setting and user issue access are checked before inserting a comment or run.
- A comment without `@Warrant` remains a normal comment and creates no AI/provider work.
- A valid mention creates one human comment, one agent-owned `working` comment, and one mention
  run—even when the client retries the same idempotency key.
- An agent-comment record is visibly marked `Warrant`, retains an immutable originating mention
  reference, and cannot be edited/deleted as a human comment.
- The Phase 1 code contains no provider call. Phase 2 alone may turn a `working` run into a
  generated response.
- Tests demonstrate tenant isolation, CSRF protection, idempotency, permission checks, alias
  token matching, owner-only feature disablement, and rate-limit behaviour.

### Phase 1 — Comments, mentions, and agent identity (2–3 days)

Status: implementation complete (2026-09-04); manual browser visual QA pending

Deliverables:

- Add an issue detail route and chronological comment composer/view.
- Add `comments` and `comment_mentions` persistence, workspace and issue indexes, author type,
  edit/deletion state, and idempotency key.
- Parse mentions server-side after markdown/plain-text normalisation; never trust a client-side
  mention flag.
- Post a visible `working` agent-owned comment only after the human comment is committed; update
  that same comment with the final output or a failure state.

Suggested minimum data model:

```text
comments(id, workspace_id, issue_id, parent_comment_id?, author_type, author_id,
         body_normalised, status, client_request_id, context_revision, created_at, updated_at,
         deleted_at?)
comment_mentions(id, comment_id, mentioned_identity, requested_text, state,
                 assistant_comment_id?, idempotency_key, created_at, completed_at?)
agent_settings(workspace_id, enabled, workspace_guidance, monthly_budget_cents,
               per_user_budget_cents, updated_by, updated_at)
agent_preferences(workspace_id, user_id, guidance, enabled, updated_at)
```

Checklist:

- [x] `POST /v1/issues/{issue_ref}/comments` validates author, body length, CSRF, workspace,
  issue visibility, and idempotency.
- [x] `GET /v1/issues/{issue_ref}/comments` is workspace/permission scoped. Pagination is deferred
  until issue threads can exceed the v1 context limit.
- [x] `@Warrant` matching is case-insensitive but respects token boundaries (do not trigger inside
  an email address or code identifier).
- [x] Duplicate submission creates at most one human comment and one assistant run.
- [x] The schema includes soft-deletion state; deleted records are already excluded from reads.
  Comment deletion/edit routes deliberately begin in Phase 3, when agent-owned changes gain
  explicit policy/audit behaviour.
- [x] Integration tests cover tenancy, CSRF, idempotency, mention parsing, owner-only enablement,
  and the discussion-page composer.

Implemented endpoints: `GET/POST /v1/issues/{issue_ref}/comments`,
`GET /v1/comment-mentions/{id}`, and owner-only `GET/PUT /v1/agent-settings`. The issue page is
`/issues/{issue_ref}`. The working agent comment is intentionally not sent to a model until Phase 2.

Latest verification: Ruff and mypy pass; the full suite passed **106 tests** on 2026-09-04. Browser
visual inspection remains pending because no controllable browser is connected.

Exit criterion: a user can create a normal comment; a valid assistant mention reliably creates
exactly one working agent comment and run without calling a model.

### Phase 2 — Permission-scoped, grounded assistant response (3–5 days)

Status: implementation complete (2026-09-04); live-provider and browser visual QA pending

Deliverables:

- Add `CommentAssistantResponse` Pydantic schema and `LLMProvider.comment_assist()`.
- Build a context assembler: issue title/body, recent visible comments, extracted issue facts,
  and top-k access-filtered related issues. Apply deterministic limits and redaction before the
  provider call.
- Persist assistant-run provenance, a generated reply, stable citations, provider usage, and
  failure reason.
- Add the fixture response implementation first, then the structured OpenAI-compatible path.
- Resolve context as the invoking user, not as the system/agent. Persist the context revision and
  citations so a response can be traced after issue/thread changes.

Suggested closed response contract:

```json
{
  "intent": "answer",
  "answer_markdown": "string, max 2,000 chars",
  "citations": [{"source_type": "issue|comment|related_issue", "source_id": "string"}],
  "uncertainties": ["string"],
  "proposed_actions": [
    {"kind": "show_related_issues|triage_draft|delegation_draft", "payload": {}}
  ]
}
```

The server must validate that every citation is in the assembled context and every proposed
action is a known, non-mutating kind. Render assistant markdown using an allow-list sanitizer;
do not render arbitrary HTML.

Checklist:

- [x] Prompt states that comments are untrusted data and assistant text cannot authorise actions.
- [x] Provider input contains only the source issue, up to 30 visible non-deleted issue comments,
  bounded related issues, and workspace guidance. The current synthetic workspace has no finer
  issue ACL than workspace membership; the source-comment author is the permission context.
- [x] Workspace feature enablement and workspace guidance are resolved
  before the provider call; workspace guidance wins on conflict.
- [x] Schema validation, malformed-output repair, timeout, retry, and fixture/liveness labelling
  follow the existing provider conventions.
- [x] A model failure changes the placeholder to a concise retriable failure—never fabricates an answer.
- [x] Assistant responses identify fixture/provider provenance in the persisted mention response and
  render their context IDs and uncertainties in the discussion UI.
- [x] Model usage is recorded using operation `comment_assist`; raw prompt/reply are not telemetry.
- [x] The service rejects any citation ID outside the assembled context; provider-failure and
  completed-response paths are integration tested.

Implemented contract: `CommentAssistNarrative` is a closed Pydantic response with
`answer_markdown`, `citation_ids`, and `uncertainties`; it has no authority/action fields.
`POST /v1/comment-mentions/{id}/process` turns a working mention into a completed or failed
agent-owned comment. This synchronous endpoint is the Phase 2 execution seam; a queued worker is
only needed when real-provider latency makes request/response handling unsuitable.

Exit criterion: a mention produces a cited, persisted, permission-safe assistant response or a
clear failed state.

### Phase 3 — Controlled actions, toward Linear parity (2–4 days)

Deliverables:

- Render action cards from the server-validated proposal, not model-generated links or forms.
- Reuse existing related-issues, triage, and delegation services to build deterministic previews.
- Add confirmation dialogs with a diff/summary, actor permission checks, CSRF, and audit events.
- Add an explicit agent-comment edit/delete capability only for the assistant's own comments,
  with immutable audit records and a visible edit indicator.

Safe action progression:

```text
AI proposal -> deterministic preview -> human confirmation -> existing service -> audit event
```

Checklist:

- [ ] The model cannot submit to an action endpoint directly.
- [ ] The server reconstructs proposal data from current records; it does not trust saved model JSON.
- [ ] A triage action uses existing `apply_triage()` permissions and records the human actor.
- [ ] A delegation action creates only a draft/pre-filled form; existing policy still makes the verdict.
- [ ] Stale/revoked/deleted source context invalidates the action card and requires regeneration.
- [ ] Any future create/update issue action maps to a specific Warrant service operation and
  permission check; generic model tool calls remain prohibited.
- [ ] Tests prove a crafted assistant payload cannot change issue status, assignee, policy, or warrant.

Exit criterion: a user can safely apply one useful action with an explicit and auditable
confirmation, while no AI output has write authority.

### Phase 4 — Evaluation, rollout, and hardening (2–3 days)

Status: local QA in progress (fixture-only; no production claims)

Deliverables:

- Add `evaluations/comment_assist_golden.json` with expected intent, citations, refusal/
  uncertainty, and allowed proposal kinds.
- Add unit, integration, security, and end-to-end coverage.
- Instrument usage, completion, retry, action-acceptance, failure, p95 latency, and cost metrics.
- Release behind a workspace feature flag and conduct a synthetic-data pilot.

Checklist:

- [x] Fixture grounding and provider-failure cases are defined in
  `evaluations/comment_assist_golden.json`; integration tests enforce completed versus failed,
  non-actionable behaviour. Cross-workspace access is covered by the comment API integration test.
- [x] The fixture provider failure produces a failed agent comment with no answer/citations/actions;
  the existing injection normalisation occurs before comment-assist context assembly.
- [x] Fixture results are explicitly labelled in the UI/provider provenance. Live-provider results
  remain unmeasured and are not represented as QA evidence.
- [x] Workspace enablement, per-user/workspace mention rate limits, and provider failure handling
  are implemented and covered locally. A production operations runbook is deferred by scope.
- [ ] Desktop and mobile visual QA for long threads, pending state, errors, citations, and action
  cards requires a connected controllable browser and remains pending.
- [ ] Privacy/security review and rollback procedure are production rollout work and remain pending
  by explicit scope.

Local QA verification (2026-09-04): Ruff passed; comment-assist golden and integration coverage
passed (7 focused tests). This phase is complete for fixture/local QA only, not for production
release readiness.

Exit criterion: the feature meets its agreed quality/latency/cost targets in a controlled pilot;
it can be disabled without affecting ordinary commenting.

## Implementation order in this codebase

1. Extend `schemas.py` with comment requests/responses, `CommentAssistantResponse`, citations,
   proposal kinds, and closed validators.
2. Add tables/indexes and idempotent migration checks in `db.py`; implement repository helpers.
3. Add comment/mention lifecycle methods to `service.py`, reusing normalisation, redaction,
   retrieval, `record_usage()`, `telemetry()`, and audit append operations.
4. Add `comment_assist()` to every `LLMProvider` implementation in `providers.py`; fixture first.
5. Expose the comment and action-preview endpoints in `main.py` with the existing workspace and
   CSRF dependencies.
6. Add `issue.html`, CSS, and minimal JavaScript for submit/poll/retry. Use polling initially;
   introduce streaming only after the non-streaming contract is stable.
7. Add tests and evaluation cases before enabling a live provider.

## Proposed API surface

| Endpoint | Purpose |
| --- | --- |
| `GET /issues/{issue_ref}` | Render the issue detail and comment thread. |
| `GET /v1/issues/{issue_ref}/comments?cursor=` | Read a paginated visible thread. |
| `POST /v1/issues/{issue_ref}/comments` | Create a human comment; server detects `@Linear`. |
| `GET /v1/comment-mentions/{id}` | Poll pending/completed/failed assistant state. |
| `POST /v1/comment-mentions/{id}/retry` | Explicit, rate-limited regeneration after failure. |
| `POST /v1/comment-actions/{id}/preview` | Deterministic preview of one proposal. |
| `POST /v1/comment-actions/{id}/apply` | Confirmed human mutation, when an approved kind ships. |

Every mutating endpoint needs an authenticated actor, workspace-scoped lookup, CSRF validation,
and idempotency handling. Return `404`, not `403`, for inaccessible workspace resources, matching
the project’s current boundary.

## Definition of done

The feature is complete when a permitted user can mention `@Linear` in an issue comment, receive
a clearly-labelled, cited answer based only on accessible context, and optionally confirm a
server-validated draft action. Normal comments remain reliable if AI is unavailable, and no model
output can independently alter issue, policy, delegation, or warrant state.
