from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from .db import Database
from .providers import LLMProvider, ProviderError
from .security import redact_secrets


class RepositoryError(RuntimeError):
    """A typed, user-safe repository capability failure."""


@dataclass(frozen=True)
class RepositoryFile:
    path: str
    language: str
    size: int
    symbols: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()
    module: str = ""
    package: str = ""


@dataclass(frozen=True)
class CodeSource:
    path: str
    start_line: int
    end_line: int
    reason: str
    snippet: str
    score: float = 0.0
    module: str = ""
    edge: str = "text"


@dataclass(frozen=True)
class ContextBudget:
    """Aggregate limits applied to every grounded answer, per query."""

    max_snippets: int = 12
    max_total_chars: int = 12_000

    def apply(self, sources: Sequence[CodeSource]) -> tuple[tuple[CodeSource, ...], bool]:
        kept: list[CodeSource] = []
        total = 0
        truncated = False
        for source in sources:
            if len(kept) >= self.max_snippets:
                truncated = True
                break
            remaining = self.max_total_chars - total
            if remaining <= 0:
                truncated = True
                break
            snippet = source.snippet
            if len(snippet) > remaining:
                snippet = snippet[:remaining]
                truncated = True
            total += len(snippet)
            kept.append(source if snippet == source.snippet else replace_snippet(source, snippet))
        return tuple(kept), truncated


def replace_snippet(source: CodeSource, snippet: str) -> CodeSource:
    return CodeSource(
        path=source.path,
        start_line=source.start_line,
        end_line=source.end_line,
        reason=source.reason,
        snippet=snippet,
        score=source.score,
        module=source.module,
        edge=source.edge,
    )


@dataclass(frozen=True)
class CodeAnswer:
    answer: str
    repository_id: str
    revision: str
    sources: tuple[CodeSource, ...]
    cached_index: bool
    ignore_source: str = "denylist"
    truncated: bool = False
    dependency_resolved: bool | None = None
    modules: tuple[str, ...] = field(default_factory=tuple)
    synthesized: bool = False


class RepositoryProvider(Protocol):
    repository_id: str

    def get_repository_metadata(self) -> dict[str, Any]: ...

    def get_current_revision(self) -> str: ...

    def list_files(self) -> list[str]: ...

    def read_file(self, path: str) -> str: ...

    def search_text(self, terms: list[str], limit: int = 20) -> list[CodeSource]: ...

    def get_diff(self, base_revision: str, worktree: Path | None = None) -> str: ...


LANGUAGES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".html": "HTML",
    ".css": "CSS",
    ".sql": "SQL",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".md": "Markdown",
    ".json": "JSON",
    ".sh": "Shell",
}

EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".runtime",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "vendor",
    "__pycache__",
    ".next",
    "target",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".uv-cache",
}
SECRET_NAMES = {
    "id_rsa",
    "id_ed25519",
    "credentials",
    "credentials.json",
    "secrets.json",
    ".npmrc",
    ".pypirc",
}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}

IGNORE_FILE = ".gitignore"
SNIPPET_CONTEXT_BEFORE = 2
SNIPPET_CONTEXT_AFTER = 3
MAX_SNIPPET_CHARS = 3_000
PYTHON_SUFFIXES = {".py", ".pyi"}
SCRIPT_SUFFIXES = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}


@dataclass(frozen=True)
class IgnoreRule:
    """One compiled `.gitignore` line, relative to the directory that declared it."""

    base: str
    pattern: re.Pattern[str]
    negated: bool
    directory_only: bool


def translate_ignore_pattern(pattern: str) -> str:
    """Translate a gitignore glob into an unanchored regex body (stdlib only)."""
    parts: list[str] = []
    index = 0
    length = len(pattern)
    while index < length:
        char = pattern[index]
        if char == "*":
            if pattern[index : index + 3] == "**/":
                parts.append("(?:.*/)?")
                index += 3
                continue
            if pattern[index : index + 2] == "**":
                parts.append(".*")
                index += 2
                continue
            parts.append("[^/]*")
            index += 1
            continue
        if char == "?":
            parts.append("[^/]")
            index += 1
            continue
        if char == "[":
            close = pattern.find("]", index + 2)
            if close == -1:
                parts.append(re.escape(char))
                index += 1
                continue
            body = pattern[index + 1 : close]
            if body.startswith("!"):
                body = f"^{body[1:]}"
            parts.append(f"[{body}]")
            index = close + 1
            continue
        if char == "\\" and index + 1 < length:
            parts.append(re.escape(pattern[index + 1]))
            index += 2
            continue
        parts.append(re.escape(char))
        index += 1
    return "".join(parts)


