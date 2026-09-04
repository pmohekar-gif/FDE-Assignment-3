from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRUCTURED_OUTPUT_MODES = {"json_schema", "json_object", "none"}
MODEL_STRUCTURED_OUTPUT_MODES = {
    ("openrouter", "minimax/minimax-m3:free"): "json_object",
}


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
    openrouter_http_referer: str = "https://linear-ai-warrant.local"
    openrouter_title: str = "Warrant Synthetic Live Check"
    openrouter_reasoning: str | None = None
    structured_output_mode: str = "auto"
    provider_timeout_seconds: float | None = None
    # Linear read-only import adapter (optional)
    linear_mode: str = "off"  # "off" | "stub" | "live"
    linear_api_key: str | None = None
    linear_api_base_url: str = "https://api.linear.app/graphql"

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
            openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            openrouter_model=os.getenv("OPENROUTER_MODEL", "minimax/minimax-m3:free"),
            openrouter_http_referer=os.getenv(
                "OPENROUTER_HTTP_REFERER", "https://linear-ai-warrant.local"
            ),
            openrouter_title=os.getenv("OPENROUTER_TITLE", "Warrant Synthetic Live Check"),
            openrouter_reasoning=os.getenv("OPENROUTER_REASONING") or None,
            structured_output_mode=os.getenv("STRUCTURED_OUTPUT_MODE", "auto").lower(),
            provider_timeout_seconds=(
                float(os.environ["PROVIDER_TIMEOUT_SECONDS"])
                if "PROVIDER_TIMEOUT_SECONDS" in os.environ
                else None
            ),
            linear_mode=os.getenv("LINEAR_MODE", "off").lower(),
            linear_api_key=os.getenv("LINEAR_API_KEY") or None,
            linear_api_base_url=os.getenv(
                "LINEAR_API_BASE_URL", "https://api.linear.app/graphql"
            ),
        )

    @property
    def fixture_mode(self) -> bool:
        return self.ai_provider in {"fixture", "mock"}

    @property
    def linear_stub_mode(self) -> bool:
        return self.linear_mode == "stub"

    @property
    def live_model(self) -> str:
        return self.openrouter_model if self.ai_provider == "openrouter" else self.openai_model

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
        return MODEL_STRUCTURED_OUTPUT_MODES.get((self.ai_provider, self.live_model), "none")

    @property
    def resolved_provider_timeout_seconds(self) -> float:
        if self.provider_timeout_seconds is not None:
            return self.provider_timeout_seconds
        return 45.0 if self.ai_provider == "openrouter" else 12.0
