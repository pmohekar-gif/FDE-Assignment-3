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
from .triage import TriageRecommendationService


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
        "risk_class_macro_f1": _target_record(">= 0.75", metrics["risk_class_macro_f1"], None),
        "retrieval_recall_at_10": _target_record(
            ">= 0.85",
            metrics["retrieval_recall_at_10"],
            metrics["retrieval_recall_at_10"] >= 0.85,
        ),
        "possible_duplicate_precision": _target_record(
            ">= 0.85",
            metrics["possible_duplicate_precision"],
            metrics["possible_duplicate_precision"] >= 0.85,
        ),
        "semantic_search_recall_at_10": _target_record(
            ">= 0.85",
            metrics["semantic_search_recall_at_10"],
            metrics["semantic_search_recall_at_10"] >= 0.85,
        ),
        "exact_key_search_success": _target_record(
            "1.00",
            metrics["exact_key_search_success"],
            metrics["exact_key_search_success"] == 1.0,
        ),
        "brief_unsupported_authority_count": _target_record(
            "0",
            metrics["brief_unsupported_authority_count"],
            metrics["brief_unsupported_authority_count"] == 0,
        ),
        "brief_contradiction_count": _target_record(
            "0",
            metrics["brief_contradiction_count"],
            metrics["brief_contradiction_count"] == 0,
        ),
        "brief_required_fact_coverage": _target_record(
            "1.00",
            metrics["brief_required_fact_coverage"],
            metrics["brief_required_fact_coverage"] == 1.0,
        ),
        "triage_team_accuracy": _target_record(
            ">= 0.85", metrics["triage_team_accuracy"], metrics["triage_team_accuracy"] >= 0.85
        ),
        "triage_priority_macro_f1": _target_record(
            ">= 0.75",
            metrics["triage_priority_macro_f1"],
            metrics["triage_priority_macro_f1"] >= 0.75,
        ),
        "triage_label_precision": _target_record(
            ">= 0.80",
            metrics["triage_label_precision"],
            metrics["triage_label_precision"] >= 0.80,
        ),
        "triage_label_recall": _target_record(
            ">= 0.80", metrics["triage_label_recall"], metrics["triage_label_recall"] >= 0.80
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
                    artifacts=[EvidenceArtifact(type="test", ref="ci://claimed-without-output")],
                    test_output="",
                    claimed_criteria=(incomplete["extraction"]["result"]["acceptance_criteria"]),
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


def _retrieval_metrics() -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Measure the advisory ranker against explicit synthetic relevance labels."""
    labels_path = PROJECT_ROOT / "evaluations" / "retrieval_golden.json"
    labels = json.loads(labels_path.read_text())
    with tempfile.TemporaryDirectory(prefix="warrant-retrieval-eval-") as directory:
        settings = Settings.from_env()
        settings = Settings(**{**settings.__dict__, "database_path": Path(directory) / "eval.db"})
        reset_and_seed(settings)
        retrieval = RetrievalService(Database(settings.database_path))
        cases: list[dict[str, Any]] = []
        retrieved_relevant = 0
        labelled_relevant = 0
        predicted_duplicates = 0
        correct_duplicates = 0
        for label in labels:
            result = retrieval.suggest_related("ws-demo", label["source"], top_k=10)
            assert result is not None
            returned = [item["external_key"] for item in result.suggestions]
            predicted = [
                item["external_key"]
                for item in result.suggestions
                if item["relation"] == "possible_duplicate"
            ]
            relevant = set(label["relevant"])
            duplicates = set(label["duplicates"])
            hits = relevant.intersection(returned)
            duplicate_hits = duplicates.intersection(predicted)
            retrieved_relevant += len(hits)
            labelled_relevant += len(relevant)
            predicted_duplicates += len(predicted)
            correct_duplicates += len(duplicate_hits)
            cases.append(
                {
                    "source": label["source"],
                    "returned": returned,
                    "relevant_hits": sorted(hits),
                    "predicted_duplicates": predicted,
                    "duplicate_hits": sorted(duplicate_hits),
                }
            )
        return (
            {
                "retrieval_recall_at_10": round(retrieved_relevant / labelled_relevant, 4),
                "possible_duplicate_precision": round(
                    correct_duplicates / predicted_duplicates if predicted_duplicates else 0, 4
                ),
            },
            cases,
        )


def _search_metrics() -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Measure issue discovery separately from issue-to-issue similarity."""
    labels_path = PROJECT_ROOT / "evaluations" / "search_golden.json"
    labels = json.loads(labels_path.read_text())
    with tempfile.TemporaryDirectory(prefix="warrant-search-eval-") as directory:
        settings = Settings.from_env()
        settings = Settings(**{**settings.__dict__, "database_path": Path(directory) / "eval.db"})
        reset_and_seed(settings)
        retrieval = RetrievalService(Database(settings.database_path))
        cases: list[dict[str, Any]] = []
        for label in labels:
            result = retrieval.search_issues("ws-demo", label["query"], limit=10)
            returned = [item["external_key"] for item in result.results]
            rank = returned.index(label["expected"]) + 1 if label["expected"] in returned else None
            cases.append({**label, "returned": returned, "rank": rank, "hit": rank is not None})
        exact = [case for case in cases if case["slice"] == "exact_key"]
        semantic = [case for case in cases if case["slice"] == "semantic"]
        return (
            {
                "semantic_search_recall_at_10": round(
                    sum(case["hit"] for case in semantic) / len(semantic), 4
                ),
                "exact_key_search_success": round(
                    sum(case["rank"] == 1 for case in exact) / len(exact), 4
                ),
            },
            cases,
        )


def _brief_grounding_metrics() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Gate narrative summaries against deterministic facts and authority boundaries."""
    labels = json.loads((PROJECT_ROOT / "evaluations" / "brief_golden.json").read_text())
    cases: list[dict[str, Any]] = []
    unsupported_patterns = (
        "pre-approved",
        "is approved",
        "is authorized",
        "grant tools",
        "may proceed without",
        "execute immediately",
    )
    contradiction_count = 0
    unsupported_count = 0
    covered_facts = 0
    required_facts = 0
    for index, label in enumerate(labels):
        with tempfile.TemporaryDirectory(prefix="warrant-brief-eval-") as directory:
            settings = Settings.from_env()
            settings = Settings(
                **{**settings.__dict__, "database_path": Path(directory) / "eval.db"}
            )
            reset_and_seed(settings)
            db = Database(settings.database_path)
            provider = FixtureProvider("brief" if label["mode"] == "structured_fallback" else None)
            service = WarrantService(db, settings, provider, RetrievalService(db))
            detail = service.create_delegation(
                "ws-demo",
                DelegationCreate(
                    issue_ref=label["issue"],
                    requester_id="lead-web",
                    target_agent_id="codex-cloud",
                    idempotency_key=f"brief-eval-{index}",
                ),
            )
            brief = service.delegation_brief(detail["id"], "ws-demo")
            prose = brief["prose"]
            corpus = " ".join(
                [prose["summary"], *prose["evidence_notes"], *prose["human_next_steps"]]
            ).lower()
            unsupported = [pattern for pattern in unsupported_patterns if pattern in corpus]
            contradiction = label["expected_verdict"] == "ALLOW" and any(
                pattern in corpus for pattern in ("do not execute", "policy denied")
            )
            checks = {
                "issue_key": label["issue"].lower() in prose["summary"].lower(),
                "evidence_sufficiency": "evidence sufficiency" in corpus,
                "policy_reasons": any(
                    phrase in corpus for phrase in ("policy reasons", "deterministic reasons")
                ),
            }
            unsupported_count += len(unsupported)
            contradiction_count += int(contradiction)
            covered_facts += sum(checks.values())
            required_facts += len(checks)
            cases.append(
                {
                    **label,
                    "actual_source": brief["prose_source"],
                    "authority_boundary": brief["authority_boundary"],
                    "unsupported_authority": unsupported,
                    "contradiction": contradiction,
                    "required_fact_checks": checks,
                }
            )
    return (
        {
            "brief_unsupported_authority_count": unsupported_count,
            "brief_contradiction_count": contradiction_count,
            "brief_required_fact_coverage": round(covered_facts / required_facts, 4),
        },
        cases,
    )


def _triage_metrics() -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Measure advisory triage dimensions on explicit synthetic labels."""
    labels = json.loads((PROJECT_ROOT / "evaluations" / "triage_golden.json").read_text())
    with tempfile.TemporaryDirectory(prefix="warrant-triage-eval-") as directory:
        settings = Settings.from_env()
        settings = Settings(**{**settings.__dict__, "database_path": Path(directory) / "eval.db"})
        reset_and_seed(settings)
        db = Database(settings.database_path)
        triage = TriageRecommendationService(db, RetrievalService(db))
        cases: list[dict[str, Any]] = []
        label_hits = 0
        label_predictions = 0
        label_expected = 0
        for label in labels:
            result = triage.recommend("ws-demo", label["issue"])
            assert result is not None
            # Weak neighbour labels remain visible, but are not counted as accepted predictions.
            predicted_labels = {
                item["label"] for item in result.labels if item["confidence"] >= 0.7
            }
            expected_labels = set(label["labels"])
            label_hits += len(predicted_labels & expected_labels)
            label_predictions += len(predicted_labels)
            label_expected += len(expected_labels)
            cases.append(
                {
                    **label,
                    "actual_team": result.team["recommended"],
                    "actual_priority": result.priority["recommended"],
                    "actual_labels": sorted(predicted_labels),
                }
            )

        priorities = sorted({case["priority"] for case in cases})
        priority_f1: list[float] = []
        for priority in priorities:
            true_positive = sum(
                case["priority"] == priority and case["actual_priority"] == priority
                for case in cases
            )
            false_positive = sum(
                case["priority"] != priority and case["actual_priority"] == priority
                for case in cases
            )
            false_negative = sum(
                case["priority"] == priority and case["actual_priority"] != priority
                for case in cases
            )
            denominator = 2 * true_positive + false_positive + false_negative
            priority_f1.append(2 * true_positive / denominator if denominator else 0.0)

        return (
            {
                "triage_team_accuracy": round(
                    sum(case["team"] == case["actual_team"] for case in cases) / len(cases), 4
                ),
                "triage_priority_macro_f1": round(sum(priority_f1) / len(priority_f1), 4),
                "triage_label_precision": round(label_hits / label_predictions, 4),
                "triage_label_recall": round(label_hits / label_expected, 4),
            },
            cases,
        )


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
    retrieval_metrics, retrieval_cases = _retrieval_metrics()
    search_metrics, search_cases = _search_metrics()
    brief_metrics, brief_cases = _brief_grounding_metrics()
    triage_metrics, triage_cases = _triage_metrics()
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
        **retrieval_metrics,
        **search_metrics,
        **brief_metrics,
        **triage_metrics,
        "judge_precision_satisfied": "NOT_MEASURED",
        "p95_preflight_latency_ms": "NOT_MEASURED",
        "cost_per_delegation_usd": "NOT_MEASURED",
    }
    report = {
        "status": "MEASURED_SYNTHETIC_POLICY_E2E_AND_RETRIEVAL",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": str(golden_path.relative_to(PROJECT_ROOT)),
            "cases": len(results),
            "synthetic": True,
            "retrieval_path": "evaluations/retrieval_golden.json",
            "retrieval_cases": len(retrieval_cases),
            "search_path": "evaluations/search_golden.json",
            "search_cases": len(search_cases),
            "brief_path": "evaluations/brief_golden.json",
            "brief_cases": len(brief_cases),
            "triage_path": "evaluations/triage_golden.json",
            "triage_cases": len(triage_cases),
        },
        "provider_mode": "none (pure deterministic policy evaluation)",
        "metrics": metrics,
        "targets": _targets(metrics),
        "limitations": [
            "This run measures deterministic policy behaviour on synthetic labelled cases.",
            "The E2E slice uses deterministic fixture extraction/judging and synthetic issues.",
            "Retrieval quality is measured only on a small synthetic labelled set; it is not "
            "evidence of production or customer-data quality.",
            "Semantic search uses deterministic token-hash vectors, not a production embedding "
            "model; its small synthetic search set is a regression signal only.",
            "Brief grounding is measured on fixture and deterministic fallback narratives; "
            "live-model grounding still requires separate evidence.",
            "Triage quality is measured on three synthetic demo issues and deterministic "
            "signals; it does not establish production routing quality.",
            "Live-model judge quality, production latency, and cost remain NOT_MEASURED.",
        ],
        "e2e_slices": e2e,
        "retrieval_cases": retrieval_cases,
        "search_cases": search_cases,
        "brief_cases": brief_cases,
        "triage_cases": triage_cases,
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
            f"| `{key}` | {target['proposed_target']} | `{rendered}` | **{target['status']}** |"
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
    if report["metrics"]["brief_unsupported_authority_count"]:
        raise SystemExit("evaluation gate failed: brief contains unsupported authority language")


if __name__ == "__main__":
    main()
