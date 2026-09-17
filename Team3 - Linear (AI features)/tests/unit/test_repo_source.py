"""A repository URL is untrusted input that becomes a path and an argv.

These tests cover the three things that decide whether that is safe: what the parser
accepts, where the resulting path is allowed to land, and whether a credential can escape
into somewhere another local user can read it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from warrant.repo_source import (
    RepositoryCloneError,
    RepositorySource,
    checkout_path,
    ensure_checkout,
    parse_repository_url,
)


@pytest.mark.parametrize(
    "raw",
    [
        "https://github.com/pmohekar-gif/FDE-Assignment-3",
        "https://github.com/pmohekar-gif/FDE-Assignment-3.git",
        "https://github.com/pmohekar-gif/FDE-Assignment-3/",
        "git@github.com:pmohekar-gif/FDE-Assignment-3.git",
        "pmohekar-gif/FDE-Assignment-3",
        "  pmohekar-gif/FDE-Assignment-3  ",
    ],
)
def test_every_form_a_person_pastes_parses_to_the_same_repository(raw):
    source = parse_repository_url(raw)

    assert source.owner == "pmohekar-gif"
    assert source.name == "FDE-Assignment-3"
    assert source.clone_url == "https://github.com/pmohekar-gif/FDE-Assignment-3.git"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", "repository URL is required"),
        ("https://gitlab.com/owner/repo", "only github.com"),
        ("git@gitlab.com:owner/repo.git", "only github.com"),
        ("https://user:ghp_secret@github.com/owner/repo", "credentials embedded"),
        # Refused one step earlier than the others: the extra path segments mean it is
        # not a repository URL at all, so it never reaches name validation.
        ("https://github.com/owner/../../etc", "unrecognised repository reference"),
        ("https://github.com/owner/..", "not a valid GitHub name"),
        ("owner/..", "not a valid GitHub name"),
        ("owner/-upload-pack=touched", "not a valid GitHub name"),
        ("-oProxyCommand/repo", "not a valid GitHub name"),
        ("not a url at all", "unrecognised repository reference"),
        ("https://github.com/owner", "unrecognised repository reference"),
        ("x/" + "y" * 300, "not a valid GitHub name"),
    ],
)
def test_hostile_or_malformed_references_are_refused_with_a_reason(raw, expected):
    with pytest.raises(RepositoryCloneError, match=expected):
        parse_repository_url(raw)


def test_a_repository_name_can_never_be_read_by_git_as_a_flag():
    """A leading `-` in an owner or repository turns an argv position into an option."""
    for hostile in ("-upload-pack", "--upload-pack"):
        with pytest.raises(RepositoryCloneError):
            parse_repository_url(f"{hostile}/repo")
        with pytest.raises(RepositoryCloneError):
            parse_repository_url(f"owner/{hostile}")


def test_the_checkout_path_is_deterministic_and_inside_the_clone_root(tmp_path):
    source = parse_repository_url("pmohekar-gif/FDE-Assignment-3")

    first = checkout_path(tmp_path, source)
    second = checkout_path(tmp_path, source)

    assert first == second, "the same repository must reuse one clone, not clone twice"
    assert first == tmp_path.resolve() / "pmohekar-gif" / "FDE-Assignment-3"
    assert first.is_relative_to(tmp_path.resolve())


def test_two_repositories_that_share_a_name_do_not_share_a_checkout(tmp_path):
    mine = checkout_path(tmp_path, parse_repository_url("pmohekar-gif/warrant"))
    theirs = checkout_path(tmp_path, parse_repository_url("someone-else/warrant"))

    assert mine != theirs


def test_the_token_never_reaches_the_clone_url():
    """`ps` is world-readable, so a token in argv is a token published locally."""
    source = RepositorySource(owner="pmohekar-gif", name="FDE-Assignment-3")

    authenticated = source.authenticated_url("ghp_a_real_looking_secret")

    assert "ghp_a_real_looking_secret" not in authenticated
    assert authenticated.startswith("https://x-access-token@github.com/")


def _local_origin(tmp_path: Path) -> Path:
    """A real Git repository on disk, used as a clone source without touching a network."""
    origin = tmp_path / "origin"
    origin.mkdir()
    run = lambda *args: subprocess.run(  # noqa: E731 - terse on purpose, test-local
        ["git", *args], cwd=origin, check=True, capture_output=True, text=True
    )
    run("init", "-q", "-b", "main")
    run("config", "user.email", "test@example.invalid")
    run("config", "user.name", "Test")
    run("config", "commit.gpgsign", "false")
    (origin / "README.md").write_text("origin\n", encoding="utf-8")
    run("add", "-A")
    run("commit", "-q", "-m", "initial")
    return origin


def test_a_second_session_reuses_the_existing_checkout_instead_of_recloning(
    tmp_path, monkeypatch
):
    """Cloning once and fetching after is the difference between a usable feature and a
    minute of network per session."""
    origin = _local_origin(tmp_path)
    source = RepositorySource(owner="local", name="fixture")
    monkeypatch.setattr(
        RepositorySource, "authenticated_url", lambda self, token: str(origin), raising=True
    )
    clone_root = tmp_path / "clones"

    first = ensure_checkout(source, clone_root)
    second = ensure_checkout(source, clone_root)

    assert first["cloned"] is True
    assert second["cloned"] is False
    assert first["root"] == second["root"]
    assert second["revision"] == first["revision"]


def test_a_checkout_that_cannot_be_fetched_is_reported_not_abandoned(tmp_path, monkeypatch):
    """A stale checkout is still a working base to branch from; losing the remote should
    degrade the session's provenance, not refuse the session."""
    origin = _local_origin(tmp_path)
    source = RepositorySource(owner="local", name="fixture")
    monkeypatch.setattr(
        RepositorySource, "authenticated_url", lambda self, token: str(origin), raising=True
    )
    clone_root = tmp_path / "clones"
    ensure_checkout(source, clone_root)

    # The remote disappears between one session and the next.
    for item in sorted(origin.rglob("*"), reverse=True):
        item.unlink() if item.is_file() else item.rmdir()
    origin.rmdir()

    result = ensure_checkout(source, clone_root)

    assert result["cloned"] is False
    assert result["updated"] is False
    assert "fetch failed" in result["update_reason"]
    assert result["revision"], "the existing checkout still has a revision to branch from"


def test_a_clone_failure_names_the_repository_rather_than_raising_a_git_error(tmp_path):
    source = RepositorySource(owner="local", name="does-not-exist")

    with pytest.raises(RepositoryCloneError, match="could not clone local/does-not-exist"):
        ensure_checkout(
            source, tmp_path / "clones", token=None, timeout=30
        )


def test_an_occupied_non_git_directory_is_refused_rather_than_cloned_into(tmp_path):
    source = RepositorySource(owner="local", name="occupied")
    clone_root = tmp_path / "clones"
    target = clone_root / "local" / "occupied"
    target.mkdir(parents=True)
    (target / "important.txt").write_text("not ours to overwrite", encoding="utf-8")

    with pytest.raises(RepositoryCloneError, match="already exists and is not a Git checkout"):
        ensure_checkout(source, clone_root)

    assert (target / "important.txt").exists()
