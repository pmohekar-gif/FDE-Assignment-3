from pathlib import Path

from warrant.policy import PolicyContext, evaluate_policy, load_policy
from warrant.retrieval import RetrievalResult
from warrant.schemas import ExtractionResult, Verdict

POLICY = load_policy(
    (Path(__file__).parents[2] / "policies" / "default.v1.yaml").read_text()
)


def test_extracted_surface_outside_declared_scope_is_retained_as_risk_signal(client):
    service = client.app.state.service
    db = client.app.state.db
    issue = db.one(
        "SELECT * FROM issues WHERE workspace_id=? AND external_key=?",
        ("ws-demo", "WEB-4519"),
    )
    requester = db.one(
        "SELECT * FROM users WHERE workspace_id=? AND id=?",
        ("ws-demo", "lead-web"),
    )
    outside = "services/auth/keys/signing.py"
    extraction = ExtractionResult(
        reproduction_present=True,
        acceptance_criteria=["copy remains readable"],
        affected_surfaces=["web/reports/EmptyState.tsx", outside],
        data_classes=[],
        external_side_effects=[],
        missing_information=[],
        scope_estimate="small",
        embedded_instruction_detected=False,
        confidence=1.0,
    )
    risk, approvers, is_owner = service._assess_risk(
        "ws-demo",
        issue,
        requester,
        0.0,
        RetrievalResult("HYBRID", 1.0, [], [], []),
        extraction,
        False,
        False,
    )

    assert risk.proposed_surfaces == ["web/reports/EmptyState.tsx"]
    assert risk.features["surfaces_outside_declared_scope"] == [outside]
    assert any(outside in item for item in extraction.missing_information)
    assert risk.evidence_sufficiency < 1.0

    decision = evaluate_policy(
        PolicyContext(risk, requester["id"], is_owner, "v1", "test-sha", approvers, POLICY)
    )
    assert decision.verdict == Verdict.REQUIRE_APPROVAL
    assert "SURFACES_OUTSIDE_DECLARED_SCOPE" in decision.reason_codes
