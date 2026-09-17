"""Resolve a coding session's checkout from a GitHub repository URL.

Until now a session could only ever run against the single checkout named by
`REPOSITORY_ROOT`. That is one path in one `.env` file, so the product worked against
exactly one repository per deployment and pointing it somewhere else meant editing
configuration and restarting the server. The `coding_sessions.repository_root` column has
always been written per session; nothing ever wrote a *different* value into it.

This module supplies the missing half: given a GitHub URL, produce a real local Git
checkout under a managed root that a session can branch from, cloning it on first use and
fetching it on later ones. Everything else -- warrants, scope preflight, worktrees, the
diff, the publisher -- already takes a path and needs no change.

Three properties matter more than convenience here:

* **The URL is untrusted input.** It arrives on an API request, and it ends up deciding a
  filesystem path and an argv. Owner and repository names are validated against a strict
  character class, a leading `-` is refused so a name can never be read by `git` as a
  flag, and the resulting path is re-checked to be inside the managed clone root.
* **The token never reaches argv.** `ps` is world-readable on the platforms this runs on,
  so a token interpolated into a clone URL is a token published to every local user.
  Git asks for the password through `GIT_ASKPASS` instead, and the helper reads it from
  its own environment, which is not.
* **A refresh never discards work.** An existing checkout is only fetched and
  fast-forwarded. A session's branch lives in a detached worktree created from a
  revision, so there is nothing to gain from resetting the base checkout and a published
  branch to lose.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .repository import RepositoryError

# GitHub's own rule for both owners and repositories, minus the leading-dash case which is
# excluded separately because it is an argv hazard rather than a naming one.
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_SUPPORTED_HOSTS = frozenset({"github.com", "www.github.com"})
_HTTPS = re.compile(r"^https://(?P<host>[^/@]+)/(?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?/?$")
_SSH = re.compile(r"^git@(?P<host>[^:]+):(?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?/?$")
_SHORTHAND = re.compile(r"^(?P<owner>[^/\s]+)/(?P<name>[^/\s]+?)(?:\.git)?$")

# The clone is a network call against a host we do not control, so it gets its own budget
# rather than borrowing the short one the local-git helpers use.
DEFAULT_CLONE_TIMEOUT_SECONDS = 300


class RepositoryCloneError(RepositoryError):
    """A repository URL could not be resolved into a usable local checkout.

    Subclasses `RepositoryError` deliberately: every caller and error handler that already
    knows how to report "the repository is not usable" reports this correctly with no
    change, and a clone failure is exactly that condition arriving earlier.
    """


@dataclass(frozen=True)
class RepositorySource:
    """One validated GitHub repository, and the two forms of it the rest of the code needs."""

    owner: str
    name: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def clone_url(self) -> str:
        """The anonymous HTTPS URL. Credentials are supplied out of band, never here."""
        return f"https://github.com/{self.owner}/{self.name}.git"

    def authenticated_url(self, token: str | None) -> str:
        """The clone URL, carrying a *username* when a token exists -- never the token.

        Git needs a username to decide it should ask for a password at all; supplying
        `x-access-token` makes it ask, and `GIT_ASKPASS` answers. The secret itself stays
        out of argv, and therefore out of `ps` and out of any shell history.
        """
        if not token:
            return self.clone_url
        return f"https://x-access-token@github.com/{self.owner}/{self.name}.git"


def parse_repository_url(raw: str) -> RepositorySource:
    """Validate an untrusted repository reference into an owner/name pair.

    Accepts the three forms a person actually pastes: a browser URL, an SSH remote, and
    the bare `owner/name` shorthand. Everything else is refused with the reason, because
    a silent normalisation of an unexpected string is how a path traversal or an argv
    injection gets in.
    """
    candidate = (raw or "").strip()
    if not candidate:
        raise RepositoryCloneError("a repository URL is required")
    if len(candidate) > 500:
        raise RepositoryCloneError("repository URL is implausibly long")
    if "@" in candidate and not candidate.startswith("git@"):
        # `https://user:token@github.com/...` would work, and would then be persisted on
        # the session row and echoed back in the timeline. Refuse it and use the
        # configured credential instead.
        raise RepositoryCloneError(
            "credentials embedded in a repository URL are refused; "
            "configure GITHUB_TOKEN instead"
        )
    for pattern in (_HTTPS, _SSH, _SHORTHAND):
        match = pattern.match(candidate)
        if match is None:
            continue
        groups = match.groupdict()
        host = groups.get("host", "github.com").casefold()
        if host not in _SUPPORTED_HOSTS:
            raise RepositoryCloneError(
                f"only github.com repositories are supported; got host {host!r}"
            )
        return _validated(groups["owner"], groups["name"])
    raise RepositoryCloneError(
        "unrecognised repository reference; expected https://github.com/<owner>/<repo>, "
        "git@github.com:<owner>/<repo>.git, or <owner>/<repo>"
    )


def _validated(owner: str, name: str) -> RepositorySource:
    for label, value in (("owner", owner), ("repository", name)):
        if not _NAME.match(value):
            raise RepositoryCloneError(
                f"{label} name {value!r} is not a valid GitHub name"
            )
        if value in {".", ".."} or value.startswith("-"):
            raise RepositoryCloneError(f"{label} name {value!r} is refused")
    return RepositorySource(owner=owner, name=name)


def checkout_path(clone_root: Path, source: RepositorySource) -> Path:
    """Where this repository's managed checkout lives: `<clone root>/<owner>/<name>`.

    Deterministic, so the same repository is cloned once and reused by every later
    session, and re-checked against the clone root so a name that survived validation
    still cannot land outside it.
    """
    root = clone_root.expanduser().resolve()
    target = (root / source.owner / source.name).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise RepositoryCloneError("resolved checkout path escaped the clone root") from exc
    return target


@contextmanager
def _git_environment(token: str | None) -> Iterator[dict[str, str]]:
    """A minimal environment for `git`, with the token reachable but not visible.

    `GIT_TERMINAL_PROMPT=0` is the important one: without it a private repository and no
    usable credential make `git` block on a username prompt that no one will ever answer,
    which presents as a hung request rather than a refused one.
    """
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    if not token:
        yield env
        return
    with tempfile.TemporaryDirectory(prefix="warrant-git-") as directory:
        askpass = Path(directory) / "askpass.sh"
        askpass.write_text('#!/bin/sh\nprintf %s "$WARRANT_GIT_TOKEN"\n', encoding="utf-8")
        askpass.chmod(0o700)
        yield {**env, "GIT_ASKPASS": str(askpass), "WARRANT_GIT_TOKEN": token}


def _git(
    args: list[str],
    cwd: Path | None,
    env: dict[str, str],
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd is not None else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RepositoryCloneError(f"git unavailable: {type(exc).__name__}") from exc


def _detail(result: subprocess.CompletedProcess[str], token: str | None) -> str:
    """The last line of git's own complaint, with any credential scrubbed out."""
    text = (result.stderr or result.stdout or "").strip()
    if token:
        text = text.replace(token, "***")
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else "unknown error"


