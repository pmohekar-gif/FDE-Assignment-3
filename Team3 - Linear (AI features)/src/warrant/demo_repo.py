"""Build the self-contained Git checkout the coding-session demo actually needs.

Coding sessions refuse to run outside a Git checkout, and the delivered project folder
ships a `.gitignore` but no `.git`. Rather than weaken that requirement, `make demo-repo`
materialises a small, real repository under `.runtime/demo-repo` (gitignored) whose paths
are exactly the `path_hints` declared by the seeded issues and the globs declared by
`policies/surfaces.yaml`, so retrieval, warrant scope and worktree diffs line up on the
same files.

The demo repository carries its own fast, dependency-free checks (`make test`,
`make lint`, stdlib only) so verification discovery has something real and quick to find
instead of running this project's whole suite inside every worktree.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, Settings
from .verification import discover_verification_plan

DEMO_GIT_USER = "Warrant Demo"
DEMO_GIT_EMAIL = "demo@example.invalid"
DEFAULT_BRANCH = "main"
STALE_GIT_LOCK_SECONDS = 300
RECOVERABLE_GIT_LOCKS = (
    Path(".git/index.lock"),
    Path(".git/HEAD.lock"),
    Path(".git/objects/maintenance.lock"),
)

FILES: dict[str, str] = {
    ".gitignore": "__pycache__/\n*.py[cod]\nnode_modules/\n.DS_Store\n",
    "README.md": """# Northstar demo service repository (SIMULATED)

A fictional, self-contained checkout used by the Warrant coding-session demo. Every path
here matches a seeded issue `path_hint` and a `policies/surfaces.yaml` glob, so policy
scope, retrieval evidence and agent diffs all refer to the same files.

Two kinds of file live here. The product surfaces named by `policies/surfaces.yaml`
(`services/**`, `web/**`, `infra/**`) are written out in full. Every other seeded issue
path hint gets a labelled stand-in carrying the `SIMULATED stand-in file` banner, so a
warrant scoped to that hint resolves to a real tracked file instead of nothing.

Checks are stdlib-only and finish in well under a second:

    make test   # python3 -m unittest discover -q -s tests -t .
    make lint   # python3 -m compileall -q services tests src
""",
    "Makefile": """.PHONY: test lint

test:
\tpython3 -m unittest discover -q -s tests -t .

lint:
\tpython3 -m compileall -q services tests $(wildcard src)
""",
    ".github/workflows/ci.yml": """name: ci

on:
  push:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: unit tests
        run: make test
      - name: lint
        run: make lint
