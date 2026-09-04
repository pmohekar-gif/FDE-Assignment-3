from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .schemas import Consequence, PolicyDecision, Reversibility, RiskAssessment, Verdict


class PolicyValidationError(ValueError):
    def __init__(self, errors: list[dict[str, Any]]) -> None:
        super().__init__("policy validation failed")
        self.errors = errors


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: str = Field(min_length=1, max_length=80)
    operator: Literal["truthy", "eq", "gte", "lt"] = "truthy"
    value: bool | float | str | None = None

    @model_validator(mode="after")
    def value_required_for_comparison(self) -> Condition:
        if self.operator != "truthy" and self.value is None:
            raise ValueError(f"operator {self.operator!r} requires a value")
        return self


class PolicyRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^R-[0-9]{3}$")
    conditions: list[Condition] = Field(min_length=1)
    match: Literal["all", "any"] = "all"
    verdict: Verdict
    reason_codes: list[str] = Field(min_length=1)
    terminal: bool = False
    fail_closed: bool = False


class MatrixCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    reason_code: str = Field(min_length=1)
    rule_id: str = Field(pattern=r"^M-[A-Z0-9-]+$")
    required_features: list[str] = Field(default_factory=list)
    missing_required_verdict: Verdict = Verdict.DENY
    missing_required_reason: str = "REQUIRED_SAFEGUARD_MISSING"


class PolicyDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    allow_sufficiency_threshold: float = Field(ge=0, le=1)
    rules: list[PolicyRule] = Field(min_length=1)
    matrix: dict[Consequence, dict[Reversibility, MatrixCell]]
    tool_grants: dict[Consequence, list[str]]
    never_grantable_tools: list[str] = Field(min_length=1)

    @field_validator("rules")
    @classmethod
    def unique_rule_ids(cls, rules: list[PolicyRule]) -> list[PolicyRule]:
        ids = [rule.id for rule in rules]
        if len(ids) != len(set(ids)):
            raise ValueError("rule ids must be unique")
        return rules

    @model_validator(mode="after")
    def complete_matrix_and_grants(self) -> PolicyDocument:
        missing_consequences = set(Consequence) - set(self.matrix)
        if missing_consequences:
            names = ", ".join(sorted(value.value for value in missing_consequences))
            raise ValueError(f"matrix missing consequences: {names}")
        for consequence, row in self.matrix.items():
            missing = set(Reversibility) - set(row)
            if missing:
                names = ", ".join(sorted(value.value for value in missing))
                raise ValueError(f"matrix.{consequence.value} missing reversibility: {names}")
        missing_grants = set(Consequence) - set(self.tool_grants)
        if missing_grants:
            names = ", ".join(sorted(value.value for value in missing_grants))
            raise ValueError(f"tool_grants missing consequences: {names}")
        never = set(self.never_grantable_tools)
        leaked = {tool for grants in self.tool_grants.values() for tool in grants if tool in never}
        if leaked:
            names = ", ".join(sorted(leaked))
            raise ValueError(f"never-grantable tools present in grants: {names}")
        return self


@dataclass(frozen=True)
class PolicyContext:
    risk: RiskAssessment
    requester_id: str
    requester_is_code_owner: bool
    policy_version: str
    policy_sha: str
    approver_ids: list[str]
    policy: PolicyDocument | None


def load_policy(source: str) -> PolicyDocument:
    """Parse and validate policy YAML without performing I/O or changing state."""
    try:
        raw = yaml.safe_load(source)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        raise PolicyValidationError(
            [
                {
                    "line": mark.line + 1 if mark else None,
                    "column": mark.column + 1 if mark else None,
                    "message": exc.problem or str(exc),
                }
            ]
        ) from exc
    if not isinstance(raw, dict):
        raise PolicyValidationError(
            [{"line": 1, "column": 1, "message": "policy must be a YAML mapping"}]
        )
    try:
        return PolicyDocument.model_validate(raw)
    except ValidationError as exc:
        errors = [
            {
                "line": _find_key_line(source, error["loc"]) or 1,
                "path": ".".join(str(part) for part in error["loc"]),
                "message": error["msg"],
            }
            for error in exc.errors(include_url=False)
        ]
        raise PolicyValidationError(errors) from exc


