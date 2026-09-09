# GitHub PR-first Review Flow

## Delivered behavior

Warrant now supports an additive GitHub PR-first governance flow. It does not replace the
existing issue-first `agent_execution` flow where Warrant creates a local worktree and
launches a coding agent.

The new flow is explicitly typed as:

```text
coding_sessions.session_kind = github_pr_review
```

This means Warrant reviewed an externally-created GitHub pull request. It did **not**
launch the agent, control the worktree, write to GitHub, merge, deploy, or mutate the
repository.

## UI flow

`/integrations/github` now starts from one PR URL input:

```text
https://github.com/{owner}/{repo}/pull/{number}
```

The browser parses the URL into owner, repo, and PR number, then uses the existing
read-only GitHub adapter APIs to fetch PR metadata, changed files, and check runs. After
fetching evidence, the operator selects a tracked Warrant issue from a searchable issue
picker and starts a GitHub PR review session.

## API surface

- `GET /v1/adapters/github/pull-request/evidence` returns a bounded aggregate of PR
  metadata, changed files, and check runs. It does not include raw patches.
- `POST /v1/integrations/github/pr-link` links one PR to one Warrant issue. Re-linking
  the same PR to the same issue is idempotent; linking it to a different issue returns
  `409 Conflict`.
- `POST /v1/coding-sessions/github-pr-review` creates a completed review session with
  `session_kind=github_pr_review`.

All mutating routes require the existing CSRF boundary and admin/owner authority.

## Governance review

The PR review is deterministic and fail-closed. It records:

- whether an existing Warrant delegation and warrant were found;
- whether the warrant was valid, expired, revoked, or missing;
- whether a prior `agent_execution` session already consumed that warrant;
- changed files from the PR;
- active warrant scope used for file matching, when available;
- files outside warrant scope;
- GitHub check state: `passed`, `failed`, `pending`, or `none_found`;
- protected/security-sensitive surface matches from the Warrant surface map;
- a human review checklist.

If no pre-existing Warrant authority exists, the session remains a post-hoc governance
review: `pre_authorized=false`, `governance.gap=true`, and the verdict is inconclusive.
Warrant never fabricates delegation or warrant records to make the PR look authorized.

## Data model

`coding_sessions.delegation_id` and `coding_sessions.warrant_id` are nullable only for
`github_pr_review` sessions. Database checks preserve the invariant that
`agent_execution` sessions must carry real delegation and warrant ids.

The old broad `UNIQUE(warrant_id)` constraint was replaced by a partial unique index:

```sql
CREATE UNIQUE INDEX idx_coding_sessions_unique_agent_warrant
ON coding_sessions(warrant_id)
WHERE session_kind='agent_execution' AND warrant_id IS NOT NULL;
```

That keeps one Warrant-launched execution per warrant while allowing multiple external
PR review sessions to reference the same warrant.

## Intelligence boundary

Implementation alignment with the ticket is currently deterministic `INCONCLUSIVE`.
The PR review deliberately does not send raw GitHub patches to the LLM provider. A future
alignment judge needs a separately designed, bounded, redacted diff pathway and provider
contract before it can claim ticket-satisfaction evidence.

## Configuration

```dotenv
GITHUB_PR_REVIEW_ENABLED=false
```

The feature also requires `GITHUB_MODE=stub` or `GITHUB_MODE=live`. With the flag disabled
or GitHub mode off, session creation returns a controlled error.

## Tests

Coverage includes GitHub adapter regressions, PR link conflicts, no-warrant post-hoc PR
reviews, existing-warrant reviews, session detail rendering, feature-flag failures,
SQLite contract immutability, old-schema migration, and preservation of one
`agent_execution` per warrant.
