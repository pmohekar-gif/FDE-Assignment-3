from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


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
    openrouter_http_referer: str = "https://github.com/pmohekar-gif/FDE-Assignment-3"
    openrouter_x_title: str = "Warrant"
    structured_output_mode: str | None = None
    provider_timeout_seconds: float | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        raw_db = os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "data" / "warrant.db"))
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
            openrouter_base_url=os.getenv(
                "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
            ),
            openrouter_model=os.getenv("OPENROUTER_MODEL", "minimax/minimax-m3:free"),
            openrouter_http_referer=os.getenv(
                "OPENROUTER_HTTP_REFERER",
                "https://github.com/pmohekar-gif/FDE-Assignment-3",
            ),
            openrouter_x_title=os.getenv("OPENROUTER_X_TITLE", "Warrant"),
            structured_output_mode=os.getenv("STRUCTURED_OUTPUT_MODE") or None,
            provider_timeout_seconds=(
                float(os.environ["PROVIDER_TIMEOUT_SECONDS"])
                if "PROVIDER_TIMEOUT_SECONDS" in os.environ
                else None
            ),
        )

    @property
    def fixture_mode(self) -> bool:
        return self.ai_provider in {"fixture", "mock"}
