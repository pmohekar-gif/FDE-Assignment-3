from warrant.evaluation import _brief_grounding_metrics


def test_brief_grounding_has_zero_unsupported_authority_or_contradictions():
    metrics, cases = _brief_grounding_metrics()

    assert len(cases) == 2
    assert {case["actual_source"] for case in cases} == {"model", "structured_fallback"}
    assert metrics["brief_unsupported_authority_count"] == 0
    assert metrics["brief_contradiction_count"] == 0
    assert metrics["brief_required_fact_coverage"] == 1.0
    assert all(case["authority_boundary"]["authorising"] is False for case in cases)
