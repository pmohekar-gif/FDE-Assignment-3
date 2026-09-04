# Contextual Agent, Code Intelligence, Coding Sessions, and Slack

## Delivered behavior

The product now has one contextual Agent spanning issues, delegation decisions,
warrants, verification, repository code, and coding-session artifacts. It is deliberately
advisory: responses include `authoritative: false` and `authorising: false`, and the
Agent has no method that approves work or issues a warrant.

Code Intelligence reads the configured repository instead of seeded issue prose. It
indexes file metadata, symbols, and imports by repository revision and answers with
real path, line range, and snippet citations. The local provider rejects absolute and
parent-traversal paths, escaping symlinks, ignored/generated trees, secret filenames,
binaries, invalid UTF-8, and oversize files. Secret-like strings are redacted from
returned snippets.

Coding sessions implement this state model:

```text
QUEUED → PREPARING → RUNNING → VERIFYING → AWAITING_REVIEW → COMPLETED
   └──────────────→ CANCELLED / FAILED ←───────────────────────┘
```

Starting a session requires a Git checkout and an active policy-issued warrant granting
`write_files` and `run_tests`. The service snapshots the contract, creates an isolated
worktree/branch, invokes the selected runner without a shell, persists redacted bounded
activity, requires a non-empty in-scope diff, runs host-owned verification, and stores
the diff even when PR publication is unavailable. The built-in mock is always labelled
simulated. Codex is a real subprocess adapter and requires the explicit
external-execution feature flag.

The Slack adapter validates and deduplicates Events API calls. App mentions reuse the
same Agent, `status ISSUE-123` reads the same records, and `start coding ISSUE-123`
enters the normal Warrant flow. Deny stops immediately; approval-required returns a
review deep link; only an active warrant can reach the coding service.

## Configuration

The safe defaults enable read-only Agent/code assistance and disable external effects:

```dotenv
AGENT_CHAT_ENABLED=true
CODE_INTELLIGENCE_ENABLED=true
REPOSITORY_ROOT=.runtime/demo-repo
EXTERNAL_CODING_AGENT_ENABLED=false
CODING_AGENT_PROVIDER=mock
CODING_SESSION_ROOT=.runtime/coding-sessions
VERIFICATION_DISCOVERY_ENABLED=true
VERIFICATION_COMMAND=git diff --check
PROTECTED_BRANCHES=main,master,production
CODING_SESSION_RETENTION=3
PR_PUBLISHING_ENABLED=false
SLACK_ENABLED=false
SLACK_BOT_TOKEN=
SLACK_SIGNING_SECRET=
SLACK_USER_MAP={}
APPLICATION_BASE_URL=http://127.0.0.1:8000
```

### The demo checkout

Sessions require a Git checkout, and the delivered project folder ships a `.gitignore`
but no `.git`, so `REPOSITORY_ROOT=.` returns a typed 503 naming the root and the remedy.
`make demo-repo` creates a small self-contained checkout under the gitignored
`.runtime/demo-repo` whose files are exactly the seeded issues' `path_hints` and the
`policies/surfaces.yaml` globs, and which carries its own stdlib-only checks
(`make test`, `make lint`). It is idempotent, and `make demo` runs it first. The built-in
default `REPOSITORY_ROOT` stays the conservative project root.

If an interrupted demo leaves one of Git's known zero-byte lock files behind,
`make demo-repo` removes it only after it is at least five minutes old. Recent or
non-empty locks are treated as potentially active and fail with a safe diagnostic.

### Verification discovery

Verification is a property of the target repository, so the checks are discovered from
the checkout in priority order: `package.json` scripts (test/lint/typecheck/build) →
`pyproject.toml` tooling and `Makefile` targets → shell-free `run:` steps under
`.github/workflows` → the configured `VERIFICATION_COMMAND`. The first tier with a
runnable candidate wins; a candidate whose executable (or `-m` module) is not present is
skipped with a recorded reason. Every command stays an argv list — a CI `run:` line that
needs a shell (pipes, `&&`, redirection, expansion) is refused rather than reinterpreted
— and the environment whitelist is unchanged. The chosen plan is recorded on the session
contract before the agent starts, and each check persists its own `command`, `exit_code`,
`duration_ms` and `summary` in `verification_check_results`.

`VERIFICATION_COMMAND` is now only the fallback, and defaults to the fast, argv-only
`git diff --check`. The old `uv run pytest -q` default ran this project's entire suite
(minutes) inside every session worktree.

COMPLETED still requires all of: a clean agent exit, a non-empty diff, every changed path
inside warrant scope, and every required check passing. A failing required check fails the
session; an agent exit code alone is never success.

### Worktree lifecycle

The agent's OS process id and the owning server pid are persisted on the session row, so
a session left behind by a restart is identifiable; on startup such sessions are failed
with their recorded pids instead of hanging forever. On terminal states, worktrees beyond
`CODING_SESSION_RETENTION` (newest first) are removed with `git worktree remove` plus
`git worktree prune`, and their branches deleted unless a PR was published from them.

Real Codex mode requires the CLI to be installed/authenticated and
supported by the host sandbox. `PR_PUBLISHING_ENABLED=true` is insufficient on its own:
`gh auth status` and a GitHub `origin` must pass before the service commits or pushes
anything.

Map real Slack member IDs to existing Warrant identities:

```dotenv
SLACK_USER_MAP={"U012ABCDEF":"engineer-demo"}
```

## API surface

- `POST /v1/agent/query` — grounded Q&A with optional issue, delegation, repository,
  coding-session, and conversation scope.
- `POST /v1/code/query` — repository answer with path/line/snippet evidence.
- `GET /v1/code/index/status` and `POST /v1/code/index/refresh` — revision cache state.
- `GET /v1/coding-sessions/capabilities` — exact runner/PR availability and real/mock truth.
- `POST /v1/coding-sessions` — start after warrant validation.
- `GET /v1/coding-sessions/{id}` — contract, timeline, verification, diff, and PR artifact.
- `POST /v1/coding-sessions/{id}/cancel` — requester, warrant authority, admin, or owner.
- `POST /v1/coding-sessions/{id}/pull-request` — admin/owner draft-PR request.
- `POST /v1/integrations/slack/events` — signed Slack URL verification and app mentions.

Mutating browser/API routes require the existing CSRF token. Slack uses its own raw-body
signature boundary. The public session endpoint records the trusted source as `api`;
Slack supplies `slack` internally so clients cannot spoof that audit field.

## Verification and honest status

All local Agent, repository, mock execution, Slack, security, and regression tests pass.
The opt-in real-Codex E2E test is skipped unless `RUN_REAL_CODEX=1`. In this workspace,
an attempted real run failed because the enclosing sandbox denied Codex's in-process
app-server operation; an unsandboxed retry was not authorised. `gh` is installed but
not authenticated. Therefore the adapters are implemented, but successful real agent
execution, Slack delivery, and PR publication remain unverified external capabilities.

Pstack was checked as requested but was not installed as an executable or skill. It was
not used and is not a runtime dependency.
