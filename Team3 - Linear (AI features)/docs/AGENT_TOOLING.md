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
- Baseline is **444 passed, 1 skipped** (2026-09-10). Any other numbers are a regression
  to explain, not to wave through.
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
Codex session remains a separate end-to-end check:
`RUN_REAL_CODEX=1 pytest tests/e2e/test_real_codex_session.py`.

## `make diagnose-agent-hooks`

Answers one question: why did a governed coding session report `hook: <Name> Blocked`?

That line means the agent CLI's own lifecycle hooks stopped the run — no warrant, scope
or verification rule was involved. It is ambiguous in an important way: **the CLI prints
it both when a hook deliberately denies and when a hook merely fails**, because a gating
hook that exits non-zero is treated as a denial. The two have opposite fixes.

A governed session also inherits the operator's *global* agent configuration, because
`HOME` and `CODEX_HOME` must reach the subprocess for the CLI to authenticate. A hook
installed globally, or by a globally installed plugin, is therefore in force even though
nothing in this repository mentions it. This project registers only `PostToolUse` and
`Stop`.

```
make diagnose-agent-hooks              # read-only: configuration + environment
make diagnose-agent-hooks ARGS=--run   # also runs each hook under that environment
```

It prints three things:

1. Every configuration file a session loads — `hooks.json` and `config.toml`, global
   and project — the hooks each registers, and which of them gate the turn itself
   (`UserPromptSubmit`, `SessionStart`). A file that cannot be parsed is reported as
   unread rather than treated as hook-free.
2. The environment a session gives the agent, and which variables it strips from your
   shell — highlighting the ones a hook or the CLI most often needs. Proxy and CA-bundle
   variables are the usual culprits on a corporate network; they are not passed by
   default because a proxy URL can embed credentials.
3. With `--run`, each hook's exit status under exactly that environment. **Non-zero means
   the hook is failing, not deciding**: add the names it needs to
   `CODING_AGENT_ENV_PASSTHROUGH` (secret-shaped names are refused). **Exit zero means it
   is denying on purpose**, so read its logic — this project's prompt contains the phrase
   "access secrets" and lists `.env`, `.pem` and `.key` restricted-path patterns, and the
   runner passes `--ask-for-approval never` because the warrant *is* the approval.

Read-only by default. `--run` executes your own hook scripts, so it is opt-in.

### `CODING_AGENT_ISOLATED_HOME` — when the denial is real, but not yours

Run the diagnostic against this repository's own operator hooks (2026-09-10): every
registered hook exited 0 under the governed environment, so the block was a deliberate
denial, not a failure — but the denying hook (`UserPromptSubmit`, from `~/.codex/hooks.json`)
turned out to be a global hook installed by an unrelated project (its `if [ -f ... ]`
guard names a path under a different repository entirely), not anything this project or
its `.codex/hooks.json` registers.

`CODING_AGENT_ISOLATED_HOME=true` runs each governed session under a private `CODEX_HOME`
instead: your `auth.json` is copied in so the CLI still authenticates, `config.toml`'s
`model`/`provider` settings come along, but `hooks.json` is left behind entirely and any
`[hooks...]` tables in `config.toml` are stripped (`coding.prepare_isolated_agent_home`,
`coding.strip_hooks_table`). A governed session already carries its own approval — the
warrant, and `--ask-for-approval never` — so a global hook belonging to some other tool has
no standing to gate it. The private home lives beside the session's worktree (never inside
it, so it cannot pollute a diff) and is removed with it on teardown.

Use `CODING_AGENT_ENV_PASSTHROUGH` when `--run` shows a hook failing (non-zero exit);
use `CODING_AGENT_ISOLATED_HOME` when it shows a hook denying (exit 0) and that hook
does not belong to this project.

See `docs/LIMITATIONS.md` for the standing caveat on unverified external-agent execution.