def ensure_checkout(
    source: RepositorySource,
    clone_root: Path,
    *,
    token: str | None = None,
    timeout: int = DEFAULT_CLONE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Return a usable local checkout of `source`, cloning or refreshing as needed.

    First use clones. Later uses fetch and, when the checkout is clean and its branch is
    strictly behind, fast-forward it. A refresh that cannot fast-forward is reported, not
    forced: the base checkout may still hold a branch from a session whose pull request is
    open, and discarding that to save one `git fetch` is a bad trade.
    """
    target = checkout_path(clone_root, source)
    existed = (target / ".git").is_dir()
    with _git_environment(token) as env:
        if not existed:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and any(target.iterdir()):
                raise RepositoryCloneError(
                    f"{target} already exists and is not a Git checkout; "
                    "remove it or choose another REPOSITORY_CLONE_ROOT"
                )
            result = _git(
                ["clone", "--origin", "origin", source.authenticated_url(token), str(target)],
                None,
                env,
                timeout,
            )
            if result.returncode != 0:
                raise RepositoryCloneError(
                    f"could not clone {source.slug}: {_detail(result, token)}"
                )
            updated = True
            update_reason = "cloned"
        else:
            updated, update_reason = _refresh(target, env, timeout, token)
        branch = _git(["symbolic-ref", "--quiet", "--short", "HEAD"], target, env, 30)
        revision = _git(["rev-parse", "HEAD"], target, env, 30)
    if revision.returncode != 0 or not revision.stdout.strip():
        raise RepositoryCloneError(
            f"{source.slug} was checked out but has no commit to branch from"
        )
    return {
        "slug": source.slug,
        "root": target,
        "clone_url": source.clone_url,
        "cloned": not existed,
        "updated": updated,
        "update_reason": update_reason,
        "branch": branch.stdout.strip() or "(detached)",
        "revision": revision.stdout.strip(),
        "authenticated": bool(token),
    }


def _refresh(
    target: Path, env: dict[str, str], timeout: int, token: str | None
) -> tuple[bool, str]:
    """Fetch, then fast-forward if that is safe. Never destructive, never fatal."""
    fetched = _git(["fetch", "--prune", "origin"], target, env, timeout)
    if fetched.returncode != 0:
        # A stale-but-present checkout is still a working base for a session, so a failed
        # fetch degrades rather than refuses -- but it is reported so the caller can say
        # which revision the work actually started from.
        return False, f"fetch failed, using the existing checkout: {_detail(fetched, token)}"
    merged = _git(["merge", "--ff-only", "--quiet"], target, env, 60)
    if merged.returncode != 0:
        return False, f"kept the existing revision: {_detail(merged, token)}"
    return True, "fetched and fast-forwarded"
