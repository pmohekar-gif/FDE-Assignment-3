from __future__ import annotations

import fnmatch
import hashlib
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .audit import AuditLedger
from .config import PROJECT_ROOT, Settings
from .db import Database
from .policy import (
    PolicyContext,
    PolicyValidationError,
    evaluate_policy,
    granted_tools,
    load_policy,
)
from .providers import LLMProvider, ProviderError, ProviderMalformed
from .retrieval import RetrievalResult, RetrievalService
from .schemas import (
    Consequence,
    DelegationCreate,
    EvidenceSubmission,
    ExtractionResult,
    HumanDecision,
    PolicyDecision,
    Reversibility,
    RiskAssessment,
    TriageApplication,
    Verdict,
    VerificationValue,
)
from .security import normalise_untrusted


def intersect_declared_scope(proposed: list[str], declared: list[str]) -> list[str]:
    """Return the narrower pattern wherever proposed and declared scopes overlap."""
    intersection: list[str] = []
    for candidate in proposed:
        for boundary in declared:
            if fnmatch.fnmatch(candidate, boundary):
                intersection.append(candidate)
            elif fnmatch.fnmatch(boundary, candidate):
                intersection.append(boundary)
    return list(dict.fromkeys(intersection))


def partition_declared_scope(
    extracted: list[str], declared: list[str]
) -> tuple[list[str], list[str]]:
    """Return the bounded scope and extracted surfaces that do not overlap it."""
    bounded = intersect_declared_scope(extracted, declared)
    outside = [
        candidate
        for candidate in extracted
        if not any(
            fnmatch.fnmatch(candidate, boundary) or fnmatch.fnmatch(boundary, candidate)
            for boundary in declared
        )
    ]
    return bounded, list(dict.fromkeys(outside))


class DomainError(RuntimeError):
    status_code = 400


class NotFound(DomainError):
    status_code = 404


class Forbidden(DomainError):
    status_code = 403


class Unauthorized(DomainError):
    status_code = 401


class Conflict(DomainError):
    status_code = 409


class Gone(DomainError):
    status_code = 410

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details


class InvalidEvidence(DomainError):
    status_code = 422

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details


class InvalidPolicy(DomainError):
    status_code = 422

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        super().__init__("policy validation failed")
        self.errors = errors


