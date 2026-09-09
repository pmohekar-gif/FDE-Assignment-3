"""Run deterministic Code Intelligence quality checks against a synthetic checkout."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from warrant.db import Database
from warrant.repository import CodeIntelligenceService, LocalRepositoryProvider


def build_fixture(root: Path) -> None:
    (root / "pkg").mkdir(parents=True)
    (root / "templates").mkdir()
    (root / "docs").mkdir()
    (root / "pkg" / "policy.py").write_text(
        "def evaluate_policy(context):\n    return 'REQUIRE_APPROVAL'\n"
    )
    (root / "pkg" / "service.py").write_text(
        "from .policy import evaluate_policy\n\n\ndef decide(context):\n"
        "    return evaluate_policy(context)\n"
    )
    (root / "templates" / "assistant.html").write_text(
        "<p>Where is evaluate_policy implemented?</p>\n"
    )
    (root / "docs" / "examples.md").write_text(
        "Example query: Where is evaluate_policy implemented?\n"
    )


def evaluate() -> dict[str, Any]:
    golden_path = Path(__file__).with_name("code_intelligence_golden.json")
    cases = {item["id"]: item for item in json.loads(golden_path.read_text())["cases"]}
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "repository"
        build_fixture(root)
        db = Database(Path(temporary) / "evaluation.db")
        db.migrate()
        service = CodeIntelligenceService(db, LocalRepositoryProvider(root))
        service.refresh()

        exact = service.query(cases["exact-symbol-definition"]["query"])
        dependency = service.query(cases["dependency-importer"]["query"])
        no_match = service.query(cases["no-match"]["query"])
        false_positive = service.query(cases["ui-copy-does-not-outrank-code"]["query"])
        impact_case = cases["impact-preflight"]
        impact = service.impact_preflight(impact_case["path"], impact_case["symbol"])

    exact_expected = cases["exact-symbol-definition"]["expected_first"]
    metric_results = {
        "exact_symbol_first_citation": bool(exact.sources)
        and exact.sources[0].path == exact_expected["path"]
        and exact.sources[0].edge == exact_expected["edge"]
        and exact.sources[0].rank_tier == exact_expected["rank_tier"],
        "dependency_edges_present": {
            "definition",
            "call_site",
        }
        <= {source.edge for source in dependency.sources},
        "no_match_has_no_citations": len(no_match.sources)
        == cases["no-match"]["expected_source_count"],
        "false_positive_suppressed": bool(false_positive.sources)
        and not false_positive.sources[0].path.startswith(
            tuple(cases["ui-copy-does-not-outrank-code"]["forbidden_first_path_prefixes"])
        ),
        "impact_preflight_grounded": bool(impact["definitions"])
        and impact["definitions"][0]["path"] == impact_case["expected_definition_path"]
        and impact_case["expected_direct_dependent"] in impact["direct_dependents"],
    }
    total = len(metric_results)
    passed = sum(metric_results.values())
    return {
        "status": "MEASURED_SYNTHETIC_CODE_INTELLIGENCE",
        "dataset": {"path": str(golden_path.name), "cases": len(cases), "synthetic": True},
        "metrics": {
            "source_quality_pass_rate": passed / total,
            "exact_symbol_first_citation": float(metric_results["exact_symbol_first_citation"]),
            "dependency_edge_grounding": float(metric_results["dependency_edges_present"]),
            "no_match_honesty": float(metric_results["no_match_has_no_citations"]),
            "false_positive_suppression": float(metric_results["false_positive_suppressed"]),
            "impact_preflight_grounding": float(metric_results["impact_preflight_grounded"]),
        },
        "results": metric_results,
        "limitations": [
            "Synthetic fixture only; this does not measure production repository quality.",
            "No live provider is called; provider summarization quality is not measured.",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2, sort_keys=True))
