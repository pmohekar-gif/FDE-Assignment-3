# New Ticket Creation — Execution Plan

## Goal

Replace the sidebar **Issues** destination with a **New ticket** flow. A workspace member can create a normal issue, review the generated ticket reference, and then use the existing Discussion, `@Warrant`, Code Intelligence, Impact Preflight, Triage, and Delegation features on that persisted issue.

Ticket creation is an ordinary user action. It must never grant authority, trigger an AI run, issue a warrant, or create a delegation automatically.

## Phase 0 — Baseline and boundaries

- [x] Confirm there is no existing `POST /v1/issues` endpoint or issue-create schema.
- [x] Confirm the current sidebar **Issues** link points to the Triage/inbox anchor.
- [x] Confirm issue discussion/comment routes require an existing issue.
- [x] Preserve the existing issue database shape and per-workspace unique external reference constraint.
- [x] Record the baseline test/lint results before implementation: 41 focused integration tests passed; Ruff passed.

## Phase 1 — Safe creation domain contract

- [x] Add a strict `IssueCreate` request schema: title, description, team, priority, labels, and idempotency key.
- [x] Permit only known workspace teams and bounded, normalized user input.
- [x] Generate a collision-safe external reference using the selected team prefix.
- [x] Create the issue inside a database transaction and add it to issue search/retrieval.
- [x] Enforce workspace isolation and authenticated/selected actor authorization.
- [x] Append an immutable `issue_created` audit event.
- [x] Add integration tests for validation, idempotency, reference generation, authorization, audit, and workspace boundaries (3 passed; Ruff passed).

## Phase 2 — New Ticket UI and navigation

- [x] Add a `/issues/new` page with title, description, team, priority, and optional labels.
- [x] Replace the sidebar **Issues** link with **New ticket**.
- [x] Keep Triage as the place to review existing tickets.
- [x] Show explicit success/failure feedback and redirect only after a successful create.
- [x] Add UI route and behavior coverage (24 UI tests passed; Ruff passed).

## Phase 3 — Existing-ticket workflow handoff

- [x] Redirect a newly created ticket to its Discussion page.
- [x] Make the generated issue reference visible in the resulting Discussion-page URL.
- [x] Verify that normal comments stay non-AI and `@Warrant` requests create only the linked advisory AI response.
- [x] Verify Code Intelligence Impact Preflight still opens a reviewable comment draft for any persisted issue reference, including a new ticket.
- [x] Verify no issue creation or AI suggestion automatically starts triage, delegation, approval, or execution.

## Phase 4 — Safety, resilience, and release verification

- [x] Verify malformed input, duplicate submissions, unknown teams, and database failures fail safely without partial tickets (including a simulated audit-storage failure that rolls back the ticket).
- [x] Verify rate limiting and audit behavior are preserved for downstream `@Warrant` comments (20 accepted requests per user/hour; the next request is rejected and only accepted comments are audited).
- [x] Run relevant unit/integration tests and lint: 32 focused tests passed; Ruff passed. `mypy src/warrant` still reports pre-existing errors in `repository.py`, `service.py`, `agent.py`, and `main.py`; it is not clean.
- [ ] Manually verify: create ticket → return to Triage → open Discussion → post normal comment → post `@Warrant` comment → use an Impact Preflight draft.
- [x] Update this checklist only after each item is verified.
