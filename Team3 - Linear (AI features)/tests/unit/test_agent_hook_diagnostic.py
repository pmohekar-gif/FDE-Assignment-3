"""The hook diagnostic must be safe to run and honest about what it found.

It exists because `hook: <Name> Blocked` is ambiguous: the CLI prints it both when a hook
denies and when a hook merely fails. Getting the parse or the safety default wrong would
make it worse than nothing.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_script():
    spec = importlib.util.spec_from_file_location(
        "diagnose_agent_hooks", PROJECT_ROOT / "scripts" / "diagnose_agent_hooks.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["diagnose_agent_hooks"] = module
    spec.loader.exec_module(module)
    return module


def test_hooks_are_read_out_of_a_real_hooks_json(tmp_path: Path):
    script = load_script()
    path = tmp_path / "hooks.json"
    path.write_text(
        json.dumps(
            {
                "hooks": {
                    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "guard.sh"}]}],
                    "PostToolUse": [{"hooks": [{"type": "command", "command": "lint.sh"}]}],
                }
            }
        )
    )
    entries, error = script.hooks_from_json(path)
    assert error is None
    assert {(item["event"], item["command"]) for item in entries} == {
        ("UserPromptSubmit", "guard.sh"),
        ("PostToolUse", "lint.sh"),
    }


def test_an_unparseable_config_is_reported_rather_than_ignored(tmp_path: Path):
    script = load_script()
    path = tmp_path / "hooks.json"
    path.write_text("{ not json")
    entries, error = script.hooks_from_json(path)
    assert entries == []
    assert error and "JSONDecodeError" in error


def test_a_config_without_hooks_is_not_an_error(tmp_path: Path):
    script = load_script()
    path = tmp_path / "hooks.json"
    path.write_text(json.dumps({"description": "no hooks here"}))
    assert script.hooks_from_json(path) == ([], None)


def test_the_project_hook_config_parses_and_gates_nothing():
    # If this project ever registers a turn-gating hook, the diagnostic's central claim
    # ("the blocked hook is not one of its own") stops being true.
    script = load_script()
    entries, error = script.hooks_from_json(PROJECT_ROOT / ".codex" / "hooks.json")
    assert error is None
    events = {str(item["event"]) for item in entries}
    assert events == {"PostToolUse", "Stop"}
    assert not events & script.TURN_GATING_HOOKS


def test_a_hook_that_fails_is_distinguished_from_one_that_denies(tmp_path: Path):
    script = load_script()
    failing = tmp_path / "needs_user.sh"
    failing.write_text('set -u\necho "user is $SOME_VARIABLE_NO_ONE_SETS"\n')
    status, output = script.run_hook(f"sh {failing}", {"PATH": "/usr/bin:/bin"})
    assert status != 0, "a hook missing a variable it needs must exit non-zero"
    assert "SOME_VARIABLE_NO_ONE_SETS" in output
    passing = tmp_path / "quiet.sh"
    passing.write_text("exit 0\n")
    assert script.run_hook(f"sh {passing}", {"PATH": "/usr/bin:/bin"}) == (0, "")


def toml_reader_available() -> bool:
    """Whether a TOML parser is importable as `tomllib` for this test run.

    `tomllib` is stdlib from 3.11, which this project requires; on 3.10 the API-identical
    `tomli` backport stands in so the parse logic is still covered rather than skipped.
    """
    try:
        import tomllib  # noqa: F401

        return True
    except ModuleNotFoundError:
        try:
            import tomli

            sys.modules["tomllib"] = tomli
            return True
        except ModuleNotFoundError:
            return False


@pytest.mark.skipif(not toml_reader_available(), reason="no TOML parser available")
def test_a_gating_hook_registered_in_config_toml_is_found(tmp_path: Path):
    # config.toml is one of the two files the failure message points an operator at, in
    # both of the shapes Codex accepts: a table per event, and an array of hook tables.
    script = load_script()
    path = tmp_path / "config.toml"
    path.write_text(
        'model = "gpt-5.5"\n\n'
        "[hooks.UserPromptSubmit]\n"
        'command = "sh guard.sh"\n\n'
        "[[hooks.PostToolUse.hooks]]\n"
        'command = ["sh", "lint.sh"]\n'
    )
    entries, error = script.hooks_from_toml(path)
    assert error is None
    found = {(str(item["event"]), str(item["command"])) for item in entries}
    assert ("UserPromptSubmit", "sh guard.sh") in found
    assert ("PostToolUse", "sh lint.sh") in found, "an argv list is joined, not dropped"
    gating = [item for item in entries if str(item["event"]) in script.TURN_GATING_HOOKS]
    assert [str(item["event"]) for item in gating] == ["UserPromptSubmit"]


@pytest.mark.skipif(not toml_reader_available(), reason="no TOML parser available")
def test_a_config_toml_without_hooks_is_not_an_error(tmp_path: Path):
    script = load_script()
    path = tmp_path / "config.toml"
    path.write_text('model = "gpt-5.5"\napproval_policy = "never"\n')
    assert script.hooks_from_toml(path) == ([], None)


def test_an_unreadable_config_toml_is_reported_not_guessed_at(tmp_path: Path):
    script = load_script()
    path = tmp_path / "config.toml"
    path.write_text("this is [not valid toml\n")
    entries, error = script.hooks_from_toml(path)
    assert entries == []
    assert error, "a file that cannot be parsed must say so, never look hook-free"


def test_the_governed_environment_matches_what_the_runner_would_pass(monkeypatch):
    script = load_script()
    monkeypatch.setenv("USER", "operator")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-appear")
    environment = script.governed_environment()
    assert "USER" in environment
    assert "AWS_SECRET_ACCESS_KEY" not in environment


def test_the_diagnostic_executes_nothing_unless_asked(monkeypatch, capsys):
    """Default is read-only: these are the operator's own scripts."""
    script = load_script()
    monkeypatch.setattr(
        script, "run_hook", lambda *_: pytest.fail("no hook may run without --run")
    )
    monkeypatch.setattr(sys, "argv", ["diagnose_agent_hooks.py"])
    with pytest.raises(SystemExit) as exit_info:
        script.main()
    assert exit_info.value.code in (0, 1)
    printed = capsys.readouterr().out
    assert "Re-run with --run" in printed
    assert "Governed agent environment" in printed
