from pathlib import Path

from warrant.policy import (
    PolicyContext,
    evaluate_policy,
    granted_tools,
    load_policy,
    policy_never_increases_autonomy,
)
from warrant.schemas import Consequence, Reversibility, RiskAssessment, Verdict

POLICY = (Path(__file__).parents[2] / "policies" / "default.v1.yaml").read_text()
DOCUMENT = load_policy(POLICY)


def risk(
    features=None,
    sufficiency=0.9,
    completeness=1.0,
    consequence=Consequence.INTERNAL_MODIFICATION,
    reversibility=Reversibility.AUTOMATIC,
):
    return RiskAssessment(
        consequence=consequence,
        reversibility=reversibility,
        composite_risk="LOW",
        evidence_sufficiency=sufficiency,
        features=features or {},
        proposed_surfaces=["web/reports/View.tsx"],
        retrieval_mode="HYBRID" if completeness == 1 else "LEXICAL_ONLY",
        retrieval_completeness=completeness,
    )


def decide(value, owner=True):
    return evaluate_policy(
        PolicyContext(value, "user", owner, "v1", "test-sha", ["lead"], DOCUMENT)
    )


def test_standard_reversible_work_is_allowed():
    assert decide(risk()).verdict == Verdict.ALLOW


def test_protected_or_external_work_requires_approval():
    assert decide(risk({"protected_surface": True})).verdict == Verdict.REQUIRE_APPROVAL
    assert decide(risk({"external_side_effect": True})).verdict == Verdict.REQUIRE_APPROVAL


def test_irreversible_and_security_sensitive_rules_are_terminal_denies():
    irreversible = risk(reversibility=Reversibility.IRREVERSIBLE)
    assert decide(irreversible).verdict == Verdict.REQUIRE_APPROVAL
    security = decide(risk({"security_sensitive": True}))
    assert security.verdict == Verdict.DENY
    assert "R-001" in security.matched_rule_ids


def test_matrix_has_required_irreversible_and_destructive_divergences():
    external = decide(
        risk(
            {"external_side_effect": True, "irreversible": True},
            consequence=Consequence.EXTERNAL_SIDE_EFFECT,
            reversibility=Reversibility.IRREVERSIBLE,
        )
    )
    assert external.verdict == Verdict.DENY
    assert "IRREVERSIBLE_EXTERNAL_SIDE_EFFECT" in external.reason_codes

    with_rollback = decide(
        risk(
            {"destructive": True, "rollback_available": True},
            consequence=Consequence.DESTRUCTIVE,
        )
    )
    without_rollback = decide(
        risk(
            {"destructive": True, "rollback_available": False},
            consequence=Consequence.DESTRUCTIVE,
        )
    )
    assert with_rollback.verdict == Verdict.REQUIRE_APPROVAL
    assert without_rollback.verdict == Verdict.DENY
    assert "ROLLBACK_REQUIRED" in without_rollback.reason_codes


def test_unknown_or_degraded_evidence_fails_closed():
    degraded = decide(risk({"extraction_unavailable": True}, 0.35, 0.5))
    assert degraded.verdict == Verdict.REQUIRE_APPROVAL
    assert degraded.fail_closed is True
    fallback = decide(risk({"provider_fallback_used": True}))
    assert fallback.verdict == Verdict.REQUIRE_APPROVAL
    assert fallback.fail_closed is True


def test_injection_cannot_create_authority():
    result = decide(risk({"injection_signal": 0.99}))
    assert result.verdict == Verdict.REQUIRE_APPROVAL
    assert "R-003" in result.matched_rule_ids


def test_failure_monotonicity_never_increases_autonomy():
    healthy = decide(risk())
    for features in ({"extraction_unavailable": True}, {"policy_unavailable": True}):
        degraded = decide(risk(features, 0.3, 0.5))
        assert policy_never_increases_autonomy(healthy, degraded)


def test_yaml_edit_changes_deterministic_output():
    input_risk = risk({"injection_signal": 0.99})
    assert decide(input_risk).verdict == Verdict.REQUIRE_APPROVAL
    edited = POLICY.replace(
        "verdict: REQUIRE_APPROVAL\n    reason_codes: [INJECTION_SIGNAL]",
        "verdict: DENY\n    reason_codes: [LOCAL_POLICY_CHANGE]",
        1,
    ).replace("version: v1", "version: v-test", 1)
    document = load_policy(edited)
    result = evaluate_policy(
        PolicyContext(input_risk, "user", True, "v-test", "edited-sha", ["lead"], document)
    )
    assert result.verdict == Verdict.DENY
    assert "LOCAL_POLICY_CHANGE" in result.reason_codes


def test_interpreter_does_not_parse_or_perform_io(monkeypatch):
    monkeypatch.setattr(
        "warrant.policy.yaml.safe_load",
        lambda _: (_ for _ in ()).throw(AssertionError("unexpected policy load")),
    )
    assert decide(risk()).verdict == Verdict.ALLOW


def test_invalid_policy_fails_closed_as_unavailable():
    result = evaluate_policy(
        PolicyContext(risk(), "user", True, "broken", "broken-sha", ["lead"], None)
    )
    assert result.verdict == Verdict.REQUIRE_APPROVAL
    assert result.reason_codes == ["POLICY_UNAVAILABLE"]
    assert result.fail_closed is True


def test_read_only_is_default_capability_and_never_grantable_is_yaml_driven():
    allowed, denied = granted_tools(POLICY, Consequence.READ_ONLY)
    assert allowed == ["read_repo"]
    assert {"merge_pr", "deploy", "migrate_db", "rotate_secret", "delete_data"} <= set(denied)