""",
    "services/__init__.py": "",
    "services/billing/__init__.py": "",
    "services/billing/retry.py": '''"""Checkout capture retries (PAY-4471 surface)."""

from __future__ import annotations

RETRY_WINDOW_SECONDS = 5.0


class DuplicateCapture(Exception):
    """Raised when the same checkout attempt is captured twice."""


class CaptureLedger:
    """Remembers which idempotency keys were already captured."""

    def __init__(self) -> None:
        self._captured: dict[str, float] = {}

    def capture(self, idempotency_key: str, now: float) -> str:
        previous = self._captured.get(idempotency_key)
        if previous is not None and now - previous <= RETRY_WINDOW_SECONDS:
            raise DuplicateCapture(idempotency_key)
        self._captured[idempotency_key] = now
        return idempotency_key


def retry_capture(ledger: CaptureLedger, idempotency_key: str, now: float) -> bool:
    """Return True when this retry produced a new capture, False when it was suppressed."""
    try:
        ledger.capture(idempotency_key, now)
    except DuplicateCapture:
        return False
    return True
''',
    "services/billing/invoices.py": '''"""Invoice rendering (synthetic PAY surface)."""

from __future__ import annotations


def invoice_number(sequence: int, prefix: str = "NS") -> str:
    if sequence < 1:
        raise ValueError("invoice sequence starts at 1")
    return f"{prefix}-{sequence:06d}"


def total_minor_units(lines: list[dict[str, int]]) -> int:
    return sum(int(line["quantity"]) * int(line["unit_minor_units"]) for line in lines)
''',
    "services/billing/ledger/__init__.py": "",
    "services/billing/ledger/entries.py": '''"""Append-only billing ledger."""

from __future__ import annotations


class LedgerClosed(Exception):
    """Raised when a posted ledger entry is edited or removed."""


class Ledger:
    def __init__(self) -> None:
        self._entries: list[dict[str, object]] = []

    def post(self, entry: dict[str, object]) -> int:
        self._entries.append(dict(entry))
        return len(self._entries)

    def amend(self, index: int, entry: dict[str, object]) -> None:
        raise LedgerClosed("ledger entries are append-only; post a reversal instead")

    def entries(self) -> list[dict[str, object]]:
        return [dict(item) for item in self._entries]
''',
    "services/auth/__init__.py": "",
    "services/auth/keys/__init__.py": "",
    "services/auth/keys/signing.py": '''"""Signing key material (SEC-4502 surface)."""

from __future__ import annotations

ACTIVE_KEY_ID = "signing-2024-06"
RETIRED_KEY_IDS = ("signing-2023-11",)


class KeyExpired(Exception):
    """Raised when a retired key is used to sign."""


def resolve_key_id(requested: str | None = None) -> str:
    key_id = requested or ACTIVE_KEY_ID
    if key_id in RETIRED_KEY_IDS:
        raise KeyExpired(key_id)
    return key_id


def rotate(active: str, next_key: str, retired: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    """Return the new active key and the retired set, refusing to reuse a retired key."""
    if next_key in retired or next_key == active:
        raise KeyExpired(next_key)
    return next_key, (*retired, active)
''',
    "services/exports/__init__.py": "",
    "services/exports/worker.py": '''"""Background export worker (synthetic DATA issues surface)."""

from __future__ import annotations

MAX_ATTEMPTS = 3


def next_delay_seconds(attempt: int) -> int:
    if attempt < 1 or attempt > MAX_ATTEMPTS:
        raise ValueError("attempt is outside the retry budget")
    return 2 ** (attempt - 1)


def export_name(workspace: str, day: str) -> str:
    return f"{workspace}-activity-{day}.csv"
''',
    "infra/deploy/auth.yaml": """service: auth
replicas: 3
strategy: rolling
health_check:
  path: /healthz
  timeout_seconds: 2
signing_key_secret: auth-signing-key
""",
    "infra/build/pipeline.yaml": """pipeline: northstar-build
stages:
  - name: unit
    command: [make, test]
  - name: lint
    command: [make, lint]
artifacts:
  retain_days: 14
""",
    "web/checkout/RetryButton.tsx": """import { useState } from 'react';

export const RETRY_LABEL = 'Retry payment';

export function RetryButton({ onRetry }: { onRetry: () => Promise<void> }) {
  const [pending, setPending] = useState(false);
  async function handleClick() {
    if (pending) return;
    setPending(true);
    try {
      await onRetry();
    } finally {
      setPending(false);
    }
  }
  return (
    <button type="button" disabled={pending} onClick={handleClick}>
      {RETRY_LABEL}
    </button>
  );
}
""",
    "web/reports/EmptyState.tsx": """export const emptyState = 'No activity';

export function EmptyState({ href }: { href: string }) {
  return (
    <div className="empty-state">
      <p>{emptyState}</p>
      <a href={href}>Learn about reports</a>
    </div>
  );
}
""",
    "web/reports/Table.tsx": """export type Row = { id: string; label: string; total: number };

export const PAGE_SIZE = 25;

export function page(rows: Row[], index: number): Row[] {
  const start = Math.max(0, index) * PAGE_SIZE;
  return rows.slice(start, start + PAGE_SIZE);
}
""",
    "web/onboarding/Checklist.tsx": """export const STEPS = [
  'Invite a teammate',
  'Connect a repository',
  'Create a report',
];

export function remaining(completed: string[]): string[] {
  return STEPS.filter((step) => !completed.includes(step));
}
""",
    "docs/architecture.md": """# Northstar demo architecture

- `services/billing/**` owns capture, retries and invoices. `services/billing/ledger/**`
  is append-only and irreversible.
