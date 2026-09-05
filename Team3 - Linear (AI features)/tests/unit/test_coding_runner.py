from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from warrant.coding import (
    CodingAgentError,
    GhPullRequestPublisher,
    MockPullRequestPublisher,
    PublisherAvailability,
    PullRequestPublisher,
    PullRequestPublishError,
    SubprocessCodingAgentRunner,
    validated_base_branch,
    validated_reviewers,
)
from warrant.config import Settings
from warrant.db import Database
from warrant.verification import (
    VerificationCheck,
    checks_from_contract,
    ci_run_candidates,
    discover_verification_plan,
    makefile_targets,
    runnable,
)

WORKFLOW = """
name: ci
on: [push]
jobs:
  verify:
    steps:
      - uses: actions/checkout@v4
      - name: install
        run: npm ci
      - name: unit
        run: make test
      - name: chained
        run: pytest -q && ruff check .
      - name: piped
        run: pytest -q | tee out.txt
      - name: multi
        run: |
          make lint
          make build
      - name: types
        run: mypy src
"""


def stub_runnable(monkeypatch, available: bool = True) -> None:
    """Decide availability deterministically, so priority is what is under test."""
    monkeypatch.setattr(
        "warrant.verification.runnable",
        lambda command: (available, "stub available" if available else "stub unavailable"),
    )


