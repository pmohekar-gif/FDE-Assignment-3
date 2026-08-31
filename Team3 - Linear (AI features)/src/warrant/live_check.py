from __future__ import annotations

import json
import statistics
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, Settings
from .db import Database
from .providers import build_provider
from .retrieval import RetrievalService
from .schemas import DelegationCreate
from .seed import reset_and_seed
from .service import WarrantService

REFERENCE_ISSUES = (
    ("PAY-4471", "engineer-demo", "REQUIRE_APPROVAL"),
    ("SEC-4502", "security-lead", "DENY"),
    ("WEB-4519", "lead-web", "ALLOW"),
)


def _percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def run(settings: Settings | None = None) -> tuple[dict[str, Any], Path]:
    configured = settings or Settings.from_env()
    if configured.ai_provider not in {"openai", "openrouter"}:
        raise SystemExit("live-check requires AI_PROVIDER=openai or AI_PROVIDER=openrouter")

    with tempfile.TemporaryDirectory(prefix="warrant-live-") as directory:
        live_settings = replace(configured, database_path=Path(directory) / "live.db")
        reset_and_seed(live_settings)
        db = Database(live_settings.database_path)
        provider = build_provider(live_settings)
        service = WarrantService(db, live_settings, provider, RetrievalService(db))
        calls = []
        findings = []
        for issue, requester, expected in REFERENCE_ISSUES:
            detail = service.create_delegation(
                live_settings.workspace_id,
                DelegationCreate(
                    issue_ref=issue,
                    requester_id=requester,
                    target_agent_id="codex-cloud",
                    idempotency_key=f"live-{issue}",
                ),
                source="live-check",
            )
            usage = db.one(
                "SELECT * FROM model_usage WHERE delegation_id=? "
                "AND operation='extract_delegation_facts' ORDER BY created_at DESC LIMIT 1",
                (detail["id"],),
            ) or {}
            actual = detail["decision"]["verdict"]
            item = {
                "issue": issue,
                "expected_verdict": expected,
                "verdict": actual,
                "provider": usage.get("provider", provider.name),
                "model": usage.get("model", provider.model),
                "serving_provider": usage.get("serving_provider"),
                "schema_repair_count": usage.get("schema_repair_count", 0),
                "latency_ms": usage.get("latency_ms"),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "reasoning_tokens": usage.get("reasoning_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "reported_cost_usd": usage.get("reported_cost_usd"),
            }
            calls.append(item)
            if actual != expected:
                findings.append(
                    {"issue": issue, "expected_verdict": expected, "actual_verdict": actual}
                )
            print(
                f"{issue}: verdict={actual} model={item['model']} "
                f"serving_provider={item['serving_provider'] or 'NOT_REPORTED'} "
                f"repairs={item['schema_repair_count']} latency_ms={item['latency_ms']} "
                f"tokens={item['input_tokens']}/{item['output_tokens']} "
                f"reported_cost_usd={item['reported_cost_usd']}"
            )

    latencies = [item["latency_ms"] for item in calls if item["latency_ms"] is not None]
    now = datetime.now(timezone.utc)
    report = {
        "status": "PASS" if not findings else "FINDINGS",
        "measured_at": now.isoformat(),
        "synthetic_data_only": True,
        "provider": configured.ai_provider,
        "configured_model": provider.model,
        "structured_output_mode": getattr(
            getattr(provider, "primary", None), "structured_output_mode", "none"
        ),
        "calls": calls,
        "latency_ms": {
            "sample_count": len(latencies),
            "p50": round(statistics.median(latencies)) if latencies else "NOT_MEASURED",
            "p95": _percentile(latencies, 0.95) if len(latencies) >= 3 else "NOT_MEASURED",
        },
        "cost_note": (
            "Measured while using OpenRouter's free MiniMax M3 endpoint; $0 inference cost "
            "is promotional/free-endpoint economics and is not representative of production "
            "unit economics. A $0 result does not satisfy the <$0.06 production cost target."
            if configured.ai_provider == "openrouter"
            else None
        ),
        "findings": findings,
    }
    output = PROJECT_ROOT / "evaluations" / f"live-run-{now.date().isoformat()}.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {output}")
    return report, output


def main() -> None:
    report, _ = run()
    if report["findings"]:
        raise SystemExit("live-check finding: one or more deterministic verdicts changed")


if __name__ == "__main__":
    main()
