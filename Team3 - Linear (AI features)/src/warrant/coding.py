from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import Settings
from .db import Database
from .repository import LocalRepositoryProvider, RepositoryError
from .schemas import CodingSessionCreate
from .security import SECRET_PATTERNS, normalise_untrusted
from .service import Conflict, Forbidden, NotFound, WarrantService
from .verification import (
    VerificationCheck,
    VerificationPlan,
    checks_from_contract,
    discover_verification_plan,
)

SESSION_STATES = {
    "QUEUED",
    "PREPARING",
    "RUNNING",
    "VERIFYING",
    "AWAITING_REVIEW",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
}
TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}
TRANSITIONS = {
    "QUEUED": {"PREPARING", "CANCELLED", "FAILED"},
    "PREPARING": {"RUNNING", "CANCELLED", "FAILED"},
    "RUNNING": {"VERIFYING", "CANCELLED", "FAILED"},
    "VERIFYING": {"AWAITING_REVIEW", "CANCELLED", "FAILED"},
    "AWAITING_REVIEW": {"COMPLETED", "FAILED"},
}



class CodingAgentError(RuntimeError):
    pass


class RestrictedPathError(CodingAgentError):
    """A session touched a path the execution contract forbids outright."""


class WarrantNoLongerValid(CodingAgentError):
    """The authorising warrant stopped being valid after the session was created."""


class PullRequestPublishError(CodingAgentError):
    """A publisher could not produce a usable, verifiable pull-request record."""


# Material no warrant can ever place in an agent's write set, whatever the approved scope
# says. These are kept separate from the surface map because they are properties of the
# checkout, not of the workspace's declared product surfaces.
#
# Kept as glob strings purely for the audit trail recorded on the execution contract
# (`_restricted_paths()` folds these into the human-readable "restricted_paths" list). The
# actual enforcement in `_execute()` does NOT match these via `fnmatch` against a candidate
# path: `fnmatch.fnmatch(name, pattern)` requires a literal "/" in the candidate wherever the
# pattern has one, and forbids one wherever it does not. That means "**/*.pem" never matches
# a repo-root "id_rsa.pem", and ".env*" never matches a nested "web/.env" — silently letting
# both straight through the "unconditional" baseline. `_is_baseline_restricted_path()` checks
# path components and the basename directly instead, so nesting depth cannot buy an exemption.
BASELINE_RESTRICTED_PATHS: tuple[str, ...] = (".git/**", ".env*", "**/*.pem", "**/*.key")


def _is_baseline_restricted_path(path: str) -> bool:
    """Whether `path` is checkout material forbidden regardless of nesting or scope.

    Deliberately independent of `fnmatch`'s slash-literal semantics (see the comment on
    `BASELINE_RESTRICTED_PATHS`): this checks the basename and path components of `path`
    directly, so `.env`, `web/.env`, `id_rsa.pem`, and `services/keys/id_rsa.pem` are all
    caught the same way, wherever in the tree they land.
    """
    normalised = path.replace("\\", "/")
    parts = [part for part in normalised.split("/") if part]
    if not parts:
        return False
    if ".git" in parts[:-1] or parts[-1] == ".git":
        return True
    name = parts[-1]
    if name.startswith(".env"):
        return True
    return name.endswith(".pem") or name.endswith(".key")


def _git_detail(result: subprocess.CompletedProcess[str]) -> str:
    """The last, user-safe line of a failed git invocation."""
    lines = (result.stderr or result.stdout or "").strip().splitlines()
    return normalise_untrusted("", lines[-1] if lines else "no output").text[:300]


@dataclass(frozen=True)
class RunnerResult:
    exit_code: int
    output: str
    duration_ms: int
    timed_out: bool = False
    cancelled: bool = False
    truncated: bool = False


class CodingAgentRunner(ABC):
    name: str
    real: bool
    # The session service installs this so the agent's OS process id reaches the session
    # row. An in-memory Popen handle alone leaves a restart-orphaned session
    # unidentifiable, and therefore uncancellable.
    on_process_start: Callable[[str, int], None] | None = None

    def report_process(self, session_id: str, pid: int) -> None:
        callback = self.on_process_start
        if callback is not None:
            callback(session_id, pid)

    @abstractmethod
    def is_available(self) -> tuple[bool, str]: ...

    @abstractmethod
    def run(self, session_id: str, workspace: Path, prompt: str) -> RunnerResult: ...

    @abstractmethod
    def cancel(self, session_id: str) -> bool: ...


class SubprocessCodingAgentRunner(CodingAgentRunner):
    def __init__(self, executable: str, settings: Settings) -> None:
        self.executable = executable
        self.settings = settings
        self.name = Path(executable).name
        self.real = True
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._lock = threading.Lock()

    def is_available(self) -> tuple[bool, str]:
        resolved = shutil.which(self.executable)
        return (bool(resolved), resolved or f"{self.executable} executable not found")

    def _command(self, workspace: Path, prompt: str) -> list[str]:
        if self.name == "codex":
            return [
                self.executable,
                "--sandbox",
                "workspace-write",
                "--ask-for-approval",
                "never",
                "exec",
                "--cd",
                str(workspace),
                "--ephemeral",
                prompt,
            ]
        raise CodingAgentError("unsupported real coding-agent executable")

    @staticmethod
    def _environment() -> dict[str, str]:
        allowed = {
            "PATH",
            "HOME",
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "TERM",
            "CODEX_HOME",
            "OPENAI_API_KEY",
        }
        return {key: value for key, value in os.environ.items() if key in allowed}

    def run(self, session_id: str, workspace: Path, prompt: str) -> RunnerResult:
        available, reason = self.is_available()
        if not available:
            raise CodingAgentError(reason)
        started = time.monotonic()
        process = subprocess.Popen(
            self._command(workspace, prompt),
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=self._environment(),
            start_new_session=True,
        )
        with self._lock:
            self._processes[session_id] = process
        self.report_process(session_id, process.pid)
        timed_out = False
        cancelled = False
        try:
            output, _ = process.communicate(timeout=self.settings.coding_agent_timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._terminate(process)
            output, _ = process.communicate()
        finally:
            with self._lock:
                cancelled = session_id not in self._processes and process.returncode not in {
                    0,
                    None,
                }
                self._processes.pop(session_id, None)
        maximum = self.settings.coding_agent_max_output_bytes
        truncated = len(output) > maximum
        if truncated:
            output = output[-maximum:]
        return RunnerResult(
            exit_code=process.returncode if process.returncode is not None else -1,
            output=output.decode("utf-8", errors="replace"),
            duration_ms=int((time.monotonic() - started) * 1000),
            timed_out=timed_out,
            cancelled=cancelled,
            truncated=truncated,
        )

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass

    def cancel(self, session_id: str) -> bool:
        with self._lock:
            process = self._processes.pop(session_id, None)
        if process is None:
            return False
        self._terminate(process)
        return True


class MockCodingAgentRunner(CodingAgentRunner):
    name = "mock"
    real = False

    def __init__(self) -> None:
        self._cancelled: set[str] = set()

    def is_available(self) -> tuple[bool, str]:
        return True, "built-in visibly simulated runner"

    def run(self, session_id: str, workspace: Path, prompt: str) -> RunnerResult:
        if session_id in self._cancelled:
            return RunnerResult(-15, "SIMULATED runner cancelled", 0, cancelled=True)
        match = re.search(r"^Allowed paths: (.+)$", prompt, re.MULTILINE)
        allowed = json.loads(match.group(1)) if match else []
        target = str(allowed[0]) if allowed else "CODING_SESSION_MOCK.md"
        target = target.replace("**", "simulated").replace("*", "simulated")
        relative = Path(target)
        if relative.is_absolute() or ".." in relative.parts:
            raise CodingAgentError("mock runner refused an unsafe warrant path")
        marker = workspace / target
        try:
            marker.resolve().relative_to(workspace.resolve())
        except ValueError as exc:
            raise CodingAgentError("mock runner path escaped its worktree") from exc
        marker.parent.mkdir(parents=True, exist_ok=True)
        prefix = marker.read_text() + "\n" if marker.exists() else ""
        marker.write_text(
            prefix + "# Simulated coding-agent output\n\n"
            "This file was produced by the visibly labelled mock runner.\n\n"
            f"Prompt summary: {prompt[:400]}\n"
        )
        return RunnerResult(0, "SIMULATED runner wrote CODING_SESSION_MOCK.md", 1)

    def cancel(self, session_id: str) -> bool:
        self._cancelled.add(session_id)
        return True


@dataclass(frozen=True)
class PublisherAvailability:
    """Whether a publisher may be used, and the user-safe reason when it may not."""

    available: bool
    reason: str

    def __bool__(self) -> bool:
        return self.available


@dataclass(frozen=True)
class PullRequestRef:
    """A pull request the publisher has actually observed, never an inferred one."""

    provider: str
    number: int | None
    url: str
    state: str
    draft: bool
    # Reviewers the host actually asked for. Empty with a populated `reviewer_error` means
    # the PR exists but nobody was asked to review it -- a distinction worth keeping,
    # because "approval requested" is exactly the claim an audit trail must not overstate.
    reviewers: tuple[str, ...] = ()
    reviewer_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "number": self.number,
            "url": self.url,
            "state": self.state,
            "draft": self.draft,
            "reviewers": list(self.reviewers),
            "reviewer_error": self.reviewer_error,
        }


