#!/bin/sh
# Stop hook: restate this project's verification standard at the end of a turn.
#
# Output contract (identical for Claude Code and Codex, verified against both docs):
#   exit 0 with JSON on stdout carrying only `systemMessage`.
#
# `systemMessage` is a universal, non-blocking output field in both CLIs: it surfaces a
# message to the user and does NOT ask the agent to keep working. That is deliberate.
# Returning `decision: "block"` here would restart the turn on every single stop and
# loop forever, so this hook only ever reminds. It runs no command and reads no input.

cat <<'JSON'
{
  "systemMessage": "Warrant verification standard: run tests as `pytest -o addopts=` -- pyproject sets addopts=\"-q\", which hides the summary line, so a bare `pytest` cannot show you the counts. Baseline is 268 passed, 1 skipped; any other numbers are a regression to explain, not to wave through. Full gate: `make check` (lint, typecheck, unit, integration, eval, build). Agent CLI argv check: `make verify-agent-cli`."
}
JSON
