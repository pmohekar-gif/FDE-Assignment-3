#!/usr/bin/env bash
# Audit-chain demo against an already-running Warrant server.
#
#   Terminal 1:  make dev
#   Terminal 2:  ./scripts/demo_audit_chain.sh
#
# Shows the three things that make the ledger an accountability record rather than a log:
#   1. admin-only read, hash-chained, verified over the WHOLE ledger (filters cannot hide a break)
#   2. the database itself refuses UPDATE/DELETE on audit_events
#   3. if that guard is removed, the hash chain still names the exact broken sequence number
#
# Step 5 (tamper) works on a THROWAWAY COPY of the database. Your real data/warrant.db is
# never modified. Skip it with:  TAMPER=0 ./scripts/demo_audit_chain.sh
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
ADMIN_USER="${ADMIN_USER:-admin-demo}"
NON_ADMIN_USER="${NON_ADMIN_USER:-lead-web}"
PASSWORD="${PASSWORD:-warrant-demo}"
DB="${DATABASE_PATH:-data/warrant.db}"
TAMPER="${TAMPER:-1}"

PY="${PY:-python3}"
jqf() { "$PY" -c "import sys,json;d=json.load(sys.stdin);$1"; }
step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

tok() {
  curl -sS -X POST "$BASE_URL/v1/auth/token" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$1\",\"password\":\"$PASSWORD\"}" | jqf "print(d['access_token'])"
}

step "1. sign in as $ADMIN_USER (the ledger is admin-only)"
ADMIN=$(tok "$ADMIN_USER")
echo "token acquired"

step "2. read the ledger -- chain verification runs over every event, not just the page"
curl -sS "$BASE_URL/v1/audit?limit=10" -H "Authorization: Bearer $ADMIN" > /tmp/warrant-audit.json
jqf "
print('chain_verified :', d['chain_verified'])
print('broken_at_seq  :', d['broken_at_seq'])
print('returned       :', len(d['events']), 'events (newest first)')
print()
for e in d['events'][:10]:
    print('  #%-4s %-30s %-24s %s' % (e['seq'], e['event_type'], e['actor_id'], e['hash'][:16]))
" < /tmp/warrant-audit.json

step "3. every hash commits to the one before it"
jqf "
ev = sorted(d['events'], key=lambda e: e['seq'])
for a, b in zip(ev, ev[1:]):
    ok = 'links' if b['prev_hash'] == a['hash'] else 'BROKEN'
    print('  #%-4s -> #%-4s  %s' % (a['seq'], b['seq'], ok))
" < /tmp/warrant-audit.json

step "4. a non-admin cannot read it at all"
NON_ADMIN=$(tok "$NON_ADMIN_USER")
printf '  %s -> HTTP %s\n' "$NON_ADMIN_USER" \
  "$(curl -sS -o /dev/null -w '%{http_code}' "$BASE_URL/v1/audit" -H "Authorization: Bearer $NON_ADMIN")"

step "5. filters narrow the view, never the verification"
for q in 'verdict=ALLOW' 'verdict=DENY' 'agent_id=codex-cloud'; do
  curl -sS "$BASE_URL/v1/audit?$q&limit=100" -H "Authorization: Bearer $ADMIN" \
    | jqf "print('  %-26s %3d events | chain_verified=%s' % ('$q', len(d['events']), d['chain_verified']))"
done

step "6. export the ledger as CSV (what you hand an auditor)"
curl -sS "$BASE_URL/v1/audit?format=csv&limit=300" -H "Authorization: Bearer $ADMIN" \
  > /tmp/warrant-audit.csv
echo "  wrote /tmp/warrant-audit.csv ($(wc -l < /tmp/warrant-audit.csv) lines)"
head -3 /tmp/warrant-audit.csv | cut -c1-120

if [ "$TAMPER" != "1" ]; then
  printf '\n(tamper demo skipped)\n'
  exit 0
fi

step "7. tamper demo -- on a throwaway COPY of $DB"
cp "$DB" /tmp/warrant-tamper.db
echo "  copied to /tmp/warrant-tamper.db"

echo
echo "  7a. the database itself refuses to rewrite history:"
"$PY" - <<'EOF'
import sqlite3
c = sqlite3.connect('/tmp/warrant-tamper.db')
seq = c.execute("SELECT seq FROM audit_events ORDER BY seq LIMIT 1 OFFSET 4").fetchone()[0]
try:
    c.execute("UPDATE audit_events SET payload_json='{\"tampered\":true}' WHERE seq=?", (seq,))
except sqlite3.IntegrityError as error:
    print(f"      UPDATE seq={seq} -> refused: {error}")
try:
    c.execute("DELETE FROM audit_events WHERE seq=?", (seq,))
except sqlite3.IntegrityError as error:
    print(f"      DELETE seq={seq} -> refused: {error}")
EOF

echo
echo "  7b. now assume the attacker has DBA rights and drops the guard:"
"$PY" - <<'EOF'
import sqlite3
c = sqlite3.connect('/tmp/warrant-tamper.db')
c.execute("DROP TRIGGER audit_no_update")
seq = c.execute("SELECT seq FROM audit_events ORDER BY seq LIMIT 1 OFFSET 4").fetchone()[0]
c.execute(
    "UPDATE audit_events SET payload_json=? WHERE seq=?",
    ('{"verdict":"ALLOW","tampered":true}', seq),
)
c.commit()
print(f"      trigger dropped, seq={seq} payload rewritten, hashes left untouched")
EOF

echo
echo "  7c. the hash chain still catches it, and names the sequence:"
# Re-derived here from stdlib only, mirroring AuditLedger.verify_detail. Deliberately does
# not import `warrant`: an auditor checking the ledger should not have to trust -- or even
# install -- the application that wrote it. Any Python 3 will do.
"$PY" - <<'EOF'
import hashlib
import json
import sqlite3

GENESIS = "0" * 64
FIELDS = (
    "workspace_id", "seq", "event_type", "actor_type", "actor_id",
    "subject_type", "subject_id", "payload", "created_at",
)

connection = sqlite3.connect("/tmp/warrant-tamper.db")
connection.row_factory = sqlite3.Row
previous, verified, broken = GENESIS, True, None
for row in connection.execute("SELECT * FROM audit_events ORDER BY workspace_id, seq"):
    content = {name: row[name] for name in FIELDS if name != "payload"}
    content["payload"] = json.loads(row["payload_json"] or "{}")
    canonical = json.dumps(content, separators=(",", ":"), sort_keys=True, ensure_ascii=True)
    expected = hashlib.sha256((previous + canonical).encode()).hexdigest()
    if row["prev_hash"] != previous or row["hash"] != expected:
        verified, broken = False, row["seq"]
        break
    previous = row["hash"]
print(f"      independent re-verification -> verified={verified} broken_at_seq={broken}")
EOF

printf '\n\033[1mOpen %s/audit (as %s) to see the same thing in the UI.\033[0m\n' "$BASE_URL" "$ADMIN_USER"
