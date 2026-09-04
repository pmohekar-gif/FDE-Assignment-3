from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import asdict
from typing import Annotated, Any
from urllib.parse import parse_qsl, quote

from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from .agent import AgentService
from .auth import AuthService, is_html_path, is_open_path, safe_next_path, session_actor_id
from .coding import CodingAgentError, CodingSessionService
from .config import PROJECT_ROOT, Settings
from .db import Database
from .policy import PolicyValidationError, granted_tools, load_policy
from .providers import ProviderError, build_provider
from .repository import CodeIntelligenceService, LocalRepositoryProvider, RepositoryError
from .retrieval import RetrievalService
from .schemas import (
    AgentQuery,
    AuthTokenRequest,
    CodeQuery,
    CodingSessionCancel,
    CodingSessionCreate,
    Consequence,
    DelegationBriefTelemetry,
    DelegationCreate,
    EvidenceSubmission,
    HumanDecision,
    PolicySimulationSource,
    PolicySource,
    PullRequestCreate,
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
from .slack import SlackAdapter, SlackVerificationError, verify_slack_request
from .triage import TriageRecommendationService
from .ui import REMEDIATION_BY_REASON, explain_codes, explain_rules, pipeline_trace

# Ordered verdict buckets for the grouped operator queue. Presentation only: the ordering
# reflects "who has to act next", never a re-ranking of the deterministic verdict itself.
QUEUE_BUCKETS: tuple[tuple[str, str, str], ...] = (
    ("REQUIRE_APPROVAL", "Requires approval", "a named human must decide"),
    ("ALLOW", "Allowed", "warrant issued automatically"),
    ("DENY", "Denied", "no warrant and no override path"),
    ("PROCESSING", "Processing", "no deterministic verdict recorded yet"),
)
NOT_MEASURED_METRICS: tuple[str, ...] = (
    "risk_class_macro_f1",
    "judge_precision_satisfied",
    "p95_preflight_latency_ms",
    "cost_per_delegation_usd",
)


def _initials(display_name: str | None, fallback: str) -> str:
    parts = [part for part in (display_name or "").split() if part]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    if parts:
        return parts[0][:2].upper()
    return (fallback or "??")[:2].upper()


def _queue_rows(db: Database, workspace_id: str, limit: int = 60) -> list[dict[str, Any]]:
    """Queue rows for the grouped triage list.

    The list endpoints do not expose evidence sufficiency or the requester's display name,
    and the sufficiency ring needs both, so this read-only join assembles exactly the
    columns the row renders. Nothing is derived that the API would answer differently.
    """
    rows = db.all(
        "SELECT d.id,d.status,d.created_at,d.requester_id,i.external_key,i.title,i.team,"
        "u.display_name AS requester_name,p.result_json AS decision_json,"
        "r.result_json AS risk_json "
        "FROM delegations d JOIN issues i ON i.id=d.issue_id "
        "LEFT JOIN users u ON u.id=d.requester_id "
        "LEFT JOIN policy_decisions p ON p.delegation_id=d.id "
        "LEFT JOIN risk_assessments r ON r.delegation_id=d.id "
        "WHERE d.workspace_id=? ORDER BY d.created_at DESC LIMIT ?",
        (workspace_id, limit),
    )
    for row in rows:
        decision = Database.loads(row.pop("decision_json"), {})
        risk = Database.loads(row.pop("risk_json"), {})
        row["verdict"] = decision.get("verdict") or "PROCESSING"
        row["reason_codes"] = decision.get("reason_codes") or []
        row["evidence_sufficiency"] = risk.get("evidence_sufficiency")
        row["requester_name"] = row.get("requester_name") or row["requester_id"]
        row["requester_initials"] = _initials(row["requester_name"], row["requester_id"])
    return rows


def _queue_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for verdict, label, note in QUEUE_BUCKETS:
        bucket_rows = [row for row in rows if row["verdict"] == verdict]
        if not bucket_rows:
            continue
        groups.append(
            {
                "verdict": verdict,
                "label": label,
                "note": note,
                "rows": bucket_rows,
                "first_bucket": not groups,
            }
        )
    return groups


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
    repository = LocalRepositoryProvider(
        settings.repository_root,
        max_file_bytes=settings.repository_max_file_bytes,
        max_results=settings.repository_max_results,
    )
    code = CodeIntelligenceService(db, repository, llm=provider)
    agent = AgentService(db, service, code)
    coding = CodingSessionService(db, settings, service, repository)
    slack = SlackAdapter(db, settings, service, agent, coding)
    auth = AuthService(db, settings, service.audit)
    if auth.enabled:
        auth.ensure_credentials()

    app = FastAPI(
        title="Warrant",
        description="Deterministic delegation control plane for AI agent work",
        version="0.1.0",
    )
    app.state.settings = settings
    app.state.db = db
    app.state.service = service
    app.state.triage = triage
    app.state.repository = repository
    app.state.code = code
    app.state.agent = agent
    app.state.coding = coding
    app.state.slack = slack
    app.state.auth = auth
    templates = Jinja2Templates(directory=str(PROJECT_ROOT / "src" / "warrant" / "templates"))
    app.mount(
        "/static",
        StaticFiles(directory=str(PROJECT_ROOT / "src" / "warrant" / "static")),
        name="static",
    )

    def workspace(value: str | None) -> str:
        return value or settings.workspace_id

    def acting_id(request: Request, claimed: str | None) -> str:
        """Resolve the acting identity.

        With auth enabled the server-side session is the only source: any client-supplied
        `X-Actor-Id` header or `actor_id` query value is ignored outright, never merged.
        With auth disabled the existing header-driven demo path is unchanged.
        """
        authenticated = session_actor_id(request)
        return authenticated if authenticated is not None else (claimed or "")

    def declared_id(request: Request, claimed: str) -> str:
        """Body-declared identity (approver_id / actor_id) must be the signed-in user.

        Rejecting instead of silently rewriting keeps the recorded authority honest: an
        approval performed under a session is always attributed to that session's user.
        """
        authenticated = session_actor_id(request)
        if authenticated is not None and claimed != authenticated:
            raise Forbidden("declared actor must match the authenticated session")
        return claimed

    def evaluation_report() -> dict[str, Any]:
        path = PROJECT_ROOT / "evaluations" / "results.json"
        if not path.exists():
            return {"status": "NOT_YET_MEASURED", "metrics": {}, "targets": {}, "limitations": []}
        return json.loads(path.read_text())

    def feature_flags() -> dict[str, bool]:
        """The same flag map /healthz reports, so the UI cannot drift from the server."""
        return {
            "agent_chat": settings.agent_chat_enabled,
            "code_intelligence": settings.code_intelligence_enabled,
            "external_coding_agent": settings.external_coding_agent_enabled,
            "slack": settings.slack_enabled,
            "pr_publishing": settings.pr_publishing_enabled,
        }

    def policy_surface(workspace_id: str) -> dict[str, Any]:
        """Never-grantable tools and per-consequence grants, for the shell's tool chips."""
        active = service._active_policy(workspace_id)
        if not active:
            return {"version": "none", "never_grantable_tools": [], "tool_grants": {}}
        never: list[str] = []
        grants: dict[str, list[str]] = {}
        try:
            document = load_policy(active["yaml_source"])
            never = list(dict.fromkeys(document.never_grantable_tools))
            blocked = set(never)
            grants = {
                str(getattr(consequence, "value", consequence)): [
                    tool for tool in tools if tool not in blocked
                ]
                for consequence, tools in document.tool_grants.items()
            }
        except PolicyValidationError:
            never = ["merge_pr", "deploy", "migrate_db", "rotate_secret", "delete_data"]
        return {
            "version": str(active["version"]),
            "never_grantable_tools": never,
            "tool_grants": grants,
        }

    def page_context(workspace_id: str, request: Request | None = None) -> dict[str, Any]:
        users = db.all(
            "SELECT id,display_name,role,code_owner_paths_json FROM users "
            "WHERE workspace_id=? ORDER BY display_name",
            (workspace_id,),
        )
        for user in users:
            user["code_owner_paths"] = Database.loads(user.pop("code_owner_paths_json"), [])
        policy_view = policy_surface(workspace_id)
        counts = (
            db.one(
                "SELECT (SELECT COUNT(*) FROM delegations WHERE workspace_id=?) AS delegations,"
                "(SELECT COUNT(*) FROM delegations WHERE workspace_id=? AND "
                "status='awaiting_approval')"
                " AS triage,"
                "(SELECT COUNT(*) FROM coding_sessions WHERE workspace_id=?) AS sessions,"
                "(SELECT COUNT(*) FROM issues WHERE workspace_id=?) AS issues,"
                "(SELECT COUNT(*) FROM audit_events WHERE workspace_id=?) AS audit_events",
                (workspace_id,) * 5,
            )
            or {}
        )
        flags = feature_flags()
        audit_ok = service.audit.verify(workspace_id)
        return {
            "workspace_id": workspace_id,
            "users": users,
            "auth_enabled": settings.auth_enabled,
            "current_user": (
                getattr(request.state, "actor", None) if request is not None else None
            ),
            "agents": db.all(
                "SELECT * FROM agents WHERE workspace_id=? ORDER BY name", (workspace_id,)
            ),
            "fixture_mode": settings.fixture_mode,
            "provider": provider.name,
            "csrf_token": settings.csrf_token,
            "fixture_failure": settings.fixture_failure,
            "agent_chat_enabled": settings.agent_chat_enabled,
            "code_intelligence_enabled": settings.code_intelligence_enabled,
            "external_coding_agent_enabled": settings.external_coding_agent_enabled,
            "slack_enabled": settings.slack_enabled,
            "pr_publishing_enabled": settings.pr_publishing_enabled,
            # Shell chrome. Read-only counters and policy facts the sidebar and rails render.
            "allow_threshold": settings.allow_sufficiency_threshold,
            "warrant_ttl_minutes": settings.warrant_ttl_minutes,
            "never_grantable_tools": policy_view["never_grantable_tools"],
            "tool_grants": policy_view["tool_grants"],
            "features_enabled": flags,
            "audit_ok": audit_ok,
            "repository_id": repository.repository_id,
            "nav": {
                "triage": int(counts.get("triage") or 0),
                "delegations": int(counts.get("delegations") or 0),
                "sessions": int(counts.get("sessions") or 0),
                "issues": int(counts.get("issues") or 0),
                "audit_events": int(counts.get("audit_events") or 0),
                "audit_ok": audit_ok,
                "policy_version": policy_view["version"],
                "evaluation": len((evaluation_report().get("targets") or {})),
                "integrations": sum(1 for enabled in flags.values() if enabled),
            },
        }

    def scalar_count(sql: str) -> int:
        row = db.one(sql)
        return int(row["n"]) if row else 0

    def require_csrf(value: str | None) -> None:
        if value != settings.csrf_token:
            raise DomainError("missing or invalid CSRF token")

    @app.middleware("http")
    async def authentication_gate(request: Request, call_next: Any) -> Response:
        """Bind the acting identity to a JWT-backed session when AUTH_ENABLED is true.

        Disabled by default, in which case this is a pass-through and the header-driven
        demo path behaves exactly as before.
        """
        if not settings.auth_enabled:
            return await call_next(request)
        authorization = request.headers.get("authorization")
        if authorization is not None:
            scheme, separator, credential = authorization.partition(" ")
            token = (
                credential
                if separator and scheme.lower() == "bearer" and credential and " " not in credential
                else None
            )
            request.state.auth_source = "bearer"
        else:
            token = request.cookies.get(auth.cookie_name)
            request.state.auth_source = "cookie" if token else None
        verified = auth.verify_session(token)
        request.state.actor = verified["actor"] if verified else None
        request.state.session_id = verified["session_id"] if verified else None
        request.state.session_expires_at = verified["expires_at"] if verified else None
        path = request.url.path
        if verified is None and not is_open_path(path):
            if is_html_path(path):
                wanted = f"{path}?{request.url.query}" if request.url.query else path
                target = "/login" if path == "/" else f"/login?next={quote(wanted, safe='/')}"
                return RedirectResponse(target, status_code=303)
            return JSONResponse(
                {"error": "authentication required", "type": "Unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)

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

    @app.exception_handler(RepositoryError)
    async def handle_repository_error(_: Request, exc: RepositoryError) -> JSONResponse:
        return JSONResponse(
            {"error": str(exc), "type": type(exc).__name__, "repository_available": False},
            status_code=503,
        )

    @app.exception_handler(CodingAgentError)
    async def handle_coding_agent_error(_: Request, exc: CodingAgentError) -> JSONResponse:
        return JSONResponse({"error": str(exc), "type": type(exc).__name__}, status_code=503)

    async def read_form(request: Request) -> dict[str, str]:
        """Parse a sign-in submission with the stdlib only.

        `python-multipart` is not a project dependency and adding one is out of scope, so
        neither FastAPI's `Form()` nor Starlette's `request.form()` is available. The
        login/logout templates post `application/x-www-form-urlencoded`; a JSON body is
        also accepted so `curl` and API clients can sign in without an HTML form.
        """
        raw = (await request.body())[:8192]
        if request.headers.get("content-type", "").startswith("application/json"):
            try:
                payload = json.loads(raw or b"{}")
            except json.JSONDecodeError as exc:
                raise DomainError("sign-in body is not valid JSON") from exc
            if not isinstance(payload, dict):
                raise DomainError("sign-in body must be a JSON object")
            return {str(key): str(value) for key, value in payload.items()}
        return dict(
            parse_qsl(raw.decode("utf-8", "replace"), keep_blank_values=True, max_num_fields=20)
        )

    def login_page(
        request: Request, next_path: str, error: str | None, status_code: int = 200
    ) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": error,
                "next": next_path,
                "credentials": auth.demo_credentials() if settings.auth_enabled else [],
                **page_context(settings.workspace_id, request),
            },
            status_code=status_code,
        )

    @app.get("/login", response_class=HTMLResponse)
    async def login_form(request: Request, next: str = "/") -> Response:
        """Demo sign-in form. Open by design; it lists the demo credentials on screen."""
        target = safe_next_path(next)
        if not settings.auth_enabled:
            return RedirectResponse(target, status_code=303)
        if getattr(request.state, "actor", None):
            return RedirectResponse(target, status_code=303)
        return login_page(request, target, None)

    @app.post("/login")
    async def login_submit(request: Request) -> Response:
        submitted = await read_form(request)
        target = safe_next_path(submitted.get("next"))
        if not settings.auth_enabled:
            return RedirectResponse(target, status_code=303)
        require_csrf(submitted.get("csrf_token"))
        username = submitted.get("username", "")
        actor = auth.verify_credentials(username, submitted.get("password", ""))
        if actor is None:
            auth.record_login_failure(username)
            return login_page(
                request, target, "Sign-in failed: unknown user or wrong password.", 401
            )
        token, session = auth.issue_session(str(actor["id"]))
        auth.record_login(actor, str(session["id"]))
        response = RedirectResponse(target, status_code=303)
        response.set_cookie(
            auth.cookie_name,
            token,
            max_age=auth.ttl_seconds,
            httponly=True,
            samesite="lax",
            secure=auth.cookie_secure,
            path="/",
        )
        return response

    @app.post("/v1/auth/token")
    async def auth_token(body: AuthTokenRequest) -> Response:
        """Exchange the shared demo password and a seeded user ID for a JWT."""
        if not settings.auth_enabled:
            return JSONResponse(
                {"error": "JWT authentication is disabled", "type": "NotFound"},
                status_code=404,
                headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
            )
        actor = auth.verify_credentials(body.username, body.password)
        if actor is None:
            auth.record_login_failure(body.username)
            return JSONResponse(
                {"error": "invalid credentials", "type": "Unauthorized"},
                status_code=401,
                headers={
                    "WWW-Authenticate": "Bearer",
                    "Cache-Control": "no-store",
                    "Pragma": "no-cache",
                },
            )
        token, session = auth.issue_session(str(actor["id"]))
        auth.record_login(actor, str(session["id"]))
        return JSONResponse(
            {
                "access_token": token,
                "token_type": "bearer",
                "expires_in": auth.ttl_seconds,
                "user": actor,
            },
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    @app.get("/v1/auth/me")
    async def auth_me(request: Request) -> Response:
        """Return the current database identity, never authority copied from JWT claims."""
        actor = getattr(request.state, "actor", None)
        if actor is None:
            return JSONResponse(
                {"error": "authentication required", "type": "Unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return JSONResponse(
            {
                "user": actor,
                "session": {
                    "id": getattr(request.state, "session_id", None),
                    "expires_at": getattr(request.state, "session_expires_at", None),
                },
            }
        )

    @app.post("/v1/auth/logout", status_code=204)
    async def auth_logout(request: Request, x_csrf_token: str | None = Header(None)) -> Response:
        """Revoke the current bearer or cookie session immediately."""
        if not settings.auth_enabled:
            return JSONResponse(
                {"error": "JWT authentication is disabled", "type": "NotFound"},
                status_code=404,
            )
        if getattr(request.state, "auth_source", None) == "cookie":
            require_csrf(x_csrf_token)
        session_id = str(request.state.session_id)
        actor_id = str(request.state.actor["id"])
        auth.revoke_session(session_id)
        auth.record_logout(actor_id, session_id)
        response = Response(status_code=204)
        if getattr(request.state, "auth_source", None) == "cookie":
            response.delete_cookie(
                auth.cookie_name,
                path="/",
                httponly=True,
                samesite="lax",
                secure=auth.cookie_secure,
            )
        return response

    @app.post("/logout")
    async def logout(request: Request) -> Response:
        submitted = await read_form(request)
        if not settings.auth_enabled:
            return RedirectResponse("/", status_code=303)
        require_csrf(submitted.get("csrf_token"))
        session_id = getattr(request.state, "session_id", None)
        actor = getattr(request.state, "actor", None)
        if session_id and actor:
            auth.revoke_session(str(session_id))
            auth.record_logout(str(actor["id"]), str(session_id))
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(
            auth.cookie_name,
            path="/",
            httponly=True,
            samesite="lax",
            secure=auth.cookie_secure,
        )
        return response

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(
        request: Request, q: str = "", team: str = "", page: int = 1
    ) -> HTMLResponse:
        workspace_id = settings.workspace_id
        page_size = 18
        page = max(1, page)
        report = evaluation_report()
        evaluation_metrics = dict(report.get("metrics") or {})
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
        queue = _queue_rows(db, workspace_id)
        needs_decision = [item for item in queue if item["status"] == "awaiting_approval"]
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "issues": issues,
                "queue": queue,
                "queue_groups": _queue_groups(queue),
                "needs_decision": needs_decision,
                "evaluation_metrics": evaluation_metrics,
                "evaluation_targets": report.get("targets", {}),
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
                **page_context(workspace_id, request),
            },
        )

    @app.get("/delegations", response_class=HTMLResponse)
    async def delegations_page(request: Request) -> HTMLResponse:
        """Every delegation, grouped by deterministic verdict."""
        workspace_id = settings.workspace_id
        queue = _queue_rows(db, workspace_id, limit=200)
        return templates.TemplateResponse(
            request,
            "delegations.html",
            {
                "queue": queue,
                "queue_groups": _queue_groups(queue),
                **page_context(workspace_id, request),
            },
        )

    @app.get("/coding-sessions", response_class=HTMLResponse)
    async def coding_sessions_page(request: Request) -> HTMLResponse:
        """Index of governed coding sessions.

        There is no list endpoint for coding sessions (only `GET /v1/coding-sessions/{id}`),
        so this route reads the summary columns directly. Per-session detail still comes
        from the service through the session page.
        """
        workspace_id = settings.workspace_id
        rows = db.all(
            "SELECT c.id,c.state,c.provider,c.created_at,c.delegation_id,"
            "i.external_key,i.title,d.additions,d.deletions "
            "FROM coding_sessions c JOIN issues i ON i.id=c.issue_id "
            "LEFT JOIN diff_artifacts d ON d.session_id=c.id "
            "WHERE c.workspace_id=? ORDER BY c.created_at DESC LIMIT 100",
            (workspace_id,),
        )
        for row in rows:
            row["provider_kind"] = "real" if row["provider"] == "codex" else "mock"
            additions, deletions = row.pop("additions"), row.pop("deletions")
            row["diff_summary"] = (
                f"+{additions} −{deletions}" if additions is not None else "no diff"
            )
        return templates.TemplateResponse(
            request,
            "sessions.html",
            {"sessions": rows, **page_context(workspace_id, request)},
        )

    @app.get("/code", response_class=HTMLResponse)
    async def code_page(request: Request) -> HTMLResponse:
        """Code Intelligence. Index status and answers are fetched from the API by the page."""
        return templates.TemplateResponse(
            request,
            "code.html",
            {
                "example_queries": [
                    "Where is the policy verdict computed?",
                    "Where is an active warrant re-checked before execution?",
                    "How is the audit chain hashed?",
                ],
                **page_context(settings.workspace_id, request),
            },
        )

    @app.get("/integrations", response_class=HTMLResponse)
    async def integrations_page(request: Request) -> HTMLResponse:
        """Which features are on, and what the Slack adapter is actually configured with."""
        return templates.TemplateResponse(
            request,
            "integrations.html",
            {
                "slack": {
                    "enabled": settings.slack_enabled,
                    "signing_secret_present": bool(settings.slack_signing_secret),
                    "bot_token_present": bool(settings.slack_bot_token),
                    "app_id": settings.slack_app_id,
                    "user_map_size": len(settings.slack_user_map or {}),
                    "configured": bool(settings.slack_enabled and settings.slack_signing_secret),
                },
                "repository_root": str(settings.repository_root),
                "coding_agent_provider": settings.coding_agent_provider,
                "coding_session_root": str(settings.coding_session_root),
                **page_context(settings.workspace_id, request),
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
                "coding_sessions": coding.list_for_delegation(delegation_id, workspace_id),
                **page_context(workspace_id, request),
            },
        )

    @app.get("/coding-sessions/{session_id}", response_class=HTMLResponse)
    async def coding_session_page(request: Request, session_id: str) -> HTMLResponse:
        workspace_id = settings.workspace_id
        session = coding.get(session_id, workspace_id)
        return templates.TemplateResponse(
            request,
            "coding_session.html",
            {"session": session, **page_context(workspace_id, request)},
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
        service.require_admin(workspace_id, acting_id(request, actor_id))
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
                **page_context(workspace_id, request),
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
                "rule_explanations": {
                    item["id"]: item["explanation"]
                    for item in explain_rules([rule.id for rule in document.rules])
                },
                **page_context(workspace_id, request),
            },
        )

    @app.get("/evaluation", response_class=HTMLResponse)
    async def evaluation_page(request: Request) -> HTMLResponse:
        report = evaluation_report()
        metrics = report.get("metrics") or {}
        return templates.TemplateResponse(
            request,
            "evaluation.html",
            {
                "report": report,
                "not_measured": [
                    key
                    for key in NOT_MEASURED_METRICS
                    if str(metrics.get(key, "NOT_MEASURED")) == "NOT_MEASURED"
                ],
                **page_context(settings.workspace_id, request),
            },
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
    ) -> Any:
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
        request: Request,
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
            acting_id(request, x_actor_id),
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

    @app.post("/v1/agent/query")
    async def agent_query_endpoint(
        body: AgentQuery,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> Any:
        require_csrf(x_csrf_token)
        if not settings.agent_chat_enabled:
            return JSONResponse({"error": "contextual Agent is disabled"}, status_code=503)
        return agent.query(workspace(x_workspace_id), body)

    @app.post("/v1/code/query")
    async def code_query_endpoint(
        body: CodeQuery,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> Any:
        require_csrf(x_csrf_token)
        if not settings.code_intelligence_enabled:
            return JSONResponse({"error": "Code Intelligence is disabled"}, status_code=503)
        if body.repository_id != repository.repository_id:
            raise NotFound("repository not found")
        result = code.query(body.query, body.limit)
        return {
            "answer": result.answer,
            "repository_id": result.repository_id,
            "revision": result.revision,
            "cached_index": result.cached_index,
            "ignore_source": result.ignore_source,
            "truncated": result.truncated,
            "dependency_resolved": result.dependency_resolved,
            "modules": list(result.modules),
            "sources": [asdict(item) for item in result.sources],
            "authoritative": False,
            "authorising": False,
        }

    @app.get("/v1/code/index/status")
    async def code_index_status_endpoint() -> dict[str, Any]:
        if not settings.code_intelligence_enabled:
            return {
                "enabled": False,
                "indexed": False,
                "authoritative": False,
                "authorising": False,
            }
        return {
            "enabled": True,
            **code.status(),
            "authoritative": False,
            "authorising": False,
        }

    @app.post("/v1/code/index/refresh")
    async def code_index_refresh_endpoint(
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> Any:
        require_csrf(x_csrf_token)
        if not settings.code_intelligence_enabled:
            return JSONResponse({"error": "Code Intelligence is disabled"}, status_code=503)
        return code.refresh(force=True)

    @app.get("/v1/coding-sessions/capabilities")
    async def coding_capabilities_endpoint() -> dict[str, Any]:
        return coding.capabilities()

    @app.post("/v1/coding-sessions", status_code=202)
    async def create_coding_session_endpoint(
        body: CodingSessionCreate,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> Any:
        require_csrf(x_csrf_token)
        return coding.start(workspace(x_workspace_id), body, trusted_source="api")

    @app.get("/v1/coding-sessions/{session_id}")
    async def get_coding_session_endpoint(
        session_id: str,
        x_workspace_id: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        return coding.get(session_id, workspace(x_workspace_id))

    @app.post("/v1/coding-sessions/{session_id}/cancel")
    async def cancel_coding_session_endpoint(
        request: Request,
        session_id: str,
        body: CodingSessionCancel,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        require_csrf(x_csrf_token)
        return coding.cancel(
            session_id, workspace(x_workspace_id), declared_id(request, body.actor_id)
        )

    @app.post("/v1/coding-sessions/{session_id}/pull-request")
    async def create_pull_request_endpoint(
        request: Request,
        session_id: str,
        body: PullRequestCreate,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        require_csrf(x_csrf_token)
        workspace_id = workspace(x_workspace_id)
        service.require_admin(workspace_id, declared_id(request, body.actor_id))
        return coding.publish_pr(
            session_id, workspace_id, body.title, body.body, body.reviewers, body.base
        )

    @app.post("/v1/integrations/slack/events")
    async def slack_events_endpoint(
        request: Request,
        x_slack_request_timestamp: Annotated[str | None, Header()] = None,
        x_slack_signature: Annotated[str | None, Header()] = None,
        x_workspace_id: Annotated[str | None, Header()] = None,
    ) -> Any:
        if not settings.slack_enabled or not settings.slack_signing_secret:
            return JSONResponse({"error": "Slack integration is not configured"}, status_code=503)
        raw = await request.body()
        if (
            not x_slack_request_timestamp
            or not x_slack_signature
            or not verify_slack_request(
                settings.slack_signing_secret,
                x_slack_request_timestamp,
                raw,
                x_slack_signature,
            )
        ):
            raise Unauthorized("invalid or expired Slack signature")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return JSONResponse({"error": "invalid Slack payload"}, status_code=422)
        try:
            return slack.handle(workspace(x_workspace_id), payload)
        except SlackVerificationError as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)

    @app.post("/v1/policies/simulate")
    async def simulate_policy_endpoint(
        request: Request,
        body: PolicySimulationSource,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_actor_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict:
        require_csrf(x_csrf_token)
        workspace_id = workspace(x_workspace_id)
        service.require_admin(workspace_id, acting_id(request, x_actor_id))
        return service.simulate_policy(body.yaml_source, workspace_id, body.n)

    @app.post("/v1/policies", status_code=201)
    async def activate_policy_endpoint(
        request: Request,
        body: PolicySource,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_actor_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict:
        require_csrf(x_csrf_token)
        return service.activate_policy(
            workspace(x_workspace_id), acting_id(request, x_actor_id), body.yaml_source
        )

    @app.post("/v1/delegations/{delegation_id}/decision")
    async def decide_endpoint(
        request: Request,
        delegation_id: str,
        body: HumanDecision,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_actor_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict:
        require_csrf(x_csrf_token)
        declared_id(request, body.approver_id)
        if session_actor_id(request) is None and x_actor_id and x_actor_id != body.approver_id:
            raise Forbidden("acting identity must match approver_id")
        return service.decide(delegation_id, workspace(x_workspace_id), body)

    @app.get("/v1/warrants/{warrant_id}")
    async def get_warrant_endpoint(
        warrant_id: str, x_workspace_id: Annotated[str | None, Header()] = None
    ) -> dict:
        return service.get_warrant(warrant_id, workspace(x_workspace_id))

    @app.post("/v1/warrants/{warrant_id}/revoke")
    async def revoke_warrant_endpoint(
        request: Request,
        warrant_id: str,
        body: WarrantRevocation,
        x_workspace_id: Annotated[str | None, Header()] = None,
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> dict:
        require_csrf(x_csrf_token)
        return service.revoke_warrant(
            warrant_id,
            workspace(x_workspace_id),
            declared_id(request, body.actor_id),
            body.reason,
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
        request: Request,
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
        service.require_admin(workspace_id, acting_id(request, x_actor_id))
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
            "features": {
                "agent_chat": settings.agent_chat_enabled,
                "code_intelligence": settings.code_intelligence_enabled,
                "external_coding_agent": settings.external_coding_agent_enabled,
                "slack": settings.slack_enabled,
                "pr_publishing": settings.pr_publishing_enabled,
            },
        }

    return app


app = create_app(auto_seed=True)