def parse_ignore_file(text: str, base: str) -> tuple[IgnoreRule, ...]:
    """Parse one `.gitignore` body into ordered rules; later rules win."""
    rules: list[IgnoreRule] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        line = re.sub(r"(?<!\\)\s+$", "", raw)
        if not line:
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:]
        directory_only = line.endswith("/")
        line = line.rstrip("/")
        if line.startswith("/"):
            line = line[1:]
        if not line:
            continue
        body = translate_ignore_pattern(line)
        expression = f"^{body}$" if "/" in line else f"^(?:.*/)?{body}$"
        try:
            compiled = re.compile(expression)
        except re.error:
            continue
        rules.append(IgnoreRule(base, compiled, negated, directory_only))
    return tuple(rules)


class IgnoreMatcher:
    """Last-match-wins evaluation of the cumulative rules that apply to a path."""

    def __init__(self, rules: Sequence[IgnoreRule]) -> None:
        self.rules = tuple(rules)

    def __bool__(self) -> bool:
        return bool(self.rules)

    def is_ignored(self, relative: str, is_dir: bool) -> bool:
        decision = False
        for rule in self.rules:
            if rule.directory_only and not is_dir:
                continue
            candidate = relative
            if rule.base:
                prefix = f"{rule.base}/"
                if not relative.startswith(prefix):
                    continue
                candidate = relative[len(prefix) :]
            if rule.pattern.match(candidate):
                decision = not rule.negated
        return decision


def build_snippet(lines: Sequence[str], number: int) -> tuple[int, int, str]:
    """Return the real, redacted excerpt around a real line number."""
    start = max(1, number - SNIPPET_CONTEXT_BEFORE)
    end = min(len(lines), number + SNIPPET_CONTEXT_AFTER)
    body = "\n".join(f"{index}: {lines[index - 1]}" for index in range(start, end + 1))
    return start, end, redact_secrets(body)[:MAX_SNIPPET_CHARS]


def module_for_path(relative: str) -> str:
    """Derive the import module/package identifier from the path and language convention."""
    path = PurePosixPath(relative)
    parts = list(path.parts)
    if not parts:
        return ""
    suffix = path.suffix.lower()
    if suffix in PYTHON_SUFFIXES:
        parts[-1] = path.stem
        if parts[-1] == "__init__":
            parts.pop()
        if parts and parts[0] == "src":
            parts.pop(0)
        return ".".join(parts)
    if suffix in SCRIPT_SUFFIXES:
        parts[-1] = path.stem
        if parts[-1] == "index":
            parts.pop()
        if parts and parts[0] == "src":
            parts.pop(0)
        return "/".join(parts)
    return path.stem


def package_for_module(module: str) -> str:
    for separator in (".", "/"):
        if separator in module:
            return module.rsplit(separator, 1)[0]
    return ""


def resolve_import(raw: str, importer_module: str, known: set[str]) -> str | None:
    """Resolve one extracted import string to an indexed module, or None."""
    if not raw:
        return None
    if raw.startswith("."):
        if "/" in raw:
            rest = raw
            depth = 0
            while rest.startswith("./") or rest.startswith("../"):
                if rest.startswith("./"):
                    rest = rest[2:]
                else:
                    rest = rest[3:]
                    depth += 1
            base = importer_module.split("/")[:-1]
            if depth:
                base = base[: max(0, len(base) - depth)]
            candidate = "/".join([*base, rest]).strip("/")
            return candidate if candidate in known else None
        dots = len(raw) - len(raw.lstrip("."))
        rest = raw[dots:]
        base = importer_module.split(".")[:-1]
        if dots > 1:
            base = base[: max(0, len(base) - (dots - 1))]
        pieces = [*base, rest] if rest else base
        candidate = ".".join(piece for piece in pieces if piece)
        return candidate if candidate in known else None
    for separator in (".", "/"):
        if separator not in raw and raw not in known:
            continue
        parts = raw.split(separator)
        while parts:
            candidate = separator.join(parts)
            if candidate in known:
                return candidate
            parts.pop()
    return raw if raw in known else None


