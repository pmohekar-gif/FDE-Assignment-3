#!/usr/bin/env bash
# Governed draft-PR demo against a REAL GitHub repository.
#
# The full chain: delegate -> policy verdict -> human approval -> warrant -> agent runs in
# an isolated worktree on its own feature branch -> host verifies -> reviewed diff is
# committed, pushed, and opened as a DRAFT pull request with reviewers requested.
#
# One-time setup (see PREFLIGHT below for what is checked):
#   brew install gh && gh auth login
#   git clone https://github.com/<you>/<repo> ~/code/<repo>
#   # in .env:
#   REPOSITORY_ROOT=/Users/<you>/code/<repo>
#   PR_PUBLISHING_ENABLED=true
#   PR_BASE_BRANCH=main
#   PR_REVIEWERS=teammate-one,teammate-two
#   make dev            # restart so the new .env is read
#
# Then:  ./scripts/demo_pull_request.sh
# Reviewers can also be passed per run:  REVIEWERS=alice,bob ./scripts/demo_pull_request.sh
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
USER_ID="${USER_ID:-lead-web}"
ADMIN_USER="${ADMIN_USER:-admin-demo}"   # publishing is admin/owner-only
PASSWORD="${PASSWORD:-warrant-demo}"
ISSUE="${ISSUE:-WEB-4519}"
PROVIDER="${PROVIDER:-mock}"
CSRF="${CSRF_TOKEN:-replace-with-a-random-token}"
KEY="${IDEMPOTENCY_KEY:-pr-demo-$(date +%s)}"
REVIEWERS="${REVIEWERS:-}"               # comma-separated; empty = use PR_REVIEWERS from .env
PR_BASE="${PR_BASE:-}"                   # empty = use PR_BASE_BRANCH from .env

PY="${PY:-python3}"
jqf() { "$PY" -c "import sys,json;d=json.load(sys.stdin);$1"; }
step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
die() { printf '\n\033[1;31m%s\033[0m\n' "$1" >&2; exit 1; }

tok() {
  curl -sS -X POST "$BASE_URL/v1/auth/token" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$1\",\"password\":\"$PASSWORD\"}" | jqf "print(d['access_token'])"
}

step "PREFLIGHT -- everything that must be true before a real PR can be opened"
ADMIN=$(tok "$ADMIN_USER")
curl -sS "$BASE_URL/v1/coding-sessions/capabilities" -H "Authorization: Bearer $ADMIN" \
  > /tmp/warrant-pr-capabilities.json
jqf "
git, pr = d['git_checkout'], d['pr_publishing']
print('  repository       :', d['repository']['root'])
print('  git checkout     :', git['available'], '-', git['reason'])
print('  pr publishing    :', pr['enabled'], '| available:', pr['available'], '-', pr['reason'])
print('  base branch      :', pr['base_branch'])
print('  default reviewers:', pr['default_reviewers'] or '(none configured)')
raise SystemExit(0 if (git['available'] and pr['available']) else 1)
" < /tmp/warrant-pr-capabilities.json || die "Preflight failed -- fix the reason printed above, then re-run.
Common causes:
  'PR publishing feature flag is disabled'  -> set PR_PUBLISHING_ENABLED=true in .env and restart make dev
  'gh CLI is not installed'                 -> brew install gh
  'gh CLI is not authenticated'             -> gh auth login
  'no compatible GitHub origin'             -> point REPOSITORY_ROOT at a clone whose origin is GitHub"

step "1. delegate $ISSUE  (deterministic policy decides, the model does not)"
LEAD=$(tok "$USER_ID")
DELEG=$(curl -sS -X POST "$BASE_URL/v1/delegations" -H "Authorization: Bearer $LEAD" \
  -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -d "{\"issue_ref\":\"$ISSUE\",\"requester_id\":\"$USER_ID\",\"target_agent_id\":\"codex-cloud\",\"idempotency_key\":\"$KEY\"}")
echo "$DELEG" | jqf "
print('  delegation:', d['id'])
print('  verdict   :', d['decision']['verdict'], d['decision']['reason_codes'])
"
DID=$(echo "$DELEG" | jqf "print(d['id'])")

step "2. human approval -> warrant  (this is where authority actually comes from)"
curl -sS -X POST "$BASE_URL/v1/delegations/$DID/decision" -H "Authorization: Bearer $LEAD" \
  -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -d "{\"action\":\"approve\",\"approver_id\":\"$USER_ID\",\"rationale\":\"Demo: governed PR\"}" \
  > /tmp/warrant-pr-approval.json