def write(root: Path, relative: str, body: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def test_codex_runner_uses_argument_list_and_minimal_environment(tmp_path, monkeypatch):
    settings = replace(
        Settings.from_env(),
        coding_agent_timeout_seconds=1,
        coding_agent_max_output_bytes=8,
    )
    runner = SubprocessCodingAgentRunner("codex", settings)
    prompt = "change copy; touch /tmp/should-not-run"
    command = runner._command(tmp_path, prompt)
    assert command[-1] == prompt
    assert command[0] == "codex" and "exec" in command
    assert "--sandbox" in command and "workspace-write" in command
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-pass")
    assert "AWS_SECRET_ACCESS_KEY" not in runner._environment()


class EchoSubprocessRunner(SubprocessCodingAgentRunner):
    """A real subprocess runner with a harmless command, to exercise process reporting."""

    def _command(self, workspace: Path, prompt: str) -> list[str]:
        return ["python3", "-c", "print('simulated agent')"]


def test_subprocess_runner_reports_its_process_id_to_the_session(tmp_path):
    settings = replace(Settings.from_env(), coding_agent_timeout_seconds=30)
    runner = EchoSubprocessRunner("python3", settings)
    reported: list[tuple[str, int]] = []
    runner.on_process_start = lambda session_id, pid: reported.append((session_id, pid))
    result = runner.run("ses_unit_pid", tmp_path, "prompt")
    assert result.exit_code == 0
    assert [item[0] for item in reported] == ["ses_unit_pid"]
    assert reported[0][1] > 0


def test_package_json_scripts_outrank_makefile_and_ci(tmp_path, monkeypatch):
    stub_runnable(monkeypatch)
    write(
        tmp_path,
        "package.json",
        json.dumps({"scripts": {"test": "jest", "lint": "eslint .", "typecheck": "tsc --noEmit"}}),
    )
    write(tmp_path, "Makefile", "test:\n\tpytest -q\n")
    write(tmp_path, ".github/workflows/ci.yml", WORKFLOW)
    plan = discover_verification_plan(tmp_path, ("git", "diff", "--check"))
    assert plan.source == "package.json"
    assert [check.name for check in plan.checks] == ["test", "lint", "typecheck"]
    assert plan.checks[0].command == ("npm", "run", "--silent", "test")
    assert all(check.required for check in plan.checks)


def test_pyproject_and_makefile_are_the_second_tier(tmp_path, monkeypatch):
    stub_runnable(monkeypatch)
    write(tmp_path, "pyproject.toml", "[tool.pytest.ini_options]\naddopts = '-q'\n")
    write(tmp_path, "Makefile", ".PHONY: lint\nlint:\n\truff check .\n")
    write(tmp_path, ".github/workflows/ci.yml", WORKFLOW)
    plan = discover_verification_plan(tmp_path, ("git", "diff", "--check"))
    assert plan.source == "pyproject.toml+makefile"
    assert [" ".join(check.command) for check in plan.checks] == [
        "python3 -m pytest -q",
        "make lint",
    ]


def test_ci_workflows_are_the_third_tier_and_refuse_shell_strings(tmp_path, monkeypatch):
    stub_runnable(monkeypatch)
    write(tmp_path, ".github/workflows/ci.yml", WORKFLOW)
    plan = discover_verification_plan(tmp_path, ("git", "diff", "--check"))
    assert plan.source == "github-actions"
    commands = [" ".join(check.command) for check in plan.checks]
    # `npm ci` classifies as nothing, and every shell-dependent line is refused outright.
    assert commands == ["make test", "mypy src"]
    assert not any("&&" in item or "|" in item for item in commands)


def test_ci_candidates_reject_pipes_chains_and_multiline_steps():
    candidates = ci_run_candidates(WORKFLOW)
    assert [" ".join(check.command) for check in candidates] == ["make test", "mypy src"]
    assert [check.name for check in candidates] == ["test", "typecheck"]


def test_configured_command_is_the_documented_last_resort(tmp_path):
    plan = discover_verification_plan(tmp_path, ("git", "diff", "--check"))
    assert plan.source == "configured"
    assert plan.checks[0].command == ("git", "diff", "--check")
    assert plan.checks[0].name == "configured"


def test_unavailable_candidates_are_skipped_with_a_recorded_reason(tmp_path, monkeypatch):
    write(tmp_path, "Makefile", "test:\n\tpytest -q\n")
    monkeypatch.setattr(
        "warrant.verification.shutil.which", lambda name: None if name == "make" else "/usr/bin/git"
    )
    plan = discover_verification_plan(tmp_path, ("git", "diff", "--check"))
    assert plan.source == "configured"
    assert [item["reason"] for item in plan.skipped] == ["make is not on PATH"]


def test_discovery_can_be_disabled_without_losing_the_gate(tmp_path, monkeypatch):
    stub_runnable(monkeypatch)
    write(tmp_path, "Makefile", "test:\n\tpytest -q\n")
    plan = discover_verification_plan(tmp_path, ("git", "diff", "--check"), enabled=False)
    assert plan.source == "configured"
    assert [check.command for check in plan.checks] == [("git", "diff", "--check")]


def test_max_checks_caps_the_discovered_plan(tmp_path, monkeypatch):
    stub_runnable(monkeypatch)
    write(
        tmp_path,
        "package.json",
        json.dumps({"scripts": {"test": "jest", "lint": "eslint .", "build": "vite build"}}),
    )
    plan = discover_verification_plan(tmp_path, ("git", "diff", "--check"), max_checks=2)
    assert len(plan.checks) == 2


def test_makefile_target_parsing_ignores_recipes_and_variables():
    text = (
        ".PHONY: test lint\nCC = gcc\ntest:\n\tpytest -q\n\tmake sub\nlint: fmt\n\truff check .\n"
    )
    assert makefile_targets(text) == ["test", "lint"]


def test_runnable_reports_missing_executables_and_missing_modules():
    assert runnable(())[0] is False
    assert runnable(("definitely-not-a-real-binary-xyz",))[0] is False
    ok, reason = runnable(("python3", "-m", "not_a_real_module_xyz"))
    assert ok is False and "not_a_real_module_xyz" in reason
    assert runnable((shutil.which("git") or "git", "--version"))[0] is True


def test_contract_checks_round_trip_and_ignore_malformed_entries():
    original = VerificationCheck("test", ("make", "test"), "makefile")
    restored = checks_from_contract([original.to_dict(), {"command": []}, "nonsense", {}])
    assert restored == [original]


class ScriptedGhPublisher(GhPullRequestPublisher):
    """A gh publisher whose only subprocess boundary is replaced by canned results."""

    def __init__(self, outputs: dict[str, subprocess.CompletedProcess[str]]) -> None:
        super().__init__(enabled=True)
        self.outputs = outputs
        self.calls: list[list[str]] = []

    def availability(self, workspace: Path) -> PublisherAvailability:
        return PublisherAvailability(True, "scripted for the test")

    def _run(self, args, cwd, timeout=60):  # type: ignore[override]
        self.calls.append(list(args))
        return self.outputs.get(
            " ".join(args[:3]), subprocess.CompletedProcess(list(args), 0, "", "")
        )


def completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, "")


