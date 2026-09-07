# GitHub Adapter Feasibility Spike

**Status**: SPIKE ONLY — No adapter implementation yet.  
**Author**: Engineering (FDE Assignment, Team 3)  
**Date**: 2024-09-07  
**Ticket**: GitHub adapter feasibility — read-only import for Warrant delegation accountability  

---

## 1. Goal

Assess how Warrant can safely read GitHub repository / pull request / commit / check-run metadata to strengthen delegation accountability, without becoming a GitHub clone and without adding write authority.

**Product constraints:**
- Do not implement the adapter yet.
- Do not add new dependencies unless clearly justified in the doc.
- Do not create branches, PRs, comments, reviews, merges, deployments, labels, or status checks.
- GitHub remains system of record for code hosting and PR state.
- Warrant remains system of record only for delegation authority, warrants, evidence, and audit.
- AI output must not approve, deny, issue warrants, widen scope, merge PRs, or bypass deterministic policy.
- No customer code, secrets, or private repo content should be sent to OpenRouter free MiniMax.
- Tests must not make real network calls.

---

## 2. Recommended Scope

- **Read-only metadata only**: We retrieve bounded metadata to display accountability state and enrich session evidence. The adapter must not become an automatic policy authority without a separately reviewed deterministic policy change.
- **Candidate objects**:
  - Repository identity
  - Pull request metadata
  - Commit metadata
  - Changed file paths
  - Check suite / check run status
  - Branch protection summary (if available read-only)
- **Explicitly out of scope**:
  - Creating PRs
  - Comments/reviews
  - Merging
  - Deployments
  - Status/check writes
  - Repository settings mutation

---

## 3. API Options

Compare:
- **GitHub REST API**: Standard JSON API, easy to consume without extra GraphQL libraries. Well documented, standard endpoints for PRs, Commits, and Check Runs.
- **GitHub GraphQL API**: Allows fetching deeply nested objects (e.g., PR + Commits + Check Runs) in one query. Minimizes network requests but increases query complexity.
- **`gh` CLI as subprocess**: Relies on a system dependency (`gh`). Extremely brittle for a backend service (stdout parsing, subprocess overhead), but provides simple out-of-the-box auth if the environment is already authenticated.

**Recommendation for MVP**: **GitHub REST API** via the existing `httpx` dependency. It avoids GraphQL query complexity and avoids adding a new client library. Basic PR metadata, changed files, commits, commit statuses, and check runs map directly to REST endpoints and should remain well within rate limits for explicit per-PR refreshes.

---

## 4. Authentication Options

Compare:
- **Fine-grained personal access token (PAT)**: Easiest for developers to generate. Scoped to specific repositories with read-only access.
- **GitHub App installation token**: Requires creating and installing a GitHub App. Standard for production backend-to-backend integrations, highly secure, short-lived tokens.
- **Existing `gh` CLI auth**: Reads from `~/.config/gh/hosts.yml`. Convenient for local dev, not viable for deployed service.

**Recommend MVP option**: **Fine-grained personal access token (PAT)**. It is fast to set up for the assignment and can be strictly read-only scoped.
**Recommend production option**: **GitHub App installation token** to avoid tying backend functionality to an individual user's token.

**Required permissions/scopes**:
- Repository metadata (Read)
- Pull requests (Read) — PR metadata and list-files endpoint
- Commit statuses (Read)
- Checks (Read)
- Contents (Read) only if the MVP later chooses endpoints that require it; do not read file contents or patches
- Administration (Read) only if branch-protection summary is included; otherwise defer branch protection

---

## 5. Data Mapping

Proposed Warrant DTOs and fields:

### `GitHubRepositoryDTO`
- **Field**: `full_name` (GitHub source: `repository.full_name`) -> Warrant use: Identity/linking. May be sensitive (private repo name). Store in local DB.
- **Field**: `default_branch` (GitHub source: `repository.default_branch`) -> Warrant use: Accountability rule checking. Not sensitive. Store in local DB.

### `GitHubPullRequestDTO`
- **Field**: `id`, `number`, `html_url`, `state`, `draft`, `merged`, `base.ref`, `head.sha` (GitHub source: pull request response) -> Warrant use: link display and PR state tracking. Store locally as metadata.
- **Field**: `title` (GitHub source: `pull_request.title`) -> Warrant use: operator display only. Potentially sensitive; store locally only, redact before any display where appropriate, and never send to OpenRouter for real/private repos.
- **Field**: `body` -> **omit in MVP**. PR bodies can contain customer data, logs, credentials, or prompt-injection text; do not fetch/store unless a later reviewed design needs it.

### `GitHubCommitDTO`
- **Field**: `sha`, `html_url` (GitHub source: commit response) -> Warrant use: linking code changes to delegation. Store locally.
- **Field**: `message` (GitHub source: `commit.commit.message`) -> Warrant use: optional operator display only. Potentially sensitive; prefer a SHA-256 fingerprint or first-line redacted summary, not raw long messages.

### `GitHubCheckRunDTO`
- **Field**: `id`, `name`, `status`, `conclusion`, `started_at`, `completed_at`, `html_url` (GitHub source: check-run/status response) -> Warrant use: external CI evidence display and audit context. Store minimal subset. These values must not replace Warrant's host-owned verification verdict.

### `GitHubChangedFileDTO`
- **Field**: `filename`, `status`, `additions`, `deletions` (GitHub source: PR files endpoint) -> Warrant use: compare external PR contents with the warrant scope for operator review. Potentially sensitive (architectural leakage). Store bounded path metadata locally; do not store patches or file contents; do not send to AI.

