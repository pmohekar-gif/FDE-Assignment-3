from __future__ import annotations

import os
import time

import pytest

from warrant.demo_repo import DemoRepositoryError, build_demo_repository


def test_demo_repository_recovers_old_empty_git_locks(tmp_path):
    root = tmp_path / "demo-repo"
    build_demo_repository(root)
    old = time.time() - 600
    locks = [root / ".git" / "index.lock", root / ".git" / "HEAD.lock"]
    for lock in locks:
        lock.touch()
        os.utime(lock, (old, old))

    summary = build_demo_repository(root)

    assert summary["stale_locks_removed"] == [".git/index.lock", ".git/HEAD.lock"]
    assert not any(lock.exists() for lock in locks)


@pytest.mark.parametrize("recent,content", [(True, b""), (False, b"owner-data")])
def test_demo_repository_refuses_a_potentially_active_git_lock(tmp_path, recent, content):
    root = tmp_path / "demo-repo"
    build_demo_repository(root)
    lock = root / ".git" / "index.lock"
    lock.write_bytes(content)
    if not recent:
        old = time.time() - 600
        os.utime(lock, (old, old))

    with pytest.raises(DemoRepositoryError, match="potentially active Git lock"):
        build_demo_repository(root)