class PullRequestPublisher(ABC):
    """The outbound edge of a coding session.

    A publisher reports availability and moves an already-verified diff outward. It has no
    say in ALLOW / REQUIRE_APPROVAL / DENY: every gate (feature flag, warrant tool grant,
    completed verification, admin/owner actor, live warrant) is enforced by the session
    service before a publisher is ever called.
    """

    name: str

    @abstractmethod
    def availability(self, workspace: Path) -> PublisherAvailability: ...

    def is_available(self, workspace: Path) -> bool:
        """Plain boolean gate; `availability` carries the reason for the refusal."""
        return self.availability(workspace).available

    @abstractmethod
    def create_draft_pull_request(
        self,
        workspace: Path,
        branch: str,
        title: str,
        body: str,
        *,
        base: str = "",
        reviewers: Sequence[str] = (),
    ) -> PullRequestRef: ...

    @abstractmethod
    def get_pull_request(self, workspace: Path, branch: str) -> PullRequestRef | None: ...


# GitHub usernames are alphanumeric with single internal hyphens; a review request may also
# name an `org/team` slug, which additionally allows underscores and dots in the team part.
GITHUB_HANDLE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}(?:/[A-Za-z0-9][A-Za-z0-9._-]{0,98})?$"
)
# Branch names reach `git push` and `gh --base` as argv. Refuse anything that could be read
# as an option or a refspec trick rather than a branch.
GIT_BRANCH_NAME = re.compile(r"^(?!-)(?!.*\.\.)[A-Za-z0-9][A-Za-z0-9._/-]{0,240}$")


def validated_reviewers(reviewers: Sequence[str]) -> list[str]:
    """De-duplicated, order-preserving reviewer handles, or a typed refusal.

    These become `gh` arguments. Even though every call is argv-only and never shell-
    interpreted, an unvalidated handle beginning with `-` would still be parsed by `gh`
    itself as a flag, so the shape is checked rather than trusted.
    """
    cleaned: list[str] = []
    for raw in reviewers:
        handle = str(raw).strip()
        if not handle:
            continue
        if not GITHUB_HANDLE.match(handle):
            raise PullRequestPublishError(
                f"{handle!r} is not a valid GitHub username or org/team slug; refusing to "
                "pass it to gh"
            )
        if handle not in cleaned:
            cleaned.append(handle)
    return cleaned


def validated_base_branch(base: str) -> str:
    """An empty string (meaning 'the repository default'), or a safe branch name."""
    candidate = str(base or "").strip()
    if candidate and not GIT_BRANCH_NAME.match(candidate):
        raise PullRequestPublishError(
            f"{candidate!r} is not a valid base branch name; refusing to pass it to gh"
        )
    return candidate


# A GitHub pull-request URL, matched as a whole so a truncated or decorated `gh` line can
# never be recorded as an artifact. The trailing number is the PR number.
GITHUB_PR_URL = re.compile(
    r"https://[A-Za-z0-9.\-]*github\.[A-Za-z0-9.\-]+/[^\s/]+/[^\s/]+/pull/(\d+)",
    re.IGNORECASE,
)


class GhPullRequestPublisher(PullRequestPublisher):
    name = "gh-cli"

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    @staticmethod
    def _run(args: list[str], cwd: Path, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
            env={
                key: value
                for key, value in os.environ.items()
                if key in {"PATH", "HOME", "GH_TOKEN"}
            },
        )

    def availability(self, workspace: Path) -> PublisherAvailability:
        if not self.enabled:
            return PublisherAvailability(False, "PR publishing feature flag is disabled")
        if not shutil.which("gh"):
            return PublisherAvailability(False, "gh CLI is not installed")
        auth = self._run(["gh", "auth", "status"], workspace)
        if auth.returncode != 0:
            return PublisherAvailability(False, "gh CLI is not authenticated")
        remote = self._run(["git", "remote", "get-url", "origin"], workspace)
        if remote.returncode != 0 or "github.com" not in remote.stdout.casefold():
            return PublisherAvailability(False, "repository has no compatible GitHub origin")
        return PublisherAvailability(True, "available")

    @staticmethod
    def parse_pull_request_url(output: str | None) -> tuple[str, int]:
        """Extract one verifiable PR URL and number, or refuse with a typed error.

        `gh` prints human chatter alongside the URL, and on a partial failure it can print
        nothing usable at all. Indexing the last line raised a bare `IndexError` and, worse,
        could record a non-URL line as the artifact. Nothing is recorded unless a whole
        GitHub pull-request URL with a numeric id is present.
        """
        for line in reversed((output or "").splitlines()):
            match = GITHUB_PR_URL.search(line.strip())
            if match:
                return match.group(0), int(match.group(1))
        detail = normalise_untrusted("", (output or "").strip() or "no output").text[:200]
        raise PullRequestPublishError(
            "gh did not return a parseable GitHub pull-request URL; refusing to record an "
            f"unverifiable pull request (output: {detail})"
        )

    def create_draft_pull_request(
        self,
        workspace: Path,
        branch: str,
        title: str,
        body: str,
        *,
        base: str = "",
        reviewers: Sequence[str] = (),
    ) -> PullRequestRef:
        availability = self.availability(workspace)
        if not availability:
            raise CodingAgentError(availability.reason)
        # Validated before the push, so a bad handle costs nothing and pushes nothing.
        requested = validated_reviewers(reviewers)
        target = validated_base_branch(base)
        push = self._run(["git", "push", "--set-upstream", "origin", branch], workspace, 120)
        if push.returncode != 0:
            raise CodingAgentError("failed to push coding-session branch")
        command = ["gh", "pr", "create", "--draft", "--title", title, "--body", body]
        if target:
            command += ["--base", target]
        # One `--reviewer` per handle: `gh` accepts a comma list, but a per-handle flag keeps
        # a malformed entry from silently swallowing the ones after it.
        for handle in requested:
            command += ["--reviewer", handle]
        created = self._run(command, workspace, 120)
        if created.returncode == 0:
            url, number = self.parse_pull_request_url(created.stdout)
            return PullRequestRef(self.name, number, url, "draft", True, tuple(requested))
        if not requested:
            raise PullRequestPublishError("gh could not create a draft pull request")
        # A review request fails on its own terms (handle is not a collaborator, team not
        # visible to the token) and would otherwise take the whole PR down with it. Retry
        # once without reviewers, and record that they were NOT requested rather than
        # reporting a review that nobody was actually asked for.
        detail = normalise_untrusted("", (created.stderr or "").strip() or "no output").text[:200]
        retried = self._run(
            ["gh", "pr", "create", "--draft", "--title", title, "--body", body]
            + (["--base", target] if target else []),
            workspace,
            120,
        )
        if retried.returncode != 0:
            raise PullRequestPublishError("gh could not create a draft pull request")
        url, number = self.parse_pull_request_url(retried.stdout)
        return PullRequestRef(
            self.name, number, url, "draft", True, (), f"reviewers not requested: {detail}"
        )

    def get_pull_request(self, workspace: Path, branch: str) -> PullRequestRef | None:
        availability = self.availability(workspace)
        if not availability:
            return None
        viewed = self._run(
            ["gh", "pr", "view", branch, "--json", "number,url,state,isDraft"], workspace
        )
        if viewed.returncode != 0:
            return None
        try:
            payload = json.loads(viewed.stdout)
        except json.JSONDecodeError as exc:
            raise PullRequestPublishError(
                "gh returned unparseable JSON for the coding-session pull request"
            ) from exc
        if not isinstance(payload, dict):
            raise PullRequestPublishError(
                "gh returned an unexpected JSON shape for the coding-session pull request"
            )
        url, parsed_number = self.parse_pull_request_url(str(payload.get("url") or ""))
        number = payload.get("number")
        return PullRequestRef(
            self.name,
            number if isinstance(number, int) else parsed_number,
            url,
            str(payload.get("state") or "unknown").casefold(),
            bool(payload.get("isDraft")),
        )