- `services/auth/keys/**` holds signing key material and is security sensitive.
- `infra/deploy/**` is the production deployment surface; `infra/build/**` is CI.
- `web/**` is the reversible product surface owned by the web lead.
""",
    "tests/__init__.py": "",
    "tests/test_billing_retry.py": """from __future__ import annotations

import unittest

from services.billing.invoices import invoice_number, total_minor_units
from services.billing.ledger.entries import Ledger, LedgerClosed
from services.billing.retry import CaptureLedger, retry_capture


class RetryTests(unittest.TestCase):
    def test_second_retry_inside_the_window_does_not_capture_again(self) -> None:
        ledger = CaptureLedger()
        self.assertTrue(retry_capture(ledger, "checkout-1", 100.0))
        self.assertFalse(retry_capture(ledger, "checkout-1", 101.0))

    def test_retry_after_the_window_is_a_new_capture(self) -> None:
        ledger = CaptureLedger()
        self.assertTrue(retry_capture(ledger, "checkout-1", 100.0))
        self.assertTrue(retry_capture(ledger, "checkout-1", 200.0))


class InvoiceTests(unittest.TestCase):
    def test_invoice_number_is_zero_padded(self) -> None:
        self.assertEqual(invoice_number(42), "NS-000042")

    def test_total_multiplies_quantity_by_unit_price(self) -> None:
        lines = [{"quantity": 2, "unit_minor_units": 500}]
        self.assertEqual(total_minor_units(lines), 1000)


class LedgerTests(unittest.TestCase):
    def test_posted_entries_cannot_be_amended(self) -> None:
        ledger = Ledger()
        ledger.post({"amount_minor_units": 100})
        with self.assertRaises(LedgerClosed):
            ledger.amend(0, {"amount_minor_units": 0})


if __name__ == "__main__":
    unittest.main()
""",
    "tests/test_signing_keys.py": """from __future__ import annotations

import unittest

from services.auth.keys.signing import ACTIVE_KEY_ID, KeyExpired, resolve_key_id, rotate
from services.exports.worker import next_delay_seconds


class SigningKeyTests(unittest.TestCase):
    def test_default_key_is_the_active_key(self) -> None:
        self.assertEqual(resolve_key_id(), ACTIVE_KEY_ID)

    def test_retired_keys_are_refused(self) -> None:
        with self.assertRaises(KeyExpired):
            resolve_key_id("signing-2023-11")

    def test_rotation_retires_the_previous_key(self) -> None:
        active, retired = rotate("signing-2024-06", "signing-2025-01", ("signing-2023-11",))
        self.assertEqual(active, "signing-2025-01")
        self.assertIn("signing-2024-06", retired)


class ExportWorkerTests(unittest.TestCase):
    def test_backoff_doubles_within_the_budget(self) -> None:
        self.assertEqual([next_delay_seconds(n) for n in (1, 2, 3)], [1, 2, 4])

    def test_attempt_outside_the_budget_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            next_delay_seconds(4)


if __name__ == "__main__":
    unittest.main()
