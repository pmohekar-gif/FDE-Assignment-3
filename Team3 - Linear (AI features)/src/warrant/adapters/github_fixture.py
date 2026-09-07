from __future__ import annotations

STUB_GITHUB_PR = {
    "id": 123456789,
    "number": 42,
    "html_url": "https://github.com/example-org/repo/pull/42",
    "state": "open",
    "draft": False,
    "title": "[SIMULATED] Fix memory leak in auth",
    "merged": False,
    "base": {"ref": "main"},
    "head": {"sha": "abcdef1234567890"},
}

STUB_GITHUB_FILES = [
    {
        "filename": "src/auth.py",
        "status": "modified",
        "additions": 10,
        "deletions": 5,
    },
    {
        "filename": "tests/test_auth.py",
        "status": "modified",
        "additions": 20,
        "deletions": 0,
    },
]

STUB_GITHUB_CHECKS = [
    {
        "id": 987654321,
        "name": "lint",
        "status": "completed",
        "conclusion": "success",
        "started_at": "2026-09-01T12:00:00Z",
        "completed_at": "2026-09-01T12:05:00Z",
        "html_url": "https://github.com/example-org/repo/runs/987654321",
    },
    {
        "id": 987654322,
        "name": "test",
        "status": "completed",
        "conclusion": "success",
        "started_at": "2026-09-01T12:00:00Z",
        "completed_at": "2026-09-01T12:10:00Z",
        "html_url": "https://github.com/example-org/repo/runs/987654322",
    },
]
