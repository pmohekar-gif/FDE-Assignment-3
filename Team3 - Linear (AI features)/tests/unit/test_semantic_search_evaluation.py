from warrant.evaluation import _search_metrics


def test_labelled_semantic_search_slices_meet_documented_synthetic_targets():
    metrics, cases = _search_metrics()

    assert len(cases) == 6
    assert metrics["semantic_search_recall_at_10"] >= 0.85
    assert metrics["exact_key_search_success"] == 1.0
    assert all(case["hit"] for case in cases)
