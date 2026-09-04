#!/usr/bin/env bash
# End-to-end coding-session demo against a already-running Warrant server.
#
#   Terminal 1:  make dev
#   Terminal 2:  ./scripts/demo_coding_session.sh
#
# Walks the full governed path: sign in -> delegate -> policy verdict -> human
# approval -> warrant -> coding session -> worktree -> verification -> diff.
# Nothing here touches the target repository's checked-out branch: the agent runs
# in a throwaway git worktree and the diff is held for review.
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
USER_ID="${USER_ID:-lead-web}"
PASSWORD="${PASSWORD:-warrant-demo}"
ISSUE="${ISSUE:-WEB-4519}"
PROVIDER="${PROVIDER:-mock}"
# Must match CSRF_TOKEN in .env; every mutating API call carries it.
CSRF="${CSRF_TOKEN:-replace-with-a-random-token}"
KEY="${IDEMPOTENCY_KEY:-demo-$(date +%s)}"

PY="${PY:-python3}"
jqf() { "$PY" -c "import sys,json;d=json.load(sys.stdin);$1"; }
step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

step "0. server reachable, auth gate on?"
code=$(curl -sS -o /dev/null -w '%{http_code}' "$BASE_URL/")
echo "GET / -> $code  (303 = auth gate ON, 200 = auth gate OFF)"

step "1. sign in as $USER_ID (bearer token, same JWT the browser cookie carries)"
TOKEN=$(curl -sS -X POST "$BASE_URL/v1/auth/token" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USER_ID\",\"password\":\"$PASSWORD\"}" \
  | jqf "print(d['access_token'])")
AUTH="Authorization: Bearer $TOKEN"
echo "token acquired (${#TOKEN} chars)"

step "2. capabilities: what can actually run here"
curl -sS "$BASE_URL/v1/coding-sessions/capabilities" -H "$AUTH" | jqf "
print('git checkout :', d['git_checkout']['available'], '-', d['git_checkout']['root'])
print('runners      :', {k: v['available'] for k, v in d['runners'].items()})
print('verification :', [c['name'] for c in d['verification']['checks']], 'from', d['verification']['source'])
print('pr publishing:', d['pr_publishing']['enabled'], '-', d['pr_publishing']['reason'])
"

step "3. delegate $ISSUE to the agent -> deterministic policy verdict"
DELEG=$(curl -sS -X POST "$BASE_URL/v1/delegations" -H "$AUTH" -H "X-CSRF-Token: $CSRF" \
  -H 'Content-Type: application/json' \
  -d "{\"issue_ref\":\"$ISSUE\",\"requester_id\":\"$USER_ID\",\"target_agent_id\":\"codex-cloud\",\"idempotency_key\":\"$KEY\"}")
echo "$DELEG" | jqf "
print('delegation :', d['id'])
print('verdict    :', d['decision']['verdict'])
print('reasons    :', d['decision']['reason_codes'])
print('surfaces   :', d['risk_assessment']['proposed_surfaces'])
"
DID=$(echo "$DELEG" | jqf "print(d['id'])")

step "4. human approval -> warrant is minted (authority comes from here, not the model)"
curl -sS -X POST "$BASE_URL/v1/delegations/$DID/decision" -H "$AUTH" -H "X-CSRF-Token: $CSRF" \
  -H 'Content-Type: application/json' \
  -d "{\"action\":\"approve\",\"approver_id\":\"$USER_ID\",\"rationale\":\"Demo: scoped copy fix\"}" \
  > /tmp/warrant-demo-approval.json
jqf "
w = d.get('warrant') or {}
print('warrant  :', w.get('id'), '| status:', w.get('status'))
print('scope    :', w.get('scope_surfaces'))
print('expires  :', w.get('expires_at'))
" < /tmp/warrant-demo-approval.json

# Policy refuses to mint a second warrant over scope an active one already holds, so a
# re-run against the same issue approves into nothing. That is correct behaviour, not a
# failure -- but it stops the demo, so say exactly how to clear it.
if ! jqf "raise SystemExit(0 if (d.get('warrant') or {}).get('id') else 1)" \
     < /tmp/warrant-demo-approval.json; then
  cat >&2 <<'HINT'

No warrant was minted. The usual cause on a repeat run is a still-active warrant from a
previous demo already covering this scope (look for CONCURRENT_WARRANT /
SCOPE_FULLY_HELD_BY_CONCURRENT_WARRANT in the verdict reasons above).

Clear demo state and run again:

    make demo-reset       # re-seeds data/warrant.db
    make worktree-prune   # drops leftover session worktrees

Or demo a different issue:  ISSUE=PAY-2210 ./scripts/demo_coding_session.sh
HINT
  exit 1
fi

step "5. start the coding session (provider=$PROVIDER)"
SID=$(curl -sS -X POST "$BASE_URL/v1/coding-sessions" -H "$AUTH" -H "X-CSRF-Token: $CSRF" \
  -H 'Content-Type: application/json' \
  -d "{\"delegation_id\":\"$DID\",\"provider\":\"$PROVIDER\",\"source\":\"api\"}" \
  | jqf "print(d.get('id') or d)")
echo "session: $SID"
echo "watch it live at: $BASE_URL/coding-sessions/$SID"

step "6. poll to a terminal state"
for _ in $(seq 1 60); do
  curl -sS "$BASE_URL/v1/coding-sessions/$SID" -H "$AUTH" > /tmp/warrant-demo-session.json
  STATE=$(jqf "print(d['state'])" < /tmp/warrant-demo-session.json)
  echo "  $STATE"
  case "$STATE" in COMPLETED|FAILED|CANCELLED) break ;; esac
  sleep 1
done

step "7. what the host verified, and what it is holding for review"
jqf "
print('state       :', d['state'])
print('worktree    :', d.get('worktree_path'))
print('verification:', [(c['name'], 'exit ' + str(c['exit_code'])) for c in d.get('verification_checks') or []])
print('changed     :', [f['path'] for f in (d.get('diff') or {}).get('changed_files') or []])
print('restricted  :', (d.get('contract') or {}).get('restricted_paths'))
print('allowed     :', (d.get('contract') or {}).get('allowed_paths'))
print()
print('timeline:')
[print('  -', e['event_type']) for e in d.get('events') or []]
print()
print('error       :', d.get('error'))
" < /tmp/warrant-demo-session.json

printf '\n\033[1mOpen %s/coding-sessions to see it in the UI.\033[0m\n' "$BASE_URL"