def _find_key_line(source: str, location: tuple[Any, ...]) -> int | None:
    keys = [str(value) for value in location if not isinstance(value, int)]
    if not keys:
        return None
    key = keys[-1]
    for line_number, line in enumerate(source.splitlines(), 1):
        if line.lstrip().startswith(f"{key}:"):
            return line_number
    return None


def _condition_matches(condition: Condition, features: dict[str, Any]) -> bool:
    actual = features.get(condition.feature)
    if condition.operator == "truthy":
        return bool(actual)
    if condition.operator == "eq":
        return actual == condition.value
    if condition.operator == "gte":
        return isinstance(actual, (int, float)) and actual >= condition.value  # type: ignore[operator]
    if condition.operator == "lt":
        return isinstance(actual, (int, float)) and actual < condition.value  # type: ignore[operator]
    return False


def _failure_decision(context: PolicyContext) -> PolicyDecision:
    return PolicyDecision(
        verdict=Verdict.REQUIRE_APPROVAL,
        reason_codes=["POLICY_UNAVAILABLE"],
        matched_rule_ids=["R-020"],
        approver_ids=context.approver_ids,
        proposed_surfaces=context.risk.proposed_surfaces,
        policy_version=context.policy_version or "unavailable",
        policy_sha=context.policy_sha,
        fail_closed=True,
    )


def evaluate_policy(context: PolicyContext) -> PolicyDecision:
    """Pure deterministic interpreter. AI/provider output cannot set a verdict."""
    policy = context.policy
    if policy is None:
        return _failure_decision(context)
    if policy.version != context.policy_version:
        return _failure_decision(context)

    risk = context.risk
    features = dict(risk.features)
    features.update(
        {
            "evidence_sufficiency": risk.evidence_sufficiency,
            "requester_is_not_code_owner": (
                not context.requester_is_code_owner and bool(risk.proposed_surfaces)
            ),
            "evidence_degraded_or_unknown": bool(features.get("extraction_unavailable"))
            or risk.retrieval_completeness < 1
            or risk.evidence_sufficiency < policy.allow_sufficiency_threshold,
        }
    )
    cell = policy.matrix[risk.consequence][risk.reversibility]
    verdict = cell.verdict
    reasons = [cell.reason_code]
    matched = [cell.rule_id]
    fail_closed = False
    if any(not bool(features.get(name)) for name in cell.required_features):
        verdict = cell.missing_required_verdict
        reasons = [cell.missing_required_reason]

    autonomy = {Verdict.DENY: 0, Verdict.REQUIRE_APPROVAL: 1, Verdict.ALLOW: 2}
    for rule in policy.rules:
        results = [_condition_matches(condition, features) for condition in rule.conditions]
        is_match = all(results) if rule.match == "all" else any(results)
        if not is_match:
            continue
        matched.append(rule.id)
        reasons.extend(rule.reason_codes)
        fail_closed = fail_closed or rule.fail_closed
        if rule.terminal:
            verdict = rule.verdict
            break
        if autonomy[rule.verdict] < autonomy[verdict]:
            verdict = rule.verdict

    return PolicyDecision(
        verdict=verdict,
        reason_codes=list(dict.fromkeys(reasons)),
        matched_rule_ids=list(dict.fromkeys(matched)),
        approver_ids=context.approver_ids,
        proposed_surfaces=risk.proposed_surfaces,
        policy_version=policy.version,
        policy_sha=context.policy_sha,
        fail_closed=fail_closed,
    )


def granted_tools(policy_source: str, consequence: Consequence) -> tuple[list[str], list[str]]:
    policy = load_policy(policy_source)
    never = list(dict.fromkeys(policy.never_grantable_tools))
    allowed = [tool for tool in policy.tool_grants[consequence] if tool not in set(never)]
    return allowed, never


def policy_never_increases_autonomy(healthy: PolicyDecision, degraded: PolicyDecision) -> bool:
    order = {Verdict.DENY: 0, Verdict.REQUIRE_APPROVAL: 1, Verdict.ALLOW: 2}
    return order[degraded.verdict] <= order[healthy.verdict]
