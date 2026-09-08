import runpy
from pathlib import Path

evaluate = runpy.run_path(
    str(Path(__file__).parents[2] / "evaluations" / "evaluate_code_intelligence.py")
)["evaluate"]


def test_synthetic_code_intelligence_evaluator_measures_all_quality_contracts():
    report = evaluate()

    assert report["status"] == "MEASURED_SYNTHETIC_CODE_INTELLIGENCE"
    assert report["dataset"] == {
        "path": "code_intelligence_golden.json",
        "cases": 5,
        "synthetic": True,
    }
    assert report["metrics"]["source_quality_pass_rate"] == 1.0
    assert all(report["results"].values())
