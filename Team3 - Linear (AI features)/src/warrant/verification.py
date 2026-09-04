"""Verification-command discovery for governed coding sessions.

The control plane never trusts an agent's own claim that it verified its work. It runs
the checks itself, after the agent exits, inside the isolated worktree. Which checks are
authoritative is a property of the *target* repository, not of this project, so they are
discovered from the checkout in a fixed priority order:

1. `package.json` scripts (test, lint, typecheck, build)
2. `pyproject.toml` tool configuration, then `Makefile` targets
3. simple `run:` steps in `.github/workflows/*`
4. the operator-configured `VERIFICATION_COMMAND` fallback

The first tier that yields at least one runnable check wins; the plan is then recorded on
the session contract so the command list is auditable and cannot change mid-session.

Every candidate stays an argv list. A CI `run:` line that needs a shell (pipes, `&&`,
redirection, variable expansion) is refused rather than reinterpreted, because handing it
to a shell would widen execution beyond the argv contract the sandbox depends on.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CHECK_KINDS: tuple[str, ...] = ("test", "lint", "typecheck", "build")

# Script/target names that really mean one of the four check kinds, most specific first.
SCRIPT_ALIASES: dict[str, tuple[str, ...]] = {
    "test": ("test", "tests", "test:unit", "unit"),
    "lint": ("lint", "lint:js", "eslint", "ruff"),
    "typecheck": ("typecheck", "type-check", "types", "tsc", "mypy"),
    "build": ("build", "compile"),
}

MAKE_ALIASES: dict[str, tuple[str, ...]] = {
    "test": ("test", "tests", "unit"),
    "lint": ("lint", "ruff", "flake8"),
    "typecheck": ("typecheck", "mypy", "types"),
    "build": ("build",),
}

# A `run:` line containing any of these needs a shell interpreter, so it is not eligible.
SHELL_METACHARACTERS = ("&&", "||", "|", ";", ">", "<", "$", "`", "*", "?", "~")

CI_KIND_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("typecheck", ("mypy", "tsc", "typecheck", "type-check")),
    ("lint", ("lint", "ruff", "eslint", "flake8")),
    ("test", ("pytest", "test", "unittest", "jest", "vitest")),
    ("build", ("build",)),
)

MAKE_TARGET = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9_.\-]*)\s*:(?!=)")
MAX_WORKFLOW_BYTES = 256_000


@dataclass(frozen=True)
class VerificationCheck:
    """One authoritative check the host runs itself, as an argv list."""

    name: str
    command: tuple[str, ...]
    source: str
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": list(self.command),
            "source": self.source,
            "required": self.required,
        }


@dataclass(frozen=True)
class VerificationPlan:
    """The discovered check list plus the candidates that were refused, and why."""

    checks: tuple[VerificationCheck, ...]
    source: str
    skipped: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "checks": [check.to_dict() for check in self.checks],
            "skipped": [dict(item) for item in self.skipped],
        }


def checks_from_contract(value: Any) -> list[VerificationCheck]:
    """Rebuild checks from a stored contract, ignoring anything malformed."""
    restored: list[VerificationCheck] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        command = tuple(str(part) for part in item.get("command") or ())
        if not command:
            continue
        restored.append(
            VerificationCheck(
                name=str(item.get("name") or "check"),
                command=command,
                source=str(item.get("source") or "contract"),
                required=bool(item.get("required", True)),
            )
        )
    return restored


def _read(path: Path, limit: int = MAX_WORKFLOW_BYTES) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > limit:
            return None
        return path.read_text("utf-8", errors="replace")
    except OSError:
        return None


def _python_module_available(interpreter: str, module: str) -> bool:
    """True when `interpreter -m module` can actually import, probed with an argv list."""
    probe = (
        "import importlib.util as u,sys\n"
        "try:\n"
        f"    found = u.find_spec({module!r}) is not None\n"
        "except Exception:\n"
        "    found = False\n"
        "sys.exit(0 if found else 1)\n"
    )
    try:
        result = subprocess.run(
            [interpreter, "-c", probe],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env={
                key: value
                for key, value in os.environ.items()
                if key in {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"}
            },
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def runnable(command: Sequence[str]) -> tuple[bool, str]:
    """Whether a candidate can execute here: real executable, and real module if `-m`."""
    if not command:
        return False, "candidate command is empty"
    resolved = shutil.which(command[0])
    if resolved is None:
        return False, f"{command[0]} is not on PATH"
    if len(command) >= 3 and command[1] == "-m" and Path(command[0]).name.startswith("python"):
        if not _python_module_available(resolved, command[2]):
            return False, f"{command[2]} is not importable by {command[0]}"
    return True, "available"


def _package_json_candidates(root: Path) -> list[VerificationCheck]:
    text = _read(root / "package.json")
    if text is None:
        return []
    try:
        document = json.loads(text)
    except (ValueError, TypeError):
        return []
    scripts = document.get("scripts") if isinstance(document, dict) else None
    if not isinstance(scripts, dict):
        return []
    available = {str(key) for key in scripts}
    candidates: list[VerificationCheck] = []
    for kind in CHECK_KINDS:
        for alias in SCRIPT_ALIASES[kind]:
            if alias in available and str(scripts[alias]).strip():
                candidates.append(
                    VerificationCheck(kind, ("npm", "run", "--silent", alias), "package.json")
                )
                break
    return candidates


def _pyproject_candidates(root: Path) -> list[VerificationCheck]:
    """Derive checks from configured tooling.

    Read as text rather than parsed TOML on purpose: `tomllib` is 3.11+, the marker
    sections are unambiguous, and a malformed `pyproject.toml` must degrade to the next
    tier instead of raising inside a coding session.
    """
    text = _read(root / "pyproject.toml")
    if text is None:
        return []
    lowered = text.casefold()
    candidates: list[VerificationCheck] = []
    if "[tool.pytest" in lowered or "pytest" in lowered:
        candidates.append(
            VerificationCheck("test", ("python3", "-m", "pytest", "-q"), "pyproject.toml")
        )
    if "[tool.ruff" in lowered or "ruff" in lowered:
        candidates.append(
            VerificationCheck("lint", ("python3", "-m", "ruff", "check", "."), "pyproject.toml")
        )
    if "[tool.mypy" in lowered or "mypy" in lowered:
        candidates.append(
            VerificationCheck("typecheck", ("python3", "-m", "mypy", "."), "pyproject.toml")
        )
    return candidates


def makefile_targets(text: str) -> list[str]:
    """Ordered, de-duplicated real targets, including names declared only in `.PHONY`."""
    found: list[str] = []
    for line in text.splitlines():
        if line.startswith("\t"):
            continue
        stripped = line.strip()
        if stripped.startswith(".PHONY"):
            _, _, names = stripped.partition(":")
            found.extend(names.replace("=", " ").split())
            continue
        match = MAKE_TARGET.match(stripped)
        if match:
            found.append(match.group(1))
    return [name for name in dict.fromkeys(found) if not name.startswith(".")]


def _makefile_candidates(root: Path) -> list[VerificationCheck]:
    text = _read(root / "Makefile") or _read(root / "makefile")
    if text is None:
        return []
    targets = set(makefile_targets(text))
    candidates: list[VerificationCheck] = []
    for kind in CHECK_KINDS:
        for alias in MAKE_ALIASES[kind]:
            if alias in targets:
                candidates.append(VerificationCheck(kind, ("make", alias), "makefile"))
                break
    return candidates


def _classify_ci_command(command: Sequence[str]) -> str | None:
    haystack = " ".join(command).casefold()
    for kind, markers in CI_KIND_MARKERS:
        if any(marker in haystack for marker in markers):
            return kind
    return None


def ci_run_candidates(text: str) -> list[VerificationCheck]:
    """Extract shell-free `run:` steps from one workflow document."""
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    if not isinstance(document, dict):
        return []
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return []
    candidates: list[VerificationCheck] = []
    for job in jobs.values():
        steps = job.get("steps") if isinstance(job, dict) else None
        for step in steps if isinstance(steps, list) else []:
            if not isinstance(step, dict):
                continue
            raw = step.get("run")
            if not isinstance(raw, str) or not raw.strip():
                continue
            line = raw.strip()
            if "\n" in line or any(token in line for token in SHELL_METACHARACTERS):
                continue
            try:
                command = tuple(shlex.split(line))
            except ValueError:
                continue
            kind = _classify_ci_command(command)
            if not command or kind is None:
                continue
            candidates.append(VerificationCheck(kind, command, "github-actions"))
    return candidates


def _github_actions_candidates(root: Path) -> list[VerificationCheck]:
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir():
        return []
    candidates: list[VerificationCheck] = []
    for path in sorted(workflows.iterdir()):
        if path.suffix.casefold() not in {".yml", ".yaml"}:
            continue
        text = _read(path)
        if text is None:
            continue
        candidates.extend(ci_run_candidates(text))
    return candidates


def _filter(
    candidates: Iterable[VerificationCheck],
    seen: set[tuple[str, ...]],
    skipped: list[dict[str, str]],
) -> list[VerificationCheck]:
    kept: list[VerificationCheck] = []
    for candidate in candidates:
        if candidate.command in seen:
            continue
        seen.add(candidate.command)
        ok, reason = runnable(candidate.command)
        if not ok:
            skipped.append(
                {
                    "name": candidate.name,
                    "command": " ".join(candidate.command),
                    "source": candidate.source,
                    "reason": reason,
                }
            )
            continue
        kept.append(candidate)
    return kept


def discover_verification_plan(
    root: Path,
    fallback: Sequence[str],
    max_checks: int = 4,
    enabled: bool = True,
) -> VerificationPlan:
    """Inspect a target checkout and return the checks the host will run itself."""
    limit = max(1, max_checks)
    fallback_command = tuple(str(part) for part in fallback)
    fallback_check = (
        VerificationCheck("configured", fallback_command, "configured")
        if fallback_command
        else None
    )
    if not enabled:
        checks = (fallback_check,) if fallback_check else ()
        return VerificationPlan(checks, "configured" if checks else "none")

    skipped: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    tiers: tuple[list[VerificationCheck], ...] = (
        _package_json_candidates(root),
        _pyproject_candidates(root) + _makefile_candidates(root),
        _github_actions_candidates(root),
    )
    for candidates in tiers:
        kept = _filter(candidates, seen, skipped)[:limit]
        if kept:
            # Name the sources actually used, not the tier, so the record stays literal.
            source = "+".join(dict.fromkeys(check.source for check in kept))
            return VerificationPlan(tuple(kept), source, tuple(skipped))
    if fallback_check is None:
        return VerificationPlan((), "none", tuple(skipped))
    return VerificationPlan((fallback_check,), "configured", tuple(skipped))
