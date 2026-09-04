"""
linear_fixture.py — Static stub fixture for offline demo / CI use.

This fixture is used when LINEAR_MODE=stub. It clearly labels every response
as SIMULATED so it cannot be confused with real customer data. It is the ONLY
fixture permitted — there is no implicit fallback based on AI_PROVIDER.
"""

from __future__ import annotations

# STUB for offline demo / CI — clearly labelled as SIMULATED.
# This mimics the exact raw JSON shape returned by the Linear GraphQL API.
STUB_LINEAR_ISSUE: dict = {
    "id": "stub-uuid-0000-0000-0000-000000000001",
    "identifier": "ENG-001",
    "title": "[SIMULATED] Fix memory leak in agent runner",
    "description": (
        "Profiler shows 40 MB/h growth under sustained load. "
        "Traced to the embedding cache not being evicted on context flush. "
        "Acceptance criteria: memory growth must remain below 1 MB/h in a 24-hour soak test."
    ),
    "url": "https://linear.app/example-org/issue/ENG-001",
    "priority": 2,
    "updatedAt": "2024-09-01T12:00:00.000Z",
    "createdAt": "2024-08-28T09:00:00.000Z",
    "team": {"id": "team-stub-001", "name": "Engineering", "key": "ENG"},
    "labels": {"nodes": [{"id": "lbl-001", "name": "bug", "color": "#eb5757"}]},
    "state": {"id": "state-001", "name": "In Progress", "type": "started"},
    "assignee": {"id": "user-001", "name": "Alice"},
}