class LocalRepositoryProvider:
    def __init__(
        self,
        root: Path,
        repository_id: str = "local",
        max_file_bytes: int = 512_000,
        max_results: int = 20,
    ) -> None:
        self.root = root.resolve()
        self.repository_id = repository_id
        self.max_file_bytes = max_file_bytes
        self.max_results = max_results
        self._is_git: bool | None = None
        self._ignore_cache: dict[tuple[str, int], tuple[IgnoreRule, ...]] = {}
        if not self.root.is_dir():
            raise RepositoryError("configured repository root is unavailable")

    @staticmethod
    def _git(args: list[str], cwd: Path, timeout: int = 10) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=cwd,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RepositoryError(f"git unavailable: {type(exc).__name__}") from exc

    def is_git_repository(self) -> bool:
        if self._is_git is None:
            result = self._git(["rev-parse", "--is-inside-work-tree"], self.root)
            self._is_git = result.returncode == 0 and result.stdout.strip() == "true"
        return self._is_git

    def _directory_ignore_rules(
        self, relative_dir: str, inherited: tuple[IgnoreRule, ...]
    ) -> tuple[IgnoreRule, ...]:
        base = self.root / relative_dir if relative_dir else self.root
        candidate = base / IGNORE_FILE
        try:
            stamp = candidate.stat().st_mtime_ns
        except OSError:
            return inherited
        key = (relative_dir, stamp)
        own = self._ignore_cache.get(key)
        if own is None:
            try:
                own = parse_ignore_file(
                    candidate.read_text("utf-8", errors="replace"), relative_dir
                )
            except OSError:
                return inherited
            self._ignore_cache[key] = own
        return (*inherited, *own)

    def has_ignore_file(self) -> bool:
        if (self.root / IGNORE_FILE).is_file():
            return True
        for current, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = [
                directory
                for directory in dirs
                if directory not in EXCLUDED_DIRS and not (Path(current) / directory).is_symlink()
            ]
            if IGNORE_FILE in files:
                return True
        return False

    def ignore_source(self) -> str:
        """Name the ignore guarantee that is actually enforced on this checkout."""
        if self.is_git_repository():
            return "git"
        if self.has_ignore_file():
            return "gitignore"
        return "denylist"

    def is_ignored(self, value: str) -> bool:
        """True when the path, or any ancestor directory, is excluded by a `.gitignore`."""
        parts = [part for part in PurePosixPath(value).parts if part not in {"", "."}]
        if not parts:
            return False
        rules = self._directory_ignore_rules("", ())
        prefix = ""
        for index, part in enumerate(parts):
            candidate = f"{prefix}{part}" if prefix else part
            is_dir = index < len(parts) - 1
            if IgnoreMatcher(rules).is_ignored(candidate, is_dir):
                return True
            if is_dir:
                rules = self._directory_ignore_rules(candidate, rules)
                prefix = f"{candidate}/"
        return False

    def get_repository_metadata(self) -> dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "root": str(self.root),
            "revision": self.get_current_revision(),
            "git": self.is_git_repository(),
            "ignore_source": self.ignore_source(),
            "file_count": len(self.list_files()),
        }

    def get_current_revision(self) -> str:
        result = self._git(["rev-parse", "HEAD"], self.root)
        if result.returncode == 0:
            return result.stdout.strip()
        digest = hashlib.sha256()
        for relative in self.list_files():
            path = self.root / relative
            stat = path.stat()
            digest.update(relative.encode())
            digest.update(str(stat.st_size).encode())
            digest.update(str(stat.st_mtime_ns).encode())
        return f"tree-{digest.hexdigest()[:24]}"

    def _allowed_relative(self, relative: Path) -> bool:
        if not relative.parts or any(part in EXCLUDED_DIRS for part in relative.parts):
            return False
        name = relative.name.lower()
        if name == ".env" or name.startswith(".env."):
            return False
        if name in SECRET_NAMES or relative.suffix.lower() in SECRET_SUFFIXES:
            return False
        if name.endswith((".min.js", ".map", ".lock")):
            return False
        return relative.suffix.lower() in LANGUAGES or name in {
            "dockerfile",
            "makefile",
            "readme",
            "license",
        }

    def _resolve(self, value: str) -> Path:
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise RepositoryError("repository path traversal is not allowed")
        if not self._allowed_relative(relative):
            raise RepositoryError("repository path is excluded")
        if not self.is_git_repository() and self.is_ignored(relative.as_posix()):
            raise RepositoryError("repository path is excluded by .gitignore")
        candidate = (self.root / relative).resolve(strict=True)
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise RepositoryError("repository symlink escape is not allowed") from exc
        if not candidate.is_file():
            raise RepositoryError("repository path is not a file")
        if candidate.stat().st_size > self.max_file_bytes:
            raise RepositoryError("repository file exceeds the configured size limit")
        return candidate

    def list_files(self) -> list[str]:
        candidates: list[str]
        if self.is_git_repository():
            result = self._git(
                ["ls-files", "--cached", "--others", "--exclude-standard"], self.root
            )
            candidates = result.stdout.splitlines() if result.returncode == 0 else []
        else:
            candidates = []
            inherited_by_dir: dict[str, tuple[IgnoreRule, ...]] = {"": ()}
            for current, dirs, files in os.walk(self.root, followlinks=False):
                current_path = Path(current)
                relative_dir = current_path.relative_to(self.root).as_posix()
                relative_dir = "" if relative_dir == "." else relative_dir
                rules = self._directory_ignore_rules(
                    relative_dir, inherited_by_dir.get(relative_dir, ())
                )
                matcher = IgnoreMatcher(rules)
                kept: list[str] = []
                for directory in sorted(dirs):
                    if directory in EXCLUDED_DIRS or (current_path / directory).is_symlink():
                        continue
                    child = f"{relative_dir}/{directory}" if relative_dir else directory
                    if matcher.is_ignored(child, True):
                        continue
                    inherited_by_dir[child] = rules
                    kept.append(directory)
                dirs[:] = kept
                for name in sorted(files):
                    relative_name = f"{relative_dir}/{name}" if relative_dir else name
                    if matcher.is_ignored(relative_name, False):
                        continue
                    candidates.append(relative_name)
        allowed: list[str] = []
        for value in sorted(set(candidates)):
            relative = Path(value)
            if not self._allowed_relative(relative):
                continue
            try:
                path = self._resolve(value)
            except (OSError, RepositoryError):
                continue
            if path.stat().st_size > self.max_file_bytes:
                continue
            try:
                sample = path.read_bytes()[:8192]
                if b"\x00" in sample:
                    continue
                sample.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            allowed.append(relative.as_posix())
        return allowed

    def read_file(self, path: str) -> str:
        raw = self._resolve(path).read_bytes()
        if b"\x00" in raw[:8192]:
            raise RepositoryError("binary repository files are excluded")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RepositoryError("non-UTF-8 repository files are excluded") from exc

    def search_text(self, terms: list[str], limit: int = 20) -> list[CodeSource]:
        clean = [term.casefold() for term in terms if len(term) > 1][:12]
        if not clean:
            return []
        matches: list[CodeSource] = []
        for relative in self.list_files():
            try:
                lines = self.read_file(relative).splitlines()
            except RepositoryError:
                continue
            path_score = sum(3 for term in clean if term in relative.casefold())
            for number, line in enumerate(lines, start=1):
                line_lower = line.casefold()
                hits = sum(1 for term in clean if term in line_lower)
                if not hits:
                    continue
                symbol_bonus = (
                    6
                    if re.match(r"\s*(?:class|def|async def|function|export|const|let|var)\b", line)
                    else 0
                )
                code_bonus = 2 if Path(relative).suffix in {".py", ".ts", ".tsx", ".js"} else 0
                template_penalty = 2 if "/templates/" in f"/{relative}" else 0
                test_penalty = 6 if relative.startswith("tests/") else 0
                start, end, snippet = build_snippet(lines, number)
                matches.append(
                    CodeSource(
                        path=relative,
                        start_line=start,
                        end_line=end,
                        reason="Matched repository text or symbol",
                        snippet=snippet,
                        score=float(
                            hits * 2
                            + path_score
                            + symbol_bonus
                            + code_bonus
                            - template_penalty
                            - test_penalty
                        ),
                        module=module_for_path(relative),
                        edge="text",
                    )
                )
        matches.sort(key=lambda item: (-item.score, item.path, item.start_line))
        diverse: list[CodeSource] = []
        per_file: dict[str, int] = {}
        for match in matches:
            if per_file.get(match.path, 0) >= 2:
                continue
            diverse.append(match)
            per_file[match.path] = per_file.get(match.path, 0) + 1
            if len(diverse) >= min(limit, self.max_results):
                break
        return diverse

    def get_diff(self, base_revision: str, worktree: Path | None = None) -> str:
        target = (worktree or self.root).resolve()
        result = self._git(["diff", "--no-ext-diff", "--binary", base_revision, "--"], target, 30)
        if result.returncode not in {0, 1}:
            raise RepositoryError("git could not generate the coding-session diff")
        return result.stdout


