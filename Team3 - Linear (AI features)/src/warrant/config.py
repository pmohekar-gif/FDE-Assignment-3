from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRUCTURED_OUTPUT_MODES = {"json_schema", "json_object", "none"}
# Grid Dynamics Bifrost gateway. The configured base URL addresses the
# `/anthropic` protocol adapter; the OpenAI-compatible adapter and the model
# catalogue both live on the gateway origin (see providers.bifrost_origin).
BIFROST_DEFAULT_BASE_URL = "https://bifrost.evergreen.gcp.griddynamics.net/anthropic"
# "" is the Bifrost auto-resolve sentinel: BIFROST_MODEL unset means the model id
# is discovered from GET /v1/models at call time, so it cannot be registered here
# by name. Every model behind the gateway is json_object regardless, because the
# gateway does not enforce JSON Schema server-side — see
# resolved_structured_output_mode.
MODEL_STRUCTURED_OUTPUT_MODES = {
    ("openrouter", "minimax/minimax-m3:free"): "json_object",
    ("bifrost", ""): "json_object",
    ("bifrost", "minimax-m3"): "json_object",
}


def _load_dotenv(path: Path = PROJECT_ROOT / ".env") -> None:
    """Populate os.environ from a `.env` file, stdlib-only (no python-dotenv dependency).

    Real process environment variables always win: this only fills in names that are not
    already set, matching conventional dotenv precedence. Silently a no-op when the file
    is absent, so `.env` stays optional. `.env.example` is documentation only and is never
    read here.
    """
    if not path.is_file():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _env_names(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Parse a comma- or whitespace-separated env list, preserving order."""
    raw = os.getenv(name)
    if raw is None:
        return default
    names = [item.strip() for item in raw.replace(",", " ").split()]
    return tuple(dict.fromkeys(item for item in names if item))


def _env_string_map(name: str) -> dict[str, str]:
    raw = os.getenv(name, "{}")
    value: Any = json.loads(raw)
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise ValueError(f"{name} must be a JSON object mapping strings to strings")
    return value


@dataclass(frozen=True)
class Settings:
    database_path: Path
    ai_provider: str
    openai_api_key: str | None
    openai_base_url: str
    openai_model: str
    webhook_secret: str
    csrf_token: str
    warrant_ttl_minutes: int
    allow_sufficiency_threshold: float
    fixture_failure: str | None
    debug: bool
    ai_fallback_provider: str | None = None
    provider_retry_base_ms: int = 25
    workspace_id: str = "ws-demo"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "minimax/minimax-m3:free"
    openrouter_http_referer: str = "https://linear-ai-warrant.local"
    openrouter_title: str = "Warrant Synthetic Live Check"
    openrouter_reasoning: str | None = None
    # Bifrost gateway. The credential is a gateway-issued *virtual key*, held
    # separately from any Anthropic/OpenAI key so both can be present at once.
    # An empty bifrost_model means "auto-resolve from GET /v1/models".
    bifrost_api_key: str | None = None
    bifrost_base_url: str = BIFROST_DEFAULT_BASE_URL
    bifrost_model: str = ""
    structured_output_mode: str = "auto"
    provider_timeout_seconds: float | None = None
    agent_chat_enabled: bool = True
    code_intelligence_enabled: bool = True
    external_coding_agent_enabled: bool = False
    repository_root: Path = PROJECT_ROOT
    repository_max_file_bytes: int = 512_000
    repository_max_results: int = 20
    coding_agent_provider: str = "codex"
    coding_session_root: Path = PROJECT_ROOT / ".runtime" / "coding-sessions"
    demo_repository_root: Path = PROJECT_ROOT / ".runtime" / "demo-repo"
    coding_agent_timeout_seconds: int = 900
    coding_agent_max_output_bytes: int = 1_000_000
    # Last-resort fallback only: discovery normally derives the checks from the target
    # repository. `git diff --check` is fast, argv-only, and needs nothing beyond the Git
    # checkout coding sessions already require, so it can never hang a worktree.
    verification_command: tuple[str, ...] = ("git", "diff", "--check")
    verification_discovery_enabled: bool = True
    verification_max_checks: int = 4
    verification_timeout_seconds: int = 300
    protected_branches: tuple[str, ...] = ("main", "master", "production")
    coding_session_retention: int = 3
    pr_publishing_enabled: bool = False
    # Draft PRs open against this branch. Empty means "let the host decide", i.e. the
    # repository's own default branch, which is what `gh pr create` uses with no `--base`.
    pr_base_branch: str = ""
    # Default reviewers requested on every published draft PR. GitHub usernames, or
    # `org/team` slugs. A per-request list overrides this; both are validated before they
    # reach argv, so a handle can never smuggle in a `gh` flag.
    pr_reviewers: tuple[str, ...] = ()
    slack_enabled: bool = False
    slack_signing_secret: str | None = None
    slack_bot_token: str | None = None
    slack_app_id: str | None = None
    slack_user_map: dict[str, str] | None = None
    application_base_url: str = "http://127.0.0.1:8000"
    # Mock demo sign-in. Default off so the header-driven demo/API path is unchanged.
    # This is an identity gate for the demo, not a production identity provider.
    auth_enabled: bool = False
    demo_password: str = "warrant-demo"
    session_secret: str = "demo-session-secret-change-me-32-bytes"
    session_ttl_minutes: int = 720

    @classmethod
    def from_env(cls) -> "Settings":
        raw_db = os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "data" / "warrant.db"))
        verification = tuple(shlex.split(os.getenv("VERIFICATION_COMMAND", "git diff --check")))
        if not verification:
            raise ValueError("VERIFICATION_COMMAND must contain an executable")
        return cls(
            database_path=Path(raw_db),
            ai_provider=os.getenv("AI_PROVIDER", "fixture").lower(),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            webhook_secret=os.getenv("WEBHOOK_SECRET", "demo-webhook-secret-change-me"),
            csrf_token=os.getenv("CSRF_TOKEN", "demo-csrf-token"),
            warrant_ttl_minutes=int(os.getenv("WARRANT_TTL_MINUTES", "240")),
            allow_sufficiency_threshold=float(os.getenv("ALLOW_SUFFICIENCY_THRESHOLD", "0.70")),
            fixture_failure=os.getenv("FIXTURE_FAILURE") or None,
            debug=_env_bool("DEBUG", False),
            ai_fallback_provider=os.getenv("AI_FALLBACK_PROVIDER") or None,
            provider_retry_base_ms=int(os.getenv("PROVIDER_RETRY_BASE_MS", "25")),
            workspace_id=os.getenv("WORKSPACE_ID", "ws-demo"),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
            openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            openrouter_model=os.getenv("OPENROUTER_MODEL", "minimax/minimax-m3:free"),
            openrouter_http_referer=os.getenv(
                "OPENROUTER_HTTP_REFERER", "https://linear-ai-warrant.local"
            ),
            openrouter_title=os.getenv("OPENROUTER_TITLE", "Warrant Synthetic Live Check"),
            openrouter_reasoning=os.getenv("OPENROUTER_REASONING") or None,
            bifrost_api_key=os.getenv("BIFROST_API_KEY") or None,
            bifrost_base_url=os.getenv("BIFROST_BASE_URL") or BIFROST_DEFAULT_BASE_URL,
            bifrost_model=(os.getenv("BIFROST_MODEL") or "").strip(),
            structured_output_mode=os.getenv("STRUCTURED_OUTPUT_MODE", "auto").lower(),
            provider_timeout_seconds=(
                float(os.environ["PROVIDER_TIMEOUT_SECONDS"])
                if "PROVIDER_TIMEOUT_SECONDS" in os.environ
                else None
            ),
            agent_chat_enabled=_env_bool("AGENT_CHAT_ENABLED", True),
            code_intelligence_enabled=_env_bool("CODE_INTELLIGENCE_ENABLED", True),
            external_coding_agent_enabled=_env_bool("EXTERNAL_CODING_AGENT_ENABLED", False),
            repository_root=Path(os.getenv("REPOSITORY_ROOT", str(PROJECT_ROOT))).resolve(),
            repository_max_file_bytes=int(os.getenv("REPOSITORY_MAX_FILE_BYTES", "512000")),
            repository_max_results=int(os.getenv("REPOSITORY_MAX_RESULTS", "20")),
            coding_agent_provider=os.getenv("CODING_AGENT_PROVIDER", "codex").lower(),
            coding_session_root=Path(
                os.getenv(
                    "CODING_SESSION_ROOT",
                    str(PROJECT_ROOT / ".runtime" / "coding-sessions"),
                )
            ).resolve(),
            demo_repository_root=Path(
                os.getenv("DEMO_REPOSITORY_ROOT", str(PROJECT_ROOT / ".runtime" / "demo-repo"))
            ).resolve(),
            coding_agent_timeout_seconds=int(os.getenv("CODING_AGENT_TIMEOUT_SECONDS", "900")),
            coding_agent_max_output_bytes=int(
                os.getenv("CODING_AGENT_MAX_OUTPUT_BYTES", "1000000")
            ),
            verification_command=verification,
            verification_discovery_enabled=_env_bool("VERIFICATION_DISCOVERY_ENABLED", True),
            verification_max_checks=int(os.getenv("VERIFICATION_MAX_CHECKS", "4")),
            verification_timeout_seconds=int(os.getenv("VERIFICATION_TIMEOUT_SECONDS", "300")),
            protected_branches=_env_names("PROTECTED_BRANCHES", ("main", "master", "production")),
            coding_session_retention=int(os.getenv("CODING_SESSION_RETENTION", "3")),
            pr_publishing_enabled=_env_bool("PR_PUBLISHING_ENABLED", False),
            pr_base_branch=os.getenv("PR_BASE_BRANCH", "").strip(),
            pr_reviewers=_env_names("PR_REVIEWERS", ()),
            slack_enabled=_env_bool("SLACK_ENABLED", False),
            slack_signing_secret=os.getenv("SLACK_SIGNING_SECRET") or None,
            slack_bot_token=os.getenv("SLACK_BOT_TOKEN") or None,
            slack_app_id=os.getenv("SLACK_APP_ID") or None,
            slack_user_map=_env_string_map("SLACK_USER_MAP"),
            application_base_url=os.getenv("APPLICATION_BASE_URL", "http://127.0.0.1:8000"),
            auth_enabled=_env_bool("AUTH_ENABLED", False),
            demo_password=os.getenv("DEMO_PASSWORD", "warrant-demo"),
            session_secret=os.getenv(
                "SESSION_SECRET", "demo-session-secret-change-me-32-bytes"
            ),
            session_ttl_minutes=int(os.getenv("SESSION_TTL_MINUTES", "720")),
        )

    @property
    def fixture_mode(self) -> bool:
        return self.ai_provider in {"fixture", "mock"}

    @property
    def live_model(self) -> str:
        if self.ai_provider == "openrouter":
            return self.openrouter_model
        # Empty for Bifrost when BIFROST_MODEL is unset: the id is only known
        # after the provider resolves it against the gateway catalogue.
        if self.ai_provider == "bifrost":
            return self.bifrost_model
        return self.openai_model

    @property
    def resolved_structured_output_mode(self) -> str:
        if self.structured_output_mode != "auto":
            if self.structured_output_mode not in STRUCTURED_OUTPUT_MODES:
                raise ValueError(
                    "STRUCTURED_OUTPUT_MODE must be json_schema, json_object, none, or auto"
                )
            return self.structured_output_mode
        if self.ai_provider == "openai":
            return "json_schema"
        # The Bifrost gateway does not validate JSON Schema server-side (same as
        # OpenRouter), so any model it fronts — including one auto-resolved after
        # this property is read — gets json_object plus Warrant's client-side
        # Pydantic validation. Never json_schema: that would claim an enforcement
        # guarantee the gateway does not provide.
        default = "json_object" if self.ai_provider == "bifrost" else "none"
        return MODEL_STRUCTURED_OUTPUT_MODES.get((self.ai_provider, self.live_model), default)

    @property
    def resolved_provider_timeout_seconds(self) -> float:
        if self.provider_timeout_seconds is not None:
            return self.provider_timeout_seconds
        return 45.0 if self.ai_provider in {"openrouter", "bifrost"} else 12.0
