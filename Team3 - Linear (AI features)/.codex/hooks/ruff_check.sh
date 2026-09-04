#!/bin/sh
# PostToolUse hook: lint the project after an agent edits Python under src/ or tests/.
#
# Output contract (identical for Claude Code and Codex, verified against both docs):
#   exit 0  nothing to say (irrelevant edit, lint clean, or ruff unavailable)
#   exit 2  lint failed; the reason on stderr is shown to the model
# On PostToolUse neither CLI can undo the edit, so exit 2 is feedback, not a block.
#
# Safety: read-only. Runs `ruff check` and nothing else. Never commits, pushes,
# deletes, writes files, or touches anything outside this repository.

set -u

# The repo root is two levels above this script, so the hook is correct whether the
# agent started in the root or in a subdirectory.
hook_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 0
root=$(CDPATH= cd -- "$hook_dir/../.." && pwd) || exit 0

payload=$(cat)

# Only lint when the event actually touched Python under src/ or tests/. Matching the
# raw payload rather than one named field keeps this working across both CLIs' differing
# tool-input shapes (Claude's Edit/Write `file_path`, Codex's `apply_patch` command text).
printf '%s' "$payload" |
	grep -Eq '(^|[^A-Za-z0-9_./-])(src|tests)/[A-Za-z0-9_./-]*\.py' || exit 0

# Resolve a ruff that actually runs on this machine. The checked-in .venv is not
# relocatable and may have been built for another OS, so every candidate is probed with
# --version rather than assumed to work from the fact that the file exists.
ruff_cmd=""
for candidate in \
	"$root/.venv/bin/ruff" \
	"ruff" \
	"$root/.venv/bin/python -m ruff" \
	"python3 -m ruff"; do
	# Unquoted on purpose: these are literal strings, and the `-m ruff` forms must split.
	# shellcheck disable=SC2086
	if $candidate --version >/dev/null 2>&1; then
		ruff_cmd="$candidate"
		break
	fi
done

# Lint being unavailable is not the agent's fault: stay silent instead of blocking.
[ -n "$ruff_cmd" ] || exit 0

cd -- "$root" || exit 0

# Exactly what `make lint` runs, so the hook and the gate can never disagree.
# shellcheck disable=SC2086
output=$($ruff_cmd check src tests 2>&1)
status=$?

[ "$status" -eq 0 ] && exit 0

{
	echo "ruff check failed after this edit. The project gate (\`make lint\`) runs the"
	echo "same command, so this will fail CI until it is fixed:"
	echo
	printf '%s\n' "$output" | head -n 40
} >&2
exit 2