class MockPullRequestPublisher(PullRequestPublisher):
    """A visibly labelled publisher that performs no outbound work.

    It exists so the publish path — every gate, the head-revision record and the artifact
    row — is testable without the `gh` CLI or a GitHub remote. The URLs it returns point at
    `example.invalid` so a simulated artifact can never be mistaken for a real PR.
    """

    name = "mock-pr"

    def __init__(self, available: bool = True, reason: str = "simulated publisher") -> None:
        self.available = available
        self.reason = reason
        self.created: list[PullRequestRef] = []
        self.base = ""
        self._by_branch: dict[str, PullRequestRef] = {}

    def availability(self, workspace: Path) -> PublisherAvailability:
        return PublisherAvailability(self.available, self.reason)

    def create_draft_pull_request(
        self,
        workspace: Path,
        branch: str,
        title: str,
        body: str,
        *,
        base: str = "",
        reviewers: Sequence[str] = (),
    ) -> PullRequestRef:
        availability = self.availability(workspace)
        if not availability:
            raise CodingAgentError(availability.reason)
        # Validated on the simulated path too, so a malformed handle is caught in a demo
        # rather than first surfacing against a real repository.
        requested = validated_reviewers(reviewers)
        self.base = validated_base_branch(base)
        number = len(self.created) + 1
        reference = PullRequestRef(
            self.name,
            number,
            f"https://example.invalid/simulated/pull/{number}",
            "draft",
            True,
            tuple(requested),
        )
        self.created.append(reference)
        self._by_branch[branch] = reference
        return reference

    def get_pull_request(self, workspace: Path, branch: str) -> PullRequestRef | None:
        return self._by_branch.get(branch)