@pytest.mark.parametrize(
    "output",
    [
        "",
        "\n",
        "Warning: 3 uncommitted changes\n",
        "https://github.com/acme/repo/pull/not-a-number\n",
        "https://gitlab.com/acme/repo/pull/12\n",
    ],
)
def test_malformed_gh_output_raises_a_typed_error_instead_of_indexerror(tmp_path, output):
    publisher = ScriptedGhPublisher({"gh pr create": completed(output)})
    with pytest.raises(PullRequestPublishError) as raised:
        publisher.create_draft_pull_request(tmp_path, "agent/x", "title", "body")
    assert "parseable" in str(raised.value)
    # It stays inside the project's own error hierarchy, so the API still answers 503.
    assert isinstance(raised.value, CodingAgentError)


def test_gh_publisher_extracts_the_pull_request_url_from_noisy_output(tmp_path):
    publisher = ScriptedGhPublisher(
        {
            "gh pr create": completed(
                "Creating draft pull request for agent/x into main\n"
                "https://github.com/acme/repo/pull/318\n"
            )
        }
    )
    reference = publisher.create_draft_pull_request(tmp_path, "agent/x", "title", "body")
    assert reference.provider == "gh-cli"
    assert reference.number == 318
    assert reference.url == "https://github.com/acme/repo/pull/318"
    assert reference.state == "draft" and reference.draft is True
    assert publisher.calls[0][:3] == ["git", "push", "--set-upstream"]


def test_gh_publisher_reports_a_failed_creation_as_a_typed_error(tmp_path):
    publisher = ScriptedGhPublisher({"gh pr create": completed("", returncode=1)})
    with pytest.raises(PullRequestPublishError):
        publisher.create_draft_pull_request(tmp_path, "agent/x", "title", "body")


def test_gh_get_pull_request_is_defensive_about_absent_and_malformed_answers(tmp_path):
    absent = ScriptedGhPublisher({"gh pr view": completed("", returncode=1)})
    assert absent.get_pull_request(tmp_path, "agent/x") is None

    for broken in ("not json at all", json.dumps(["unexpected"]), json.dumps({"url": "nope"})):
        publisher = ScriptedGhPublisher({"gh pr view": completed(broken)})
        with pytest.raises(PullRequestPublishError):
            publisher.get_pull_request(tmp_path, "agent/x")

    found = ScriptedGhPublisher(
        {
            "gh pr view": completed(
                json.dumps(
                    {
                        "number": 7,
                        "url": "https://github.com/acme/repo/pull/7",
                        "state": "OPEN",
                        "isDraft": True,
                    }
                )
            )
        }
    )
    reference = found.get_pull_request(tmp_path, "agent/x")
    assert reference is not None
    assert (reference.number, reference.state, reference.draft) == (7, "open", True)


def test_reviewers_and_base_branch_reach_gh_as_validated_argv(tmp_path):
    publisher = ScriptedGhPublisher(
        {"gh pr create": completed("https://github.com/acme/repo/pull/42\n")}
    )
    reference = publisher.create_draft_pull_request(
        tmp_path,
        "agent/x",
        "title",
        "body",
        base="main",
        # Duplicates collapse, order is preserved, and an org/team slug is a valid handle.
        reviewers=["teammate-one", "acme/reviewers", "teammate-one"],
    )
    create = next(call for call in publisher.calls if call[:3] == ["gh", "pr", "create"])
    assert create[create.index("--base") + 1] == "main"
    assert [create[i + 1] for i, part in enumerate(create) if part == "--reviewer"] == [
        "teammate-one",
        "acme/reviewers",
    ]
    assert reference.reviewers == ("teammate-one", "acme/reviewers")
    assert reference.reviewer_error is None


@pytest.mark.parametrize(
    "handle",
    ["--repo=other/repo", "-x", "not a handle", "has_underscore", "", "a" * 60],
)
def test_a_reviewer_handle_that_could_be_read_as_a_flag_is_refused(tmp_path, handle):
    publisher = ScriptedGhPublisher(
        {"gh pr create": completed("https://github.com/acme/repo/pull/42\n")}
    )
    if handle == "":
        # Blank entries are dropped rather than refused: nothing reaches argv either way.
        assert validated_reviewers([handle]) == []
        return
    with pytest.raises(PullRequestPublishError):
        validated_reviewers([handle])
    # And the refusal happens before anything is pushed.
    with pytest.raises(PullRequestPublishError):
        publisher.create_draft_pull_request(
            tmp_path, "agent/x", "title", "body", reviewers=[handle]
        )
    assert publisher.calls == []