jqf "
w = d.get('warrant') or {}
print('  warrant:', w.get('id'), '| status:', w.get('status'))
print('  scope  :', w.get('scope_surfaces'))
print('  grants :', (d.get('decision') or {}).get('allowed_tools') or w.get('grants'))
" < /tmp/warrant-pr-approval.json
jqf "raise SystemExit(0 if (d.get('warrant') or {}).get('id') else 1)" \
  < /tmp/warrant-pr-approval.json \
  || die "No warrant minted -- an earlier active warrant probably still covers this scope.
Run: make demo-reset && make worktree-prune    (or try a different ISSUE=)"

step "3. coding session -- agent works on its own feature branch, never on the base branch"
SID=$(curl -sS -X POST "$BASE_URL/v1/coding-sessions" -H "Authorization: Bearer $LEAD" \
  -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
  -d "{\"delegation_id\":\"$DID\",\"provider\":\"$PROVIDER\",\"source\":\"api\"}" \
  | jqf "print(d.get('id') or d)")
echo "  session: $SID"
for _ in $(seq 1 60); do
  curl -sS "$BASE_URL/v1/coding-sessions/$SID" -H "Authorization: Bearer $LEAD" \
    > /tmp/warrant-pr-session.json
  STATE=$(jqf "print(d['state'])" < /tmp/warrant-pr-session.json)
  echo "  $STATE"
  case "$STATE" in COMPLETED|FAILED|CANCELLED) break ;; esac
  sleep 1
done
jqf "
print('  branch      :', d.get('branch_name'))
print('  verification:', [(c['name'], 'exit ' + str(c['exit_code'])) for c in d.get('verification_checks') or []])
print('  changed     :', [f['path'] for f in (d.get('diff') or {}).get('changed_files') or []])
raise SystemExit(0 if d['state'] == 'COMPLETED' else 1)
" < /tmp/warrant-pr-session.json || die "Session did not complete -- nothing is published from a failed session."

step "4. publish the DRAFT pull request and request review"
PAYLOAD=$("$PY" - "$ADMIN_USER" "$REVIEWERS" "$PR_BASE" <<'EOF'
import json, sys
actor, reviewers, base = sys.argv[1], sys.argv[2], sys.argv[3]
body = {
    "actor_id": actor,
    "title": "Governed agent change (draft)",
    "body": (
        "Opened by a Warrant coding session.\n\n"
        "- deterministic policy verdict + named human approval\n"
        "- agent confined to the warrant's scope in an isolated git worktree\n"
        "- verification run by the host, not claimed by the agent\n"
    ),
}
# Only send the keys the operator actually set, so the configured defaults still apply.
if reviewers.strip():
    body["reviewers"] = [r.strip() for r in reviewers.split(",") if r.strip()]
if base.strip():
    body["base"] = base.strip()
print(json.dumps(body))
EOF
)
curl -sS -X POST "$BASE_URL/v1/coding-sessions/$SID/pull-request" \
  -H "Authorization: Bearer $ADMIN" -H "X-CSRF-Token: $CSRF" \
  -H 'Content-Type: application/json' -d "$PAYLOAD" > /tmp/warrant-pr-published.json
jqf "
if 'error' in d:
    print('  refused:', d['error'])
    raise SystemExit(1)
print('  url       :', d['url'])
print('  number    :', d['number'], '| state:', d['state'], '| provider:', d['provider'])
print('  base      :', d.get('base'))
print('  reviewers :', d.get('reviewers') or '(none requested)')
if d.get('reviewer_error'):
    print('  NOTE      :', d['reviewer_error'])
    print('              The PR exists, but no review was requested. Reviewers must be')
    print('              collaborators on the target repository.')
" < /tmp/warrant-pr-published.json

step "5. the same facts, on the auditable session timeline"
curl -sS "$BASE_URL/v1/coding-sessions/$SID" -H "Authorization: Bearer $LEAD" | jqf "
for e in d.get('events') or []:
    if e['event_type'] in {'changes_committed', 'warrant_rechecked', 'pr_created'}:
        print('  -', e['event_type'], json.dumps(e['payload']))
"

printf '\n\033[1mOpen the PR from the URL above, or %s/coding-sessions/%s in the UI.\033[0m\n' \
  "$BASE_URL" "$SID"
