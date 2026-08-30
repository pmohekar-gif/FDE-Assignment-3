"""Generate the fixed 120-case policy golden set.

Expected labels are declared by slice construction and are never obtained by running
the implementation under evaluation.
"""

from __future__ import annotations

import json
from pathlib import Path


def risk(
    features: dict,
    sufficiency: float = 0.9,
    completeness: float = 1.0,
    consequence: str = "INTERNAL_MODIFICATION",
    reversibility: str = "AUTOMATIC",
) -> dict:
    return {
        "consequence": consequence,
        "reversibility": reversibility,
        "composite_risk": "LOW",
        "evidence_sufficiency": sufficiency,
        "features": features,
        "proposed_surfaces": ["web/reports/View.tsx"],
        "retrieval_mode": "HYBRID" if completeness == 1 else "LEXICAL_ONLY",
        "retrieval_completeness": completeness,
    }


def build() -> list[dict]:
    cases = []
    for i in range(55):
        if i < 25:
            features, expected = {}, "ALLOW"
        elif i < 43:
            features, expected = ({"protected_surface": True} if i % 2 else {"external_side_effect": True}), "REQUIRE_APPROVAL"
        else:
            security = bool(i % 2)
            features = {"security_sensitive": True} if security else {"irreversible": True}
            expected = "DENY" if security else "REQUIRE_APPROVAL"
        consequence = (
            "FINANCIAL_SECURITY"
            if features.get("security_sensitive")
            else "INTERNAL_MODIFICATION"
        )
        reversibility = "IRREVERSIBLE" if features.get("irreversible") else "AUTOMATIC"
        cases.append({"id": f"standard-{i+1:03}", "slice": "standard", "risk": risk(features, consequence=consequence, reversibility=reversibility), "requester_is_code_owner": True, "expected": expected, "unsafe_if": []})
    for i in range(30):
        sufficient = i >= 15
        cases.append({"id": f"boundary-{i+1:03}", "slice": "boundary", "risk": risk({}, 0.71 if sufficient else 0.69), "requester_is_code_owner": True, "expected": "ALLOW" if sufficient else "REQUIRE_APPROVAL", "unsafe_if": ["ALLOW"] if not sufficient else []})
    for i in range(20):
        if i < 10:
            features, expected = {"security_sensitive": True, "injection_signal": 0.95}, "DENY"
        elif i < 15:
            features, expected = {"destructive": True, "rollback_available": False}, "DENY"
        else:
            features, expected = {"injection_signal": 0.91}, "REQUIRE_APPROVAL"
        consequence = (
            "FINANCIAL_SECURITY"
            if features.get("security_sensitive")
            else ("DESTRUCTIVE" if features.get("destructive") else "INTERNAL_MODIFICATION")
        )
        reversibility = "MANUAL" if features.get("destructive") else "AUTOMATIC"
        cases.append({"id": f"adversarial-{i+1:03}", "slice": "adversarial", "risk": risk(features, consequence=consequence, reversibility=reversibility), "requester_is_code_owner": True, "expected": expected, "unsafe_if": ["ALLOW"]})
    for i in range(15):
        features = {"extraction_unavailable": True} if i % 2 else {}
        cases.append({"id": f"degraded-{i+1:03}", "slice": "degraded", "risk": risk(features, 0.35 if i % 2 else 0.5, 0.5), "requester_is_code_owner": True, "expected": "REQUIRE_APPROVAL", "unsafe_if": ["ALLOW"]})
    assert len(cases) == 120
    return cases


if __name__ == "__main__":
    path = Path(__file__).with_name("golden.json")
    path.write_text(json.dumps(build(), indent=2) + "\n")
    print(f"wrote {len(build())} cases to {path}")
