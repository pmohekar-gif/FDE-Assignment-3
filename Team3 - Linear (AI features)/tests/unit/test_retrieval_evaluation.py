from warrant.evaluation import _retrieval_metrics


def test_labelled_retrieval_metrics_meet_documented_synthetic_targets():
    metrics, cases = _retrieval_metrics()

    assert len(cases) == 4
    assert metrics["retrieval_recall_at_10"] >= 0.85
    assert metrics["possible_duplicate_precision"] >= 0.85
    assert all(case["relevant_hits"] for case in cases)
    assert all(case["duplicate_hits"] for case in cases)
