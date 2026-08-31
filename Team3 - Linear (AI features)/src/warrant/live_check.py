from __future__ import annotations

import json
import statistics
import tempfile
from datetime import date, datetime, timezone
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


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percentile)
    return ordered[index]


def _settings_for_temp_db(settings: Settings, database_path: Path) -> Settings:
    return Settings(**{**settings.__dict__, "database_path": database_path})


def run(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or Settings.from_env()
    if settings.fixture_mode:
        raise SystemExit(
            "make live-check requires a live provider. Set AI_PROVIDER=openrouter "
            "and OPENROUTER_API_KEY for the MiniMax M3 free endpoint."
        )
    with tempfile.TemporaryDirectory(prefix="warrant-live-check-") as directory:
        live_settings = _settings_for_temp_db(settings, Path(directory) / "live-check.db")
        reset_and_seed(live_settings)
        db = Database(live_settings.database_path)
        provider = build_provider(live_settings)
        service = WarrantService(db, live_settings, provider, RetrievalService(db))

        calls = []
        failures = []
        for issue_ref, requester_id, expected in REFERENCE_ISSUES:
            detail = service.create_delegation(
                live_settings.workspace_id,
                DelegationCreate(
                    issue_ref=issue_ref,
                    requester_id=requester_id,
                    target_agent_id="codex-cloud",
                    idempotency_key=f"live-check-{issue_ref}",
                ),
            )
            usage = db.one(
                "SELECT * FROM model_usage WHERE delegation_id=? "
                "AND operation='extract_delegation_facts' ORDER BY created_at DESC LIMIT 1",
                (detail["id"],),
            )
            actual = detail["decision"]["verdict"]
            safe = actual == expected
            if not safe:
                failures.append({"issue_ref": issue_ref, "expected": expected, "actual": actual})
            calls.append(
                {
                    "issue_ref": issue_ref,
                    "delegation_id": detail["id"],
                    "expected_verdict": expected,
                    "actual_verdict": actual,
                    "safe": safe,
                    "provider": usage["provider"] if usage else provider.name,
                    "model": usage["model"] if usage else provider.model,
                    "serving_provider": usage["serving_provider"] if usage else None,
                    "structured_output_mode": (
                        usage["structured_output_mode"]
                        if usage
                        else getattr(provider, "structured_output_mode", None)
                    ),
                    "schema_repair_count": (
                        usage["schema_repair_count"] if usage else "NOT_MEASURED"
                    ),
                    "latency_ms": usage["latency_ms"] if usage else "NOT_MEASURED",
                    "input_tokens": usage["input_tokens"] if usage else "NOT_MEASURED",
                    "output_tokens": usage["output_tokens"] if usage else "NOT_MEASURED",
                    "reasoning_tokens": usage["reasoning_tokens"] if usage else "NOT_MEASURED",
                    "total_tokens": usage["total_tokens"] if usage else "NOT_MEASURED",
                    "reported_cost_usd": (usage["reported_cost_usd"] if usage else "NOT_MEASURED"),
                }
            )
        latencies = [
            int(call["latency_ms"]) for call in calls if isinstance(call["latency_ms"], int)
        ]
        costs = [
            float(call["reported_cost_usd"])
            for call in calls
            if isinstance(call["reported_cost_usd"], int | float)
        ]
        metrics = {
            "p50_preflight_latency_ms": int(statistics.median(latencies))
            if latencies
            else "NOT_MEASURED",
            "p95_preflight_latency_ms": _percentile(latencies, 0.95)
            if len(latencies) >= 20
            else "NOT_MEASURED",
            "cost_per_delegation_usd": round(sum(costs) / len(costs), 6)
            if len(costs) == len(calls)
            else "NOT_MEASURED",
            "schema_repair_total": sum(
                int(call["schema_repair_count"])
                for call in calls
                if isinstance(call["schema_repair_count"], int)
            ),
        }
        report = {
            "status": "PASS" if not failures else "FINDING_VERDICT_DRIFT",
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "synthetic_data_only": True,
            "provider": live_settings.ai_provider,
            "configured_model": live_settings.live_model,
            "configured_base_url": (
                live_settings.openrouter_base_url
                if live_settings.ai_provider == "openrouter"
                else live_settings.openai_base_url
            ),
            "structured_output_mode": live_settings.resolved_structured_output_mode,
            "timeout_seconds": live_settings.resolved_provider_timeout_seconds,
            "calls": calls,
            "metrics": metrics,
            "cost_target_assessment": (
                "NOT_COMPARABLE_TO_PRODUCTION_TARGET: measured while using OpenRouter's "
                "free MiniMax M3 endpoint; $0 inference cost is promotional/free-endpoint "
                "economics and is not representative of production unit economics."
                if live_settings.ai_provider == "openrouter"
                and live_settings.openrouter_model == "minimax/minimax-m3:free"
                else "MEASURED_PROVIDER_REPORTED_COST"
            ),
            "routing_caveat": (
                "OpenRouter and the serving inference provider are separate processing "
                "layers; serving-provider retention and processing behaviour must be "
                "verified before non-synthetic use."
            ),
            "failures": failures,
        }
        output_path = PROJECT_ROOT / "evaluations" / f"live-run-{date.today().isoformat()}.json"
        output_path.write_text(json.dumps(report, indent=2) + "\n")
        return {**report, "path": str(output_path)}


def main() -> None:
    report = run()
    print(f"wrote {report['path']}")
    print("issue      verdict            model                         serving provider")
    print("          repair  latency  tokens in/out  cost")
    for call in report["calls"]:
        serving_provider = str(call["serving_provider"] or "NOT_EXPOSED")[:17]
        print(
            f"{call['issue_ref']:<10} {call['actual_verdict']:<18} "
            f"{str(call['model'])[:28]:<29} {serving_provider:<17} "
            f"{call['schema_repair_count']!s:<7} {call['latency_ms']!s:<8} "
            f"{call['input_tokens']!s}/{call['output_tokens']!s:<10} "
            f"{call['reported_cost_usd']!s}"
        )
    print(json.dumps(report["metrics"], indent=2))
    if report["failures"]:
        raise SystemExit("live-check finding: deterministic reference verdict changed")


if __name__ == "__main__":
    main()