class CodingSessionService:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        warrant: WarrantService,
        repository: LocalRepositoryProvider,
        runners: dict[str, CodingAgentRunner] | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.warrant = warrant
        self.repository = repository
        self.runners = runners or {
            "mock": MockCodingAgentRunner(),
            "codex": SubprocessCodingAgentRunner("codex", settings),
        }
        self.publisher: PullRequestPublisher = GhPullRequestPublisher(
            settings.pr_publishing_enabled
        )
        self._threads: dict[str, threading.Thread] = {}
        self._teardown_lock = threading.Lock()
        self.host_pid = os.getpid()
        self.reconcile_orphaned_sessions()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:16]}"

    def _record_agent_pid(self, session_id: str, pid: int) -> None:
        self.db.execute(
            "UPDATE coding_sessions SET agent_pid=?,host_pid=? WHERE id=?",
            (int(pid), self.host_pid, session_id),
        )
        self._event(session_id, "agent_process_started", agent_pid=int(pid), host_pid=self.host_pid)

    def reconcile_orphaned_sessions(self) -> list[str]:
        """Fail sessions left non-terminal by a previous server process.

        The supervising thread and the Popen handle die with the process that owned them,
        so a session recorded as RUNNING by an older `host_pid` can never progress and
        can never be cancelled through the runner. Recording the outcome (with the agent
        pid that was persisted) is what makes it identifiable and actionable instead.
        """
        placeholders = ",".join("?" for _ in TERMINAL_STATES)
        rows = self.db.all(
            "SELECT id,agent_pid,host_pid,worktree_path FROM coding_sessions "
            f"WHERE state NOT IN ({placeholders}) AND host_pid IS NOT NULL AND host_pid<>?",
            (*sorted(TERMINAL_STATES), self.host_pid),
        )
        reconciled: list[str] = []
        for row in rows:
            message = (
                "session was orphaned by a server restart "
                f"(recorded host pid {row['host_pid']}, agent pid {row['agent_pid']})"
            )
            self.db.execute("UPDATE coding_sessions SET error=? WHERE id=?", (message, row["id"]))
            try:
                self._transition(
                    row["id"],
                    "FAILED",
                    "session_orphaned",
                    error=message,
                    agent_pid=row["agent_pid"],
                    previous_host_pid=row["host_pid"],
                    host_pid=self.host_pid,
                )
            except (Conflict, NotFound):
                continue
            reconciled.append(row["id"])
        if reconciled:
            self._reap_worktrees()
        return reconciled

    def capabilities(self) -> dict[str, Any]:
        runner_capabilities: dict[str, dict[str, Any]] = {}
        for name, runner in self.runners.items():
            available, reason = runner.is_available()
            runner_capabilities[name] = {
                "available": available,
                "reason": reason,
                "real": runner.real,
            }
        publishing = self.publisher.availability(self.repository.root)
        git_ready = self.repository.is_git_repository()
        return {
            "external_execution_enabled": self.settings.external_coding_agent_enabled,
            "repository": self.repository.get_repository_metadata(),
            "runners": runner_capabilities,
            "git_checkout": {
                "available": git_ready,
                "root": str(self.repository.root),
                "reason": "available" if git_ready else self._not_a_git_checkout(),
            },
            "verification": {
                **self._discover_plan().to_dict(),
                "discovery_enabled": self.settings.verification_discovery_enabled,
                "configured_fallback": list(self.settings.verification_command),
                "max_checks": self.settings.verification_max_checks,
                "timeout_seconds": self.settings.verification_timeout_seconds,
            },
            "worktrees": {
                "root": str(self.settings.coding_session_root),
                "retained_sessions": self.settings.coding_session_retention,
                "protected_branches": list(self.settings.protected_branches),
            },
            "pr_publishing": {
                "enabled": self.settings.pr_publishing_enabled,
                "provider": self.publisher.name,
                "available": publishing.available,
                "reason": publishing.reason,
                "base_branch": self.settings.pr_base_branch or "repository default",
                "default_reviewers": list(self.settings.pr_reviewers),
            },
        }

    def _not_a_git_checkout(self) -> str:
        """The typed 503 for a non-Git root, with the root and the remedy in the message."""
        return (
            "coding sessions require the configured repository to be a Git checkout; "
            f"{self.repository.root} is not one. Run `make demo-repo` and set "
            "REPOSITORY_ROOT to the demo checkout it prints, or point REPOSITORY_ROOT at "
            "an existing Git checkout."
        )

    def _discover_plan(self) -> VerificationPlan:
        return discover_verification_plan(
            self.repository.root,
            self.settings.verification_command,
            max_checks=self.settings.verification_max_checks,
            enabled=self.settings.verification_discovery_enabled,
        )

    def _append_event(
        self, connection: Any, session_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        # The sequence is allocated and written by one statement inside one immediate
        # transaction: the agent thread, the verification loop and an operator cancel all
        # append concurrently, and a read-then-insert raced on `UNIQUE(session_id, seq)`.
        connection.execute(
            "INSERT INTO coding_session_events "
            "(id,session_id,seq,event_type,payload_json,created_at) "
            "SELECT ?,?,COALESCE(MAX(seq),0)+1,?,?,? FROM coding_session_events "
            "WHERE session_id=?",
            (
                self._id("cse"),
                session_id,
                event_type,
                Database.dumps(payload),
                self._now(),
                session_id,
            ),
        )

    def _audit(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        session = self.db.one("SELECT workspace_id FROM coding_sessions WHERE id=?", (session_id,))
        if session:
            self.warrant.audit.append(
                session["workspace_id"],
                event_type,
                "system",
                "coding-session-service",
                "coding_session",
                session_id,
                payload,
            )

    def _event(self, session_id: str, event_type: str, **payload: Any) -> None:
        with self.db.transaction() as connection:
            self._append_event(connection, session_id, event_type, payload)
        self._audit(session_id, event_type, payload)

    def _transition(self, session_id: str, state: str, event_type: str, **payload: Any) -> None:
        """Move state and record the event atomically.

        A reader that sees a terminal state must also see the event that produced it, and
        a concurrent cancel must not be able to interleave with the executor thread
        between the guard and the write.
        """
        if state not in SESSION_STATES:
            raise ValueError("unknown coding-session state")
        recorded = {"state": state, **payload}
        if state in TERMINAL_STATES:
            # Reserve one retention slot for this session before making its terminal
            # state observable. Otherwise a caller can see COMPLETED while the older
            # worktree is still awaiting the finally-block cleanup.
            self._reap_worktrees(reserved_terminal_slots=1)
        with self.db.transaction() as connection:
            row = connection.execute(
                "SELECT state FROM coding_sessions WHERE id=?", (session_id,)
            ).fetchone()
            if row is None:
                raise NotFound("coding session not found")
            current = row["state"]
            if state not in TRANSITIONS.get(current, set()):
                raise Conflict(f"invalid coding-session transition {current} -> {state}")
            finished = self._now() if state in TERMINAL_STATES else None
            started = self._now() if state == "RUNNING" else None
            connection.execute(
                "UPDATE coding_sessions SET state=?,started_at=COALESCE(started_at,?),"
                "finished_at=COALESCE(?,finished_at) WHERE id=?",
                (state, started, finished, session_id),
            )
            self._append_event(connection, session_id, event_type, recorded)
        self._audit(session_id, event_type, recorded)

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:45]
        return cleaned or "work"

    def _checked_out_branch(self) -> str | None:
        """The branch the target checkout has on HEAD, or None when HEAD is detached."""
        result = LocalRepositoryProvider._git(
            ["symbolic-ref", "--quiet", "--short", "HEAD"], self.repository.root
        )
        name = result.stdout.strip()
        return name or None

    def _branch_exists(self, branch: str) -> bool:
        result = LocalRepositoryProvider._git(
            ["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], self.repository.root
        )
        return result.returncode == 0 and bool(result.stdout.strip())

    def _protected_branches(self) -> set[str]:
        """Names no session may write to: the configured set plus the live checkout."""
        protected = {name.casefold() for name in self.settings.protected_branches}
        checked_out = self._checked_out_branch()
        if checked_out:
            protected.add(checked_out.casefold())
        return protected

    def _assert_branch_writable(self, branch: str) -> None:
        """Refuse a session whose derived branch is protected.

        The previous guard compared the already-prefixed `agent/...` name against a bare
        set of protected names, so it could never fire. This compares the whole derived
        ref *and* its leaf against the configured protected names and against the branch
        the target repository currently has checked out.
        """
        leaf = branch.rsplit("/", 1)[-1]
        protected = self._protected_branches()
        for candidate in (branch, leaf):
            if candidate.casefold() in protected:
                raise Forbidden(
                    f"protected branch '{candidate}' cannot be used for coding sessions"
                )

    def _approval_snapshot(
        self, detail: dict[str, Any], warrant: dict[str, Any], workspace_id: str
    ) -> dict[str, Any]:
        """The human decision that authorised this session, or an explicit auto-ALLOW record.

        A null approval is indistinguishable from "we forgot to record it", so there is no
        null branch: either a named approver and their decided scope are snapshotted, or the
        session is refused. The control plane decided the verdict; this only reads it back.
        """
        row = self.db.one("SELECT * FROM approvals WHERE delegation_id=?", (detail["id"],))
        verdict = str((detail.get("decision") or {}).get("verdict") or "")
        if row is not None:
            if row["action"] not in {"approve", "narrow"}:
                raise Forbidden("the delegation's human decision did not authorise execution")
            approver = self.db.one(
                "SELECT id,display_name,role FROM users WHERE id=? AND workspace_id=?",
                (row["approver_id"], workspace_id),
            )
            if approver is None:
                raise Forbidden("the approving user is not a member of this workspace")
            return {
                "id": row["id"],
                "approver_id": approver["id"],
                "approver_name": approver["display_name"],
                "approver_role": approver["role"],
                "action": row["action"],
                "scope_surfaces": Database.loads(row["narrowed_scope_json"], []),
                "rationale": row["rationale"],
                "decided_at": row["decided_at"],
            }
        if verdict != "ALLOW" or warrant.get("authority_user_id") != "system-policy":
            raise Forbidden(
                "no approval record authorises this warrant; refusing to start a session "
                "whose authorising decision cannot be identified"
            )
        return {
            "required": False,
            "reason": "auto_allow",
            "authority": "system-policy",
            "policy_decision_verdict": verdict,
            "scope_surfaces": list(warrant.get("scope_surfaces") or []),
            "decided_at": warrant.get("issued_at"),
        }

    def _restricted_paths(self, workspace_id: str, granted_scope: list[str]) -> list[str]:
        """Paths this session may never write, derived from real policy and warrant data.

        Every protected surface in the workspace surface map (seeded from
        `policies/surfaces.yaml`) is forbidden unless the warrant's own scope grants it, so
        narrowing an approval narrows the write set. The baseline checkout material is
        forbidden unconditionally — an approved scope cannot buy access to `.git` or to key
        material that merely happens to sit inside an allowed directory.
        """
        restricted = list(BASELINE_RESTRICTED_PATHS)
        for row in self.db.all(
            "SELECT glob FROM surfaces WHERE workspace_id=? AND protected=1", (workspace_id,)
        ):
            glob = str(row["glob"])
            if any(fnmatch.fnmatch(glob, str(pattern)) for pattern in granted_scope):
                continue
            restricted.append(glob)
        return list(dict.fromkeys(restricted))

    def _assert_warrant_live(
        self, session_id: str, warrant_id: str, workspace_id: str, stage: str
    ) -> None:
        """Re-read the warrant's live state and abort if it stopped authorising this work.

        The warrant is checked once when the session is created, but revocation and expiry
        happen on wall-clock time and by human action. Anything that reaches outward — the
        runner, and the PR publisher — re-checks first, and the outcome is recorded on the
        session timeline either way.
        """
        self.warrant.sweep_expired_warrants(workspace_id)
        row = self.db.one(
            "SELECT * FROM warrants WHERE id=? AND workspace_id=?", (warrant_id, workspace_id)
        )
        reason: str | None = None
        if row is None:
            reason = "the authorising warrant no longer exists"
        elif row["revoked_at"]:
            reason = "the authorising warrant was revoked"
        elif row["expired_at"]:
            reason = "the authorising warrant has expired"
        else:
            try:
                expires = datetime.fromisoformat(str(row["expires_at"]))
            except (TypeError, ValueError):
                reason = "the authorising warrant has an unreadable expiry"
            else:
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires <= datetime.now(timezone.utc):
                    reason = "the authorising warrant has expired"
        if reason is not None:
            self._event(
                session_id,
                "warrant_recheck_failed",
                stage=stage,
                warrant_id=warrant_id,
                reason=reason,
            )
            raise WarrantNoLongerValid(f"{reason}; {stage} aborted")
        self._event(
            session_id,
            "warrant_rechecked",
            stage=stage,
            warrant_id=warrant_id,
            status="active",
            expires_at=row["expires_at"] if row else None,
        )

    def _derive_branch(self, issue_key: str, title: str, session_id: str) -> str:
        """`agent/<issue-key>-<title-slug>`, uniquified only if that ref already exists."""
        branch = f"agent/{self._slug(issue_key)}-{self._slug(title)}"
        self._assert_branch_writable(branch)
        if self._branch_exists(branch):
            branch = f"{branch}-{session_id[-8:]}"
            self._assert_branch_writable(branch)
        return branch

    def start(
        self,
        workspace_id: str,
        request: CodingSessionCreate,
        *,
        trusted_source: str | None = None,
    ) -> dict[str, Any]:
        detail = self.warrant.get_delegation(request.delegation_id, workspace_id)
        warrant = detail.get("warrant")
        if not warrant or warrant["status"] != "active":
            raise Forbidden("an active policy-issued warrant is required before coding")
        if (
            "write_files" not in warrant["allowed_tools"]
            or "run_tests" not in warrant["allowed_tools"]
        ):
            raise Forbidden("the warrant does not grant code modification and verification")
        provider_name = request.provider or self.settings.coding_agent_provider
        if provider_name not in self.runners:
            raise CodingAgentError("configured coding-agent provider is unsupported")
        runner = self.runners[provider_name]
        if runner.real and not self.settings.external_coding_agent_enabled:
            raise Forbidden("external coding agent execution is disabled")
        available, reason = runner.is_available()
        if not available:
            raise CodingAgentError(f"external coding agent unavailable: {reason}")
        if not self.repository.is_git_repository():
            raise RepositoryError(self._not_a_git_checkout())
        existing = self.db.one(
            "SELECT id FROM coding_sessions WHERE warrant_id=?", (warrant["id"],)
        )
        if existing:
            raise Conflict("this warrant already has a coding session")
        base_revision = self.repository.get_current_revision()
        resolved_base = LocalRepositoryProvider._git(
            ["rev-parse", "--verify", "--quiet", f"{base_revision}^{{commit}}"],
            self.repository.root,
        )
        if resolved_base.returncode != 0 or not resolved_base.stdout.strip():
            raise RepositoryError(
                f"the configured repository has no commit to branch from ({base_revision}); "
                "run `make demo-repo`, or make an initial commit in REPOSITORY_ROOT"
            )
        session_id = self._id("ses")
        issue_key = detail["issue"]["external_key"]
        branch = self._derive_branch(issue_key, str(detail["issue"]["title"]), session_id)
        plan = self._discover_plan()
        if not plan.checks:
            raise CodingAgentError(
                "no runnable verification check could be discovered or configured for "
                f"{self.repository.root}"
            )
        worktree = (self.settings.coding_session_root / session_id).resolve()
        try:
            worktree.relative_to(self.settings.coding_session_root.resolve())
        except ValueError as exc:
            raise RepositoryError(
                "coding-session path escaped the configured runtime root"
            ) from exc
        contract = {
            "issue": detail["issue"],
            "delegation_id": detail["id"],
            "policy_decision": detail["decision"],
            "risk": detail["risk_assessment"],
            "approval": self._approval_snapshot(detail, warrant, workspace_id),
            "warrant": {key: value for key, value in warrant.items() if key != "demo_nonce"},
            "repository_id": self.repository.repository_id,
            "base_revision": base_revision,
            "allowed_paths": warrant["scope_surfaces"],
            "restricted_paths": self._restricted_paths(workspace_id, warrant["scope_surfaces"]),
            "allowed_tools": warrant["allowed_tools"],
            "expiry": warrant["expires_at"],
            "requested_outcome": request.requested_outcome or detail["issue"]["title"],
            # Kept for compatibility with sessions recorded before discovery existed.
            "verification_command": list(plan.checks[0].command),
            "verification_source": plan.source,
            "verification_checks": [check.to_dict() for check in plan.checks],
            "verification_skipped": [dict(item) for item in plan.skipped],
        }
        now = self._now()
        self.db.execute(
            "INSERT INTO coding_sessions "
            "(id,workspace_id,delegation_id,warrant_id,issue_id,requester_id,source,provider,"
            "state,repository_root,base_revision,branch_name,worktree_path,contract_json,"
            "result_json,error,created_at,started_at,finished_at,agent_pid,host_pid,"
            "worktree_removed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                session_id,
                workspace_id,
                detail["id"],
                warrant["id"],
                detail["issue_id"],
                detail["requester"]["id"],
                trusted_source or request.source,
                provider_name,
                "QUEUED",
                str(self.repository.root),
                base_revision,
                branch,
                str(worktree),
                Database.dumps(contract),
                None,
                None,
                now,
                None,
                None,
                None,
                self.host_pid,
                None,
            ),
        )
        self._event(
            session_id,
            "session_created",
            state="QUEUED",
            provider=provider_name,
            provider_kind="real" if runner.real else "mock",
            delegation_id=detail["id"],
            warrant_id=warrant["id"],
            base_revision=base_revision,
            branch=branch,
            host_pid=self.host_pid,
        )
        self._event(
            session_id,
            "verification_discovered",
            source=plan.source,
            checks=[check.to_dict() for check in plan.checks],
            skipped=[dict(item) for item in plan.skipped],
        )
        thread = threading.Thread(target=self._execute, args=(session_id,), daemon=True)
        self._threads[session_id] = thread
        thread.start()
        return self.get(session_id, workspace_id)

    def _prepare_worktree(self, session: dict[str, Any]) -> Path:
        worktree = Path(session["worktree_path"])
        worktree.parent.mkdir(parents=True, exist_ok=True)
        result = LocalRepositoryProvider._git(
            [
                "worktree",
                "add",
                "--detach",
                str(worktree),
                session["base_revision"],
            ],
            self.repository.root,
            60,
        )
        if result.returncode != 0:
            raise CodingAgentError(f"git worktree creation failed: {_git_detail(result)}")
        branch = LocalRepositoryProvider._git(
            ["switch", "-c", session["branch_name"]], worktree, 30
        )
        if branch.returncode != 0:
            raise CodingAgentError(f"coding-session branch creation failed: {_git_detail(branch)}")
        return worktree

    def _prompt(self, contract: dict[str, Any]) -> str:
        return (
            "Implement the requested outcome in this isolated Git worktree. "
            "Do not change files outside the allowed path patterns. Do not commit, push, create a "
            "pull request, access secrets, or change repository settings. Run focused checks when "
            "useful; "
            "the host will run authoritative verification after you finish.\n\n"
            f"Requested outcome: {contract['requested_outcome']}\n"
            f"Issue: {contract['issue']['external_key']} — {contract['issue']['title']}\n"
            f"Allowed paths: {json.dumps(contract['allowed_paths'])}\n"
            f"Restricted paths (never write these): "
            f"{json.dumps(contract.get('restricted_paths') or [])}\n"
            f"Acceptance criteria: {json.dumps(contract['warrant']['evidence_contract'])}"
        )

    def _execute(self, session_id: str) -> None:
        try:
            session = self.db.one("SELECT * FROM coding_sessions WHERE id=?", (session_id,))
            if session is None:
                return
            contract = Database.loads(session["contract_json"], {})
            self._transition(session_id, "PREPARING", "workspace_preparing")
            worktree = self._prepare_worktree(session)
            self._event(
                session_id, "worktree_created", path=str(worktree), branch=session["branch_name"]
            )
            current = self.db.one("SELECT state FROM coding_sessions WHERE id=?", (session_id,))
            if current and current["state"] == "CANCELLED":
                return
            self._transition(
                session_id,
                "RUNNING",
                "agent_started",
                provider=session["provider"],
                provider_kind="real" if self.runners[session["provider"]].real else "mock",
            )
            runner = self.runners[session["provider"]]
            # Installed here, not at construction, so a runner injected later still reports
            # its process id to the session row.
            runner.on_process_start = self._record_agent_pid
            # Last gate before anything executes: the warrant may have been revoked or have
            # expired while the worktree was being prepared.
            self._assert_warrant_live(
                session_id, session["warrant_id"], session["workspace_id"], "agent_run"
            )
            result = runner.run(session_id, worktree, self._prompt(contract))
            safe_output = normalise_untrusted("", result.output).text
            self._event(
                session_id,
                "agent_activity",
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                output=safe_output,
                output_truncated=result.truncated,
            )
            if result.cancelled:
                current = self.db.one("SELECT state FROM coding_sessions WHERE id=?", (session_id,))
                if current and current["state"] not in TERMINAL_STATES:
                    self._transition(session_id, "CANCELLED", "cancelled")
                return
            if result.timed_out:
                raise CodingAgentError("coding agent timed out and was terminated")
            if result.exit_code != 0:
                raise CodingAgentError(f"coding agent exited with status {result.exit_code}")
            self._event(session_id, "agent_completed", duration_ms=result.duration_ms)
            diff = self._create_diff(session_id, worktree, session["base_revision"])
            if not diff["changed_files"]:
                raise CodingAgentError("agent completed without producing a reviewable diff")
            restricted_patterns = [str(item) for item in contract.get("restricted_paths") or []]
            if not restricted_patterns:
                # Fail closed: an unenforceable contract is not a permissive one.
                raise CodingAgentError(
                    "the execution contract records no restricted paths; refusing to accept "
                    "an unenforceable diff"
                )
            restricted = [
                item["path"]
                for item in diff["changed_files"]
                if _is_baseline_restricted_path(item["path"])
                or any(fnmatch.fnmatch(item["path"], pattern) for pattern in restricted_patterns)
            ]
            if restricted:
                # Checked before the scope test: a restricted path is forbidden even when the
                # approved scope happens to name it.
                raise RestrictedPathError(
                    "agent changed restricted files: " + ", ".join(restricted)
                )
            outside = [
                item["path"]
                for item in diff["changed_files"]
                if not any(
                    fnmatch.fnmatch(item["path"], pattern) for pattern in contract["allowed_paths"]
                )
            ]
            if outside:
                raise CodingAgentError(
                    "agent changed files outside warrant scope: " + ", ".join(outside)
                )
            if diff["secret_redactions"]:
                raise CodingAgentError("diff contains secret-like material and was redacted")
            self._event(
                session_id,
                "diff_generated",
                changed_files=diff["changed_files"],
                additions=diff["additions"],
                deletions=diff["deletions"],
            )
            self._transition(session_id, "VERIFYING", "verification_started")
            verification = self._verify(session_id, worktree, contract)
            self.db.execute(
                "UPDATE coding_sessions SET result_json=? WHERE id=?",
                (
                    Database.dumps({"runner": result.__dict__, "verification": verification}),
                    session_id,
                ),
            )
            self._event(
                session_id,
                "verification_passed" if verification["passed"] else "verification_failed",
                passed=verification["passed"],
                source=verification["source"],
                summary=verification["summary"],
                command=verification["command"],
                exit_code=verification["exit_code"],
                duration_ms=verification["duration_ms"],
                checks=[
                    {
                        key: item[key]
                        for key in (
                            "name",
                            "command",
                            "source",
                            "required",
                            "exit_code",
                            "duration_ms",
                            "passed",
                            "summary",
                        )
                    }
                    for item in verification["checks"]
                ],
            )
            if not verification["passed"]:
                raise CodingAgentError(verification["summary"])
            self._transition(session_id, "AWAITING_REVIEW", "awaiting_review")
            self._transition(session_id, "COMPLETED", "session_completed")
        except Exception as exc:
            row = self.db.one("SELECT state FROM coding_sessions WHERE id=?", (session_id,))
            if row and row["state"] not in TERMINAL_STATES:
                self.db.execute(
                    "UPDATE coding_sessions SET error=? WHERE id=?", (str(exc)[:2000], session_id)
                )
                try:
                    self._transition(session_id, "FAILED", "agent_failed", error=str(exc)[:1000])
                except Conflict:
                    pass
        finally:
            self._threads.pop(session_id, None)
            self._reap_worktrees()

    def _session_checks(self, contract: dict[str, Any]) -> list[VerificationCheck]:
        """The checks this session is bound to, exactly as recorded when it started."""
        restored = checks_from_contract(contract.get("verification_checks"))
        if restored:
            return restored
        legacy = tuple(str(part) for part in contract.get("verification_command") or ())
        command = legacy or tuple(self.settings.verification_command)
        return [VerificationCheck("configured", command, "configured")] if command else []

    def _run_check(self, worktree: Path, check: VerificationCheck) -> dict[str, Any]:
        """Run one check as an argv list — never a shell string, never `shell=True`."""
        command = list(check.command)
        started = time.monotonic()
        budget = min(
            self.settings.verification_timeout_seconds,
            self.settings.coding_agent_timeout_seconds,
        )
        timeout = max(1, budget)
        try:
            result = subprocess.run(
                command,
                cwd=worktree,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
                env={
                    key: value
                    for key, value in os.environ.items()
                    if key in {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"}
                },
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "name": check.name,
                "command": command,
                "source": check.source,
                "required": check.required,
                "exit_code": None,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "passed": False,
                "summary": f"{check.name} could not complete: {type(exc).__name__}",
                "output": "",
            }
        raw_output = (result.stdout + result.stderr)[-100_000:]
        return {
            "name": check.name,
            "command": command,
            "source": check.source,
            "required": check.required,
            "exit_code": result.returncode,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "passed": result.returncode == 0,
            "summary": (
                f"{check.name} passed"
                if result.returncode == 0
                else f"{check.name} failed with exit code {result.returncode}"
            ),
            "output": normalise_untrusted("", raw_output).text,
        }

    def _verify(self, session_id: str, worktree: Path, contract: dict[str, Any]) -> dict[str, Any]:
        """Run every discovered check. A required failure fails the session, always."""
        checks = self._session_checks(contract)
        results: list[dict[str, Any]] = []
        for index, check in enumerate(checks, start=1):
            outcome = self._run_check(worktree, check)
            results.append(outcome)
            self.db.execute(
                "INSERT INTO verification_check_results "
                "(id,session_id,seq,name,source,command_json,exit_code,duration_ms,passed,"
                "required,summary,output,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    self._id("vck"),
                    session_id,
                    index,
                    outcome["name"],
                    outcome["source"],
                    Database.dumps(outcome["command"]),
                    outcome["exit_code"],
                    outcome["duration_ms"],
                    int(bool(outcome["passed"])),
                    int(bool(outcome["required"])),
                    outcome["summary"],
                    outcome["output"],
                    self._now(),
                ),
            )
            self._event(
                session_id,
                "verification_check_completed",
                name=outcome["name"],
                command=outcome["command"],
                source=outcome["source"],
                required=outcome["required"],
                exit_code=outcome["exit_code"],
                duration_ms=outcome["duration_ms"],
                passed=outcome["passed"],
                summary=outcome["summary"],
            )
        required = [item for item in results if item["required"]]
        failed = [item for item in required if not item["passed"]]
        # No check at all is never a pass: the gate needs positive evidence.
        passed = bool(required) and not failed
        if not required:
            summary = "no required verification check was available to run"
        elif failed:
            summary = "verification failed: " + "; ".join(item["summary"] for item in failed)
        else:
            summary = "verification passed: " + ", ".join(
                " ".join(item["command"]) for item in required
            )
        primary = required[0] if required else (results[0] if results else None)
        return {
            "source": str(contract.get("verification_source") or "configured"),
            "passed": passed,
            "summary": summary,
            "checks": results,
            # Flattened primary check, so single-check consumers keep working unchanged.
            "command": primary["command"] if primary else list(self.settings.verification_command),
            "exit_code": primary["exit_code"] if primary else None,
            "duration_ms": sum(item["duration_ms"] for item in results),
            "output": primary["output"] if primary else "",
        }

    def _teardown_session(self, row: dict[str, Any]) -> bool:
        """Remove one terminal session's worktree, and its branch when nothing published it."""
        raw_path = row.get("worktree_path")
        if not raw_path:
            self.db.execute(
                "UPDATE coding_sessions SET worktree_removed_at=? WHERE id=?",
                (self._now(), row["id"]),
            )
            return False
        worktree = Path(str(raw_path))
        removed = True
        if worktree.exists():
            result = LocalRepositoryProvider._git(
                ["worktree", "remove", "--force", str(worktree)], self.repository.root, 60
            )
            if result.returncode != 0 and worktree.exists():
                inside = str(worktree.resolve()).startswith(
                    str(self.settings.coding_session_root.resolve())
                )
                if inside:
                    shutil.rmtree(worktree, ignore_errors=True)
                removed = not worktree.exists()
        published = self.db.one(
            "SELECT id FROM pull_request_artifacts WHERE session_id=?", (row["id"],)
        )
        branch_deleted = False
        if removed and row.get("branch_name") and not published:
            deleted = LocalRepositoryProvider._git(
                ["branch", "-D", str(row["branch_name"])], self.repository.root, 30
            )
            branch_deleted = deleted.returncode == 0
        if removed:
            self.db.execute(
                "UPDATE coding_sessions SET worktree_removed_at=? WHERE id=?",
                (self._now(), row["id"]),
            )
            self._event(
                row["id"],
                "worktree_removed",
                path=str(worktree),
                branch=row.get("branch_name"),
                branch_deleted=branch_deleted,
                retained_sessions=self.settings.coding_session_retention,
            )
        return removed

    def _reap_worktrees(self, *, reserved_terminal_slots: int = 0) -> int:
        """Retire terminal worktrees beyond the retention window.

        Nothing removed a worktree or its branch before, so both accumulated forever. The
        newest `CODING_SESSION_RETENTION` terminal sessions are kept so a reviewer can
        still inspect (and publish from) recent work.
        """
        keep = max(0, self.settings.coding_session_retention - reserved_terminal_slots)
        placeholders = ",".join("?" for _ in TERMINAL_STATES)
        removed = 0
        with self._teardown_lock:
            try:
                rows = self.db.all(
                    "SELECT id,worktree_path,branch_name FROM coding_sessions "
                    f"WHERE state IN ({placeholders}) AND worktree_removed_at IS NULL "
                    "AND repository_root=? "
                    "ORDER BY COALESCE(finished_at,created_at) DESC, id DESC",
                    (*sorted(TERMINAL_STATES), str(self.repository.root)),
                )
            except Exception:
                return 0
            for row in rows[keep:]:
                try:
                    if self._teardown_session(row):
                        removed += 1
                except (RepositoryError, OSError):
                    continue
            if removed:
                LocalRepositoryProvider._git(["worktree", "prune"], self.repository.root, 30)
        return removed

    def _signal_recorded_process(self, session: dict[str, Any]) -> bool:
        """Signal the persisted process group, but only one this server itself started."""
        pid = session.get("agent_pid")
        if not pid or session.get("host_pid") != self.host_pid:
            return False
        try:
            os.killpg(int(pid), signal.SIGTERM)
        except (OSError, ValueError):
            return False
        return True

    def _create_diff(self, session_id: str, worktree: Path, base: str) -> dict[str, Any]:
        # The revision the diff was actually taken against is part of the artifact, not a
        # side effect of publishing: a reviewer must be able to reproduce the diff even when
        # no PR is ever opened.
        head = LocalRepositoryProvider._git(["rev-parse", "HEAD"], worktree, 10)
        head_revision = head.stdout.strip()
        if head.returncode != 0 or not head_revision:
            raise CodingAgentError(
                f"could not resolve the coding-session head revision: {_git_detail(head)}"
            )
        LocalRepositoryProvider._git(["add", "-N", "--", "."], worktree, 30)
        unified = self.repository.get_diff(base, worktree)
        if len(unified.encode()) > self.settings.coding_agent_max_output_bytes:
            raise CodingAgentError("coding-session diff exceeds the configured artifact limit")
        secret_redactions = 0
        for name, pattern in SECRET_PATTERNS:
            unified, count = pattern.subn(f"[REDACTED:{name.upper()}]", unified)
            secret_redactions += count
        numstat = LocalRepositoryProvider._git(["diff", "--numstat", base, "--"], worktree, 30)
        changed: list[dict[str, Any]] = []
        additions = deletions = 0
        for line in numstat.stdout.splitlines():
            added, removed, path = line.split("\t", 2)
            item_add = int(added) if added.isdigit() else 0
            item_remove = int(removed) if removed.isdigit() else 0
            additions += item_add
            deletions += item_remove
            changed.append({"path": path, "additions": item_add, "deletions": item_remove})
        self.db.execute(
            "INSERT INTO diff_artifacts VALUES (?,?,?,?,?,?,?,?,?)",
            (
                self._id("diff"),
                session_id,
                base,
                head_revision,
                Database.dumps(changed),
                additions,
                deletions,
                unified,
                self._now(),
            ),
        )
        return {
            "changed_files": changed,
            "additions": additions,
            "deletions": deletions,
            "unified_diff": unified,
            "secret_redactions": secret_redactions,
            "head_revision": head_revision,
        }

    def cancel(self, session_id: str, workspace_id: str, actor_id: str) -> dict[str, Any]:
        session = self.db.one(
            "SELECT * FROM coding_sessions WHERE id=? AND workspace_id=?",
            (session_id, workspace_id),
        )
        if session is None:
            raise NotFound("coding session not found")
        actor = self.db.one(
            "SELECT role FROM users WHERE id=? AND workspace_id=?", (actor_id, workspace_id)
        )
        warrant = self.db.one(
            "SELECT authority_user_id FROM warrants WHERE id=?", (session["warrant_id"],)
        )
        permitted = bool(
            actor
            and (
                actor["role"] in {"admin", "owner"}
                or actor_id == session["requester_id"]
                or (warrant and actor_id == warrant["authority_user_id"])
            )
        )
        if not permitted:
            raise Forbidden("requester, warrant authority, admin, or owner role required")
        if session["state"] in TERMINAL_STATES:
            raise Conflict("coding session is already terminal")
        self._transition(session_id, "CANCELLED", "cancelled", actor_id=actor_id)
        runner_cancelled = self.runners[session["provider"]].cancel(session_id)
        pid_signalled = False if runner_cancelled else self._signal_recorded_process(session)
        self._event(
            session_id,
            "cancel_dispatched",
            actor_id=actor_id,
            runner_cancelled=runner_cancelled,
            recorded_agent_pid=session.get("agent_pid"),
            recorded_host_pid=session.get("host_pid"),
            pid_signalled=pid_signalled,
        )
        self._reap_worktrees()
        return self.get(session_id, workspace_id)

    def get(self, session_id: str, workspace_id: str) -> dict[str, Any]:
        row = self.db.one(
            "SELECT * FROM coding_sessions WHERE id=? AND workspace_id=?",
            (session_id, workspace_id),
        )
        if row is None:
            raise NotFound("coding session not found")
        row["contract"] = Database.loads(row.pop("contract_json"), {})
        row["result"] = Database.loads(row.pop("result_json"), None)
        row["provider_kind"] = "real" if self.runners[row["provider"]].real else "mock"
        row["worktree_available"] = bool(
            row.get("worktree_path")
            and not row.get("worktree_removed_at")
            and Path(str(row["worktree_path"])).exists()
        )
        row["orphaned"] = bool(
            row["state"] not in TERMINAL_STATES
            and row.get("host_pid") is not None
            and row["host_pid"] != self.host_pid
        )
        row["verification_checks"] = [
            {**check, "command": Database.loads(check.pop("command_json"), [])}
            for check in self.db.all(
                "SELECT * FROM verification_check_results WHERE session_id=? ORDER BY seq",
                (session_id,),
            )
        ]
        row["events"] = []
        for event in self.db.all(
            "SELECT * FROM coding_session_events WHERE session_id=? ORDER BY seq", (session_id,)
        ):
            event["payload"] = Database.loads(event.pop("payload_json"), {})
            row["events"].append(event)
        diff = self.db.one("SELECT * FROM diff_artifacts WHERE session_id=?", (session_id,))
        if diff:
            diff["changed_files"] = Database.loads(diff.pop("changed_files_json"), [])
        row["diff"] = diff
        row["pull_request"] = self.db.one(
            "SELECT * FROM pull_request_artifacts WHERE session_id=?", (session_id,)
        )
        return row

    def list_for_delegation(self, delegation_id: str, workspace_id: str) -> list[dict[str, Any]]:
        rows = self.db.all(
            "SELECT id FROM coding_sessions WHERE workspace_id=? AND delegation_id=? "
            "ORDER BY created_at DESC",
            (workspace_id, delegation_id),
        )
        return [self.get(row["id"], workspace_id) for row in rows]

    def publish_pr(
        self,
        session_id: str,
        workspace_id: str,
        title: str | None,
        body: str | None,
        reviewers: Sequence[str] | None = None,
        base: str | None = None,
    ) -> dict[str, Any]:
        session = self.get(session_id, workspace_id)
        if session["state"] != "COMPLETED" or not session["diff"]:
            raise Conflict("verification and a reviewable diff are required before PR creation")
        if "open_draft_pr" not in session["contract"]["allowed_tools"]:
            raise Forbidden("the warrant does not grant draft PR creation")
        if session["pull_request"]:
            return session["pull_request"]
        worktree = Path(session["worktree_path"])
        if not session["worktree_available"]:
            raise CodingAgentError(
                "the coding-session worktree was reclaimed by retention "
                f"(CODING_SESSION_RETENTION={self.settings.coding_session_retention}); "
                "re-run the session to publish a draft PR"
            )
        if not self.settings.pr_publishing_enabled:
            # Enforced here as well as inside the gh publisher, so the flag still gates the
            # outbound path when a different publisher implementation is installed.
            raise CodingAgentError("PR publishing feature flag is disabled")
        availability = self.publisher.availability(worktree)
        if not availability:
            raise CodingAgentError(availability.reason)
        # Nothing is committed, pushed or published under a warrant that has since been
        # revoked or expired.
        self._assert_warrant_live(
            session_id, session["warrant_id"], workspace_id, "pr_publish"
        )
        paths = [item["path"] for item in session["diff"]["changed_files"]]
        staged = LocalRepositoryProvider._git(["add", "--", *paths], worktree, 30)
        if staged.returncode != 0:
            raise CodingAgentError("failed to stage the reviewed coding-session diff")
        committed = LocalRepositoryProvider._git(
            [
                "-c",
                "user.name=Warrant Coding Agent",
                "-c",
                "user.email=warrant-agent@example.invalid",
                "commit",
                "-m",
                f"{session['contract']['issue']['external_key']}: governed agent change",
            ],
            worktree,
            60,
        )
        if committed.returncode != 0:
            raise CodingAgentError("failed to commit the reviewed coding-session diff")
        head = LocalRepositoryProvider._git(["rev-parse", "HEAD"], worktree, 10)
        if head.returncode != 0:
            raise CodingAgentError("could not resolve the coding-session head revision")
        self.db.execute(
            "UPDATE diff_artifacts SET head_revision=? WHERE session_id=?",
            (head.stdout.strip(), session_id),
        )
        self._event(session_id, "changes_committed", head_revision=head.stdout.strip())
        # A per-request list overrides the configured default; an explicit empty list means
        # "no reviewers", which is why this distinguishes None from ().
        requested = list(self.settings.pr_reviewers if reviewers is None else reviewers)
        target = self.settings.pr_base_branch if base is None else base
        result = self.publisher.create_draft_pull_request(
            worktree,
            session["branch_name"],
            title or f"{session['contract']['issue']['external_key']}: agent change",
            body or "Draft PR created from a governed Warrant coding session.",
            base=target,
            reviewers=requested,
        )
        artifact = {
            "id": self._id("pr"),
            "session_id": session_id,
            "provider": result.provider,
            "number": result.number,
            "url": result.url,
            "state": result.state,
            "created_at": self._now(),
        }
        self.db.execute(
            "INSERT INTO pull_request_artifacts VALUES (?,?,?,?,?,?,?)",
            tuple(artifact.values()),
        )
        self._event(
            session_id,
            "pr_created",
            url=result.url,
            number=result.number,
            draft=result.draft,
            provider=result.provider,
            base=target or "repository default",
            reviewers=list(result.reviewers),
            reviewer_error=result.reviewer_error,
        )
        # Returned alongside the stored artifact rather than written into it: the artifact
        # row is the durable record of the PR itself, while who was asked to review it can
        # change afterwards on GitHub and is authoritative only in the event timeline.
        return {
            **artifact,
            "base": target or "repository default",
            "reviewers": list(result.reviewers),
            "reviewer_error": result.reviewer_error,
        }
