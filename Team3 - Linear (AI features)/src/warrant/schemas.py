from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


class Consequence(str, Enum):
    READ_ONLY = "READ_ONLY"
    INTERNAL_MODIFICATION = "INTERNAL_MODIFICATION"
    EXTERNAL_SIDE_EFFECT = "EXTERNAL_SIDE_EFFECT"
    DESTRUCTIVE = "DESTRUCTIVE"
    FINANCIAL_SECURITY = "FINANCIAL_SECURITY"
    UNKNOWN = "UNKNOWN"


class Reversibility(str, Enum):
    AUTOMATIC = "AUTOMATIC"
    MANUAL = "MANUAL"
    IRREVERSIBLE = "IRREVERSIBLE"
    UNKNOWN = "UNKNOWN"


class VerificationValue(str, Enum):
    PASS = "PASS"
    PASS_WITH_EXCEPTIONS = "PASS_WITH_EXCEPTIONS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class DelegationCreate(BaseModel):
    issue_ref: str = Field(min_length=2, max_length=80)
    requester_id: str = Field(min_length=2, max_length=80)
    target_agent_id: str = Field(min_length=2, max_length=80)
    idempotency_key: str = Field(min_length=4, max_length=120)


class RelatedIssueTelemetry(BaseModel):
    event: Literal["viewed", "selected"]
    source_issue_ref: str = Field(min_length=2, max_length=80)
    suggested_issue_ref: str | None = Field(default=None, min_length=2, max_length=80)
    relation: Literal["possible_duplicate", "related"] | None = None
    rank: int | None = Field(default=None, ge=1, le=10)
    result_count: int | None = Field(default=None, ge=0, le=10)

    @model_validator(mode="after")
    def selection_has_suggestion(self) -> "RelatedIssueTelemetry":
        if self.event == "selected" and not self.suggested_issue_ref:
            raise ValueError("selected events require suggested_issue_ref")
        return self


class SemanticSearchTelemetry(BaseModel):
    event: Literal["viewed", "selected"]
    query_length: int = Field(ge=2, le=300)
    result_count: int = Field(ge=0, le=50)
    team_filtered: bool
    selected_issue_ref: str | None = Field(default=None, min_length=2, max_length=80)
    rank: int | None = Field(default=None, ge=1, le=50)

    @model_validator(mode="after")
    def selection_has_issue_and_rank(self) -> "SemanticSearchTelemetry":
        if self.event == "selected" and (not self.selected_issue_ref or self.rank is None):
            raise ValueError("selected events require selected_issue_ref and rank")
        return self


class DelegationBriefTelemetry(BaseModel):
    event: Literal["viewed"] = "viewed"
    delegation_id: str = Field(min_length=4, max_length=80)
    prose_source: Literal["model", "structured_fallback"]
    stale: bool


class TriageApplication(BaseModel):
    expected_revision: int = Field(ge=1)
    team: str = Field(min_length=1, max_length=80)
    priority: Literal["urgent", "high", "medium", "low"]
    labels: list[str] = Field(max_length=12)

    @field_validator("labels")
    @classmethod
    def clean_labels(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip().lower()[:40] for value in values if value.strip()]
        return list(dict.fromkeys(cleaned))


class TriageTelemetry(BaseModel):
    issue_ref: str = Field(min_length=2, max_length=80)
    retrieval_mode: Literal["HYBRID", "LEXICAL_ONLY"]


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reproduction_present: bool | None
    acceptance_criteria: list[str] = Field(max_length=12)
    affected_surfaces: list[str] = Field(max_length=20)
    data_classes: list[str] = Field(max_length=12)
    external_side_effects: list[str] = Field(max_length=12)
    missing_information: list[str] = Field(max_length=12)
    scope_estimate: Literal["small", "medium", "large", "unknown"]
    embedded_instruction_detected: bool
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator(
        "acceptance_criteria",
        "affected_surfaces",
        "data_classes",
        "external_side_effects",
        "missing_information",
    )
    @classmethod
    def no_blank_items(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip()[:300] for value in values if value.strip()]
        return list(dict.fromkeys(cleaned))


class RiskAssessment(BaseModel):
    consequence: Consequence
    reversibility: Reversibility
    composite_risk: str
    evidence_sufficiency: float = Field(ge=0, le=1)
    features: dict[str, Any]
    proposed_surfaces: list[str]
    retrieval_mode: str
    retrieval_completeness: float


class PolicyDecision(BaseModel):
    verdict: Verdict
    reason_codes: list[str]
    matched_rule_ids: list[str]
    approver_ids: list[str]
    proposed_surfaces: list[str]
    policy_version: str
    policy_sha: str
    fail_closed: bool = False


class HumanDecision(BaseModel):
    action: Literal["approve", "deny", "narrow", "defer"]
    approver_id: str = Field(min_length=2, max_length=80)
    narrowed_surfaces: list[str] | None = None
    rationale: str | None = Field(default=None, max_length=1000)


class EvidenceArtifact(BaseModel):
    type: Literal["test", "diff", "screenshot", "log", "report", "other"]
    ref: str = Field(min_length=1, max_length=240)
    digest: str | None = Field(default=None, max_length=128)


class EvidenceSubmission(BaseModel):
    nonce: str = Field(min_length=16, max_length=200)
    files: list[str] = Field(max_length=100)
    artifacts: list[EvidenceArtifact] = Field(max_length=40)
    test_output: str = Field(max_length=20_000)
    claimed_criteria: list[str] = Field(max_length=20)
    notes: str | None = Field(default=None, max_length=4000)


class CriterionJudgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: str
    status: Literal["satisfied", "not_satisfied", "inconclusive"]
    citation: str | None


class JudgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[CriterionJudgement]
    abstained: bool
    summary: str = Field(max_length=1000)


class BriefNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=1200)
    evidence_notes: list[str] = Field(max_length=8)
    human_next_steps: list[str] = Field(max_length=8)


class WarrantView(BaseModel):
    id: str
    delegation_id: str
    scope_surfaces: list[str]
    allowed_tools: list[str]
    denied_tools: list[str]
    evidence_contract: list[str]
    authority_user_id: str
    issued_at: datetime
    expires_at: datetime
    status: str


class WebhookEnvelope(BaseModel):
    issue_ref: str
    requester_id: str
    target_agent_id: str


class PolicySource(BaseModel):
    yaml_source: str = Field(min_length=1, max_length=200_000)


class PolicySimulationSource(PolicySource):
    against: Literal["last_n_delegations"] = "last_n_delegations"
    n: int = Field(default=50, ge=1, le=500)


class WarrantRevocation(BaseModel):
    actor_id: str = Field(min_length=2, max_length=80)
    reason: str = Field(min_length=3, max_length=1000)
