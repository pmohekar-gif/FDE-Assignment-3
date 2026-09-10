#!/usr/bin/env python3
"""Find out why an agent-CLI hook blocked a governed coding session.

A coding session that dies with `hook: <Name> Blocked` is stopped by the agent CLI's own
lifecycle hooks, not by any warrant, scope or verification rule. The CLI prints the same
"Blocked" line whether the hook *denied* the event or merely *failed* -- a gating hook
that exits non-zero for any reason is treated as a denial -- so that line alone does not
say which happened, and the two have opposite fixes.

This script shows the three things needed to tell them apart:

  1. Which hooks are registered, from which configuration file, and which of them gate
     the turn itself (`UserPromptSubmit`, `SessionStart`). A governed session inherits the
     operator's global agent configuration, because `HOME` and `CODEX_HOME` have to reach
     the subprocess for the CLI to authenticate; a hook installed globally, or by a
     globally installed plugin, is therefore in force even though nothing in this
     repository mentions it.
  2. The environment a governed session actually gives the agent, and -- more usefully --
     which variables the current shell has that a governed session strips. A `set -u`
     shell hook referencing `$USER`, or a Node hook needing `XDG_CACHE_HOME`, fails for
     want of a variable and is reported as a denial.
  3. Optionally (`--run`), each hook's exit status under exactly that stripped
     environment. Non-zero means the hook is failing, not deciding: add the names it
     needs to `CODING_AGENT_ENV_PASSTHROUGH`. Exit zero means it is denying on purpose,
     so read its logic -- the prompt this project sends contains the phrase
     "access secrets" and lists `.env`, `.pem` and `.key` restricted-path patterns, and
     the runner invokes `codex exec --ask-for-approval never` because the warrant is the
     approval.

Read-only by default: it lists configuration and environment and executes nothing.
`--run` executes the hook commands, which are the operator's own scripts and could do
anything, so it is deliberately opt-in.

Exit status:
  0  the diagnosis ran (including "no agent configuration found", which is not a failure)
  1  a configuration file exists but could not be parsed
  2  with --run, at least one turn-gating hook exited non-zero under the governed
     environment -- the most likely explanation for a blocked session
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    from warrant.coding import (  # noqa: E402
        BASELINE_AGENT_ENV,
        TURN_GATING_HOOKS,
        SubprocessCodingAgentRunner,
    )
    from warrant.config import Settings  # noqa: E402
except ImportError as exc:  # pragma: no cover - environment problem, not a hook problem
    print(f"FATAL: cannot import warrant.coding ({exc}).", file=sys.stderr)
    print("Run `make setup`, or invoke this via `make diagnose-agent-hooks`.", file=sys.stderr)
    raise SystemExit(1) from exc

HOOK_TIMEOUT_SECONDS = 30
# Variables a hook or the CLI itself is most likely to miss. Proxy settings matter most:
# on a proxied corporate network nothing that reaches out works without them. They are
# NOT in the baseline because a proxy URL can embed credentials (`http://user:pass@host`),
# so passing them is an explicit, recorded decision rather than a default.
COMMONLY_NEEDED = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "ALL_PROXY",
    "all_proxy",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "XDG_DATA_HOME",
    "NVM_DIR",
    "NODE_PATH",
    "NPM_CONFIG_PREFIX",
    "PYENV_ROOT",
    "TZ",
)
# What Codex sends a UserPromptSubmit hook. The shape matters less than the fact that
# something well-formed arrives on stdin: a hook that reads stdin and finds EOF may fail
# for that reason alone, which would be a misleading result here.
SAMPLE_PAYLOAD = {
    "hook_event_name": "UserPromptSubmit",
    "prompt": "Implement the requested outcome in this isolated Git worktree.",
    "cwd": str(PROJECT_ROOT),
}


def config_files() -> list[Path]:
    """Agent configuration that a governed session would load, global first."""
    roots: list[Path] = []
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        roots.append(Path(codex_home))
    home = os.environ.get("HOME")
    if home:
        roots.append(Path(home) / ".codex")
    roots.append(PROJECT_ROOT / ".codex")
    found: list[Path] = []
    for root in roots:
        for name in ("hooks.json", "config.toml"):
            candidate = root / name
            if candidate.is_file() and candidate not in found:
                found.append(candidate)
    return found


def hooks_from_json(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    """(event, command) pairs declared in a hooks.json, plus a parse error if any."""
    try:
        document = json.loads(path.read_text("utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"{type(exc).__name__}: {exc}"
    if not isinstance(document, dict):
        return [], "top level is not an object"
    registered = document.get("hooks")
    if not isinstance(registered, dict):
        return [], None
    entries: list[dict[str, Any]] = []
    for event, groups in registered.items():
        for group in groups if isinstance(groups, list) else []:
            inner = group.get("hooks") if isinstance(group, dict) else None
            for hook in inner if isinstance(inner, list) else []:
                if not isinstance(hook, dict):
                    continue
                command = hook.get("command")
                if isinstance(command, str) and command.strip():
                    entries.append(
                        {"event": str(event), "command": command, "source": str(path)}
                    )
    return entries, None


def hooks_from_toml(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    """(event, command) pairs declared in a config.toml, plus a parse error if any.

    `tomllib` is stdlib from 3.11, which this project requires; on an older interpreter
    the file is reported rather than guessed at, because a wrong parse here would send
    the operator looking in the wrong place.
    """
    try:
        import tomllib
    except ModuleNotFoundError:
        return [], "tomllib needs Python 3.11+; inspect this file by hand"
    try:
        document = tomllib.loads(path.read_text("utf-8", errors="replace"))
    except (OSError, ValueError) as exc:
        return [], f"{type(exc).__name__}: {exc}"
    registered = document.get("hooks")
    if not isinstance(registered, dict):
        return [], None
    entries: list[dict[str, Any]] = []

    def walk(node: Any, event: str) -> None:
        """Collect every `command` under an event, whatever nesting the TOML uses."""
        if isinstance(node, dict):
            command = node.get("command")
            if isinstance(command, str) and command.strip():
                entries.append({"event": event, "command": command, "source": str(path)})
            elif isinstance(command, list) and command:
                joined = " ".join(str(part) for part in command)
                entries.append({"event": event, "command": joined, "source": str(path)})
            for key, value in node.items():
                if key != "command":
                    walk(value, event)
        elif isinstance(node, list):
            for item in node:
                walk(item, event)

    for event, node in registered.items():
        walk(node, str(event))
    return entries, None


def governed_environment() -> dict[str, str]:
    """Exactly the environment `SubprocessCodingAgentRunner` gives the agent."""
    try:
        settings = Settings.from_env()
    except ValueError:
        settings = None
    runner = SubprocessCodingAgentRunner("codex", settings or Settings.from_env())
    passed = set(runner.environment_names())
    return {key: value for key, value in os.environ.items() if key in passed}


def run_hook(command: str, environment: dict[str, str]) -> tuple[int, str]:
    """Run one hook command under the governed environment. Returns (status, output)."""
    try:
        completed = subprocess.run(
            ["sh", "-c", command],
            input=json.dumps(SAMPLE_PAYLOAD),
            capture_output=True,
            text=True,
            timeout=HOOK_TIMEOUT_SECONDS,
            check=False,
            cwd=str(PROJECT_ROOT),
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return completed.returncode, ((completed.stdout or "") + (completed.stderr or "")).strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose an agent-CLI hook that blocked a governed coding session"
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help=(
            "execute each registered hook command under the governed environment and "
            "report its exit status. These are your own hook scripts; this runs them."
        ),
    )
    arguments = parser.parse_args()

    environment = governed_environment()
    stripped = sorted(set(os.environ) - set(environment))

    print("Governed agent environment")
    print(f"  passed to the agent : {', '.join(sorted(environment)) or '(none)'}")
    print(f"  baseline            : {', '.join(BASELINE_AGENT_ENV)}")
    extra = sorted(set(environment) - set(BASELINE_AGENT_ENV))
    print(f"  passthrough in use  : {', '.join(extra) or '(none)'}")
    print(f"  stripped from this shell ({len(stripped)}): {', '.join(stripped) or '(none)'}")
    likely = [name for name in COMMONLY_NEEDED if name in stripped]
    if likely:
        print()
        print("  Of those, the ones a hook or the CLI most often needs:")
        print(f"    {', '.join(likely)}")
        print("  Proxy and CA-bundle variables are the usual culprits on a corporate")
        print("  network. They are not passed by default because a proxy URL can embed")
        print("  credentials, so granting them is an explicit decision:")
        print(f"    CODING_AGENT_ENV_PASSTHROUGH={','.join(likely[:6])}")
    print()
    print("  A hook that needs any stripped variable exits non-zero, and the CLI reports")
    print("  a failed gating hook as a denial. Add what it needs to")
    print("  CODING_AGENT_ENV_PASSTHROUGH (secret-shaped names are refused).")
    print()

    files = config_files()
    if not files:
        print("Agent configuration: none found under $CODEX_HOME, ~/.codex, or ./.codex.")
        print("A blocked hook must then come from a globally installed plugin; list your")
        print("installed plugins and inspect the hooks they register.")
        raise SystemExit(0)

    print("Agent configuration found (a governed session loads all of these):")
    entries: list[dict[str, Any]] = []
    unparsed = False
    for path in files:
        reader = hooks_from_json if path.suffix == ".json" else hooks_from_toml
        parsed, error = reader(path)
        if error:
            print(f"  {path}  NOT READ: {error}")
            unparsed = True
            continue
        entries.extend(parsed)
        events = sorted({str(item["event"]) for item in parsed})
        print(f"  {path}  hooks: {', '.join(events) or '(none registered)'}")
    print()

    gating = [item for item in entries if str(item["event"]) in TURN_GATING_HOOKS]
    if gating:
        print("Turn-gating hooks registered — these can stop a session before it starts:")
        for item in gating:
            print(f"  {item['event']}  from {item['source']}")
            print(f"    {item['command']}")
    else:
        print("No turn-gating hook (UserPromptSubmit / SessionStart) is registered in any")
        print("configuration file read above. If a session still reports one as blocked,")
        print("it comes from an installed plugin: list your plugins and inspect the hooks")
        print("they register.")
    print()

    if not arguments.run:
        print("Re-run with --run to execute each hook under the governed environment and")
        print("see whether it fails (exit non-zero) or denies deliberately (exit 0).")
        raise SystemExit(1 if unparsed else 0)

    failures = 0
    print("Running each hook under the governed environment:")
    for item in entries:
        status, output = run_hook(str(item["command"]), environment)
        gate = " [gates the turn]" if str(item["event"]) in TURN_GATING_HOOKS else ""
        verdict = "OK" if status == 0 else f"EXIT {status}"
        print(f"  {verdict:>8}  {item['event']}{gate}  ({item['source']})")
        if output:
            for line in output.splitlines()[:6]:
                print(f"            {line}")
        if status != 0 and str(item["event"]) in TURN_GATING_HOOKS:
            failures += 1
    print()
    if failures:
        print(f"RESULT: {failures} turn-gating hook(s) exited non-zero under the governed")
        print("environment. That is the most likely reason a session reported a blocked")
        print("hook: the hook is failing, not deciding. Compare the output above with the")
        print("stripped variable list and add what it needs to CODING_AGENT_ENV_PASSTHROUGH.")
        raise SystemExit(2)
    print("RESULT: every hook exited 0 under the governed environment, so a blocked")
    print("session is a deliberate denial rather than a failure. Read the hook's own")
    print("logic: this project's prompt contains the phrase 'access secrets' and lists")
    print(".env/.pem/.key restricted-path patterns, and the runner passes")
    print("--ask-for-approval never because the warrant is the approval.")
    raise SystemExit(1 if unparsed else 0)


if __name__ == "__main__":
    main()
