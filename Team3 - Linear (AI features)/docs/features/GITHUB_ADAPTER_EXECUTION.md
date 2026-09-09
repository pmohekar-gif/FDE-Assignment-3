# GitHub Adapter MVP Execution Summary

This document summarizes the execution of the GitHub adapter MVP based on the feasibility study (`GITHUB_ADAPTER_FEASIBILITY.md`).

## Overview

The read-only proxy API endpoints for GitHub integration have been successfully implemented. The MVP allows fetching of Pull Request metadata, associated files, and CI check runs.

### Scope Achieved
- **Configuration & Environment**: Added `GITHUB_MODE`, `GITHUB_TOKEN`, and `GITHUB_API_BASE_URL` to `Settings` and `.env.example`.
- **Data Transfer Objects**: Implemented Pydantic models in `github_dto.py` to ensure schema enforcement:
  - `GitHubRepositoryDTO`
  - `GitHubPullRequestDTO` (Note: `body` intentionally omitted to avoid reading/storing arbitrary PR text/customer data)
  - `GitHubCommitDTO`
  - `GitHubCheckRunDTO`
  - `GitHubChangedFileDTO`
- **Fixture Data**: Added static mock data in `github_fixture.py` mapping to common GitHub API JSON responses to allow functional testing without network calls or a token.
- **Adapter Logic**: Built `GitHubAdapter` to handle `off`, `stub`, and `live` modes using the existing `httpx` dependency. Live mode adds GitHub API-version headers and validates the configured base URL so insecure, local, and private-IP targets are refused.
- **API Endpoints**: Deployed `GET` endpoints in `main.py`, accessible exclusively via admin authority. Each response is labelled with `github` or `github-stub` source metadata:
  - `GET /v1/adapters/github/status`
  - `GET /v1/adapters/github/pull-request`
  - `GET /v1/adapters/github/pull-request/files`
  - `GET /v1/adapters/github/pull-request/checks`
- **Unit Testing**: Implemented test scenarios in `test_github_adapter.py` asserting correct behavior for both the stub and live configurations (using mock HTTP interceptors).

### Architectural Decisions Maintained

The integration surfaces are explicitly separated to maintain architectural boundaries:

**Standalone GitHub viewer:**
- Read-only interface for admin exploration
- Stateless passthrough; no persistence of PR states
- No audit attachments made when browsing

**Evidence submission integration:**
- Accepts an optional GitHub PR reference during verification (`gate-1`)
- PR metadata, files, and checks are fetched and securely persisted as an immutable snapshot (`github_evidence_snapshots`)
- Relevant audit events are written (`github_evidence_attached`, `github_scope_violation_detected`)
- Enforces scope checking during Gate 1 by explicitly comparing fetched file paths with Warrant scope constraint boundaries

## Limitations & Future Work
- **Synchronous Routes**: GitHub live calls use synchronous `httpx.get()` inside async FastAPI routes. This is acceptable for the MVP but should be refactored for production.
- **No Rate Limit Protection**: Currently, an admin can repeatedly burn GitHub API quota as there is no local caching layer.
- **Network Security**: Base URL protection rejects obvious local/private IPs, but does not DNS-resolve hostnames. A strict allowlist for `api.github.com` or approved GitHub Enterprise hosts is required for production.
- **Live Mode Verification**: Live mode remains unverified until actively tested and confirmed with a valid `GITHUB_TOKEN`.
- **Fetch Failures and Trust**: If the PR fetch encounters HTTP or parser errors during `submit_evidence`, the verification fails safely (falling back to an inconclusive verdict requiring human intervention).

## Usage
When `GITHUB_MODE=stub`, endpoints operate securely offline returning default fixtures labelled `github-stub`.
To test live data:
1. Provide a `GITHUB_TOKEN` (fine-grained personal access token).
2. Set `GITHUB_MODE=live`.
3. Use an authorized admin session to issue queries (e.g. `/v1/adapters/github/pull-request?owner=ORG&repo=REPO&number=123`).
