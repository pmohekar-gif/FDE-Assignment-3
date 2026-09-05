from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from warrant.db import Database
from warrant.repository import (
    CodeIntelligenceService,
    CodeSource,
    ContextBudget,
    LocalRepositoryProvider,
    RepositoryError,
    module_for_path,
    package_for_module,
    resolve_import,
)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "approval.py").write_text(
        "def enforce_delegation_approval(decision):\n"
        "    if decision == 'REQUIRE_APPROVAL':\n"
        "        return 'human gate'\n"
        "    return 'policy warrant'\n"
    )
    (root / ".env").write_text("TOKEN=must-not-index\n")
    (root / "secret.pem").write_text("must-not-index\n")
    (root / "binary.py").write_bytes(b"\x00binary")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "ignored.js").write_text("approval secret")
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.test")
    git(root, "config", "user.name", "Test")
    git(root, "add", "src/approval.py")
    git(root, "commit", "-qm", "initial")
    return root


def test_local_repository_rejects_traversal_secrets_binaries_and_symlink_escape(tmp_path):
    root = repository(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("secret = True\n")
    os.symlink(outside, root / "src" / "escape.py")
    provider = LocalRepositoryProvider(root)

    assert provider.list_files() == ["src/approval.py"]
    assert "human gate" in provider.read_file("src/approval.py")
    for path in ("../outside.py", ".env", "secret.pem", "binary.py", "src/escape.py"):
        with pytest.raises(RepositoryError):
            provider.read_file(path)


def test_index_is_revision_aware_and_code_answers_have_real_lines(tmp_path):
    root = repository(tmp_path)
    db = Database(tmp_path / "index.db")
    db.migrate()
    service = CodeIntelligenceService(db, LocalRepositoryProvider(root))

    first = service.query("Where is delegation approval enforced?")
    second = service.query("Where is delegation approval enforced?")
    assert first.sources[0].path == "src/approval.py"
    assert first.sources[0].start_line >= 1
    assert "def enforce_delegation_approval" in first.sources[0].snippet
    assert first.cached_index is False
    assert second.cached_index is True

    path = root / "src" / "approval.py"
    path.write_text(path.read_text() + "\ndef approval_audit():\n    return True\n")
    git(root, "add", "src/approval.py")
    git(root, "commit", "-qm", "change revision")
    changed = service.query("Where is approval audit implemented?")
    assert changed.revision != first.revision
    assert changed.cached_index is False


def non_git_repository(tmp_path: Path) -> Path:
    """A checkout with a .gitignore and NO .git — the live path for this deployment."""
    root = tmp_path / "nogit"
    (root / "pkg").mkdir(parents=True)
    (root / ".gitignore").write_text(
        "# ignored by the project\nignored_secret.py\nlogs/\ntmp_*.py\n!tmp_keep.py\n"
    )
    (root / "ignored_secret.py").write_text("PASSWORD = 'hunter2'\n")
    (root / "tmp_drop.py").write_text("dropped = True\n")
    (root / "tmp_keep.py").write_text("kept = True\n")
    (root / "logs").mkdir()
    (root / "logs" / "audit.py").write_text("SECRET_KEY = 'logged-secret-value'\n")
    (root / "pkg" / ".gitignore").write_text("nested_ignored.py\n")
    (root / "pkg" / "nested_ignored.py").write_text("API_KEY = 'nested-secret-value'\n")
    (root / "pkg" / "policy.py").write_text(
        "def evaluate_policy(context):\n    return 'REQUIRE_APPROVAL'\n"
    )
    (root / "pkg" / "service.py").write_text(
        "from .policy import evaluate_policy\n\n\ndef decide(context):\n"
        "    return evaluate_policy(context)\n"
    )
    return root


def test_gitignore_is_enforced_when_the_checkout_has_no_git_directory(tmp_path):
    root = non_git_repository(tmp_path)
    provider = LocalRepositoryProvider(root)

    assert provider.is_git_repository() is False
    assert provider.ignore_source() == "gitignore"
    listed = provider.list_files()
    assert "ignored_secret.py" not in listed
    assert "logs/audit.py" not in listed
    assert "pkg/nested_ignored.py" not in listed
    assert "tmp_drop.py" not in listed
    assert "tmp_keep.py" in listed, "an unignore rule (!) must be honoured"
    assert {"pkg/policy.py", "pkg/service.py"} <= set(listed)
    for ignored in ("ignored_secret.py", "logs/audit.py", "pkg/nested_ignored.py", "tmp_drop.py"):
        with pytest.raises(RepositoryError):
            provider.read_file(ignored)
    assert provider.search_text(["hunter2", "nested-secret-value"]) == []


def test_ignore_source_names_the_guarantee_that_is_actually_active(tmp_path):
    assert LocalRepositoryProvider(non_git_repository(tmp_path)).ignore_source() == "gitignore"
    assert LocalRepositoryProvider(repository(tmp_path)).ignore_source() == "git"
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "app.py").write_text("value = 1\n")
    assert LocalRepositoryProvider(plain).ignore_source() == "denylist"


