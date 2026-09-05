# Agent tooling

Development-time tooling for coding agents working *on* this repository. None of it is
a runtime dependency: the application neither imports nor executes anything described
here, and deleting this directory changes no product behaviour.

Do not confuse this with the coding-agent adapters in `src/warrant/coding.py`, which are
a governed product feature. This document is about the agents that edit Warrant itself.

## Lifecycle hooks

Both Claude Code and Codex are configured with the same two project-scoped hooks, so a
change made through either tool is held to the same standard.

| File | Tool | Purpose |
| --- | --- | --- |
| `.claude/settings.json` | Claude Code | Hook registration |
| `.codex/hooks.json` | Codex | Hook registration |
| `.claude/hooks/ruff_check.sh`, `.codex/hooks/ruff_check.sh` | both | `PostToolUse` lint |
| `.claude/hooks/stop_reminder.sh`, `.codex/hooks/stop_reminder.sh` | both | `Stop` reminder |

### `ruff_check.sh` — PostToolUse

Fires after an edit and runs `ruff check src tests` — byte-identical to what `make lint`
runs, so the hook and the CI gate cannot disagree.

- Only lints when the tool payload actually touched a `.py` file under `src/` or
  `tests/`. It matches the raw payload rather than one named field, so it works across
  Claude's `Edit`/`Write` (`file_path`) and Codex's `apply_patch` (command text).
- Probes each candidate `ruff` with `--version` before using it. The checked-in `.venv`
  is not relocatable and may have been built for a different OS, so existence of the
  file is never treated as proof it runs.
- Exit `0` when the edit is irrelevant, lint is clean, or ruff is unavailable. Exit `2`
  with the failure on stderr when lint fails. On `PostToolUse` neither CLI can undo the
  edit, so exit 2 is feedback to the model, not a block.

### `stop_reminder.sh` — Stop

Emits a non-blocking `systemMessage` restating the project's verification standard:

- Run tests as `pytest -o addopts=`. `pyproject.toml` sets `addopts = "-q"`, which hides
  the summary line, so a bare `pytest` shows dots and no counts.
- Baseline is **268 passed, 1 skipped**. Any other numbers are a regression to explain,
  not to wave through.
- Full gate is `make check`.

It deliberately does not return `decision: "block"`. Blocking on `Stop` restarts the turn
every single time and loops forever.

### Safety

Both hooks are read-only. They never commit, push, delete, write files, or touch
anything outside this repository. Codex will ask you to review and trust the hook before
it runs; that prompt is expected.

## `make verify-agent-cli`

Closes a real gap: `SubprocessCodingAgentRunner` shells out to an external coding-agent
CLI, and the argv it builds had never been checked against that CLI's actual `--help`.

`scripts/verify_agent_cli.py` does not run a coding task, write to the repo, or make a
network call. It:

1. Detects which agent CLIs are on `PATH` and records each one's `--version`.
2. Imports `SubprocessCodingAgentRunner` from `warrant.coding` and prints the **exact**
   argv it would construct for a sample task — read from the runner, never hardcoded.
3. Runs `--help` on each detected CLI and checks every flag in that argv against the
   help output, flag by flag, PASS/FAIL.
4. Exits non-zero if any flag is unrecognised.

```
make verify-agent-cli
```

### Interpreting the result

The read-only probe on this machine on 2026-09-04 reported:

```
claude
  path      : /Users/pmohekar/.local/bin/claude
  version   : 2.1.259 (Claude Code)
  SubprocessCodingAgentRunner builds NO argv for `claude`: unsupported real
  coding-agent executable

codex
  path      : /opt/homebrew/bin/codex
  version   : codex-cli 0.153.0
  PASS  --sandbox
  PASS  --ask-for-approval
  PASS  exec
  PASS  --cd
  PASS  --ephemeral

CLIs found    : claude, codex
flags checked : 5
RESULT: all 5 checked flags are recognised by their CLI.
```

The runner still does not support Claude Code, but its generated Codex argv now matches
the installed CLI. This proves installation and flag compatibility only. The probe does
not authenticate, contact the network, or execute a coding task, so a successful real
Codex session remains a separate end-to-end check.

See `docs/LIMITATIONS.md` for the standing caveat on unverified external-agent execution.