""",
}


PLACEHOLDER_BANNER = (
    "SIMULATED stand-in file, generated by `make demo-repo` from a seeded issue's "
    "declared path hint so that ticket's approved scope resolves to a real, tracked "
    "file in this fictional checkout. It is not a copy of any production module."
)


def _placeholder_body(relative: str) -> str:
    """Labelled, syntactically valid content for one derived path hint.

    Every generated file has to parse: the demo checkout's own `make test` / `make lint`
    are the verification a coding session runs inside its worktree, and a placeholder
    that broke them would fail every session for the wrong reason.
    """
    path = Path(relative)
    suffix = path.suffix
    slug = re.sub(r"[^a-z0-9]+", "_", path.stem.casefold()).strip("_") or "surface"
    if suffix == ".py" and path.name.startswith("test_"):
        return (
            f'"""{PLACEHOLDER_BANNER}"""\n\n'
            "from __future__ import annotations\n\nimport unittest\n\n\n"
            f"class {slug.title().replace('_', '')}Placeholder(unittest.TestCase):\n"
            '    def test_placeholder_module_is_importable(self) -> None:\n'
            "        self.assertTrue(True)\n\n\n"
            'if __name__ == "__main__":\n    unittest.main()\n'
        )
    if suffix == ".py":
        return (
            f'"""{PLACEHOLDER_BANNER}"""\n\n'
            "from __future__ import annotations\n\n"
            f'SURFACE = "{relative}"\n\n\n'
            "def describe() -> str:\n"
            '    """Return the path this stand-in represents."""\n'
            "    return SURFACE\n"
        )
    if suffix == ".md":
        return f"# {path.stem}\n\n{PLACEHOLDER_BANNER}\n\nSurface: `{relative}`\n"
    if suffix == ".html":
        return (
            f"<!-- {PLACEHOLDER_BANNER} -->\n"
            f'<section data-surface="{relative}">\n'
            f"  <p>Placeholder for {relative}</p>\n</section>\n"
        )
    if suffix == ".css":
        return f"/* {PLACEHOLDER_BANNER} */\n.{slug}-placeholder {{\n  display: block;\n}}\n"
    if suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
        return f"// {PLACEHOLDER_BANNER}\nexport const {slug}Surface = '{relative}';\n"
    if suffix in {".yaml", ".yml"}:
        return f"# {PLACEHOLDER_BANNER}\nsurface: {relative}\n"
    return f"{PLACEHOLDER_BANNER}\n\nSurface: {relative}\n"


def seeded_path_hints() -> list[str]:
    """Every path hint declared by a seeded issue, de-duplicated and ordered."""
    from .seed import ASSIGNMENT_ISSUES, HEADLINE_ISSUES

    hints: list[str] = []
    for issue in (*HEADLINE_ISSUES, *ASSIGNMENT_ISSUES):
        declared = issue.get("paths")
        for raw in declared if isinstance(declared, list) else []:
            candidate = str(raw).strip().replace("\\", "/")
            if not candidate or candidate.startswith("/") or ".." in candidate.split("/"):
                continue
            if candidate not in hints:
                hints.append(candidate)
    return hints


def derived_placeholders() -> dict[str, str]:
    """Files this checkout must carry so every seeded issue has a resolvable scope.

    The curated `FILES` set covers the fictional product surfaces the policy map names.
    The assignment-tracking issues declare hints inside the control plane's own tree
    (`src/warrant/**`, `tests/**`, `docs/features/**`), which the demo checkout did not
    contain -- so a coding session for one of those tickets had nothing in scope to
    edit, the agent exited cleanly with no changes, and the session failed with
    "agent completed without producing a reviewable diff". Deriving one labelled
    stand-in per hint makes this module's promise ("every path here matches a seeded
    issue path_hint") true, and keeps every ticket launchable.
    """
    derived: dict[str, str] = {}
    for relative in seeded_path_hints():
        if relative in FILES:
            continue
        derived[relative] = _placeholder_body(relative)
    # Unittest discovery imports test files as modules, so every generated directory on
    # a test path needs to be a package.
    for relative in list(derived):
        parts = Path(relative).parts
        if not parts or parts[0] != "tests" or Path(relative).suffix != ".py":
            continue
        for depth in range(1, len(parts)):
            init = "/".join((*parts[:depth], "__init__.py"))
            if init not in FILES and init not in derived:
                derived[init] = ""
    return derived


def demo_files() -> dict[str, str]:
    """The complete file set of the demo checkout: curated surfaces plus derived hints."""
    return {**FILES, **derived_placeholders()}


class DemoRepositoryError(RuntimeError):
    """The demo checkout could not be created."""


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args], cwd=cwd, text=True, capture_output=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DemoRepositoryError(f"git unavailable: {type(exc).__name__}") from exc


def _git_checked(args: list[str], cwd: Path) -> str:
    result = _git(args, cwd)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise DemoRepositoryError(
            f"git {' '.join(args)} failed: {detail[-1] if detail else 'unknown error'}"
        )
    return result.stdout.strip()


def write_files(root: Path) -> list[str]:
    """Write (or refresh) every demo file; returns the relative paths that changed."""
    changed: list[str] = []
    for relative, body in sorted(demo_files().items()):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.read_text("utf-8", errors="replace") == body:
            continue
        path.write_text(body, encoding="utf-8")
        changed.append(relative)
    return changed


def clear_stale_git_locks(root: Path, *, now: float | None = None) -> list[str]:
    """Remove only old, empty Git locks from this generated demo checkout.

    Git lock files contain no owner metadata. Age plus an empty-file requirement lets
    an interrupted demo run recover while a recent or non-empty lock fails safely
    instead of racing a potentially active Git operation.
    """
    current = time.time() if now is None else now
    removed: list[str] = []
    for relative in RECOVERABLE_GIT_LOCKS:
        lock = root / relative
        try:
            stat = lock.stat()
        except FileNotFoundError:
            continue
        age_seconds = max(0.0, current - stat.st_mtime)
        if stat.st_size != 0 or age_seconds < STALE_GIT_LOCK_SECONDS:
            raise DemoRepositoryError(
                f"refusing to remove potentially active Git lock {relative}; "
                "stop the Git process or wait five minutes, then retry"
            )
        lock.unlink()
        removed.append(relative.as_posix())
    return removed


def build_demo_repository(root: Path) -> dict[str, Any]:
    """Create or refresh the demo checkout. Safe to run repeatedly."""
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    initialised = False
    if not (root / ".git").exists():
        _git_checked(["init", "-q"], root)
        _git_checked(["symbolic-ref", "HEAD", f"refs/heads/{DEFAULT_BRANCH}"], root)
        initialised = True
    stale_locks_removed = clear_stale_git_locks(root)
    _git_checked(["config", "user.name", DEMO_GIT_USER], root)
    _git_checked(["config", "user.email", DEMO_GIT_EMAIL], root)
    _git_checked(["config", "commit.gpgsign", "false"], root)
    changed = write_files(root)
    _git_checked(["add", "-A"], root)
    head = _git(["rev-parse", "HEAD"], root)
    staged_clean = _git(["diff", "--cached", "--quiet"], root).returncode == 0
    committed = False
    if head.returncode != 0 or not staged_clean:
        _git_checked(
            ["commit", "-q", "-m", "Northstar demo service repository (SIMULATED)"],
            root,
        )
        committed = True
    revision = _git_checked(["rev-parse", "HEAD"], root)
    branch = _git_checked(["rev-parse", "--abbrev-ref", "HEAD"], root)
    return {
        "root": str(root),
        "initialised": initialised,
        "changed_files": changed,
        "committed": committed,
        "revision": revision,
        "branch": branch,
        "file_count": len(demo_files()),
        "derived_file_count": len(derived_placeholders()),
        "stale_locks_removed": stale_locks_removed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or refresh the gitignored demo Git checkout used by coding sessions"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="target directory (default: DEMO_REPOSITORY_ROOT, else .runtime/demo-repo)",
    )
    args = parser.parse_args()
    root = args.root
    if root is None:
        try:
            root = Settings.from_env().demo_repository_root
        except ValueError:
            root = PROJECT_ROOT / ".runtime" / "demo-repo"
    summary = build_demo_repository(root)
    plan = discover_verification_plan(Path(summary["root"]), ("git", "diff", "--check"))
    print(f"demo repository : {summary['root']}")
    print(f"branch/revision : {summary['branch']} @ {summary['revision'][:12]}")
    print(
        "state           : "
        f"{'initialised' if summary['initialised'] else 'existing'}, "
        f"{len(summary['changed_files'])} file(s) refreshed, "
        f"{'committed' if summary['committed'] else 'already current'}"
    )
    print(f"tracked files   : {summary['file_count']}")
    print(
        f"derived hints   : {summary['derived_file_count']} labelled stand-ins "
        "for seeded issue path hints"
    )
    if summary["stale_locks_removed"]:
        print("recovered locks : " + ", ".join(summary["stale_locks_removed"]))
    print(f"verification    : {plan.source}")
    for check in plan.checks:
        print(f"  - {check.name}: {' '.join(check.command)}")
    print(f"use it with     : REPOSITORY_ROOT={summary['root']}")


if __name__ == "__main__":
    main()