---

## 6. Storage Proposal

Keep storage minimal to maintain Warrant as the authority on delegation, not a GitHub replica.

**Proposed tables / metadata fields**:
- `github_repository_links`: Maps local workspace/repo concepts to external `github_repo_id`, `full_name`.
- `github_pull_request_links`: Maps a coding session/warrant to a specific PR (e.g., `session_id`, `repo_id`, `pr_number`, `state`, `last_synced_at`).
- `github_check_runs`: Lightweight cache of check run/status conclusions for a PR/commit (`pr_link_id`, `external_check_id`, `check_name`, `status`, `conclusion`, `updated_at`).
- `github_changed_files`: Optional bounded cache of PR file metadata (`pr_link_id`, `filename`, `status`, `additions`, `deletions`) with no patch/body content.

**Idempotency and update strategy**:
- Use GitHub IDs (`repository.id`, `pull_request.id`, `check_run.id`) plus `(repository_id, pr_number)` as external unique keys.
- On refresh, perform an UPSERT (update on duplicate key) to update mutable fields (`state`, `draft`, `merged`, `head_sha`, `conclusion`, `updated_at`).
- Do not persist PR bodies, file contents, patches, review comments, or check logs in the MVP.

---

## 7. Candidate API Endpoints

Read-only first endpoints for the backend to expose for UI/CLI integration:
- `GET /v1/adapters/github/status`: Health check and config state (mode).
- `GET /v1/adapters/github/pull-request?owner=&repo=&number=`: Fetch current PR metadata.
- `GET /v1/adapters/github/pull-request/{id}/checks`: Fetch check runs for the PR.
- *Optional import/link endpoint (only if justified for active connecting)*:
  `POST /v1/adapters/github/link-pull-request`

---

## 8. Adapter Modes

Recommend config similar to Linear:
```dotenv
GITHUB_MODE=off|stub|live
GITHUB_TOKEN=
GITHUB_API_BASE_URL=https://api.github.com
```

- `off`: Adapter is disabled.
- `stub`: Adapter returns static fixture data. Must be clearly labelled **[SIMULATED]**.
- `live`: Uses `GITHUB_TOKEN` to interact with GitHub API.

---

## 9. Relationship to Existing Coding Sessions

Explain how this integrates with existing PR publication/session artifacts:
- The coding session already stores a PR URL/number when publication succeeds.
- The GitHub adapter should enrich that session view with read-only metadata, check statuses, changed-file metadata, and PR state.
- The adapter **must not replace host-owned verification**. GitHub checks are external evidence; the Warrant session verification result remains the local authority for whether the governed run completed its required checks.

---

## 10. Security/Threat Model

- **Token handling**: Token must only be read from `.env` or secure vault, never logged, never committed.
- **Private repo metadata sensitivity**: Private repo names and PR titles are confidential; PR bodies are omitted in the MVP. Do not expose GitHub data in unauthenticated endpoints.
- **Changed file path leakage**: Exposing full file trees can leak IP.
- **Commit message sensitivity**: Same as PR titles; redact/hash or avoid storing raw messages, and avoid sending them to AI.
- **Webhook/signature considerations**: Webhooks are deferred for now. If added later, signature verification is mandatory.
- **Rate limits**: Adapter should handle `429` cleanly and respect rate limit headers.
- **SSRF/base URL restrictions**: `GITHUB_API_BASE_URL` must default to `https://api.github.com`; overrides should be limited to `https://` GitHub Enterprise allowlisted hosts, never arbitrary operator-supplied URLs.
- **AI boundary**: Do not send real/private GitHub metadata, titles, commit messages, file paths, or check logs to OpenRouter free MiniMax. Any model prose must be based on sanitized deterministic facts only.
- **No real network calls in tests**: All tests must mock HTTP calls using stubs.

---

## 11. Failure Behavior

- **GitHub unavailable** must not increase autonomy.
- **Missing GitHub data** should become `NOT_MEASURED` or an advisory unavailable state.
- **No policy verdict should change solely because GitHub metadata is missing**.
- **GitHub checks failing or pending** may be displayed and audited, but must not retroactively deny/approve a delegation or issue/revoke a warrant unless a future deterministic policy change explicitly defines that behavior.

---

## 12. Testing Plan

- **Unit DTO parsing tests**: Test models against sample GitHub JSON responses.
- **Adapter tests with stubbed HTTP**: Use HTTP mocking to verify the adapter correctly calls the API and handles errors.
- **Integration tests with `GITHUB_MODE=off` and `stub`**: Ensure the system handles the mock data gracefully.
- **No live GitHub required in CI**: CI runs tests with mock data.
- **Optional live smoke gated by env var only**: A smoke test script that runs only if a specific flag is set.

---

## 13. Recommendation

**Proposed MVP**:
- **Adapter mode**: `GITHUB_MODE=stub` / `live` switch.
- **Auth method**: Fine-grained Personal Access Token (PAT).
- **API choice**: GitHub REST API (v3) using the existing `httpx` dependency.
- **Endpoints**: Polling-based `GET` endpoints for PR metadata and checks.
- **Storage**: Minimal relational link tables mapping PRs and checks to local Warrant IDs.
- **Explicit non-goals**: No GitHub webhooks (yet), no write operations (no automated approvals or merges via API).
