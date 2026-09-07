# Linear Updates Picker

## Delivered behavior

Warrant now exposes `/integrations/linear`, a bounded read-only picker for Linear issues.
It is an import aid only: viewing updates does not create delegations, policy decisions,
approvals, warrants, evidence, or coding sessions.

The page shows the Linear adapter mode, the count of imported Linear issues, the latest
Linear `updatedAt` value Warrant has stored, a read-only **Check for Linear updates**
button, and a manual import-by-key form. Candidate rows are explicitly selected for
import/update.

## API surface

- `GET /v1/adapters/linear/status` returns adapter mode, imported issue count, and the
  max stored `external_updated_at` watermark.
- `GET /v1/adapters/linear/updates?team_key=&limit=25` asks Linear for issues updated
  after the local watermark minus a two-minute overlap window. The endpoint is read-only
  and returns bounded candidates labelled `linear` or `linear-stub` with import status:
  `new`, `already_imported`, or `update_available`.
- `POST /v1/adapters/linear/import-issue` remains the explicit idempotent import/update
  action for one issue reference.

## Persistence

`linear_issue_links.external_updated_at` stores Linear's `updatedAt` timestamp as
ISO-8601 text. Existing rows are backfilled from `issues.updated_at` when available and
fall back to `1970-01-01T00:00:00+00:00`.

## Safety boundaries

- Linear remains the issue system of record.
- Warrant does not bulk-sync or automatically import the latest issue.
- Raw Linear descriptions are only handled during explicit import through the existing
  normalisation/redaction flow.
- The update list is never sent to LLM providers.
- Existing OpenRouter protections for real Linear-imported content remain in force.
- Tests stub Linear HTTP behavior and must not make real network calls.