class WarrantService:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        provider: LLMProvider,
        retrieval: RetrievalService | None = None,
    ):
        self.db = db
        self.settings = settings
        self.provider = provider
        self.retrieval = retrieval or RetrievalService(db)
        self.audit = AuditLedger(db)

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def new_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:16]}"

    def telemetry(
        self, workspace_id: str, name: str, subject_id: str | None, **attributes: Any
    ) -> None:
        self.db.execute(
            "INSERT INTO telemetry_events VALUES (?,?,?,?,?,?)",
            (
                self.new_id("te"),
                workspace_id,
                name,
                subject_id,
                Database.dumps(attributes),
                self.now(),
            ),
        )

    def record_usage(
        self,
        workspace_id: str,
        delegation_id: str,
        operation: str,
        response: Any | None,
        error: Exception | None = None,
    ) -> None:
        self.db.execute(
            "INSERT INTO model_usage "
            "(id,workspace_id,delegation_id,operation,provider,model,input_tokens,"
            "output_tokens,estimated_cost_usd,latency_ms,success,error_class,"
            "reasoning_tokens,total_tokens,reported_cost_usd,serving_provider,"
            "structured_output_mode,schema_repair_count,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                self.new_id("mu"),
                workspace_id,
                delegation_id,
                operation,
                getattr(response, "provider", self.provider.name),
                getattr(response, "model", self.provider.model),
                getattr(response, "input_tokens", None),
                getattr(response, "output_tokens", None),
                getattr(response, "estimated_cost_usd", None),
                getattr(response, "latency_ms", 0),
                0 if error else 1,
                type(error).__name__ if error else None,
                getattr(response, "reasoning_tokens", None),
                getattr(response, "total_tokens", None),
                getattr(response, "reported_cost_usd", None),
                getattr(response, "serving_provider", None),
                getattr(response, "structured_output_mode", None),
                getattr(response, "schema_repair_count", 0),
                self.now(),
            ),
        )
        repairs = getattr(response, "schema_repair_count", 0) if response else 0
        # Fire on every call (including failures with repairs=0) so the metric
        # denominator is always accurate; logging only on repairs > 0 understates
        # the rate precisely when failures are most important to track.
        self.telemetry(
            workspace_id,
            "schema_repair",
            delegation_id,
            operation=operation,
            provider=getattr(response, "provider", self.provider.name),
            model=getattr(response, "model", self.provider.model),
            structured_output_mode=getattr(response, "structured_output_mode", None),
            count=repairs,
        )

    def _workspace_resource(
        self, table: str, resource_id: str, workspace_id: str
    ) -> dict[str, Any]:
        if table not in {"users", "agents", "issues", "delegations", "warrants"}:
            raise ValueError("invalid repository table")
        row = self.db.one(
            f"SELECT * FROM {table} WHERE id=? AND workspace_id=?", (resource_id, workspace_id)
        )
        if not row:
            raise NotFound("resource not found")
        return row

    def apply_triage(
        self,
        workspace_id: str,
        issue_ref: str,
        actor_id: str,
        application: TriageApplication,
        recommendation: dict[str, Any],
    ) -> dict[str, Any]:
        actor = self.db.one(
            "SELECT id FROM users WHERE id=? AND workspace_id=?", (actor_id, workspace_id)
        )
        if actor is None:
            raise Forbidden("a valid workspace user must apply triage")
        issue = self.db.one(
            "SELECT * FROM issues WHERE workspace_id=? AND external_key=?",
            (workspace_id, issue_ref),
        )
        if issue is None:
            raise NotFound("issue not found")
        team_exists = self.db.one(
            "SELECT 1 AS present FROM issues WHERE workspace_id=? AND team=? LIMIT 1",
            (workspace_id, application.team),
        )
        if team_exists is None:
            raise DomainError("team is not available in this workspace")
        with self.db.transaction() as connection:
            cursor = connection.execute(
                "UPDATE issues SET team=?,priority=?,labels_json=?,"
                "revision=revision+1,updated_at=? "
                "WHERE id=? AND workspace_id=? AND revision=?",
                (
                    application.team,
                    application.priority,
                    Database.dumps(application.labels),
                    self.now(),
                    issue["id"],
                    workspace_id,
                    application.expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise Conflict("issue revision changed; review triage again")
        updated = self.db.one(
            "SELECT external_key,team,priority,labels_json,revision FROM issues WHERE id=?",
            (issue["id"],),
        )
        if updated is None:  # pragma: no cover - guarded by the successful revision update
            raise NotFound("issue not found after triage update")
        event = self.audit.append(
            workspace_id,
            "triage_applied",
            "user",
            actor_id,
            "issue",
            issue["id"],
            {
                "issue_ref": issue_ref,
                "recommendation": recommendation,
                "previous": {
                    "team": issue["team"],
                    "priority": issue["priority"],
                    "labels": Database.loads(issue["labels_json"], []),
                    "revision": issue["revision"],
                },
                "applied": {
                    "team": application.team,
                    "priority": application.priority,
                    "labels": application.labels,
                    "revision": updated["revision"],
                },
            },
        )
        labels = Database.loads(updated.pop("labels_json"), [])
        return {
            **updated,
            "labels": labels,
            "audit_event_id": event["id"],
            "audit_seq": event["seq"],
        }

    def create_delegation(
        self,
        workspace_id: str,
        request: DelegationCreate,
        source: str = "ui",
        untrusted_origin: bool = False,
    ) -> dict[str, Any]:
        existing = self.db.one(
            "SELECT id FROM delegations WHERE workspace_id=? AND delivery_id=?",
            (workspace_id, request.idempotency_key),
        )
        if existing:
            result = self.get_delegation(existing["id"], workspace_id)
            result["idempotent_replay"] = True
            return result
        issue = self.db.one(
            "SELECT * FROM issues WHERE workspace_id=? AND (external_key=? OR id=?)",
            (workspace_id, request.issue_ref, request.issue_ref),
        )
        if not issue:
            raise NotFound("issue not found")
        requester = self._workspace_resource("users", request.requester_id, workspace_id)
        agent = self._workspace_resource("agents", request.target_agent_id, workspace_id)
        if agent["status"] != "active":
            raise InvalidEvidence("target agent is not active")

        delegation_id = self.new_id("dlg")
        now = self.now()
        self.db.execute(
            "INSERT INTO delegations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                delegation_id,
                workspace_id,
                issue["id"],
                requester["id"],
                agent["id"],
                source,
                request.idempotency_key,
                int(untrusted_origin),
                "processing",
                now,
                now,
            ),
        )
        self.audit.append(
            workspace_id,
            "delegation_received",
            "human" if source == "ui" else "tracker",
            requester["id"],
            "delegation",
            delegation_id,
            {"issue_ref": issue["external_key"], "agent_id": agent["id"], "source": source},
        )
        self.telemetry(workspace_id, "delegation_received", delegation_id, source=source)
        return self._process(delegation_id, workspace_id, issue, requester)

    def _process(
        self,
        delegation_id: str,
        workspace_id: str,
        issue: dict[str, Any],
        requester: dict[str, Any],
    ) -> dict[str, Any]:
        normalised = normalise_untrusted(issue["title"], issue["body_normalised"])
        self.audit.append(
            workspace_id,
            "content_normalised",
            "system",
            "normaliser",
            "delegation",
            delegation_id,
            {
                "redactions": normalised.redactions,
                "injection_score": normalised.injection_score,
                "raw_content_stored": False,
            },
        )
        retrieval = self.retrieval.retrieve(workspace_id, issue)

        extraction: ExtractionResult | None = None
        extraction_status = "ok"
        response = None
        error: Exception | None = None
        prompt_material = Database.dumps(
            {
                "prompt_version": "extract-v1",
                "text": normalised.text,
                "path_hints": Database.loads(issue["path_hints_json"], []),
                "candidate_ids": [item["issue_id"] for item in retrieval.candidates],
            }
        )
        prompt_hash = hashlib.sha256(prompt_material.encode()).hexdigest()
        cached = self.db.one(
            "SELECT * FROM extraction_cache WHERE issue_id=? AND issue_revision=? "
            "AND prompt_hash=?",
            (issue["id"], issue["revision"], prompt_hash),
        )
        if cached:
            extraction = ExtractionResult.model_validate_json(cached["result_json"])
            extraction_status = "cached"
            self.telemetry(workspace_id, "extraction_cache_hit", delegation_id)
        else:
            try:
                response = self.provider.extract(
                    normalised.text,
                    Database.loads(issue["path_hints_json"], []),
                    retrieval.candidates,
                )
                if not isinstance(response.value, ExtractionResult):
                    raise ProviderMalformed("extract provider returned the wrong schema")
                extraction = response.value
            except (ProviderError, ProviderMalformed) as exc:
                extraction_status = "unavailable"
                error = exc
            self.record_usage(
                workspace_id, delegation_id, "extract_delegation_facts", response, error
            )
            if extraction and not getattr(response, "degraded", False):
                self.db.execute(
                    "INSERT OR REPLACE INTO extraction_cache VALUES (?,?,?,?,?,?,?)",
                    (
                        issue["id"],
                        issue["revision"],
                        prompt_hash,
                        extraction.model_dump_json(),
                        getattr(response, "provider", self.provider.name),
                        getattr(response, "model", self.provider.model),
                        self.now(),
                    ),
                )
        self.db.execute(
            "INSERT INTO extractions VALUES (?,?,?,?,?,?,?,?)",
            (
                delegation_id,
                extraction_status,
                extraction.model_dump_json() if extraction else None,
                cached["provider"] if cached else getattr(response, "provider", self.provider.name),
                cached["model"] if cached else getattr(response, "model", self.provider.model),
                prompt_hash,
                getattr(response, "latency_ms", 0),
                self.now(),
            ),
        )
        derived_surfaces = (
            extraction.affected_surfaces
            if extraction
            else Database.loads(issue["path_hints_json"], [])
        )
        retrieval = RetrievalResult(
            retrieval.mode,
            retrieval.completeness,
            retrieval.candidates,
            retrieval.surfaces,
            self.retrieval.find_overlaps(workspace_id, derived_surfaces),
        )
        self.db.execute(
            "INSERT INTO retrieval_evidence VALUES (?,?,?,?,?,?)",
            (
                delegation_id,
                retrieval.mode,
                retrieval.completeness,
                Database.dumps(retrieval.candidates),
                Database.dumps(retrieval.overlaps),
                self.now(),
            ),
        )
        delegation = self._workspace_resource("delegations", delegation_id, workspace_id)
        risk, approvers, is_owner = self._assess_risk(
            workspace_id,
            issue,
            requester,
            normalised.injection_score,
            retrieval,
            extraction,
            bool(delegation["untrusted_origin"]),
            bool(response and response.degraded),
        )
        if extraction is not None:
            # _assess_risk can add deterministic scope-discrepancy evidence. Persist
            # that enriched extraction in both the delegation record and its cache.
            result_json = extraction.model_dump_json()
            self.db.execute(
                "UPDATE extractions SET result_json=? WHERE delegation_id=?",
                (result_json, delegation_id),
            )
            self.db.execute(
                "UPDATE extraction_cache SET result_json=? WHERE issue_id=? "
                "AND issue_revision=? AND prompt_hash=?",
                (result_json, issue["id"], issue["revision"], prompt_hash),
            )
        self.db.execute(
            "INSERT INTO risk_assessments VALUES (?,?,?)",
            (delegation_id, risk.model_dump_json(), self.now()),
        )
        policy = self._active_policy(workspace_id)
        started = time.perf_counter()
        policy_document = None
        if not policy or self.settings.fixture_failure == "policy_unloadable":
            risk.features["policy_unavailable"] = True
            policy_version, policy_sha = "unavailable", hashlib.sha256(b"").hexdigest()
        else:
            policy_version, policy_source = policy["version"], policy["yaml_source"]
            policy_sha = policy["sha256"]
            try:
                policy_document = load_policy(policy_source)
            except PolicyValidationError:
                risk.features["policy_unavailable"] = True
        decision = evaluate_policy(
            PolicyContext(
                risk,
                requester["id"],
                is_owner,
                policy_version,
                policy_sha,
                approvers,
                policy_document,
            )
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        self.db.execute(
            "INSERT INTO policy_decisions VALUES (?,?,?,?)",
            (delegation_id, decision.model_dump_json(), self.now(), latency_ms),
        )
        self.audit.append(
            workspace_id,
            "policy_decided",
            "system",
            "policy-engine",
            "delegation",
            delegation_id,
            {
                "verdict": decision.verdict.value,
                "reason_codes": decision.reason_codes,
                "matched_rule_ids": decision.matched_rule_ids,
                "policy_version": decision.policy_version,
                "fail_closed": decision.fail_closed,
            },
        )
        self.telemetry(
            workspace_id,
            "policy_decided",
            delegation_id,
            verdict=decision.verdict.value,
            fail_closed=decision.fail_closed,
        )
        status = "awaiting_approval"
        if decision.verdict == Verdict.DENY:
            status = "denied"
        elif decision.verdict == Verdict.ALLOW:
            self._issue_warrant(
                delegation_id, workspace_id, "system-policy", decision.proposed_surfaces
            )
            status = "warrant_issued"
        self.db.execute(
            "UPDATE delegations SET status=?,updated_at=? WHERE id=?",
            (status, self.now(), delegation_id),
        )
        return self.get_delegation(delegation_id, workspace_id)

    def _assess_risk(
        self,
        workspace_id: str,
        issue: dict[str, Any],
        requester: dict[str, Any],
        injection_score: float,
        retrieval: RetrievalResult,
        extraction: ExtractionResult | None,
        untrusted_origin: bool,
        provider_fallback_used: bool,
    ) -> tuple[RiskAssessment, list[str], bool]:
        declared = Database.loads(issue["path_hints_json"], [])
        extracted = extraction.affected_surfaces if extraction else declared
        proposed, outside_declared = partition_declared_scope(extracted, declared)
        if extraction is not None and outside_declared:
            additions = [
                f"Extracted surface is outside declared scope: {surface}"
                for surface in outside_declared
            ]
            extraction.missing_information = list(
                dict.fromkeys([*extraction.missing_information, *additions])
            )[:12]
        bounded_before_concurrency = list(proposed)
        held = [overlap["surface"] for overlap in retrieval.overlaps]
        proposed = [
            path
            for path in proposed
            if not any(fnmatch.fnmatch(path, item) or fnmatch.fnmatch(item, path) for item in held)
        ]
        surfaces = self.db.all("SELECT * FROM surfaces WHERE workspace_id=?", (workspace_id,))
        matched = [
            surface
            for surface in surfaces
            if any(fnmatch.fnmatch(path, surface["glob"]) for path in proposed)
        ]
        data_classes = set(extraction.data_classes if extraction else [])
        approvers: list[str] = []
        for surface in matched:
            data_classes.update(Database.loads(surface["data_classes_json"], []))
            approvers.extend(Database.loads(surface["owner_ids_json"], []))
        if not approvers:
            approvers = [
                row["id"]
                for row in self.db.all(
                    "SELECT id FROM users WHERE workspace_id=? "
                    "AND role IN ('lead','admin','owner')",
                    (workspace_id,),
                )
            ]
        owner_globs = Database.loads(requester["code_owner_paths_json"], [])
        is_owner = bool(proposed) and all(
            any(fnmatch.fnmatch(path, glob) for glob in owner_globs) for path in proposed
        )
        external = bool(extraction and extraction.external_side_effects)
        destructive_corpus = " ".join(
            [
                issue["title"],
                issue["body_normalised"],
                *Database.loads(issue["labels_json"], []),
                *(extraction.external_side_effects if extraction else []),
                *(extraction.acceptance_criteria if extraction else []),
            ]
        ).lower()
        destructive = any(
            token in destructive_corpus
            for token in (
                "delete",
                "deletion",
                "drop table",
                "destroy",
                "purge",
                "truncate",
                "wipe",
                "revoke all",
            )
        )
        missing_information = extraction.missing_information if extraction else []
        rollback_negated = any(
            phrase in destructive_corpus
            for phrase in ("no rollback", "without rollback", "cannot rollback")
        )
        rollback_available = (
            "rollback" in destructive_corpus
            and not rollback_negated
            and not any("rollback" in item.lower() for item in missing_information)
        )
        security = any(bool(surface["security_sensitive"]) for surface in matched)
        irreversible = any(bool(surface["irreversible"]) for surface in matched)
        sensitive = bool(
            data_classes & {"payment_instrument", "credential", "customer_data", "pii_email"}
        )
        protected = any(bool(surface["protected"]) for surface in matched)
        features: dict[str, Any] = {
            "protected_surface": protected,
            "security_sensitive": security,
            "irreversible": irreversible,
            "sensitive_data": sensitive,
            "external_side_effect": external,
            "destructive": destructive,
            "rollback_available": rollback_available,
            "concurrency_conflict": bool(retrieval.overlaps),
            "scope_fully_held_by_concurrent_warrant": bool(
                bounded_before_concurrency and not proposed and held
            ),
            "surfaces_outside_declared_scope": outside_declared,
            "untrusted_origin": untrusted_origin,
            "surface_map_stale": self.settings.fixture_failure == "stale_surface_map",
            "provider_fallback_used": provider_fallback_used,
            "injection_signal": injection_score,
            "extraction_unavailable": extraction is None,
            "requester_is_code_owner": is_owner,
            "sources": {
                "surface_map": [surface["id"] for surface in matched],
                "model_fields": extraction is not None,
                "overlapping_warrants": retrieval.overlaps,
                "outside_declared_scope": outside_declared,
            },
        }
        sufficiency = retrieval.completeness
        if untrusted_origin:
            sufficiency -= 0.10
        if self.settings.fixture_failure == "stale_surface_map":
            sufficiency = min(sufficiency, 0.5)
        if provider_fallback_used:
            sufficiency = min(sufficiency, 0.5)
        if extraction is None:
            sufficiency = min(sufficiency, 0.35)
        else:
            sufficiency -= min(0.3, len(extraction.missing_information) * 0.08)
            if not proposed or proposed == ["unknown/**"]:
                sufficiency -= 0.2
            if extraction.confidence is not None:
                sufficiency = min(sufficiency, 0.55 + extraction.confidence * 0.45)
        sufficiency = round(max(0, min(1, sufficiency)), 2)
        if security:
            consequence = Consequence.FINANCIAL_SECURITY
        elif destructive:
            consequence = Consequence.DESTRUCTIVE
        elif external:
            consequence = Consequence.EXTERNAL_SIDE_EFFECT
        else:
            consequence = Consequence.INTERNAL_MODIFICATION
        if irreversible:
            reversibility = Reversibility.IRREVERSIBLE
        elif destructive:
            reversibility = Reversibility.AUTOMATIC if rollback_available else Reversibility.MANUAL
        else:
            reversibility = (
                Reversibility.MANUAL if external or protected else Reversibility.AUTOMATIC
            )
        composite = (
            "CRITICAL"
            if security or irreversible
            else ("ELEVATED" if protected or sensitive or external else "LOW")
        )
        return (
            RiskAssessment(
                consequence=consequence,
                reversibility=reversibility,
                composite_risk=composite,
                evidence_sufficiency=sufficiency,
                features=features,
                proposed_surfaces=proposed,
                retrieval_mode=retrieval.mode,
                retrieval_completeness=retrieval.completeness,
            ),
            list(dict.fromkeys(approvers)),
            is_owner,
        )

    def _active_policy(self, workspace_id: str) -> dict[str, Any] | None:
        return self.db.one(
            "SELECT p.* FROM policies p JOIN workspaces w "
            "ON w.id=p.workspace_id AND w.policy_version_active=p.version "
            "WHERE p.workspace_id=?",
            (workspace_id,),
        )

    def require_admin(self, workspace_id: str, actor_id: str) -> dict[str, Any]:
        actor = self.db.one(
            "SELECT * FROM users WHERE id=? AND workspace_id=?", (actor_id, workspace_id)
        )
        if not actor or actor["role"] not in {"admin", "owner"}:
            raise Forbidden("admin or owner role required")
        return actor

    @staticmethod
    def _policy_adversarial_risks() -> list[tuple[str, RiskAssessment]]:
        def risk(
            consequence: Consequence,
            reversibility: Reversibility,
            features: dict[str, Any],
        ) -> RiskAssessment:
            return RiskAssessment(
                consequence=consequence,
                reversibility=reversibility,
                composite_risk="CRITICAL",
                evidence_sufficiency=1.0,
                features=features,
                proposed_surfaces=["services/example.py"],
                retrieval_mode="HYBRID",
                retrieval_completeness=1.0,
            )

        supplemental = [
            (
                "security_sensitive",
                risk(
                    Consequence.FINANCIAL_SECURITY,
                    Reversibility.AUTOMATIC,
                    {"security_sensitive": True},
                ),
            ),
            (
                "irreversible_external",
                risk(
                    Consequence.EXTERNAL_SIDE_EFFECT,
                    Reversibility.IRREVERSIBLE,
                    {"external_side_effect": True, "irreversible": True},
                ),
            ),
            (
                "destructive_without_rollback",
                risk(
                    Consequence.DESTRUCTIVE,
                    Reversibility.AUTOMATIC,
                    {"destructive": True, "rollback_available": False},
                ),
            ),
            (
                "prompt_injection",
                risk(
                    Consequence.INTERNAL_MODIFICATION,
                    Reversibility.AUTOMATIC,
                    {"injection_signal": 0.99},
                ),
            ),
            (
                "untrusted_origin",
                risk(
                    Consequence.INTERNAL_MODIFICATION,
                    Reversibility.AUTOMATIC,
                    {"untrusted_origin": True},
                ),
            ),
        ]
        golden_path = PROJECT_ROOT / "evaluations" / "golden.json"
        if not golden_path.exists():
            return supplemental
        golden = json.loads(golden_path.read_text())
        slice_cases = [
            (case["id"], RiskAssessment.model_validate(case["risk"]))
            for case in golden
            if case.get("slice") == "adversarial"
        ]
        return slice_cases + supplemental

    def simulate_policy(self, source: str, workspace_id: str, n: int = 50) -> dict[str, Any]:
        try:
            policy = load_policy(source)
        except PolicyValidationError as exc:
            raise InvalidPolicy(exc.errors) from exc
        proposed_sha = hashlib.sha256(source.encode()).hexdigest()
        active = self._active_policy(workspace_id)
        active_document = None
        if active:
            try:
                active_document = load_policy(active["yaml_source"])
            except PolicyValidationError:
                pass

        results = []
        for name, risk in self._policy_adversarial_risks():
            proposed = evaluate_policy(
                PolicyContext(
                    risk,
                    "simulator",
                    True,
                    policy.version,
                    proposed_sha,
                    ["admin-demo"],
                    policy,
                )
            )
            previous = evaluate_policy(
                PolicyContext(
                    risk,
                    "simulator",
                    True,
                    active["version"] if active else "unavailable",
                    active["sha256"] if active else hashlib.sha256(b"").hexdigest(),
                    ["admin-demo"],
                    active_document,
                )
            )
            results.append(
                {
                    "case": name,
                    "previous_verdict": previous.verdict.value,
                    "proposed_verdict": proposed.verdict.value,
                    "newly_allowed": (
                        proposed.verdict == Verdict.ALLOW and previous.verdict != Verdict.ALLOW
                    ),
                    "reason_codes": proposed.reason_codes,
                    "matched_rule_ids": proposed.matched_rule_ids,
                }
            )
        unsafe = [str(result["case"]) for result in results if result["newly_allowed"]]
        if unsafe:
            cases = ", ".join(unsafe)
            raise Conflict(f"policy newly allows adversarial cases: {cases}")

        delegation_rows = self.db.all(
            "SELECT d.id,d.requester_id,r.result_json AS risk_json,"
            "p.result_json AS previous_json FROM delegations d "
            "JOIN risk_assessments r ON r.delegation_id=d.id "
            "JOIN policy_decisions p ON p.delegation_id=d.id "
            "WHERE d.workspace_id=? ORDER BY d.created_at DESC LIMIT ?",
            (workspace_id, n),
        )
        diffs = []
        for row in delegation_rows:
            risk = RiskAssessment.model_validate_json(row["risk_json"])
            previous = PolicyDecision.model_validate_json(row["previous_json"])
            proposed = evaluate_policy(
                PolicyContext(
                    risk,
                    row["requester_id"],
                    bool(risk.features.get("requester_is_code_owner")),
                    policy.version,
                    proposed_sha,
                    previous.approver_ids,
                    policy,
                )
            )
            diffs.append(
                {
                    "delegation_id": row["id"],
                    "previous_verdict": previous.verdict.value,
                    "proposed_verdict": proposed.verdict.value,
                    "changed": previous.verdict != proposed.verdict,
                    "newly_allowed": (
                        proposed.verdict == Verdict.ALLOW and previous.verdict != Verdict.ALLOW
                    ),
                    "reason_codes": proposed.reason_codes,
                }
            )
        diffs.sort(key=lambda item: (not item["newly_allowed"], item["delegation_id"]))
        return {
            "valid": True,
            "version": policy.version,
            "sha": proposed_sha,
            "sha256": proposed_sha,
            "against": "last_n_delegations",
            "requested_n": n,
            "evaluated_delegations": len(diffs),
            "verdict_diffs": diffs,
            "adversarial_results": results,
            "unsafe_allows": [],
            "can_activate": True,
        }

    def activate_policy(self, workspace_id: str, actor_id: str, source: str) -> dict[str, Any]:
        actor = self.require_admin(workspace_id, actor_id)
        simulation = self.simulate_policy(source, workspace_id)
        version = simulation["version"]
        if self.db.one(
            "SELECT id FROM policies WHERE workspace_id=? AND version=?",
            (workspace_id, version),
        ):
            raise Conflict("policy versions are immutable; choose a new version")
        policy_id = self.new_id("pol")
        self.db.execute(
            "INSERT INTO policies VALUES (?,?,?,?,?,?)",
            (
                policy_id,
                workspace_id,
                version,
                simulation["sha256"],
                source,
                self.now(),
            ),
        )
        self.db.execute(
            "UPDATE workspaces SET policy_version_active=? WHERE id=?",
            (version, workspace_id),
        )
        self.audit.append(
            workspace_id,
            "policy_activated",
            "human",
            actor["id"],
            "policy",
            policy_id,
            {"version": version, "sha256": simulation["sha256"]},
        )
        return {**simulation, "id": policy_id, "activated": True}

    def decide(
        self, delegation_id: str, workspace_id: str, request: HumanDecision
    ) -> dict[str, Any]:
        delegation = self._workspace_resource("delegations", delegation_id, workspace_id)
        if delegation["status"] != "awaiting_approval":
            raise Conflict("delegation is not awaiting approval")
        decision_row = self.db.one(
            "SELECT result_json FROM policy_decisions WHERE delegation_id=?", (delegation_id,)
        )
        if not decision_row:
            raise Conflict("delegation has no policy decision")
        decision = PolicyDecision.model_validate_json(decision_row["result_json"])
        approver = self._workspace_resource("users", request.approver_id, workspace_id)
        requester = self._workspace_resource("users", delegation["requester_id"], workspace_id)
        if approver["id"] not in decision.approver_ids and approver["role"] not in {
            "admin",
            "owner",
        }:
            raise Forbidden("actor is not in the resolved approver set")
        requester_owner_globs = Database.loads(requester["code_owner_paths_json"], [])
        requester_owns = all(
            any(fnmatch.fnmatch(path, glob) for glob in requester_owner_globs)
            for path in decision.proposed_surfaces
        )
        if request.approver_id == delegation["requester_id"] and not requester_owns:
            raise Forbidden("self-approval is prohibited for non-code-owners")
        scope = decision.proposed_surfaces
        if request.action == "narrow":
            scope = request.narrowed_surfaces or []
            if not scope or not set(scope).issubset(set(decision.proposed_surfaces)):
                raise InvalidEvidence("narrowed scope must be a non-empty subset of proposed scope")
        if request.action == "approve" and not scope:
            raise Conflict(
                "scope is fully held by a concurrent warrant; clear the conflict and "
                "submit a newly evaluated delegation"
            )
        approval_id = self.new_id("apr")
        self.db.execute(
            "INSERT INTO approvals VALUES (?,?,?,?,?,?,?)",
            (
                approval_id,
                delegation_id,
                approver["id"],
                request.action,
                Database.dumps(scope),
                request.rationale,
                self.now(),
            ),
        )
        if request.action in {"deny", "defer"}:
            status = "denied_by_human" if request.action == "deny" else "deferred"
            self.db.execute(
                "UPDATE delegations SET status=?,updated_at=? WHERE id=?",
                (status, self.now(), delegation_id),
            )
            self.audit.append(
                workspace_id,
                f"approval_{request.action}",
                "human",
                approver["id"],
                "delegation",
                delegation_id,
                {"rationale": request.rationale},
            )
            return self.get_delegation(delegation_id, workspace_id)
        self._issue_warrant(delegation_id, workspace_id, approver["id"], scope)
        self.db.execute(
            "UPDATE delegations SET status='warrant_issued',updated_at=? WHERE id=?",
            (self.now(), delegation_id),
        )
        return self.get_delegation(delegation_id, workspace_id)

    def _issue_warrant(
        self, delegation_id: str, workspace_id: str, authority: str, scope: list[str]
    ) -> dict[str, Any]:
        if not scope:
            raise Conflict("cannot issue a warrant with empty scope")
        existing = self.db.one("SELECT * FROM warrants WHERE delegation_id=?", (delegation_id,))
        if existing:
            return existing
        delegation = self._workspace_resource("delegations", delegation_id, workspace_id)
        extraction_row = self.db.one(
            "SELECT result_json FROM extractions WHERE delegation_id=?", (delegation_id,)
        )
        extraction = (
            ExtractionResult.model_validate_json(extraction_row["result_json"])
            if extraction_row and extraction_row["result_json"]
            else None
        )
        contract = list(
            extraction.acceptance_criteria if extraction else ["human verification required"]
        )
        contract.extend(["diff must remain within warrant scope", "test output must be attached"])
        nonce = secrets.token_urlsafe(32)
        issued = datetime.now(timezone.utc)
        expires = issued + timedelta(minutes=self.settings.warrant_ttl_minutes)
        warrant_id = self.new_id("wrt")
        risk_row = self.db.one(
            "SELECT result_json FROM risk_assessments WHERE delegation_id=?", (delegation_id,)
        )
        if not risk_row:
            raise Conflict("delegation has no risk assessment")
        risk = RiskAssessment.model_validate_json(risk_row["result_json"])
        if risk.consequence == Consequence.DESTRUCTIVE:
            contract.append(
                "stated rollback plan and evidence of rollback readiness must be attached"
            )
        decision_row = self.db.one(
            "SELECT result_json FROM policy_decisions WHERE delegation_id=?", (delegation_id,)
        )
        warrant_decision = (
            PolicyDecision.model_validate_json(decision_row["result_json"])
            if decision_row
            else None
        )
        policy = (
            self.db.one(
                "SELECT * FROM policies WHERE workspace_id=? AND version=?",
                (workspace_id, warrant_decision.policy_version),
            )
            if warrant_decision
            else None
        )
        try:
            if not policy:
                raise PolicyValidationError([])
            allowed, denied = granted_tools(policy["yaml_source"], risk.consequence)
        except PolicyValidationError:
            # A policy outage cannot expand capabilities. Read access is the literal
            # minimum needed to collect information for a human decision.
            allowed = ["read_repo"]
            denied = ["merge_pr", "deploy", "migrate_db", "rotate_secret", "delete_data"]
        self.db.execute(
            "INSERT INTO warrants VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                warrant_id,
                workspace_id,
                delegation_id,
                delegation["target_agent_id"],
                authority,
                Database.dumps(scope),
                Database.dumps(allowed),
                Database.dumps(denied),
                Database.dumps(contract),
                hashlib.sha256(nonce.encode()).hexdigest(),
                nonce if self.settings.fixture_mode else None,
                issued.isoformat(),
                expires.isoformat(),
                None,
                None,
                None,
                None,
            ),
        )
        self.audit.append(
            workspace_id,
            "warrant_issued",
            "system" if authority == "system-policy" else "human",
            authority,
            "warrant",
            warrant_id,
            {"delegation_id": delegation_id, "scope": scope, "expires_at": expires.isoformat()},
        )
        self.telemetry(workspace_id, "warrant_issued", warrant_id, authority=authority)
        return {"id": warrant_id, "nonce": nonce}

    def submit_evidence(
        self, warrant_id: str, workspace_id: str, evidence: EvidenceSubmission
    ) -> dict[str, Any]:
        self.sweep_expired_warrants(workspace_id)
        warrant = self._workspace_resource("warrants", warrant_id, workspace_id)
        if warrant["revoked_at"]:
            raise Gone("warrant has been revoked")
        if warrant["consumed_at"]:
            raise Conflict("warrant nonce has already been consumed")
        if warrant.get("expired_at") or datetime.fromisoformat(
            warrant["expires_at"]
        ) <= datetime.now(timezone.utc):
            raise Gone("warrant has expired")
        if not secrets.compare_digest(
            hashlib.sha256(evidence.nonce.encode()).hexdigest(), warrant["nonce_hash"]
        ):
            self.audit.append(
                workspace_id,
                "nonce_rejected",
                "agent",
                warrant["agent_id"],
                "warrant",
                warrant_id,
                {},
            )
            raise Forbidden("invalid warrant nonce")
        scope = Database.loads(warrant["scope_json"], [])
        outside = [
            path
            for path in evidence.files
            if not any(fnmatch.fnmatch(path, allowed) for allowed in scope)
        ]
        contract = Database.loads(warrant["evidence_contract_json"], [])
        gate1 = {
            "nonce_valid": True,
            "warrant_unexpired": True,
            "files_within_scope": not outside,
            "outside_scope_files": outside,
            "artifacts_present": bool(evidence.artifacts),
            "test_output_present": bool(evidence.test_output.strip()),
        }
        if outside or not evidence.artifacts or not evidence.test_output.strip():
            self.db.execute(
                "UPDATE delegations SET status='verification_failed',updated_at=? WHERE id=?",
                (self.now(), warrant["delegation_id"]),
            )
            self._reduce_agent_trust(warrant["agent_id"], 0.05)
            self.audit.append(
                workspace_id,
                "evidence_gate1_failed",
                "system",
                "verification-service",
                "warrant",
                warrant_id,
                {"gate1": gate1},
            )
            raise InvalidEvidence("gate-1 verification failed", {"gate1": gate1})
        bundle_id = self.new_id("evb")
        bundle_json = evidence.model_dump_json()
        bundle_hash = hashlib.sha256(bundle_json.encode()).hexdigest()
        self.db.execute(
            "INSERT INTO evidence_bundles VALUES (?,?,?,?,?)",
            (bundle_id, warrant_id, bundle_json, bundle_hash, self.now()),
        )
        started = time.perf_counter()
        gate2: dict[str, Any] | None = None
        human_checks: list[str] = []
        response = None
        error: Exception | None = None
        try:
            response = self.provider.judge(contract[:-2], evidence)
            gate2 = response.value.model_dump()
            statuses = [item["status"] for item in gate2["criteria"]]
            if "not_satisfied" in statuses:
                verdict = VerificationValue.FAIL
            elif "inconclusive" in statuses:
                verdict = VerificationValue.PASS_WITH_EXCEPTIONS
                human_checks.extend(
                    item["criterion"]
                    for item in gate2["criteria"]
                    if item["status"] == "inconclusive"
                )
            else:
                verdict = VerificationValue.PASS
            if response.degraded and verdict == VerificationValue.PASS:
                verdict = VerificationValue.PASS_WITH_EXCEPTIONS
                human_checks.append("Fallback judge used after primary provider failure.")
        except (ProviderError, ProviderMalformed) as exc:
            error = exc
            verdict = VerificationValue.INCONCLUSIVE
            human_checks.append("Judge unavailable; a human must review gate-1 evidence.")
        self.record_usage(workspace_id, warrant["delegation_id"], "judge_evidence", response, error)
        latency = int((time.perf_counter() - started) * 1000)
        self.db.execute(
            "INSERT INTO verification_verdicts VALUES (?,?,?,?,?,?,?,?)",
            (
                bundle_id,
                verdict.value,
                Database.dumps(gate1),
                Database.dumps(gate2) if gate2 is not None else None,
                Database.dumps(human_checks),
                getattr(response, "provider", self.provider.name),
                latency,
                self.now(),
            ),
        )
        self.db.execute("UPDATE warrants SET consumed_at=? WHERE id=?", (self.now(), warrant_id))
        self.db.execute(
            "UPDATE delegations SET status='verified',updated_at=? WHERE id=?",
            (self.now(), warrant["delegation_id"]),
        )
        self.audit.append(
            workspace_id,
            "evidence_verified",
            "system",
            "verification-service",
            "warrant",
            warrant_id,
            {"verdict": verdict.value, "gate1": gate1, "human_checks": human_checks},
        )
        self.telemetry(workspace_id, "evidence_verified", warrant_id, verdict=verdict.value)
        if verdict in {VerificationValue.FAIL, VerificationValue.INCONCLUSIVE}:
            self._reduce_agent_trust(warrant["agent_id"], 0.05)
        return {
            "verdict": verdict.value,
            "gate1": gate1,
            "gate2": gate2,
            "human_check_list": human_checks,
        }

    def _reduce_agent_trust(self, agent_id: str, decrement: float) -> None:
        self.db.execute(
            "UPDATE agents SET verified_pass_rate=MAX(0,verified_pass_rate-?) WHERE id=?",
            (decrement, agent_id),
        )

    def sweep_expired_warrants(self, workspace_id: str) -> int:
        now = self.now()
        rows = self.db.all(
            "SELECT * FROM warrants WHERE workspace_id=? AND consumed_at IS NULL "
            "AND revoked_at IS NULL AND expired_at IS NULL AND expires_at<=?",
            (workspace_id, now),
        )
        for row in rows:
            self.db.execute("UPDATE warrants SET expired_at=? WHERE id=?", (now, row["id"]))
            self.db.execute(
                "UPDATE delegations SET status='warrant_expired',updated_at=? WHERE id=?",
                (now, row["delegation_id"]),
            )
            self._reduce_agent_trust(row["agent_id"], 0.02)
            self.audit.append(
                workspace_id,
                "warrant_expired",
                "system",
                "expiry-sweeper",
                "warrant",
                row["id"],
                {"expired_at": now},
            )
        return len(rows)

    def get_warrant(self, warrant_id: str, workspace_id: str) -> dict[str, Any]:
        self.sweep_expired_warrants(workspace_id)
        row = self._workspace_resource("warrants", warrant_id, workspace_id)
        if row["revoked_at"]:
            raise Gone("warrant has been revoked", {"revoke_reason": row["revoke_reason"]})
        if row["expired_at"] or datetime.fromisoformat(row["expires_at"]) <= datetime.now(
            timezone.utc
        ):
            raise Gone("warrant has expired")
        return self._warrant_view(row)

    def revoke_warrant(
        self, warrant_id: str, workspace_id: str, actor_id: str, reason: str
    ) -> dict[str, Any]:
        row = self._workspace_resource("warrants", warrant_id, workspace_id)
        actor = self.db.one(
            "SELECT * FROM users WHERE id=? AND workspace_id=?", (actor_id, workspace_id)
        )
        if not actor or (
            actor["role"] not in {"admin", "owner"} and actor_id != row["authority_user_id"]
        ):
            raise Forbidden("actor cannot revoke this warrant")
        if row["consumed_at"]:
            raise Conflict("consumed warrants cannot be revoked")
        if row["revoked_at"]:
            raise Gone("warrant has already been revoked")
        now = self.now()
        self.db.execute(
            "UPDATE warrants SET revoked_at=?,revoke_reason=? WHERE id=?",
            (now, reason, warrant_id),
        )
        self.db.execute(
            "UPDATE delegations SET status='warrant_revoked',updated_at=? WHERE id=?",
            (now, row["delegation_id"]),
        )
        self.audit.append(
            workspace_id,
            "warrant_revoked",
            "human",
            actor_id,
            "warrant",
            warrant_id,
            {"reason": reason},
        )
        return {"id": warrant_id, "status": "revoked", "reason": reason}

    def get_delegation(self, delegation_id: str, workspace_id: str) -> dict[str, Any]:
        delegation = self._workspace_resource("delegations", delegation_id, workspace_id)
        issue = self.db.one(
            "SELECT external_key,title,team,path_hints_json,demo_note,is_demo_path,revision "
            "FROM issues WHERE id=?",
            (delegation["issue_id"],),
        )
        requester = self.db.one(
            "SELECT id,display_name,role,code_owner_paths_json FROM users WHERE id=? "
            "AND workspace_id=?",
            (delegation["requester_id"], workspace_id),
        )
        agent = self.db.one(
            "SELECT id,name,vendor,status,verified_pass_rate FROM agents WHERE id=? "
            "AND workspace_id=?",
            (delegation["target_agent_id"], workspace_id),
        )
        extraction = self.db.one(
            "SELECT status,result_json,provider,model,latency_ms FROM extractions "
            "WHERE delegation_id=?",
            (delegation_id,),
        )
        risk = self.db.one(
            "SELECT result_json FROM risk_assessments WHERE delegation_id=?", (delegation_id,)
        )
        decision = self.db.one(
            "SELECT result_json FROM policy_decisions WHERE delegation_id=?", (delegation_id,)
        )
        retrieval = self.db.one(
            "SELECT * FROM retrieval_evidence WHERE delegation_id=?", (delegation_id,)
        )
        warrant = self.db.one("SELECT * FROM warrants WHERE delegation_id=?", (delegation_id,))
        verification = None
        if warrant:
            verification = self.db.one(
                "SELECT v.* FROM verification_verdicts v "
                "JOIN evidence_bundles b ON b.id=v.bundle_id "
                "WHERE b.warrant_id=?",
                (warrant["id"],),
            )
        result = {**delegation, "issue": issue}
        result["requester"] = (
            {
                **requester,
                "code_owner_paths": Database.loads(requester.pop("code_owner_paths_json"), []),
            }
            if requester
            else None
        )
        result["agent"] = agent
        result["extraction"] = (
            {**extraction, "result": Database.loads(extraction["result_json"], None)}
            if extraction
            else None
        )
        result["risk_assessment"] = Database.loads(risk["result_json"], None) if risk else None
        result["decision"] = Database.loads(decision["result_json"], None) if decision else None
        result["retrieval"] = (
            {
                "mode": retrieval["mode"],
                "completeness": retrieval["completeness"],
                "candidates": Database.loads(retrieval["candidates_json"], []),
                "overlaps": Database.loads(retrieval["overlaps_json"], []),
            }
            if retrieval
            else None
        )
        result["warrant"] = self._warrant_view(warrant) if warrant else None
        if verification:
            result["verification"] = {
                "verdict": verification["verdict"],
                "gate1": Database.loads(verification["gate1_json"], {}),
                "gate2": Database.loads(verification["gate2_json"], None),
                "human_check_list": Database.loads(verification["human_checks_json"], []),
            }
        else:
            result["verification"] = None
        return result

    def delegation_brief(
        self, delegation_id: str, workspace_id: str, force_refresh: bool = False
    ) -> dict[str, Any]:
        detail = self.get_delegation(delegation_id, workspace_id)
        risk = detail.get("risk_assessment") or {}
        decision = detail.get("decision") or {}
        facts_input = {
            "issue_revision": detail["issue"]["revision"],
            "status": detail["status"],
            "extraction": detail.get("extraction"),
            "risk": risk,
            "decision": decision,
            "retrieval": detail.get("retrieval"),
            "warrant": detail.get("warrant"),
            "verification": detail.get("verification"),
        }
        facts_hash = hashlib.sha256(Database.dumps(facts_input).encode()).hexdigest()
        prompt_hash = hashlib.sha256(
            f"delegation-brief:v1:{self.provider.name}:{self.provider.model}".encode()
        ).hexdigest()
        cached = self.db.one(
            "SELECT * FROM delegation_briefs WHERE delegation_id=? AND workspace_id=?",
            (delegation_id, workspace_id),
        )
        if cached and not force_refresh:
            cached_response = Database.loads(cached["response_json"], {})
            cached_response["lifecycle"] = {
                "cache_hit": True,
                "stale": cached["facts_hash"] != facts_hash or cached["prompt_hash"] != prompt_hash,
                "generated_at": cached["generated_at"],
                "refresh_required": cached["facts_hash"] != facts_hash
                or cached["prompt_hash"] != prompt_hash,
            }
            return cached_response

        verdict = decision.get("verdict", "UNKNOWN")
        next_step = {
            "ALLOW": "Review the issued warrant boundaries before agent execution.",
            "REQUIRE_APPROVAL": "A named approver must review the structured decision.",
            "DENY": "Do not execute; submit a newly scoped delegation if remediation is possible.",
        }.get(verdict, "Review the structured record before taking action.")
        missing_information = ((detail["extraction"] or {}).get("result") or {}).get(
            "missing_information", []
        )
        fallback = {
            "summary": (
                f"{detail['issue']['external_key']} has "
                f"{len(risk.get('proposed_surfaces', []))} proposed surface(s)."
            ),
            "evidence_notes": [
                f"Evidence sufficiency: {risk.get('evidence_sufficiency', 'unknown')}",
                f"Deterministic reasons: {', '.join(decision.get('reason_codes', []))}",
            ],
            "human_next_steps": [next_step],
        }
        response = None
        error = None
        try:
            response = self.provider.brief(
                {
                    "issue": detail["issue"],
                    "extraction": detail["extraction"],
                    "risk_assessment": risk,
                    "decision": decision,
                    "retrieval": detail["retrieval"],
                }
            )
            narrative = response.value.model_dump()
            source = "model"
        except (ProviderError, ProviderMalformed) as exc:
            error = exc
            narrative = fallback
            source = "structured_fallback"
        self.record_usage(workspace_id, delegation_id, "generate_brief", response, error)
        generated_at = self.now()
        provider_name = response.provider if response else self.provider.name
        model_name = response.model if response else self.provider.model
        brief = {
            "brief_version": "v1",
            "delegation_id": delegation_id,
            "issue": {
                "external_key": detail["issue"]["external_key"],
                "title": detail["issue"]["title"],
                "team": detail["issue"]["team"],
                "revision": detail["issue"]["revision"],
            },
            "authority_boundary": {
                "authorising": False,
                "decision_source": "deterministic_policy",
                "prose_may_change_verdict": False,
            },
            "fact_snapshot": {
                "verdict": verdict,
                "reason_codes": decision.get("reason_codes", []),
                "proposed_surfaces": risk.get("proposed_surfaces", []),
                "evidence_sufficiency": risk.get("evidence_sufficiency"),
                "missing_information": missing_information,
                "warrant_status": (detail["warrant"] or {}).get("status"),
            },
            "verdict": decision,
            "risk": risk,
            "retrieved_evidence": detail["retrieval"],
            "missing_information": missing_information,
            "warrant": detail["warrant"],
            "degraded": bool(decision and decision.get("fail_closed")),
            "prose": narrative,
            "prose_source": source,
            "provenance": {
                "provider": provider_name,
                "model": model_name,
                "prompt_hash": prompt_hash,
            },
        }
        self.db.execute(
            "INSERT INTO delegation_briefs VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(delegation_id) DO UPDATE SET "
            "workspace_id=excluded.workspace_id,issue_revision=excluded.issue_revision,"
            "facts_hash=excluded.facts_hash,prompt_hash=excluded.prompt_hash,"
            "response_json=excluded.response_json,prose_source=excluded.prose_source,"
            "provider=excluded.provider,model=excluded.model,generated_at=excluded.generated_at",
            (
                delegation_id,
                workspace_id,
                detail["issue"]["revision"],
                facts_hash,
                prompt_hash,
                Database.dumps(brief),
                source,
                provider_name,
                model_name,
                generated_at,
            ),
        )
        brief["lifecycle"] = {
            "cache_hit": False,
            "stale": False,
            "generated_at": generated_at,
            "refresh_required": False,
        }
        return brief

    def _warrant_view(self, row: dict[str, Any]) -> dict[str, Any]:
        status = (
            "revoked"
            if row["revoked_at"]
            else "expired"
            if row.get("expired_at")
            else "consumed"
            if row["consumed_at"]
            else "expired"
            if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc)
            else "active"
        )
        return {
            "id": row["id"],
            "delegation_id": row["delegation_id"],
            "agent_id": row["agent_id"],
            "authority_user_id": row["authority_user_id"],
            "scope_surfaces": Database.loads(row["scope_json"], []),
            "allowed_tools": Database.loads(row["allowed_tools_json"], []),
            "denied_tools": Database.loads(row["denied_tools_json"], []),
            "evidence_contract": Database.loads(row["evidence_contract_json"], []),
            "issued_at": row["issued_at"],
            "expires_at": row["expires_at"],
            "status": status,
            "demo_nonce": row["nonce_plain_demo"],
        }

    def list_delegations(self, workspace_id: str, limit: int = 30) -> list[dict[str, Any]]:
        rows = self.db.all(
            "SELECT d.id,d.status,d.created_at,i.external_key,i.title,i.team,p.result_json "
            "FROM delegations d JOIN issues i ON i.id=d.issue_id "
            "LEFT JOIN policy_decisions p ON p.delegation_id=d.id "
            "WHERE d.workspace_id=? ORDER BY d.created_at DESC LIMIT ?",
            (workspace_id, limit),
        )
        for row in rows:
            decision = Database.loads(row.pop("result_json"), {})
            row["verdict"] = decision.get("verdict", "PROCESSING")
            row["reason_codes"] = decision.get("reason_codes", [])
        return rows

    def audit_events(
        self,
        workspace_id: str,
        limit: int = 100,
        cursor: int | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        agent_id: str | None = None,
        authority_id: str | None = None,
        surface: str | None = None,
        verdict: str | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [workspace_id]
        conditions = ["workspace_id=?"]
        if cursor is not None:
            conditions.append("seq<?")
            params.append(cursor)
        if from_time:
            conditions.append("created_at>=?")
            params.append(from_time)
        if to_time:
            conditions.append("created_at<=?")
            params.append(to_time)
        rows = self.db.all(
            f"SELECT * FROM audit_events WHERE {' AND '.join(conditions)} "
            "ORDER BY seq DESC LIMIT 1000",
            params,
        )
        warrant_to_delegation = {
            row["id"]: row["delegation_id"]
            for row in self.db.all(
                "SELECT id,delegation_id FROM warrants WHERE workspace_id=?", (workspace_id,)
            )
        }
        delegation_context: dict[str, dict[str, Any]] = {}
        for row in self.db.all(
            "SELECT d.id,d.target_agent_id,i.external_key,p.result_json,w.authority_user_id,"
            "w.scope_json FROM delegations d JOIN issues i ON i.id=d.issue_id "
            "LEFT JOIN policy_decisions p ON p.delegation_id=d.id "
            "LEFT JOIN warrants w ON w.delegation_id=d.id WHERE d.workspace_id=?",
            (workspace_id,),
        ):
            decision = Database.loads(row["result_json"], {})
            delegation_context[row["id"]] = {
                "external_key": row["external_key"],
                "agent_id": row["target_agent_id"],
                "authority_id": row["authority_user_id"],
                "surfaces": Database.loads(row["scope_json"], []) if row["scope_json"] else [],
                "verdict": decision.get("verdict"),
            }
        filtered: list[dict[str, Any]] = []
        for row in rows:
            row["payload"] = Database.loads(row.pop("payload_json"), {})
            delegation_id = (
                row["subject_id"]
                if row["subject_type"] == "delegation"
                else row["payload"].get("delegation_id")
                or warrant_to_delegation.get(row["subject_id"])
            )
            context = delegation_context.get(str(delegation_id), {})
            row["delegation_id"] = delegation_id
            row["external_key"] = context.get("external_key")
            row["agent_id"] = context.get("agent_id") or row["payload"].get("agent_id")
            row["authority_id"] = context.get("authority_id")
            row["surfaces"] = context.get("surfaces") or row["payload"].get("scope", [])
            row["verdict"] = row["payload"].get("verdict") or context.get("verdict")
            if agent_id and row["agent_id"] != agent_id:
                continue
            if authority_id and not (
                row["authority_id"] == authority_id or row["actor_id"] == authority_id
            ):
                continue
            if surface and not any(surface.lower() in item.lower() for item in row["surfaces"]):
                continue
            if verdict and row["verdict"] != verdict:
                continue
            filtered.append(row)
            if len(filtered) >= limit:
                break
        return filtered