def test_index_entries_carry_a_module_and_the_status_exposes_the_ignore_source(tmp_path):
    root = non_git_repository(tmp_path)
    db = Database(tmp_path / "module-index.db")
    db.migrate()
    service = CodeIntelligenceService(db, LocalRepositoryProvider(root))

    refreshed = service.refresh()
    assert refreshed["ignore_source"] == "gitignore"
    assert refreshed["module_count"] >= 2
    assert refreshed["dependency_edges"] >= 1
    entries, dependents = service._load_index(refreshed["revision"])
    modules = {entry["path"]: entry["module"] for entry in entries}
    assert modules["pkg/policy.py"] == "pkg.policy"
    assert modules["pkg/service.py"] == "pkg.service"
    assert all("package" in entry for entry in entries)
    assert dependents["pkg.policy"] == ["pkg/service.py"]
    status = service.status()
    assert status["ignore_source"] == "gitignore"
    assert status["context_budget"]["max_snippets"] >= 1


def test_module_and_import_derivation_follow_language_conventions():
    assert module_for_path("src/warrant/policy.py") == "warrant.policy"
    assert module_for_path("src/warrant/__init__.py") == "warrant"
    assert module_for_path("web/reports/EmptyState.tsx") == "web/reports/EmptyState"
    assert module_for_path("src/lib/index.ts") == "lib"
    assert package_for_module("warrant.policy") == "warrant"
    assert package_for_module("web/reports/EmptyState") == "web/reports"
    assert package_for_module("policy") == ""

    known = {"warrant.policy", "warrant.service", "lib/util"}
    assert resolve_import(".policy", "warrant.service", known) == "warrant.policy"
    assert resolve_import("warrant.policy.evaluate_policy", "x", known) == "warrant.policy"
    assert resolve_import("./util", "lib/index", known) == "lib/util"
    assert resolve_import("os", "warrant.service", known) is None


def test_impact_answers_come_from_real_importer_edges_not_text_hits(tmp_path):
    root = non_git_repository(tmp_path)
    db = Database(tmp_path / "impact.db")
    db.migrate()
    service = CodeIntelligenceService(db, LocalRepositoryProvider(root))

    answer = service.query("What depends on evaluate_policy?", limit=8)
    assert answer.dependency_resolved is True
    edges = {(source.path, source.edge) for source in answer.sources}
    assert ("pkg/policy.py", "definition") in edges
    assert any(path == "pkg/service.py" and edge != "text" for path, edge in edges)
    definition = next(item for item in answer.sources if item.edge == "definition")
    importer = next(item for item in answer.sources if item.path == "pkg/service.py")
    assert definition.score > importer.score > 1
    assert "def evaluate_policy" in definition.snippet
    assert "pkg/service.py" in answer.answer
    assert answer.ignore_source == "gitignore"


def test_impact_admits_when_a_symbol_cannot_be_resolved_in_the_graph(tmp_path):
    root = non_git_repository(tmp_path)
    db = Database(tmp_path / "unresolved.db")
    db.migrate()
    service = CodeIntelligenceService(db, LocalRepositoryProvider(root))

    answer = service.query("What would break if I change never_defined_symbol?")
    assert answer.dependency_resolved is False
    assert "could not resolve" in answer.answer
    assert "cannot give you a dependency graph" in answer.answer
    assert "impact surface" not in answer.answer
    assert answer.sources == ()

    # With text hits present the admission must still precede the citations.
    partial = service.query("What depends on REQUIRE_APPROVAL?")
    assert partial.dependency_resolved is False
    assert partial.sources
    assert "could not resolve" in partial.answer
    assert "undifferentiated text matches" in partial.answer


def test_context_budget_caps_snippet_count_and_total_characters():
    sources = tuple(
        CodeSource(f"file{index}.py", 1, 5, "reason", "x" * 400, float(index))
        for index in range(10)
    )
    kept, truncated = ContextBudget(max_snippets=3, max_total_chars=10_000).apply(sources)
    assert len(kept) == 3
    assert truncated is True

    kept, truncated = ContextBudget(max_snippets=10, max_total_chars=1_000).apply(sources)
    assert sum(len(item.snippet) for item in kept) <= 1_000
    assert truncated is True

    kept, truncated = ContextBudget(max_snippets=20, max_total_chars=100_000).apply(sources)
    assert len(kept) == 10
    assert truncated is False


def test_repository_query_respects_the_aggregate_context_budget(tmp_path, monkeypatch):
    root = non_git_repository(tmp_path)
    db = Database(tmp_path / "budget.db")
    db.migrate()
    service = CodeIntelligenceService(db, LocalRepositoryProvider(root))
    monkeypatch.setattr(service, "BUDGET", ContextBudget(max_snippets=1, max_total_chars=40))

    answer = service.query("Where is evaluate_policy implemented?")
    assert len(answer.sources) == 1
    assert sum(len(item.snippet) for item in answer.sources) <= 40
    assert answer.truncated is True
    assert "truncated by the context budget" in answer.answer
