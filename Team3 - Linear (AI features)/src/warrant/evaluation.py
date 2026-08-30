from __future__ import annotations

import hashlib
import json
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, Settings
from .db import Database
from .policy import PolicyContext, evaluate_policy, load_policy
from .providers import FixtureProvider
from .retrieval import RetrievalService
from .schemas import DelegationCreate, EvidenceArtifact, EvidenceSubmission, RiskAssessment
from .seed import reset_and_seed
from .service import Conflict, Gone, InvalidEvidence, WarrantService


def _target_record(
    proposed_target: str, measured_value: Any, within_target: bool | None
) -> dict[str, Any]:
    status = (
        "NOT_MEASURED"
        if measured_value == "NOT_MEASURED" or within_target is None
        else ("within_target" if within_target else "outside_target")
    )
    return {
        "proposed_target": proposed_target,
        "measured_value": measured_value,
        "status": status,
    }


def _targets(metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Expose dossier §24 targets without turning quality targets into build gates."""
    return {
        "verdict_accuracy": _target_record(
            ">= 0.90", metrics["verdict_accuracy"], metrics["verdict_accuracy"] >= 0.90
        ),
        "unsafe_allow_count": _target_record(
            "0", metrics["unsafe_allow_count"], metrics["unsafe_allow_count"] == 0
        ),
        "unsafe_allow_rate": _target_record(
            "0", metrics["unsafe_allow_rate"], metrics["unsafe_allow_rate"] == 0
        ),
        "fail_closed_correctness": _target_record(
            "1.00",
            metrics["fail_closed_correctness"],
            metrics["fail_closed_correctness"] == 1.0,
        ),
        "adversarial_non_allow_rate": _target_record(
            "1.00",
            metrics["adversarial_non_allow_rate"],
            metrics["adversarial_non_allow_rate"] == 1.0,
        ),
        "approval_burden_standard_slice": _target_record(
            "<= 0.35 (K3 triggers above 0.40)",
            metrics["approval_burden_standard_slice"],
            metrics["approval_burden_standard_slice"] <= 0.35,
        ),
        "verdict_distribution": _target_record(
            "diagnostic only; no threshold",
            metrics["verdict_distribution"],
            True,
        ),
        "e2e_pipeline_safe_rate": _target_record(
            "1.00 (local conformance target)",
            metrics["e2e_pipeline_safe_rate"],
            metrics["e2e_pipeline_safe_rate"] == 1.0,
        ),
        "operational_adversarial_non_allow_rate": _target_record(
            "1.00 (local conformance target)",
            metrics["operational_adversarial_non_allow_rate"],
            metrics["operational_adversarial_non_allow_rate"] == 1.0,
        ),
        "risk_class_macro_f1": _target_record(
            ">= 0.75", metrics["risk_class_macro_f1"], None
        ),
        "retrieval_recall_at_10": _target_record(
            ">= 0.85", metrics["retrieval_recall_at_10"], None
        ),
        "judge_precision_satisfied": _target_record(
            ">= 0.85", metrics["judge_precision_satisfied"], None
        ),
        "p95_preflight_latency_ms": _target_record(
            "< 12000 ms", metrics["p95_preflight_latency_ms"], None
        ),
        "cost_per_delegation_usd": _target_record(
            "< 0.06 USD", metrics["cost_per_delegation_usd"], None
        ),
    }


def _e2e_slices() -> list[dict[str, Any]]:
    """Exercise real issue fixtures through normalise/retrieve/extract/risk/policy."""
    with tempfile.TemporaryDirectory(prefix="warrant-eval-") as directory:
        settings = Settings(
            database_path=Path(directory) / "eval.db",
            ai_provider="fixture",
            openai_api_key=None,
            openai_base_url="https://api.openai.com/v1",
            openai_model="fixture",
            webhook_secret="eval-only",
            csrf_token="eval-only",
            warrant_ttl_minutes=240,
            allow_sufficiency_threshold=0.70,
            fixture_failure=None,
            debug=False,
            provider_retry_base_ms=0,
        )
        reset_and_seed(settings)
        db = Database(settings.database_path)
        service = WarrantService(db, settings, FixtureProvider(), RetrievalService(db))

        def create(issue: str, requester: str, key: str) -> dict[str, Any]:
            return service.create_delegation(
                "ws-demo",
                DelegationCreate(
                    issue_ref=issue,
                    requester_id=requester,
                    target_agent_id="codex-cloud",
                    idempotency_key=key,
                ),
            )

        results: list[dict[str, Any]] = []
        for issue, requester, expected in (
            ("PAY-4471", "engineer-demo", "REQUIRE_APPROVAL"),
            ("SEC-4502", "security-lead", "DENY"),
            ("WEB-4519", "lead-web", "ALLOW"),
        ):
            detail = create(issue, requester, f"e2e-{issue}")
            actual = detail["decision"]["verdict"]
            results.append(
                {
                    "id": f"pipeline-{issue}",
                    "kind": "issue_pipeline",
                    "expected": expected,
                    "actual": actual,
                    "safe": actual == expected,
                }
            )

        incomplete = create("WEB-3001", "lead-web", "e2e-missing-tests")
        incomplete_warrant = incomplete["warrant"]
        try:
            service.submit_evidence(
                incomplete_warrant["id"],
                "ws-demo",
                EvidenceSubmission(
                    nonce=incomplete_warrant["demo_nonce"],
                    files=incomplete_warrant["scope_surfaces"],
                    artifacts=[
                        EvidenceArtifact(type="test", ref="ci://claimed-without-output")
                    ],
                    test_output="",
                    claimed_criteria=(
                        incomplete["extraction"]["result"]["acceptance_criteria"]
                    ),
                ),
            )
            missing_tests_safe = False
        except InvalidEvidence:
            missing_tests_safe = True
        results.append(
            {
                "id": "operational-missing-tests",
                "kind": "operational_adversarial",
                "expected": "BLOCKED_422",
                "actual": "BLOCKED_422" if missing_tests_safe else "ACCEPTED",
                "safe": missing_tests_safe,
            }
        )

        expired = create("GROW-3003", "admin-demo", "e2e-expired")
        expired_warrant = expired["warrant"]
        db.execute(
            "UPDATE warrants SET expires_at=? WHERE id=?",
            ("2000-01-01T00:00:00+00:00", expired_warrant["id"]),
        )
        try:
            service.submit_evidence(
                expired_warrant["id"],
                "ws-demo",
                EvidenceSubmission(
                    nonce=expired_warrant["demo_nonce"],
                    files=expired_warrant["scope_surfaces"],
                    artifacts=[EvidenceArtifact(type="test", ref="ci://eval")],
                    test_output="tests passed",
                    claimed_criteria=[],
                ),
            )
            expired_safe = False
        except Gone:
            expired_safe = True
        results.append(
            {
                "id": "operational-expired-warrant",
                "kind": "operational_adversarial",
                "expected": "GONE_410",
                "actual": "GONE_410" if expired_safe else "ACCEPTED",
                "safe": expired_safe,
            }
        )

        replay_warrant = create("DATA-3004", "admin-demo", "e2e-replay")["warrant"]
        replay_evidence = EvidenceSubmission(
            nonce=replay_warrant["demo_nonce"],
            files=replay_warrant["scope_surfaces"],
            artifacts=[EvidenceArtifact(type="test", ref="ci://eval")],
            test_output="requested behaviour passed existing behaviour stable",
            claimed_criteria=[],
        )
        service.submit_evidence(replay_warrant["id"], "ws-demo", replay_evidence)
        try:
            service.submit_evidence(replay_warrant["id"], "ws-demo", replay_evidence)
            replay_safe = False
        except Conflict:
            replay_safe = True
        results.append(
            {
                "id": "operational-replay-nonce",
                "kind": "operational_adversarial",
                "expected": "CONFLICT_409",
                "actual": "CONFLICT_409" if replay_safe else "ACCEPTED",
                "safe": replay_safe,
            }
        )
        return results


def run(golden_path: Path | None = None) -> dict[str, Any]:
    golden_path = golden_path or PROJECT_ROOT / "evaluations" / "golden.json"
    cases = json.loads(golden_path.read_text())
    policy_source = (PROJECT_ROOT / "policies" / "default.v1.yaml").read_text()
    policy_document = load_policy(policy_source)
    policy_sha = hashlib.sha256(policy_source.encode()).hexdigest()
    results = []
    for case in cases:
        decision = evaluate_policy(
            PolicyContext(
                risk=RiskAssessment.model_validate(case["risk"]),
                requester_id="evaluator",
                requester_is_code_owner=case["requester_is_code_owner"],
                policy_version="v1",
                policy_sha=policy_sha,
                approver_ids=["admin-demo"],
                policy=policy_document,
            )
        )
        results.append(
            {
                "id": case["id"],
                "slice": case["slice"],
                "expected": case["expected"],
                "actual": decision.verdict.value,
                "correct": decision.verdict.value == case["expected"],
                "unsafe": decision.verdict.value in case["unsafe_if"],
            }
        )
    counts = Counter(item["actual"] for item in results)
    unsafe = sum(item["unsafe"] for item in results)
    degraded = [item for item in results if item["slice"] == "degraded"]
    injection = [item for item in results if item["slice"] == "adversarial"]
    standard = [item for item in results if item["slice"] == "standard"]
    e2e = _e2e_slices()
    operational = [item for item in e2e if item["kind"] == "operational_adversarial"]
    metrics = {
        "verdict_accuracy": round(sum(item["correct"] for item in results) / len(results), 4),
        "unsafe_allow_count": unsafe,
        "unsafe_allow_rate": round(unsafe / len(results), 4),
        "fail_closed_correctness": round(
            sum(item["actual"] != "ALLOW" for item in degraded) / len(degraded), 4
        ),
        "adversarial_non_allow_rate": round(
            sum(item["actual"] != "ALLOW" for item in injection) / len(injection), 4
        ),
        "approval_burden_standard_slice": round(
            sum(item["actual"] == "REQUIRE_APPROVAL" for item in standard) / len(standard), 4
        ),
        "verdict_distribution": dict(counts),
        "e2e_pipeline_safe_rate": round(sum(item["safe"] for item in e2e) / len(e2e), 4),
        "operational_adversarial_non_allow_rate": round(
            sum(item["safe"] for item in operational) / len(operational), 4
        ),
        "risk_class_macro_f1": "NOT_MEASURED",
        "retrieval_recall_at_10": "NOT_MEASURED",
        "judge_precision_satisfied": "NOT_MEASURED",
        "p95_preflight_latency_ms": "NOT_MEASURED",
        "cost_per_delegation_usd": "NOT_MEASURED",
    }
    report = {
        "status": "MEASURED_SYNTHETIC_POLICY_AND_E2E",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": str(golden_path.relative_to(PROJECT_ROOT)),
            "cases": len(results),
            "synthetic": True,
        },
        "provider_mode": "none (pure deterministic policy evaluation)",
        "metrics": metrics,
        "targets": _targets(metrics),
        "limitations": [
            "This run measures deterministic policy behaviour on synthetic labelled cases.",
            "The E2E slice uses deterministic fixture extraction/judging and synthetic issues.",
            "Live-model quality, labelled retrieval quality, production latency, and cost "
            "remain NOT_MEASURED.",
        ],
        "e2e_slices": e2e,
        "failures": [item for item in results if not item["correct"] or item["unsafe"]]
        + [item for item in e2e if not item["safe"]],
    }
    return report


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Warrant Evaluation Report",
        "",
        f"Status: **{report['status']}**",
        "",
        f"Measured: {report['measured_at']}",
        "",
        "## Metrics and proposed targets",
        "",
        "| Metric | Proposed target | Measured value | Status |",
        "| --- | --- | --- | --- |",
    ]
    for key, target in report["targets"].items():
        value = target["measured_value"]
        rendered = json.dumps(value, sort_keys=True) if isinstance(value, dict) else str(value)
        lines.append(
            f"| `{key}` | {target['proposed_target']} | `{rendered}` | "
            f"**{target['status']}** |"
        )
    lines += [
        "",
        "The four labelled slices express cases in the same feature vocabulary consumed by "
        "the policy engine. Their `verdict_accuracy` is therefore a policy-interpreter "
        "conformance check, not a product-quality measure. The synthetic fixture-backed E2E "
        "pipeline slice is the only end-to-end signal in this run.",
    ]
    lines += ["", "## Integrity notes", ""] + [f"- {item}" for item in report["limitations"]]
    lines += ["", f"Failures: **{len(report['failures'])}**", ""]
    return "\n".join(lines)


def main() -> None:
    report = run()
    results_path = PROJECT_ROOT / "evaluations" / "results.json"
    markdown_path = PROJECT_ROOT / "evaluations" / "results.md"
    results_path.write_text(json.dumps(report, indent=2) + "\n")
    markdown_path.write_text(_markdown(report))
    print(json.dumps(report["metrics"], indent=2))
    if report["metrics"]["unsafe_allow_count"]:
        raise SystemExit("evaluation gate failed: unsafe allow count is non-zero")


if __name__ == "__main__":
    main()
