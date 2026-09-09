from __future__ import annotations

import json
from pathlib import Path


def test_code_intelligence_golden_cases_cover_the_refinement_contract():
    path = Path(__file__).parents[2] / "evaluations" / "code_intelligence_golden.json"
    payload = json.loads(path.read_text())

    assert payload["version"] == 1
    cases = {case["id"]: case for case in payload["cases"]}
    expected_case_ids = {
        "exact-symbol-definition",
        "dependency-importer",
        "no-match",
        "ui-copy-does-not-outrank-code",
        "impact-preflight",
    }
    assert expected_case_ids <= set(cases)
    assert cases["exact-symbol-definition"]["expected_first"]["edge"] == "definition"
    assert cases["exact-symbol-definition"]["expected_first"]["rank_tier"] == "exact_definition"
    assert "call_site" in cases["dependency-importer"]["expected_edges"]
    assert "resolved_dependency" in cases["dependency-importer"]["expected_rank_tiers"]
    assert cases["no-match"]["expected_source_count"] == 0
    assert "templates/" in cases["ui-copy-does-not-outrank-code"]["forbidden_first_path_prefixes"]
    assert cases["impact-preflight"]["expected_direct_dependent"] == "pkg/service.py"


def test_code_intelligence_unavailable_copy_is_actionable_and_non_sensitive():
    path = Path(__file__).parents[2] / "evaluations" / "code_intelligence_golden.json"
    unavailable = json.loads(path.read_text())["unavailable_root_copy"]

    assert "REPOSITORY_ROOT" in unavailable["body"]
    assert unavailable["must_not_include"] == [
        "absolute filesystem path",
        "environment value",
        "secret",
    ]
