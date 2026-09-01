from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from .config import PROJECT_ROOT, Settings
from .db import Database
from .policy import PolicyValidationError, granted_tools, load_policy
from .providers import ProviderError, build_provider
from .retrieval import RetrievalService
from .schemas import (
    Consequence,
    DelegationBriefTelemetry,
    DelegationCreate,
    EvidenceSubmission,
    HumanDecision,
    PolicySimulationSource,
    PolicySource,
    RelatedIssueTelemetry,
    SemanticSearchTelemetry,
    TriageApplication,
    TriageTelemetry,
    WarrantRevocation,
    WebhookEnvelope,
)
from .security import verify_webhook
from .seed import reset_and_seed
from .service import DomainError, Forbidden, InvalidPolicy, NotFound, Unauthorized, WarrantService
from .triage import TriageRecommendationService
from .ui import REMEDIATION_BY_REASON, explain_codes, explain_rules, pipeline_trace


def create_app(settings: Settings | None = None, auto_seed: bool = False) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.database_path)
    db.migrate()
    if auto_seed and not db.one("SELECT id FROM workspaces LIMIT 1"):
        reset_and_seed(settings)
        db = Database(settings.database_path)
    provider = build_provider(settings)
    retrieval = RetrievalService(
        db,
        embeddings_available=settings.fixture_failure
        not in {"embedding", "embeddings", "embedding_failure"},
    )
    service = WarrantService(db, settings, provider, retrieval)
    triage = TriageRecommendationService(db, retrieval)

    app = FastAPI(
        title="Warrant",
        description="Deterministic delegation control plane for AI agent work",
        version="0.1.0",
    )
    app.state.settings = settings
    app.state.db = db
    app.state.service = service
    app.state.triage = triage
    templates = Jinja2Templates(directory=str(PROJECT_ROOT / "src" / "warrant" / "templates"))
    app.mount(
        "/static",
        StaticFiles(directory=str(PROJECT_ROOT / "src" / "warrant" / "static")),
        name="static",
    )

    def workspace(value: str | None) -> str:
        return value or settings.workspace_id

    def page_context(workspace_id: str) -> dict[str, Any]:
        users = db.all(
            "SELECT id,display_name,role,code_owner_paths_json FROM users "
            "WHERE workspace_id=? ORDER BY display_name",
            (workspace_id,),
        )
        for user in users:
            user["code_owner_paths"] = Database.loads(user.pop("code_owner_paths_json"), [])
        return {
            "workspace_id": workspace_id,
            "users": users,
            "agents": db.all(
                "SELECT * FROM agents WHERE workspace_id=? ORDER BY name", (workspace_id,)
            ),
            "fixture_mode": settings.fixture_mode,
            "provider": provider.name,
            "csrf_token": settings.csrf_token,
            "fixture_failure": settings.fixture_failure,
        }

    def scalar_count(sql: str) -> int:
        row = db.one(sql)
        return int(row["n"]) if row else 0

    def require_csrf(value: str | None) -> None:
        if value != settings.csrf_token:
            raise DomainError("missing or invalid CSRF token")

    @app.exception_handler(DomainError)
    async def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        if isinstance(exc, InvalidPolicy):
            return JSONResponse(
                {"error": str(exc), "type": type(exc).__name__, "details": exc.errors},
                status_code=exc.status_code,
            )
        if hasattr(exc, "details") and exc.details is not None:
            return JSONResponse(
                {"error": str(exc), "type": type(exc).__name__, "details": exc.details},
                status_code=exc.status_code,
            )
        return JSONResponse(
            {"error": str(exc), "type": type(exc).__name__}, status_code=exc.status_code
        )

    @app.exception_handler(ProviderError)
    async def handle_provider_error(_: Request, exc: ProviderError) -> JSONResponse:
        return JSONResponse({"error": str(exc), "degraded": True}, status_code=503)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(
        request: Request, q: str = "", team: str = "", page: int = 1
    ) -> HTMLResponse:
        workspace_id = settings.workspace_id
        page_size = 18
        page = max(1, page)
        evaluation_path = PROJECT_ROOT / "evaluations" / "results.json"
        evaluation_report = (
            json.loads(evaluation_path.read_text()) if evaluation_path.exists() else {}
        )
        evaluation_metrics = evaluation_report.get("metrics", {})
        cache_hits = scalar_count(
            "SELECT COUNT(*) AS n FROM telemetry_events WHERE name='extraction_cache_hit'"
        )
        cache_misses = scalar_count(
            "SELECT COUNT(*) AS n FROM model_usage WHERE operation='extract_delegation_facts'"
        )
        evaluation_metrics["extraction_cache_hit_rate"] = (
            round(cache_hits / (cache_hits + cache_misses), 4)
            if cache_hits + cache_misses
            else "NOT_MEASURED"
        )
        cleaned_query = " ".join(q.split())[:300]
        search_mode: str | None = None
        search_completeness: float | None = None
        if cleaned_query:
            search_result = retrieval.search_issues(
                workspace_id, cleaned_query, team=team or None, limit=50
            )
            issue_count = len(search_result.results)
            page_count = max(1, math.ceil(issue_count / page_size))
            page = min(page, page_count)
            offset = (page - 1) * page_size
            issues = search_result.results[offset : offset + page_size]
            search_mode = search_result.mode
            search_completeness = search_result.completeness
        else:
            conditions = ["workspace_id=?"]
            params: list[Any] = [workspace_id]
            if team:
                conditions.append("team=?")
                params.append(team)
            where = " AND ".join(conditions)
            count = db.one(f"SELECT COUNT(*) AS n FROM issues WHERE {where}", params)
            issue_count = int(count["n"]) if count else 0
            page_count = max(1, math.ceil(issue_count / page_size))
            page = min(page, page_count)
            issues = db.all(
                "SELECT external_key,title,team,path_hints_json,demo_note,is_demo_path "
                f"FROM issues WHERE {where} "
                "ORDER BY is_demo_path DESC, CASE external_key WHEN 'PAY-4471' THEN 0 "
                "WHEN 'SEC-4502' THEN 1 WHEN 'WEB-4519' THEN 2 ELSE 3 END, external_key "
                "LIMIT ? OFFSET ?",
                [*params, page_size, (page - 1) * page_size],
            )
        delegations = service.list_delegations(workspace_id)
        needs_decision = [item for item in delegations if item["status"] == "awaiting_approval"]
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "issues": issues,
                "delegations": delegations,
                "needs_decision": needs_decision,
                "audit_ok": service.audit.verify(workspace_id),
                "evaluation_metrics": evaluation_metrics,
                "evaluation_targets": evaluation_report.get("targets", {}),
                "q": cleaned_query,
                "team": team,
                "search_mode": search_mode,
                "search_completeness": search_completeness,
                "teams": [
                    row["team"]
                    for row in db.all(
                        "SELECT DISTINCT team FROM issues WHERE workspace_id=? ORDER BY team",
                        (workspace_id,),
                    )
                ],
                "issue_count": issue_count,
                "page": page,
                "page_count": page_count,
                **page_context(workspace_id),
            },
        )

    @app.get("/delegations/{delegation_id}", response_class=HTMLResponse)
    async def delegation_page(request: Request, delegation_id: str) -> HTMLResponse:
        workspace_id = settings.workspace_id
        detail = service.get_delegation(delegation_id, workspace_id)
        brief = service.delegation_brief(delegation_id, workspace_id)
        policy = service._active_policy(workspace_id)
        preview_allowed: list[str] = []
        preview_denied: list[str] = []
        if policy and detail.get("risk_assessment"):
            try:
                preview_allowed, preview_denied = granted_tools(
                    policy["yaml_source"],
                    Consequence(detail["risk_assessment"]["consequence"]),
                )
            except PolicyValidationError:
                preview_allowed, preview_denied = (
                    ["read_repo"],
                    [
                        "merge_pr",
                        "deploy",
                        "migrate_db",
                        "rotate_secret",
                        "delete_data",
                    ],
                )
        reason_details = explain_codes((detail.get("decision") or {}).get("reason_codes", []))
        rule_details = explain_rules((detail.get("decision") or {}).get("matched_rule_ids", []))
        remediation = next(
            (
                REMEDIATION_BY_REASON[item["code"]]
                for item in reason_details
                if item["code"] in REMEDIATION_BY_REASON
            ),
            "Submit a newly scoped request whose deterministic features no longer match the "
            "denying rule; this decision cannot be overridden.",
        )
        recorded = bool(
            db.one(
                "SELECT id FROM audit_events WHERE workspace_id=? AND "
                "(subject_id=? OR json_extract(payload_json,'$.delegation_id')=?) LIMIT 1",
                (workspace_id, delegation_id, delegation_id),
            )
        )
        return templates.TemplateResponse(
            request,
            "delegation.html",
            {
                "delegation": detail,
                "brief": brief,
                "preview_allowed": preview_allowed,
                "preview_denied": preview_denied,
                "reason_details": reason_details,
                "rule_details": rule_details,
                "remediation": remediation,
                "pipeline": pipeline_trace(detail, recorded),
                **page_context(workspace_id),
            },
        )

    @app.get("/audit", response_class=HTMLResponse)
    async def audit_page(
        request: Request,
        actor_id: str = "admin-demo",
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
        agent_id: str | None = None,
        authority_id: str | None = None,
        surface: str | None = None,
        verdict: str | None = None,
        cursor: int | None = None,
    ) -> HTMLResponse:
        workspace_id = settings.workspace_id
        service.require_admin(workspace_id, actor_id)
        events = service.audit_events(
            workspace_id,
            limit=100,
            cursor=cursor,
            from_time=from_,
            to_time=to,
            agent_id=agent_id,
            authority_id=authority_id,
            surface=surface,
            verdict=verdict,
        )
        audit_groups: list[dict[str, Any]] = []
        grouped: dict[str, dict[str, Any]] = {}
        for event in events:
            key = str(event.get("delegation_id") or f"event-{event['seq']}")
            if key not in grouped:
                grouped[key] = {
                    "delegation_id": event.get("delegation_id"),
                    "external_key": event.get("external_key"),
                    "events": [],
                }
                audit_groups.append(grouped[key])
            grouped[key]["events"].append(event)
        verification = service.audit.verify_detail(workspace_id)
        return templates.TemplateResponse(
            request,
            "audit.html",
            {
                "events": events,
                "audit_groups": audit_groups,
                "chain_verified": verification["verified"],
                "broken_at_seq": verification["broken_at_seq"],
                "filters": {
                    "from": from_ or "",
                    "to": to or "",
                    "agent_id": agent_id or "",
                    "authority_id": authority_id or "",
                    "surface": surface or "",
                    "verdict": verdict or "",
                },
                "next_cursor": events[-1]["seq"] if len(events) == 100 else None,
                **page_context(workspace_id),
            },
        )

    @app.get("/policy", response_class=HTMLResponse)
    async def policy_page(request: Request) -> HTMLResponse:
        workspace_id = settings.workspace_id
        active = service._active_policy(workspace_id)
        if not active:
            raise DomainError("active policy is unavailable")
        document = load_policy(active["yaml_source"])
        lines = active["yaml_source"].splitlines()
        rule_lines: dict[str, int] = {}
        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("- id:"):
                rule_lines[stripped.split(":", 1)[1].strip()] = index
        return templates.TemplateResponse(
            request,
            "policy.html",
            {
                "policy": active,
                "document": document.model_dump(mode="json"),
                "rule_lines": rule_lines,
                **page_context(workspace_id),
            },
        )

    @app.get("/evaluation", response_class=HTMLResponse)
    async def evaluation_page(request: Request) -> HTMLResponse:
        path = PROJECT_ROOT / "evaluations" / "results.json"
        report = (
            json.loads(path.read_text())
            if path.exists()
            else {"status": "NOT_YET_MEASURED", "targets": {}, "limitations": []}
        )
        return templates.TemplateResponse(
            request,
            "evaluation.html",
            {"report": report, **page_context(settings.workspace_id)},
        )

    @app.post("/v1/delegations", status_code=201)
    async def create_delegation_endpoint(
        body: DelegationCreate,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict:
        require_csrf(x_csrf_token)
        return service.create_delegation(workspace(x_workspace_id), body)

    @app.post("/v1/hooks/tracker", status_code=202)
    async def tracker_webhook(
        request: Request,
        x_signature: Annotated[str | None, Header()] = None,
        x_timestamp: Annotated[str | None, Header()] = None,
        x_delivery_id: Annotated[str | None, Header()] = None,
        x_workspace_id: Annotated[str | None, Header()] = None,
    ) -> Any:
        raw = await request.body()
        if (
            not x_signature
            or not x_timestamp
            or not verify_webhook(settings.webhook_secret, x_timestamp, raw, x_signature)
        ):
            raise Unauthorized("invalid webhook signature or timestamp")
        try:
            envelope = WebhookEnvelope.model_validate_json(raw)
        except ValidationError as exc:
            return JSONResponse(
                {"error": "invalid webhook payload", "details": exc.errors()}, status_code=422
            )
        body = DelegationCreate(
            issue_ref=envelope.issue_ref,
            requester_id=envelope.requester_id,
            target_agent_id=envelope.target_agent_id,
            idempotency_key=x_delivery_id or f"missing-{x_timestamp}",
        )
        return service.create_delegation(
            workspace(x_workspace_id), body, source="webhook", untrusted_origin=True
        )

    @app.get("/v1/delegations/{delegation_id}")
    async def get_delegation_endpoint(
        delegation_id: str, x_workspace_id: Annotated[str | None, Header()] = None
    ) -> dict:
        return service.get_delegation(delegation_id, workspace(x_workspace_id))

    @app.get("/v1/delegations/{delegation_id}/brief")
    async def get_brief(
        delegation_id: str, x_workspace_id: Annotated[str | None, Header()] = None
    ) -> dict:
        return service.delegation_brief(delegation_id, workspace(x_workspace_id))

    @app.post("/v1/delegations/{delegation_id}/brief/refresh")
    async def refresh_brief(
        delegation_id: str,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        require_csrf(x_csrf_token)
        workspace_id = workspace(x_workspace_id)
        brief = service.delegation_brief(delegation_id, workspace_id, force_refresh=True)
        service.telemetry(
            workspace_id,
            "delegation_brief_refreshed",
            delegation_id,
            prose_source=brief["prose_source"],
            stale_before_refresh=True,
        )
        return brief

    @app.post("/v1/telemetry/delegation-brief", status_code=202)
    async def delegation_brief_telemetry(
        body: DelegationBriefTelemetry,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, bool]:
        require_csrf(x_csrf_token)
        workspace_id = workspace(x_workspace_id)
        service.get_delegation(body.delegation_id, workspace_id)
        service.telemetry(
            workspace_id,
            "delegation_brief_viewed",
            body.delegation_id,
            prose_source=body.prose_source,
            stale=body.stale,
        )
        return {"recorded": True}

    @app.get("/v1/issues/{issue_ref}/related")
    async def related_issues_endpoint(
        issue_ref: str,
        limit: int = Query(default=5, ge=1, le=10),
        x_workspace_id: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        result = retrieval.suggest_related(workspace(x_workspace_id), issue_ref, top_k=limit)
        if result is None:
            raise NotFound("issue not found")
        return {
            "source": result.source,
            "retrieval": {
                "mode": result.mode,
                "completeness": result.completeness,
            },
            "suggestions": result.suggestions,
            "advisory_only": True,
        }

    @app.get("/v1/issues/search")
    async def semantic_issue_search_endpoint(
        q: str = Query(min_length=2, max_length=300),
        team: str | None = Query(default=None, min_length=1, max_length=80),
        limit: int = Query(default=20, ge=1, le=50),
        x_workspace_id: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        result = retrieval.search_issues(workspace(x_workspace_id), q, team=team, limit=limit)
        return {
            "query": result.query,
            "team": result.team,
            "retrieval": {"mode": result.mode, "completeness": result.completeness},
            "results": result.results,
            "read_only": True,
        }

    @app.get("/v1/issues/{issue_ref}/triage-recommendation")
    async def triage_recommendation_endpoint(
        issue_ref: str,
        x_workspace_id: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        result = triage.recommend(workspace(x_workspace_id), issue_ref)
        if result is None:
            raise NotFound("issue not found")
        return asdict(result)

    @app.post("/v1/issues/{issue_ref}/triage")
    async def apply_triage_endpoint(
        issue_ref: str,
        body: TriageApplication,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_actor_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        require_csrf(x_csrf_token)
        workspace_id = workspace(x_workspace_id)
        recommendation = triage.recommend(workspace_id, issue_ref)
        if recommendation is None:
            raise NotFound("issue not found")
        return service.apply_triage(
            workspace_id,
            issue_ref,
            x_actor_id or "",
            body,
            asdict(recommendation),
        )

    @app.post("/v1/telemetry/triage-recommendation", status_code=202)
    async def triage_telemetry_endpoint(
        body: TriageTelemetry,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, bool]:
        require_csrf(x_csrf_token)
        workspace_id = workspace(x_workspace_id)
        issue = db.one(
            "SELECT id FROM issues WHERE workspace_id=? AND external_key=?",
            (workspace_id, body.issue_ref),
        )
        if issue is None:
            raise NotFound("issue not found")
        service.telemetry(
            workspace_id,
            "triage_recommendation_viewed",
            issue["id"],
            issue_ref=body.issue_ref,
            retrieval_mode=body.retrieval_mode,
        )
        return {"recorded": True}

    @app.post("/v1/telemetry/semantic-search", status_code=202)
    async def semantic_search_telemetry_endpoint(
        body: SemanticSearchTelemetry,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, bool]:
        require_csrf(x_csrf_token)
        workspace_id = workspace(x_workspace_id)
        subject_id: str | None = None
        if body.selected_issue_ref:
            issue = db.one(
                "SELECT id FROM issues WHERE workspace_id=? AND external_key=?",
                (workspace_id, body.selected_issue_ref),
            )
            if issue is None:
                raise NotFound("selected issue not found")
            subject_id = issue["id"]
        service.telemetry(
            workspace_id,
            f"semantic_search_{body.event}",
            subject_id,
            query_length=body.query_length,
            result_count=body.result_count,
            team_filtered=body.team_filtered,
            selected_issue_ref=body.selected_issue_ref,
            rank=body.rank,
        )
        return {"recorded": True}

    @app.post("/v1/telemetry/related-issues", status_code=202)
    async def related_issue_telemetry_endpoint(
        body: RelatedIssueTelemetry,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, bool]:
        require_csrf(x_csrf_token)
        workspace_id = workspace(x_workspace_id)
        source = db.one(
            "SELECT id FROM issues WHERE workspace_id=? AND external_key=?",
            (workspace_id, body.source_issue_ref),
        )
        if source is None:
            raise NotFound("source issue not found")
        service.telemetry(
            workspace_id,
            f"related_issue_suggestions_{body.event}",
            source["id"],
            source_issue_ref=body.source_issue_ref,
            suggested_issue_ref=body.suggested_issue_ref,
            relation=body.relation,
            rank=body.rank,
            result_count=body.result_count,
        )
        return {"recorded": True}

    @app.post("/v1/policies/simulate")
    async def simulate_policy_endpoint(
        body: PolicySimulationSource,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_actor_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict:
        require_csrf(x_csrf_token)
        workspace_id = workspace(x_workspace_id)
        service.require_admin(workspace_id, x_actor_id or "")
        return service.simulate_policy(body.yaml_source, workspace_id, body.n)

    @app.post("/v1/policies", status_code=201)
    async def activate_policy_endpoint(
        body: PolicySource,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_actor_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict:
        require_csrf(x_csrf_token)
        return service.activate_policy(
            workspace(x_workspace_id), x_actor_id or "", body.yaml_source
        )

    @app.post("/v1/delegations/{delegation_id}/decision")
    async def decide_endpoint(
        delegation_id: str,
        body: HumanDecision,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_actor_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict:
        require_csrf(x_csrf_token)
        if x_actor_id and x_actor_id != body.approver_id:
            raise Forbidden("acting identity must match approver_id")
        return service.decide(delegation_id, workspace(x_workspace_id), body)

    @app.get("/v1/warrants/{warrant_id}")
    async def get_warrant_endpoint(
        warrant_id: str, x_workspace_id: Annotated[str | None, Header()] = None
    ) -> dict:
        return service.get_warrant(warrant_id, workspace(x_workspace_id))

    @app.post("/v1/warrants/{warrant_id}/revoke")
    async def revoke_warrant_endpoint(
        warrant_id: str,
        body: WarrantRevocation,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict:
        require_csrf(x_csrf_token)
        return service.revoke_warrant(
            warrant_id, workspace(x_workspace_id), body.actor_id, body.reason
        )

    @app.post("/v1/warrants/{warrant_id}/evidence")
    async def submit_evidence_endpoint(
        warrant_id: str,
        body: EvidenceSubmission,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict:
        require_csrf(x_csrf_token)
        return service.submit_evidence(warrant_id, workspace(x_workspace_id), body)

    @app.get("/v1/audit")
    async def audit_endpoint(
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_actor_id: Annotated[str | None, Header()] = None,
        format: str = "json",
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = None,
        agent_id: str | None = None,
        authority_id: str | None = None,
        surface: str | None = None,
        verdict: str | None = None,
        cursor: int | None = None,
        limit: int = Query(default=100, ge=1, le=300),
    ):
        workspace_id = workspace(x_workspace_id)
        service.require_admin(workspace_id, x_actor_id or "")
        events = service.audit_events(
            workspace_id,
            limit=limit,
            cursor=cursor,
            from_time=from_,
            to_time=to,
            agent_id=agent_id,
            authority_id=authority_id,
            surface=surface,
            verdict=verdict,
        )
        verification = service.audit.verify_detail(workspace_id)
        if format == "csv":
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(
                [
                    "seq",
                    "created_at",
                    "event_type",
                    "actor_id",
                    "subject_type",
                    "subject_id",
                    "hash",
                    "delegation_id",
                    "external_key",
                    "agent_id",
                    "authority_id",
                    "surfaces",
                    "verdict",
                ]
            )
            for event in reversed(events):
                writer.writerow(
                    [
                        event["seq"],
                        event["created_at"],
                        event["event_type"],
                        event["actor_id"],
                        event["subject_type"],
                        event["subject_id"],
                        event["hash"],
                        event.get("delegation_id"),
                        event.get("external_key"),
                        event.get("agent_id"),
                        event.get("authority_id"),
                        ";".join(event.get("surfaces", [])),
                        event.get("verdict"),
                    ]
                )
            return StreamingResponse(
                iter([stream.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=warrant-audit-simulated.csv"},
            )
        return {
            "chain_verified": verification["verified"],
            "broken_at_seq": verification["broken_at_seq"],
            "events": events,
            "next_cursor": events[-1]["seq"] if len(events) == limit else None,
        }

    @app.get("/v1/evaluations")
    async def latest_evaluation() -> dict:
        path = PROJECT_ROOT / "evaluations" / "results.json"
        if not path.exists():
            return {"status": "NOT_YET_MEASURED", "run": None}
        return json.loads(path.read_text())

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics() -> str:
        lines = ["# Warrant metrics derived from persisted synthetic product events"]
        for row in db.all(
            "SELECT name,COUNT(*) AS count FROM telemetry_events GROUP BY name ORDER BY name"
        ):
            metric = "warrant_" + row["name"].replace(".", "_") + "_total"
            lines.append(f"# TYPE {metric} counter")
            lines.append(f"{metric} {row['count']}")
        for row in db.all(
            "SELECT json_extract(result_json,'$.verdict') AS verdict,COUNT(*) AS count "
            "FROM policy_decisions GROUP BY verdict"
        ):
            lines.append(
                f'warrant_policy_decisions_total{{verdict="{row["verdict"]}"}} {row["count"]}'
            )
        cache_hits = scalar_count(
            "SELECT COUNT(*) AS n FROM telemetry_events WHERE name='extraction_cache_hit'"
        )
        cache_misses = scalar_count(
            "SELECT COUNT(*) AS n FROM model_usage WHERE operation='extract_delegation_facts'"
        )
        if cache_hits + cache_misses:
            lines.append("# TYPE warrant_extraction_cache_hit_rate gauge")
            lines.append(
                f"warrant_extraction_cache_hit_rate {cache_hits / (cache_hits + cache_misses):.4f}"
            )
        else:
            lines.append("# warrant_extraction_cache_hit_rate NOT_MEASURED")
        for row in db.all(
            "SELECT provider,model,COUNT(*) AS total,"
            "SUM(schema_repair_count) AS repairs FROM model_usage "
            "GROUP BY provider,model ORDER BY provider,model"
        ):
            metric = "warrant_schema_repair_rate"
            repairs = int(row["repairs"] or 0)
            total = int(row["total"] or 0)
            rate = repairs / total if total else 0
            provider_label = str(row["provider"]).replace('"', '\\"')
            model_label = str(row["model"]).replace('"', '\\"')
            lines.append("# TYPE warrant_schema_repair_rate gauge")
            lines.append(
                f'{metric}{{provider="{provider_label}",model="{model_label}"}} {rate:.4f}'
            )
        return "\n".join(lines) + "\n"

    @app.get("/healthz")
    async def health() -> dict:
        degraded = []
        if settings.fixture_failure:
            degraded.append(settings.fixture_failure)
        return {
            "status": "degraded" if degraded else "ok",
            "database": "ok" if db.one("SELECT 1 AS ok") else "error",
            "ai_provider": provider.name,
            "fixture_mode": settings.fixture_mode,
            "degraded": degraded,
        }

    return app


app = create_app(auto_seed=True)
