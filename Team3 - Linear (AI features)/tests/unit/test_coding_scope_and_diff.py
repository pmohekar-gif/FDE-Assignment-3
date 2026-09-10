"""Regressions for the three defects that made governed sessions fail after approval.

Each test names the observable failure it prevents, not just the helper it calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from warrant.coding import (
    TURN_GATING_HOOKS,
    MockCodingAgentRunner,
    SubprocessCodingAgentRunner,
    _scope_grants_surface,
    blocked_hooks,
    prepare_isolated_agent_home,
    redact_diff_content,
    strip_hooks_table,
    validated_env_passthrough,
)
from warrant.config import Settings

BASE_SETTINGS = {
    "database_path": Path("/tmp/warrant-env-test.db"),
    "ai_provider": "fixture",
    "openai_api_key": None,
    "openai_base_url": "https://api.openai.com/v1",
    "openai_model": "fixture",
    "webhook_secret": "test",
    "csrf_token": "test",
    "warrant_ttl_minutes": 240,
    "allow_sufficiency_threshold": 0.70,
    "fixture_failure": None,
    "debug": False,
}

# The real transcript from a CHIR-1104 run whose prompt an ambient hook denied. Codex
# exited 0 having done nothing, which looked identical to "the agent declined the work".
CODEX_BLOCKED_TRANSCRIPT = """OpenAI Codex v0.153.0
--------
workdir: /tmp/ses_a4a98f1da8e147c3
model: gpt-5.5
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR]
--------
user
Implement the requested outcome in this isolated Git worktree.
hook: SessionStart
hook: SessionStart
hook: SessionStart Completed
hook: SessionStart Completed
hook: UserPromptSubmit
hook: UserPromptSubmit Blocked
"""


def test_an_approved_file_inside_a_protected_surface_is_granted_not_restricted():
    # The failure: PAY-4471 is approved for services/billing/retry.py, which lives under
    # the protected services/billing/** surface. The surface stayed on the restricted
    # list, so the session died with "agent changed restricted files" on the very file
    # the named owner had just approved.
    assert _scope_grants_surface("services/billing/retry.py", "services/billing/**") is True
    assert _scope_grants_surface("services/billing/**", "services/billing/**") is True


def test_a_broad_grant_does_not_unlock_a_nested_protected_surface():
    # The mirror-image failure of the same argument-order bug: a wide grant must not
    # silently buy access to the separately owned, irreversible ledger surface.
    assert _scope_grants_surface("services/billing/**", "services/billing/ledger/**") is False
    assert _scope_grants_surface("services/**", "services/billing/ledger/**") is False
    assert _scope_grants_surface("services/billing/ledger/**", "services/billing/ledger/**") is True


def test_an_unrelated_scope_never_grants_a_protected_surface():
    assert _scope_grants_surface("web/**", "services/billing/**") is False
    assert _scope_grants_surface("docs/architecture.md", "services/auth/keys/**") is False


def test_git_metadata_is_never_scanned_or_redacted_as_a_secret():
    # `index <blob>..<blob>` is all digits and dashes often enough that the card-PAN
    # pattern matched it, so ordinary diffs failed with "diff contains secret-like
    # material" depending on the hashes Git happened to compute -- and the recorded
    # artifact lost the revisions a reviewer needs.
    diff = (
        "diff --git a/services/billing/retry.py b/services/billing/retry.py\n"
        "index 8603970..1234567 100644\n"
        "--- a/services/billing/retry.py\n"
        "+++ b/services/billing/retry.py\n"
        "@@ -1,2 +1,3 @@\n"
        " RETRY_WINDOW_SECONDS = 5.0\n"
        "+MAX_ATTEMPTS = 3\n"
    )
    redacted, count, kinds = redact_diff_content(diff)
    assert count == 0
    assert kinds == ()
    assert redacted == diff
    assert "index 8603970..1234567 100644" in redacted


def test_a_secret_added_by_the_agent_is_still_caught_and_counted():
    diff = (
        "diff --git a/web/config.ts b/web/config.ts\n"
        "index 1111111..2222222 100644\n"
        "--- a/web/config.ts\n"
        "+++ b/web/config.ts\n"
        "@@ -1 +1,2 @@\n"
        " export const ok = true;\n"
        '+export const apiKey = "sk_live_0123456789abcdef";\n'
    )
    redacted, count, kinds = redact_diff_content(diff)
    assert count >= 1
    assert "sk_live_0123456789abcdef" not in redacted
    assert "REDACTED" in redacted
    # secret_assignment (a credential-named variable assigned a value) matches first,
    # per SECRET_PATTERNS' own ordering, before api_key gets a chance at the same text.
    assert "secret_assignment" in kinds


def test_redaction_kinds_distinguish_broad_from_narrow_patterns():
    from warrant.coding import _diagnose_secret_redaction

    narrow_only = _diagnose_secret_redaction(["jwt"])
    assert "real leak" in narrow_only
    assert "not by itself evidence" not in narrow_only

    broad_only = _diagnose_secret_redaction(["email"])
    assert "not by itself evidence" in broad_only
    assert "real leak" not in broad_only

    mixed = _diagnose_secret_redaction(["email", "jwt"])
    assert "real leak" in mixed
    assert "not by itself evidence" in mixed
    # The message never repeats the matched text, only the pattern names.
    assert "eyJ" not in mixed


def test_the_simulated_runner_amends_an_existing_in_scope_file(tmp_path: Path):
    # Turning a glob into a literal filename invented a path the target repository could
    # ignore, and an ignored write produces no diff at all.
    (tmp_path / "web" / "reports").mkdir(parents=True)
    (tmp_path / "web" / "reports" / "Table.tsx").write_text("export const PAGE_SIZE = 25;\n")
    assert MockCodingAgentRunner._target_path(tmp_path, ["web/**"]) == "web/reports/Table.tsx"
    assert (
        MockCodingAgentRunner._target_path(tmp_path, ["web/reports/Table.tsx"])
        == "web/reports/Table.tsx"
    )


def test_the_simulated_runner_falls_back_when_nothing_in_scope_exists(tmp_path: Path):
    assert MockCodingAgentRunner._target_path(tmp_path, ["docs/**"]) == "docs/simulated"
    assert MockCodingAgentRunner._target_path(tmp_path, []) == "CODING_SESSION_MOCK.md"


def test_a_blocked_prompt_hook_is_read_out_of_the_runner_transcript():
    assert blocked_hooks(CODEX_BLOCKED_TRANSCRIPT) == ["UserPromptSubmit"]
    assert "UserPromptSubmit" in TURN_GATING_HOOKS


def test_a_completed_hook_is_not_mistaken_for_a_blocked_one():
    # "SessionStart Completed" appears four times in that transcript and means the
    # opposite of a denial.
    assert "SessionStart" not in blocked_hooks(CODEX_BLOCKED_TRANSCRIPT)
    assert blocked_hooks("hook: PostToolUse\nhook: PostToolUse Completed\n") == []
    assert blocked_hooks("") == []
    assert blocked_hooks("the word Blocked appears in prose, not on a hook line") == []


def test_every_blocked_hook_is_reported_once_in_order():
    output = (
        "hook: PreToolUse Blocked\n"
        "hook: PreToolUse Blocked\n"
        "hook: UserPromptSubmit Blocked\n"
    )
    assert blocked_hooks(output) == ["PreToolUse", "UserPromptSubmit"]


def test_the_agent_environment_carries_what_shell_hooks_assume(monkeypatch):
    # A `set -u` hook referencing $USER exits non-zero, and the CLI reports a failed
    # gating hook as a denial -- so an over-tight environment looks like a policy block.
    for name in ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "TERM"):
        monkeypatch.setenv(name, f"value-of-{name}")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-reach-the-agent")
    runner = SubprocessCodingAgentRunner("codex", Settings(**BASE_SETTINGS))
    names = runner.environment_names()
    assert {"PATH", "HOME", "USER", "LOGNAME", "SHELL", "TERM"} <= set(names)
    assert "AWS_SECRET_ACCESS_KEY" not in names


def test_the_passthrough_widens_the_environment_on_request(monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", "/tmp/cache")
    monkeypatch.setenv("NODE_PATH", "/opt/node")
    runner = SubprocessCodingAgentRunner(
        "codex",
        Settings(**{**BASE_SETTINGS, "coding_agent_env_passthrough": ("XDG_CACHE_HOME",)}),
    )
    names = runner.environment_names()
    assert "XDG_CACHE_HOME" in names
    assert "NODE_PATH" not in names, "only the names the operator listed are passed"


def test_a_secret_shaped_passthrough_name_is_refused_at_startup():
    for name in ("AWS_SECRET_ACCESS_KEY", "GH_TOKEN", "DB_PASSWORD", "MY_API_KEY", "SESSION_KEY"):
        with pytest.raises(ValueError, match="secret-shaped"):
            validated_env_passthrough([name])
    # The baseline's own credential is not re-refused, and ordinary names pass.
    assert validated_env_passthrough(["OPENAI_API_KEY"]) == ()
    assert validated_env_passthrough(["XDG_CACHE_HOME", "NVM_DIR", "XDG_CACHE_HOME"]) == (
        "XDG_CACHE_HOME",
        "NVM_DIR",
    )


def test_strip_hooks_table_removes_hooks_but_keeps_model_and_provider():
    text = (
        "model = \"gpt-5.5\"\n"
        "provider = \"openai\"\n"
        "\n"
        "[hooks]\n"
        "some_setting = true\n"
        "\n"
        "[hooks.UserPromptSubmit]\n"
        "command = \"deny-everything.sh\"\n"
        "\n"
        "[[hooks.SessionStart.hooks]]\n"
        "command = [\"python3\", \"discipline_context.py\"]\n"
        "\n"
        "[sandbox]\n"
        "mode = \"workspace-write\"\n"
    )
    filtered = strip_hooks_table(text)
    assert "gpt-5.5" in filtered
    assert "[sandbox]" in filtered
    assert "workspace-write" in filtered
    assert "hooks" not in filtered
    assert "deny-everything.sh" not in filtered
    assert "discipline_context.py" not in filtered


def test_strip_hooks_table_is_a_no_op_when_there_are_no_hooks():
    text = "model = \"gpt-5.5\"\nprovider = \"openai\"\n"
    assert strip_hooks_table(text) == text


def test_prepare_isolated_agent_home_copies_credentials_and_filters_config(tmp_path: Path):
    source = tmp_path / "real-home"
    source.mkdir()
    (source / "auth.json").write_text('{"access_token": "shh"}', encoding="utf-8")
    (source / "config.toml").write_text(
        'model = "gpt-5.5"\n\n[hooks.UserPromptSubmit]\ncommand = "deny.sh"\n',
        encoding="utf-8",
    )
    # A hooks.json is deliberately not read at all -- the whole file is left behind.
    (source / "hooks.json").write_text('{"hooks": {"UserPromptSubmit": []}}', encoding="utf-8")

    target = tmp_path / "isolated-home"
    assert prepare_isolated_agent_home(target, source) is True
    assert (target / "auth.json").read_text(encoding="utf-8") == '{"access_token": "shh"}'
    config = (target / "config.toml").read_text(encoding="utf-8")
    assert "gpt-5.5" in config
    assert "deny.sh" not in config
    assert not (target / "hooks.json").exists()


def test_prepare_isolated_agent_home_reports_nothing_to_copy(tmp_path: Path):
    empty_source = tmp_path / "empty-home"
    empty_source.mkdir()
    target = tmp_path / "isolated-home"
    assert prepare_isolated_agent_home(target, empty_source) is False


def test_isolated_home_is_only_used_when_enabled_and_has_something_to_copy(
    tmp_path: Path, monkeypatch
):
    real_home = tmp_path / "home"
    (real_home / ".codex").mkdir(parents=True)
    (real_home / ".codex" / "auth.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("HOME", str(real_home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    workspace = tmp_path / "coding-sessions" / "ses-1"
    workspace.mkdir(parents=True)

    off = SubprocessCodingAgentRunner("codex", Settings(**BASE_SETTINGS))
    assert "CODEX_HOME" not in off._environment(workspace)

    on = SubprocessCodingAgentRunner(
        "codex", Settings(**{**BASE_SETTINGS, "coding_agent_isolated_home": True})
    )
    isolated_env = on._environment(workspace)
    isolated_dir = on._isolated_home_dir(workspace)
    assert isolated_env["CODEX_HOME"] == str(isolated_dir)
    assert (isolated_dir / "auth.json").exists()
    # It lives beside the worktree, not inside it -- a governed session's diff and scope
    # checks read the worktree only.
    assert isolated_dir.parent == workspace.parent
    assert not isolated_dir.is_relative_to(workspace)


def test_the_simulated_note_uses_the_target_language_comment_form(tmp_path: Path):
    # An amended Python or TypeScript file still has to parse: the target repository's
    # own checks are the verification the session runs.
    python_note = MockCodingAgentRunner._simulated_note("services/billing/retry.py", "do a thing")
    assert all(line.startswith("# ") for line in python_note.strip().splitlines())
    compile(python_note, "note.py", "exec")
    tsx_note = MockCodingAgentRunner._simulated_note("web/reports/Table.tsx", "do a thing")
    assert all(line.startswith("// ") for line in tsx_note.strip().splitlines())
    html_note = MockCodingAgentRunner._simulated_note("src/templates/page.html", "do a thing")
    assert all(
        line.startswith("<!-- ") and line.endswith(" -->")
        for line in html_note.strip().splitlines()
    )
