from __future__ import annotations

from typing import Any

REASON_GLOSSARY: dict[str, str] = {
    "STANDARD_REVERSIBLE_SCOPE": "Routine, reversible work inside an owned scope.",
    "READ_ONLY_SCOPE": "The requested authority is read-only.",
    "PROTECTED_OR_SENSITIVE_SURFACE": "The work touches a protected or sensitive surface.",
    "FINANCIAL_OR_SECURITY_ACTION": "Financial or security authority cannot be delegated.",
    "SECURITY_SENSITIVE": "The mapped surface is security-sensitive and terminally denied.",
    "INJECTION_SIGNAL": "Untrusted text contains an instruction that may be seeking authority.",
    "EXTERNAL_SIDE_EFFECT": "The work can change a system outside the repository.",
    "CONCURRENT_WARRANT": "Another active warrant overlaps the requested surface.",
    "SCOPE_FULLY_HELD_BY_CONCURRENT_WARRANT": (
        "Every bounded surface is held by another active warrant."
    ),
    "SURFACES_OUTSIDE_DECLARED_SCOPE": (
        "Extraction found surfaces the issue did not declare; they were excluded from authority."
    ),
    "CODE_OWNER_REQUIRED": "The requester does not own every proposed surface.",
    "UNTRUSTED_DELEGATION_ORIGIN": "This request arrived through an untrusted content channel.",
    "EVIDENCE_DEGRADED_OR_UNKNOWN": "Evidence is missing, degraded, or below threshold.",
    "SURFACE_MAP_STALE": "The authoritative surface map is marked stale.",
    "PROVIDER_FALLBACK_USED": "Fallback extraction was used and cannot auto-authorise work.",
    "POLICY_UNAVAILABLE": "The policy could not be loaded, so the system failed closed.",
    "ROLLBACK_REQUIRED": "Destructive work has no credible rollback contract.",
    "DESTRUCTIVE_WITH_ROLLBACK": "Destructive work has rollback evidence but needs approval.",
    "DESTRUCTIVE_MANUAL_ROLLBACK": "Destructive work with manual rollback is denied.",
    "IRREVERSIBLE_EXTERNAL_SIDE_EFFECT": "An irreversible external effect is denied.",
    "UNKNOWN_CONSEQUENCE": "The consequence cannot be classified safely.",
}

RULE_GLOSSARY: dict[str, str] = {
    "R-001": "Terminal deny for a security-sensitive mapped surface.",
    "R-002": "Requires review for protected or sensitive surfaces.",
    "R-003": "Treats prompt-injection signals as untrusted evidence.",
    "R-005": "Requires review for external side effects.",
    "R-006": "Requires review when delegation origin is untrusted.",
    "R-007": "Serialises overlapping active warrants through human review.",
    "R-012": "Requires ownership or a named approver.",
    "R-020": "Fails closed when evidence is degraded or insufficient.",
    "R-021": "Fails closed when the surface map is stale.",
    "R-022": "Fails closed after provider fallback.",
    "R-023": "Prevents issuance when concurrency removes the whole scope.",
    "R-024": "Escalates extracted surfaces that the issue did not declare.",
}

REMEDIATION_BY_REASON: dict[str, str] = {
    "SECURITY_SENSITIVE": (
        "Reduce the request to a non-security surface or use the organisation's dedicated "
        "security-change process; this rule cannot be overridden here."
    ),
    "FINANCIAL_OR_SECURITY_ACTION": (
        "Remove financial/security authority from the delegation and submit a newly scoped request."
    ),
    "ROLLBACK_REQUIRED": "Add a concrete rollback plan and submit a fresh delegation.",
    "IRREVERSIBLE_EXTERNAL_SIDE_EFFECT": (
        "Make the external action reversible or keep execution in a separately controlled process."
    ),
}


def explain_codes(codes: list[str]) -> list[dict[str, str]]:
    return [
        {"code": code, "explanation": REASON_GLOSSARY.get(code, code.replace("_", " ").title())}
        for code in codes
    ]


def explain_rules(rule_ids: list[str]) -> list[dict[str, str]]:
    return [
        {
            "id": rule_id,
            "explanation": RULE_GLOSSARY.get(
                rule_id,
                "Baseline consequence and reversibility matrix cell used for this verdict."
                if rule_id.startswith("M-")
                else "Deterministic policy rule matched this delegation.",
            ),
        }
        for rule_id in rule_ids
    ]


def pipeline_trace(detail: dict[str, Any], recorded: bool) -> list[dict[str, str]]:
    has = lambda key: bool(detail.get(key))  # noqa: E731
    warrant = detail.get("warrant")
    verification = detail.get("verification")
    verdict = (detail.get("decision") or {}).get("verdict")
    stages = [
        ("intake", True, "Request persisted"),
        ("normalise", has("extraction"), "Content redacted and injection-scored"),
        ("retrieve", has("retrieval"), "Context and overlaps retrieved"),
        ("extract", has("extraction"), "Structured facts extracted"),
        ("risk", has("risk_assessment"), "Deterministic features assembled"),
        ("policy", has("decision"), f"Verdict: {verdict or 'pending'}"),
        (
            "warrant",
            bool(warrant),
            "Issued" if warrant else ("Blocked by policy" if verdict == "DENY" else "Pending"),
        ),
        ("verify", bool(verification), "Evidence checked" if verification else "Not reached"),
        ("record", recorded, "Audit record appended" if recorded else "Pending"),
    ]
    return [
        {"name": name, "state": "complete" if complete else "pending", "detail": detail_text}
        for name, complete, detail_text in stages
    ]
