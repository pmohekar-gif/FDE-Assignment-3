from warrant.evaluation import _triage_metrics


def test_labelled_triage_metrics_meet_documented_synthetic_targets():
    metrics, cases = _triage_metrics()

    assert len(cases) == 3
    assert metrics["triage_team_accuracy"] >= 0.85
    assert metrics["triage_priority_macro_f1"] >= 0.75
    assert metrics["triage_label_precision"] >= 0.80
    assert metrics["triage_label_recall"] >= 0.80
