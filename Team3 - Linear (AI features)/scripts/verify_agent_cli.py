#!/usr/bin/env python3
"""Check the argv `SubprocessCodingAgentRunner` builds against the real CLIs' --help.

`src/warrant/coding.py` shells out to an external coding-agent CLI with a hand-written
argument vector. Nothing in the test suite has ever compared that argv against the flags
the installed CLI actually accepts, because the CLIs are not present in CI. A wrong flag
would surface only as an opaque non-zero exit inside a live coding session.

This script closes that gap on any machine where the CLIs *are* installed. It imports the
real runner (it never restates the argv, so it cannot drift from the code it checks),
prints the exact vector, then reads each detected CLI's own `--help` and reports, flag by
flag, whether that CLI recognises it.

What it will not do:
  * run a coding task, or any agent subcommand other than `--version` / `--help`
  * write, create, or delete anything, in the repository or outside it
  * open a network connection

Exit status:
  0  every flag of every detected CLI was found in that CLI's help (or no CLI is
     installed, which is not a failure -- there is simply nothing to check here)
  1  at least one flag was not recognised, or a CLI's help could not be read
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Import the runner from the source tree, so `python scripts/verify_agent_cli.py` works
# without the caller having to set PYTHONPATH.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    from warrant.coding import (  # noqa: E402
        CodingAgentError,
        CodingSessionService,
        SubprocessCodingAgentRunner,
    )
    from warrant.config import Settings  # noqa: E402
except ImportError as exc:  # pragma: no cover - environment problem, not a flag problem
    print(f"FATAL: cannot import warrant.coding ({exc}).", file=sys.stderr)
    print("Run `make setup`, or invoke this via `make verify-agent-cli`.", file=sys.stderr)
    raise SystemExit(1) from exc

# Executables the project could plausibly drive. `codex` is the one the default runner
# registry wires up; `claude` is here because it is the other CLI an operator is likely to
# have installed and to assume is supported.
CANDIDATE_EXECUTABLES = ("claude", "codex")

# A path that is only ever *formatted into* the argv, never created or written to.
SAMPLE_WORKSPACE = Path("/tmp/warrant-verify-agent-cli/sample-worktree")

SUBPROCESS_TIMEOUT_SECONDS = 20


def _sample_prompt() -> str:
    """The prompt the service really sends, so the argv is checked at full fidelity.

    `CodingSessionService._prompt` reads only its `contract` argument and never touches
    `self`, so it can be called unbound against a sample contract without standing up a
    database, a repository provider, or the warrant service. If that ever stops being
    true, fall back to a labelled placeholder: the prompt is a positional argument, so its
    exact text does not affect which *flags* get verified.
    """
    contract: dict[str, Any] = {
        "requested_outcome": "Add a regression test for the expiry guard",
        "issue": {"external_key": "WAR-123", "title": "Warrant expiry is not enforced"},
        "allowed_paths": ["src/warrant/policy.py", "tests/unit/**"],
        "warrant": {"evidence_contract": ["tests pass", "no new lint findings"]},
    }
    try:
        return CodingSessionService._prompt(None, contract)  # type: ignore[arg-type]
    except Exception:
        return "SAMPLE PROMPT (real prompt builder unavailable)"


def _run(argv: list[str]) -> tuple[int, str]:
    """Run a read-only CLI probe. Returns (exit status, combined output)."""
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
            cwd=str(PROJECT_ROOT),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def _subcommands_from_help(help_text: str) -> set[str]:
    """The subcommand names a CLI lists in its own help.

    Both `claude` and `codex` render a clap/argparse-style block. Reading the boundary out
    of the help text (instead of assuming which argv token is the subcommand) is what lets
    this script split global flags from subcommand flags without hardcoding either CLI.
    """
    names: set[str] = set()
    in_block = False
    for line in help_text.splitlines():
        if re.match(r"^\s*(commands|subcommands)\s*:\s*$", line, re.IGNORECASE):
            in_block = True
            continue
        if not in_block:
            continue
        if not line.strip():  # a blank line closes the block
            break
        if not line.startswith((" ", "\t")):  # a new unindented section closes it too
            break
        candidate = line.strip().split()[0]
        if re.fullmatch(r"[a-z][a-z0-9-]*", candidate):
            names.add(candidate)
    return names


def _flag_in_help(flag: str, help_text: str) -> bool:
    """Whether `flag` appears in help as a whole token, not as a prefix of a longer one."""
    return re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", help_text) is not None


def _split_argv(argv: list[str], subcommands: set[str]) -> tuple[list[str], str | None, list[str]]:
    """Split argv into (flags before the subcommand, the subcommand, flags after it)."""
    before: list[str] = []
    after: list[str] = []
    subcommand: str | None = None
    for token in argv[1:]:
        if subcommand is None and token in subcommands:
            subcommand = token
            continue
        target = after if subcommand is not None else before
        if token.startswith("-"):
            target.append(token.split("=", 1)[0])
    return before, subcommand, after


def _report_flags(label: str, flags: list[str], help_text: str, ok: bool) -> int:
    """Print one PASS/FAIL row per flag. Returns the number of failures."""
    failures = 0
    for flag in flags:
        if not ok:
            print(f"    FAIL  {flag:<24} could not read `{label}`")
            failures += 1
        elif _flag_in_help(flag, help_text):
            print(f"    PASS  {flag:<24} recognised by `{label}`")
        else:
            print(f"    FAIL  {flag:<24} NOT found in `{label}`")
            failures += 1
    return failures


def verify_executable(name: str, settings: Settings, prompt: str) -> tuple[bool, int, int]:
    """Verify one CLI. Returns (was it installed, failures, flags actually checked)."""
    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}")

    resolved = shutil.which(name)
    if resolved is None:
        print(f"  not installed: `{name}` is not on PATH -- nothing to verify")
        return False, 0, 0
    print(f"  path      : {resolved}")

    version_status, version_output = _run([name, "--version"])
    first_line = version_output.strip().splitlines()[0] if version_output.strip() else "(no output)"
    print(f"  version   : {first_line}" + ("" if version_status == 0 else "  [--version failed]"))

    runner = SubprocessCodingAgentRunner(name, settings)
    try:
        argv = runner._command(SAMPLE_WORKSPACE, prompt)
    except CodingAgentError as exc:
        print(f"\n  SubprocessCodingAgentRunner builds NO argv for `{name}`: {exc}")
        print("  This CLI is installed but the runner cannot drive it, so there are no")
        print("  flags to check. Not counted as a failure.")
        return True, 0, 0

    print("\n  argv SubprocessCodingAgentRunner would execute:")
    print(f"    json  {json.dumps(argv)}")
    print(f"    shell {shlex.join(argv)}")
    print(f"    ({len(argv)} elements; the prompt is a single element containing newlines)")

    help_status, help_text = _run([name, "--help"])
    help_ok = help_status == 0 and bool(help_text.strip())
    if not help_ok:
        print(f"\n  FAIL: `{name} --help` did not produce readable output")

    subcommands = _subcommands_from_help(help_text) if help_ok else set()
    before, subcommand, after = _split_argv(argv, subcommands)

    failures = 0
    checked = 0
    print(f"\n  global flags, checked against `{name} --help`:")
    if before:
        failures += _report_flags(f"{name} --help", before, help_text, help_ok)
        checked += len(before)
    else:
        print("    (none)")

    print(f"\n  subcommand, checked against the command list in `{name} --help`:")
    if subcommand is not None:
        print(f"    PASS  {subcommand:<24} listed as a subcommand of `{name}`")
        checked += 1
    else:
        # No argv token matched a listed subcommand. Either the CLI does not use
        # subcommands, or its help layout changed and the split is unreliable.
        non_flags = [token for token in argv[1:] if not token.startswith("-")]
        print("    FAIL  no argv token matched a subcommand listed in help")
        print(f"          non-flag argv tokens were: {non_flags[:3]}")
        print(f"          subcommands parsed from help: {sorted(subcommands) or '(none parsed)'}")
        failures += 1

    if subcommand is not None:
        sub_label = f"{name} {subcommand} --help"
        sub_status, sub_help = _run([name, subcommand, "--help"])
        sub_ok = sub_status == 0 and bool(sub_help.strip())
        print(f"\n  subcommand flags, checked against `{sub_label}`:")
        if after:
            failures += _report_flags(sub_label, after, sub_help, sub_ok)
            checked += len(after)
        else:
            print("    (none)")
    elif after:
        print("\n  subcommand flags: skipped, no subcommand boundary was identified")

    return True, failures, checked


def main() -> int:
    print("Warrant agent-CLI argv verification")
    print("Compares the argv SubprocessCodingAgentRunner builds against each installed")
    print("CLI's own --help. Read-only: no coding task is run and nothing is written.")
    print(f"\nsource   : {PROJECT_ROOT / 'src' / 'warrant' / 'coding.py'}")
    print(f"workspace: {SAMPLE_WORKSPACE}  (formatted into argv only, never created)")

    settings = Settings.from_env()
    prompt = _sample_prompt()

    installed: list[str] = []
    total_failures = 0
    total_checked = 0
    for name in CANDIDATE_EXECUTABLES:
        found, failures, checked = verify_executable(name, settings, prompt)
        total_failures += failures
        total_checked += checked
        if found:
            installed.append(name)

    print(f"\n{'=' * 78}\nsummary\n{'=' * 78}")
    if not installed:
        print("No agent CLI is installed on this machine, so no flag could be checked.")
        print(f"Looked for: {', '.join(CANDIDATE_EXECUTABLES)}")
        print("\nRESULT: nothing to verify (exit 0). Re-run where the CLIs are installed.")
        return 0

    print(f"CLIs found    : {', '.join(installed)}")
    print(f"flags checked : {total_checked}")
    if total_failures:
        print(f"\nRESULT: {total_failures} unrecognised flag(s). The argv in")
        print("src/warrant/coding.py does not match the installed CLI and a real coding")
        print("session would fail. Fix `SubprocessCodingAgentRunner._command`.")
        return 1
    # Distinguished from a real pass on purpose: an installed CLI the runner has no argv
    # for verifies nothing, and reporting it as a pass would be the exact overclaim this
    # script exists to prevent.
    if total_checked == 0:
        print("\nRESULT: no flag could be checked (exit 0). Every installed CLI is one")
        print("SubprocessCodingAgentRunner builds no argv for. The gap is still open --")
        print("install `codex` and re-run to actually verify the argv.")
        return 0
    print(f"\nRESULT: all {total_checked} checked flag(s) are recognised by their CLI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