def test_a_base_branch_that_could_be_read_as_a_flag_is_refused():
    assert validated_base_branch("") == ""
    assert validated_base_branch(" release/2.1 ") == "release/2.1"
    for candidate in ["--force", "-b", "a..b", "has space"]:
        with pytest.raises(PullRequestPublishError):
            validated_base_branch(candidate)


def test_a_failed_review_request_still_lands_the_pr_and_says_nobody_was_asked(tmp_path):
    class ReviewerHostilePublisher(ScriptedGhPublisher):
        """`gh` rejects the reviewer flag, as it does for a non-collaborator handle."""

        def _run(self, args, cwd, timeout=60):
            self.calls.append(list(args))
            if args[:3] == ["gh", "pr", "create"]:
                if "--reviewer" in args:
                    return subprocess.CompletedProcess(
                        list(args), 1, "", "could not add reviewer: not a collaborator\n"
                    )
                return completed("https://github.com/acme/repo/pull/43\n")
            return completed("")

    publisher = ReviewerHostilePublisher({})
    reference = publisher.create_draft_pull_request(
        tmp_path, "agent/x", "title", "body", reviewers=["outsider"]
    )
    # The PR exists...
    assert reference.number == 43
    # ...but the record must not claim a review was requested when it was not.
    assert reference.reviewers == ()
    assert reference.reviewer_error is not None
    assert "not a collaborator" in reference.reviewer_error


def test_mock_publisher_implements_the_publisher_contract_without_gh(tmp_path):
    publisher = MockPullRequestPublisher()
    assert isinstance(publisher, PullRequestPublisher)
    assert publisher.is_available(tmp_path) is True
    assert publisher.get_pull_request(tmp_path, "agent/x") is None
    reference = publisher.create_draft_pull_request(tmp_path, "agent/x", "title", "body")
    assert reference.url.startswith("https://example.invalid/")
    assert reference.draft is True and reference.number == 1
    assert publisher.get_pull_request(tmp_path, "agent/x") == reference
    assert publisher.created == [reference]

    blocked = MockPullRequestPublisher(available=False, reason="disabled for the test")
    assert blocked.is_available(tmp_path) is False
    with pytest.raises(CodingAgentError):
        blocked.create_draft_pull_request(tmp_path, "agent/x", "title", "body")

    # The real publisher still refuses outright when the feature flag is off.
    assert GhPullRequestPublisher(enabled=False).is_available(tmp_path) is False


def insert_session(db: Database, session_id: str, contract: str) -> None:
    db.execute(
        "INSERT INTO workspaces VALUES (?,?,?,?,?)", ("ws-test", "Test", "v1", "{}", "now")
    )
    db.execute(
        "INSERT INTO coding_sessions "
        "(id,workspace_id,delegation_id,warrant_id,issue_id,requester_id,source,provider,state,"
        "repository_root,base_revision,contract_json,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            session_id,
            "ws-test",
            "dlg_x",
            "wrt_x",
            "issue_x",
            "user_x",
            "api",
            "mock",
            "QUEUED",
            "/tmp",
            "HEAD",
            contract,
            "now",
        ),
    )


def test_the_execution_contract_cannot_be_updated_after_the_session_starts(tmp_path):
    """The same append-only database guarantee the audit ledger already has."""
    db = Database(tmp_path / "immutable.db")
    db.migrate()
    contract = '{"allowed_paths":["web/**"],"restricted_paths":[".git/**"]}'
    insert_session(db, "ses_immutable", contract)

    with pytest.raises(sqlite3.IntegrityError) as raised:
        db.execute(
            "UPDATE coding_sessions SET contract_json=? WHERE id=?",
            ('{"allowed_paths":["**"]}', "ses_immutable"),
        )
    assert "immutable" in str(raised.value)
    query = "SELECT contract_json,state FROM coding_sessions WHERE id=?"
    stored = db.one(query, ("ses_immutable",))
    assert stored is not None and stored["contract_json"] == contract

    # Widening it as part of a wider statement is refused too.
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "UPDATE coding_sessions SET state=?,contract_json=? WHERE id=?",
            ("PREPARING", "{}", "ses_immutable"),
        )

    # Every other column of a live session still moves normally.
    db.execute("UPDATE coding_sessions SET state=? WHERE id=?", ("PREPARING", "ses_immutable"))
    moved = db.one(query, ("ses_immutable",))
    assert moved is not None
    assert moved["state"] == "PREPARING" and moved["contract_json"] == contract