class CodeIntelligenceService:
    STOP_WORDS = {
        "a",
        "an",
        "and",
        "are",
        "does",
        "how",
        "if",
        "in",
        "is",
        "it",
        "of",
        "the",
        "this",
        "to",
        "what",
        "where",
        "which",
        "would",
    }
    IMPACT_TERMS = (
        "depend",
        "dependent",
        "dependents",
        "dependency",
        "impact",
        "affected",
        "break",
        "breaks",
        "caller",
        "callers",
        "call site",
        "call sites",
        "blast radius",
    )
    SYMBOL_TARGET_PATTERNS = (
        r"depends?\s+(?:up)?on\s+([A-Za-z_][\w.]*)",
        r"dependents?\s+of\s+([A-Za-z_][\w.]*)",
        r"dependenc(?:y|ies)\s+of\s+([A-Za-z_][\w.]*)",
        r"callers?\s+of\s+([A-Za-z_][\w.]*)",
        r"call\s+sites?\s+(?:of|for)\s+([A-Za-z_][\w.]*)",
        r"break\s+if\s+(?:i|we|you)\s+\w+\s+([A-Za-z_][\w.]*)",
        r"(?:chang(?:e|ed|ing)|modif(?:y|ied|ying)|remov(?:e|ed|ing)|renam(?:e|ed|ing))"
        r"\s+(?:the\s+)?([A-Za-z_][\w.]*)",
        r"impact\s+of\s+(?:changing\s+)?([A-Za-z_][\w.]*)",
        r"affected\s+by\s+([A-Za-z_][\w.]*)",
    )
    BUDGET = ContextBudget()

    def __init__(
        self, db: Database, provider: RepositoryProvider, llm: LLMProvider | None = None
    ) -> None:
        self.db = db
        self.provider = provider
        self.llm = llm

    def _ignore_source(self) -> str:
        resolver = getattr(self.provider, "ignore_source", None)
        return str(resolver()) if callable(resolver) else "denylist"

    def _read_lines(self, path: str) -> list[str]:
        try:
            return self.provider.read_file(path).splitlines()
        except RepositoryError:
            return []

    @staticmethod
    def _symbols(text: str) -> tuple[str, ...]:
        patterns = (
            r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)",
            r"^\s*class\s+([A-Za-z_]\w*)",
            r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)",
            r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=",
        )
        values: list[str] = []
        for line in text.splitlines():
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    values.append(match.group(1))
        return tuple(dict.fromkeys(values))

    @staticmethod
    def _imports(text: str) -> tuple[str, ...]:
        patterns = (
            r"^\s*(?:from|import)\s+([.\w]+)",
            r"^\s*import\s+.*?\s+from\s+['\"]([^'\"]+)",
            r"require\(['\"]([^'\"]+)",
        )
        values: list[str] = []
        for line in text.splitlines():
            for pattern in patterns:
                match = re.search(pattern, line)
                if match:
                    values.append(match.group(1))
        return tuple(dict.fromkeys(values))

    def refresh(self, force: bool = False) -> dict[str, Any]:
        revision = self.provider.get_current_revision()
        cached = self.db.one(
            "SELECT * FROM repository_indexes WHERE repository_id=? AND revision=?",
            (self.provider.repository_id, revision),
        )
        if cached and not force:
            metadata = Database.loads(cached["metadata_json"], {})
            return {**metadata, "cached": True, "indexed_at": cached["indexed_at"]}
        entries: list[dict[str, Any]] = []
        for relative in self.provider.list_files():
            try:
                text = self.provider.read_file(relative)
            except RepositoryError:
                continue
            module = module_for_path(relative)
            entries.append(
                {
                    "path": relative,
                    "language": LANGUAGES.get(Path(relative).suffix.lower(), "Text"),
                    "size": len(text.encode()),
                    "symbols": self._symbols(text),
                    "imports": self._imports(text),
                    "module": module,
                    "package": package_for_module(module),
                }
            )
        dependents = self.build_dependency_graph(entries)
        metadata = {
            "repository_id": self.provider.repository_id,
            "revision": revision,
            "root": str(getattr(self.provider, "root", "configured provider")),
            "file_count": len(entries),
            "symbol_count": sum(len(item["symbols"]) for item in entries),
            "module_count": len({item["module"] for item in entries if item["module"]}),
            "dependency_edges": sum(len(value) for value in dependents.values()),
            "ignore_source": self._ignore_source(),
        }
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "INSERT OR REPLACE INTO repository_indexes VALUES (?,?,?,?,?,?)",
            (
                self.provider.repository_id,
                revision,
                metadata["root"],
                Database.dumps(metadata),
                Database.dumps({"entries": entries, "dependents": dependents}),
                now,
            ),
        )
        return {**metadata, "cached": False, "indexed_at": now}

    @staticmethod
    def build_dependency_graph(entries: Sequence[dict[str, Any]]) -> dict[str, list[str]]:
        """Reverse-dependency edges: module -> paths of the files that import it."""
        known = {str(entry.get("module", "")) for entry in entries if entry.get("module")}
        dependents: dict[str, list[str]] = {}
        for entry in entries:
            module = str(entry.get("module", ""))
            for raw in entry.get("imports", ()):
                target = resolve_import(str(raw), module, known)
                if not target or target == module:
                    continue
                bucket = dependents.setdefault(target, [])
                if entry["path"] not in bucket:
                    bucket.append(entry["path"])
        return {key: sorted(value) for key, value in sorted(dependents.items())}

    def _load_index(self, revision: str) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
        row = self.db.one(
            "SELECT entries_json FROM repository_indexes WHERE repository_id=? AND revision=?",
            (self.provider.repository_id, revision),
        )
        if not row:
            return [], {}
        payload = Database.loads(row["entries_json"], [])
        if isinstance(payload, dict):
            entries = list(payload.get("entries", []))
            dependents = dict(payload.get("dependents", {}))
        else:
            entries = list(payload)
            dependents = {}
        for entry in entries:
            entry.setdefault("symbols", [])
            entry.setdefault("imports", [])
            if not entry.get("module"):
                entry["module"] = module_for_path(str(entry.get("path", "")))
            entry.setdefault("package", package_for_module(entry["module"]))
        if not dependents and entries:
            dependents = self.build_dependency_graph(entries)
        return entries, dependents

    def status(self) -> dict[str, Any]:
        revision = self.provider.get_current_revision()
        row = self.db.one(
            "SELECT * FROM repository_indexes WHERE repository_id=? AND revision=?",
            (self.provider.repository_id, revision),
        )
        if not row:
            return {
                "repository_id": self.provider.repository_id,
                "revision": revision,
                "indexed": False,
                "ignore_source": self._ignore_source(),
                "context_budget": {
                    "max_snippets": self.BUDGET.max_snippets,
                    "max_total_chars": self.BUDGET.max_total_chars,
                },
                "stale": bool(
                    self.db.one(
                        "SELECT 1 AS present FROM repository_indexes WHERE repository_id=?",
                        (self.provider.repository_id,),
                    )
                ),
            }
        return {
            **Database.loads(row["metadata_json"], {}),
            "indexed": True,
            "stale": False,
            "indexed_at": row["indexed_at"],
            "ignore_source": self._ignore_source(),
            "context_budget": {
                "max_snippets": self.BUDGET.max_snippets,
                "max_total_chars": self.BUDGET.max_total_chars,
            },
        }

    def wants_dependency_graph(self, query: str) -> bool:
        lowered = query.casefold()
        return any(term in lowered for term in self.IMPACT_TERMS)

    def target_symbol(self, query: str, entries: Sequence[dict[str, Any]]) -> str | None:
        """Resolve the question's subject to a symbol that really exists in the index."""
        known: dict[str, str] = {}
        for entry in entries:
            for name in entry.get("symbols", ()):
                known.setdefault(str(name).casefold(), str(name))
        if not known:
            return None
        for pattern in self.SYMBOL_TARGET_PATTERNS:
            match = re.search(pattern, query, re.I)
            if not match:
                continue
            candidate = match.group(1).strip(".").split(".")[-1]
            resolved = known.get(candidate.casefold())
            if resolved:
                return resolved
        best: str | None = None
        for token in re.findall(r"[A-Za-z_]\w*", query):
            if len(token) < 4 or token.casefold() in self.STOP_WORDS:
                continue
            resolved = known.get(token.casefold())
            if resolved and (best is None or len(resolved) > len(best)):
                best = resolved
        return best

    def dependency_sources(
        self,
        symbol: str,
        entries: Sequence[dict[str, Any]],
        dependents: dict[str, list[str]],
    ) -> tuple[list[CodeSource], list[str]]:
        """Real definition, importer and call-site edges for a resolved symbol."""
        definitions = [entry for entry in entries if symbol in entry.get("symbols", ())]
        if not definitions:
            folded = symbol.casefold()
            definitions = [
                entry
                for entry in entries
                if any(str(name).casefold() == folded for name in entry.get("symbols", ()))
            ]
        if not definitions:
            return [], []
        definition_pattern = re.compile(
            r"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|function|const|let|var)\s+"
            rf"{re.escape(symbol)}\b"
        )
        usage_pattern = re.compile(rf"\b{re.escape(symbol)}\b")
        invocation_pattern = re.compile(rf"\b{re.escape(symbol)}\s*\(")
        sources: list[CodeSource] = []
        modules: list[str] = []
        for entry in definitions:
            module = str(entry.get("module", ""))
            if module and module not in modules:
                modules.append(module)
            lines = self._read_lines(entry["path"])
            for number, line in enumerate(lines, start=1):
                if not definition_pattern.match(line):
                    continue
                start, end, snippet = build_snippet(lines, number)
                sources.append(
                    CodeSource(
                        path=entry["path"],
                        start_line=start,
                        end_line=end,
                        reason=f"Definition of {symbol}",
                        snippet=snippet,
                        score=100.0,
                        module=module,
                        edge="definition",
                    )
                )
                break
        importers: list[str] = []
        for module in modules:
            importers.extend(dependents.get(module, []))
        definition_paths = {entry["path"] for entry in definitions}
        importers = [path for path in dict.fromkeys(importers) if path not in definition_paths]
        primary_module = modules[0] if modules else ""
        needles = [*modules, *(part for part in (primary_module.split(".")[-1],) if part)]
        by_path = {str(entry.get("path", "")): entry for entry in entries}
        for path in importers:
            lines = self._read_lines(path)
            if not lines:
                continue
            module = str(by_path.get(path, {}).get("module", "")) or module_for_path(path)
            import_line = next(
                (
                    number
                    for number, line in enumerate(lines, start=1)
                    if re.match(r"\s*(?:from|import)\b", line)
                    and any(needle in line for needle in needles)
                ),
                None,
            )
            call_line = next(
                (
                    number
                    for number, line in enumerate(lines, start=1)
                    if invocation_pattern.search(line) and number != import_line
                ),
                None,
            ) or next(
                (
                    number
                    for number, line in enumerate(lines, start=1)
                    if usage_pattern.search(line) and number != import_line
                ),
                None,
            )
            for candidate_line, edge, score, reason in (
                (
                    import_line,
                    "import",
                    70.0,
                    f"Imports {primary_module or 'the defining module'}, which defines {symbol}",
                ),
                (call_line, "call_site", 80.0, f"Call site of {symbol}"),
            ):
                if candidate_line is None:
                    continue
                start, end, snippet = build_snippet(lines, candidate_line)
                sources.append(
                    CodeSource(
                        path=path,
                        start_line=start,
                        end_line=end,
                        reason=reason,
                        snippet=snippet,
                        score=score,
                        module=module,
                        edge=edge,
                    )
                )
        return sources, importers

    @staticmethod
    def group_locations(sources: Sequence[CodeSource], limit: int = 4) -> str:
        grouped: dict[str, list[str]] = {}
        for source in sources[:limit]:
            key = source.module or "(module unknown)"
            grouped.setdefault(key, []).append(
                f"{source.path}:{source.start_line}-{source.end_line}"
            )
        return "; ".join(f"{key} ({', '.join(value)})" for key, value in grouped.items())

    def query(self, query: str, limit: int = 8) -> CodeAnswer:
        status = self.refresh()
        terms = [
            term
            for term in re.findall(r"[A-Za-z_][A-Za-z0-9_./-]*", query.casefold())
            if term not in self.STOP_WORDS and len(term) > 1
        ]
        synonyms = {
            "approval": ("approve", "approver", "decision", "policy", "warrant"),
            "delegation": ("delegate", "decide", "warrant"),
            "authentication": ("csrf", "signature", "webhook", "require_admin"),
            "authorization": ("policy", "warrant", "scope", "forbidden"),
        }
        terms = list(
            dict.fromkeys([*terms, *(extra for term in terms for extra in synonyms.get(term, ()))])
        )[:12]
        entries, dependents = self._load_index(status["revision"])
        graph_sources: list[CodeSource] = []
        importers: list[str] = []
        symbol: str | None = None
        dependency_resolved: bool | None = None
        if self.wants_dependency_graph(query):
            dependency_resolved = False
            symbol = self.target_symbol(query, entries)
            if symbol:
                graph_sources, importers = self.dependency_sources(symbol, entries, dependents)
                dependency_resolved = bool(graph_sources)
        symbol_matches: list[str] = []
        for entry in entries:
            haystack = " ".join(
                [entry["path"], *entry.get("symbols", ()), *entry.get("imports", ())]
            ).casefold()
            if any(term in haystack for term in terms):
                symbol_matches.append(entry["path"])
        sources = [*graph_sources, *self.provider.search_text(terms, limit=max(limit * 2, 10))]
        source_keys = {(item.path, item.start_line) for item in sources}
        for path in symbol_matches[:limit]:
            if any(item.path == path for item in sources):
                continue
            lines = self._read_lines(path)
            if not lines:
                continue
            head = "\n".join(f"{index}: {line}" for index, line in enumerate(lines[:12], start=1))
            snippet = redact_secrets(head)[:MAX_SNIPPET_CHARS]
            candidate = CodeSource(
                path=path,
                start_line=1,
                end_line=min(12, len(lines)),
                reason="Path/symbol/import match",
                snippet=snippet,
                score=1.0,
                module=module_for_path(path),
                edge="text",
            )
            if (candidate.path, candidate.start_line) not in source_keys:
                sources.append(candidate)
                source_keys.add((candidate.path, candidate.start_line))
        ranked = sorted(sources, key=lambda item: (-item.score, item.path, item.start_line))[:limit]
        budgeted, truncated = self.BUDGET.apply(ranked)
        answer = self._compose_answer(budgeted, symbol, importers, dependency_resolved, truncated)
        synthesized = False
        if self.llm is not None:
            try:
                response = self.llm.answer(query, [answer])
            except ProviderError:
                pass
            else:
                candidate = response.value.answer.strip()
                if candidate:
                    answer = candidate
                    synthesized = True
        return CodeAnswer(
            answer=answer,
            repository_id=self.provider.repository_id,
            revision=status["revision"],
            sources=budgeted,
            cached_index=bool(status["cached"]),
            ignore_source=self._ignore_source(),
            truncated=truncated,
            dependency_resolved=dependency_resolved,
            modules=tuple(dict.fromkeys(item.module for item in budgeted if item.module)),
            synthesized=synthesized,
        )

    def _compose_answer(
        self,
        sources: Sequence[CodeSource],
        symbol: str | None,
        importers: Sequence[str],
        dependency_resolved: bool | None,
        truncated: bool,
    ) -> str:
        suffix = (
            " Evidence was truncated by the context budget; narrow the question for more."
            if truncated
            else ""
        )
        locations = self.group_locations(sources) if sources else ""
        if dependency_resolved is False:
            subject = symbol or "the requested symbol"
            admission = (
                f"I could not resolve {subject} to a definition in the indexed repository, so I "
                "cannot give you a dependency graph for it."
            )
            if not sources:
                return (
                    f"{admission} No repository text matched the question either, so there is no "
                    "code location I can cite." + suffix
                )
            return (
                f"{admission} The citations below are undifferentiated text matches, not importer "
                f"or call-site edges: {locations}." + suffix
            )
        if not sources:
            return (
                "No repository evidence matched this question. I cannot provide a code location "
                "without a real source match." + suffix
            )
        if dependency_resolved:
            definitions = [item for item in sources if item.edge == "definition"]
            definition_text = (
                ", ".join(f"{item.path}:{item.start_line}-{item.end_line}" for item in definitions)
                or "the indexed definition"
            )
            if importers:
                importer_text = ", ".join(importers[:6])
                return (
                    f"{symbol} is defined in {definition_text}. The revision-keyed dependency "
                    f"graph records {len(importers)} importing file(s): {importer_text}. The "
                    "citations are the real definition, import and call-site edges, grouped by "
                    f"module: {locations}." + suffix
                )
            return (
                f"{symbol} is defined in {definition_text} and no indexed module imports it, so "
                "the dependency graph records no importer edges. Anything else cited here is a "
                f"text match only: {locations}." + suffix
            )
        return (
            f"The strongest repository evidence, grouped by module, is in {locations}. The cited "
            "excerpts contain the matching endpoint, symbol, policy term, or call site; no uncited "
            "code location is inferred." + suffix
        )
