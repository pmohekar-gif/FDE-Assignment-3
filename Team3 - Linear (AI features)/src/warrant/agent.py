from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from .db import Database
from .providers import ProviderError
from .repository import CodeIntelligenceService, RepositoryError
from .schemas import AgentQuery
from .service import NotFound, WarrantService


class AgentIntent(str, Enum):
    """The closed set of questions the non-authorising Agent knows how to answer."""

    SUMMARY = "SUMMARY"
    BLOCKERS = "BLOCKERS"
    DECISION_RATIONALE = "DECISION_RATIONALE"
    EVIDENCE = "EVIDENCE"
    APPROVAL_STATUS = "APPROVAL_STATUS"
    SESSION_STATUS = "SESSION_STATUS"
    CODE_CHANGES = "CODE_CHANGES"
    CODE_LOCATION = "CODE_LOCATION"
    CODE_IMPACT = "CODE_IMPACT"
    INVESTIGATE = "INVESTIGATE"
    GENERAL = "GENERAL"


class FactKind(str, Enum):
    """Typed provenance for every assembled fact, so answers never substring-guess."""

    ISSUE = "issue"
    DELEGATION = "delegation"
    WARRANT = "warrant"
    VERIFICATION = "verification"
    SESSION = "session"
    SESSION_ERROR = "session_error"
    SESSION_DIFF = "session_diff"
    CODE = "code"
    CODE_UNAVAILABLE = "code_unavailable"


@dataclass(frozen=True)
class AgentFact:
    kind: FactKind
    text: str


@dataclass(frozen=True)
class IntentRule:
    """One ordered, deterministic rule. First rule whose trigger fires wins."""

    intent: AgentIntent
    phrases: tuple[str, ...] = ()
    patterns: tuple[re.Pattern[str], ...] = field(default_factory=tuple)

    def matches(self, lowered: str) -> bool:
        if any(phrase in lowered for phrase in self.phrases):
            return True
        return any(pattern.search(lowered) for pattern in self.patterns)


CODE_NOUNS = (
    r"file|files|filename|filenames|module|modules|package|packages|function|functions|method"
    r"|methods|class|classes|symbol|symbols|endpoint|endpoints|route|routes|handler|handlers"
    r"|service|services|line|lines|import|imports|test|tests"
)

INTENT_RULES: tuple[IntentRule, ...] = (
    IntentRule(
        AgentIntent.CODE_IMPACT,
        phrases=(
            "what depends on",
            "depends on",
            "depend on",
            "dependents of",
            "dependency of",
            "what would break",
            "would break",
            "break if",
            "breaks if",
            "impact of",
            "impacted by",
            "affected by",
            "call site",
            "call sites",
            "callers of",
            "blast radius",
            "reverse dependenc",
        ),
    ),
    # A question about a session's changes must not be captured by the locator rule below.
    IntentRule(
        AgentIntent.CODE_CHANGES,
        phrases=(
            "files changed",
            "changed files",
            "files change",
            "what changed",
            "which files did",
            "lines added",
        ),
        patterns=(
            re.compile(r"\b(?:files?|lines?)\b.{0,20}\bchanged?\b"),
            re.compile(r"\b(?:diff|diffs|patch|patches)\b"),
        ),
    ),
    IntentRule(
        AgentIntent.CODE_LOCATION,
        patterns=(
            re.compile(r"\bwhere (?:is|are|do|does|did|can i find|in the code)\b"),
            re.compile(rf"\bwhich (?:{CODE_NOUNS})\b"),
            re.compile(rf"\bwhat (?:{CODE_NOUNS})\b"),
            re.compile(rf"\b(?:{CODE_NOUNS})\b.{{0,40}}\b(?:involved|involve|touch|touched)\b"),
            re.compile(r"\b(?:implemented|implement|defined|declared|enforced|located|lives)\b"),
            re.compile(r"\bin (?:the )?(?:code|repo|repository|codebase|source)\b"),
            re.compile(rf"\b(?:locate|find)\b.{{0,40}}\b(?:{CODE_NOUNS}|code)\b"),
        ),
    ),
    IntentRule(
        AgentIntent.INVESTIGATE,
        phrases=("investigate", "root cause", "diagnose", "debug", "dig into", "look into"),
    ),
    IntentRule(
        AgentIntent.SESSION_STATUS,
        phrases=("coding session", "session", "verification", "verified", "still running"),
    ),
    IntentRule(
        AgentIntent.EVIDENCE,
        phrases=("evidence", "sufficiency", "proof", "artifact", "attachments"),
    ),
    IntentRule(
        AgentIntent.APPROVAL_STATUS,
        phrases=(
            "approval status",
            "approved",
            "approver",
            "who needs to approve",
            "who must approve",
            "awaiting approval",
            "pending approval",
            "needs approval",
            "require approval",
            "requires approval",
        ),
    ),
    IntentRule(
        AgentIntent.DECISION_RATIONALE,
        phrases=("decision", "verdict", "rationale", "reason code", "policy", "why was it denied"),
    ),
    IntentRule(
        AgentIntent.BLOCKERS,
        phrases=("blocker", "blocking", "blocked", "block", "stuck", "held up", "stopping"),
    ),
    IntentRule(
        AgentIntent.SUMMARY,
        phrases=("summar", "overview", "recap", "tell me about", "brief me", "what is this"),
    ),
)

CODE_INTENTS = frozenset(
    {
        AgentIntent.CODE_LOCATION,
        AgentIntent.CODE_IMPACT,
        AgentIntent.CODE_CHANGES,
        AgentIntent.INVESTIGATE,
    }
)

PREFERRED_KINDS: dict[AgentIntent, tuple[FactKind, ...]] = {
    AgentIntent.SUMMARY: (
        FactKind.ISSUE,
        FactKind.DELEGATION,
        FactKind.WARRANT,
        FactKind.SESSION,
    ),
    AgentIntent.BLOCKERS: (FactKind.ISSUE, FactKind.DELEGATION, FactKind.SESSION_ERROR),
    AgentIntent.DECISION_RATIONALE: (FactKind.DELEGATION, FactKind.WARRANT),
    AgentIntent.EVIDENCE: (FactKind.DELEGATION, FactKind.VERIFICATION, FactKind.WARRANT),
    AgentIntent.APPROVAL_STATUS: (FactKind.DELEGATION, FactKind.WARRANT),
    AgentIntent.SESSION_STATUS: (
        FactKind.SESSION,
        FactKind.SESSION_ERROR,
        FactKind.SESSION_DIFF,
        FactKind.VERIFICATION,
    ),
    AgentIntent.CODE_CHANGES: (FactKind.SESSION_DIFF, FactKind.SESSION, FactKind.CODE),
    AgentIntent.CODE_LOCATION: (FactKind.CODE,),
    AgentIntent.CODE_IMPACT: (FactKind.CODE,),
    AgentIntent.INVESTIGATE: (
        FactKind.ISSUE,
        FactKind.DELEGATION,
        FactKind.SESSION_ERROR,
        FactKind.CODE,
    ),
    AgentIntent.GENERAL: (),
}

# Kinds whose absence forces an explicit degradation, when that differs from the
# kinds used to compose the prose (an issue summary alone cannot answer "what is blocking").
REQUIRED_KINDS: dict[AgentIntent, tuple[FactKind, ...]] = {
    AgentIntent.BLOCKERS: (FactKind.DELEGATION, FactKind.SESSION_ERROR),
    AgentIntent.INVESTIGATE: (FactKind.DELEGATION, FactKind.SESSION_ERROR, FactKind.CODE),
}

DEGRADATIONS: dict[AgentIntent, str] = {
    AgentIntent.DECISION_RATIONALE: (
        "has no delegation yet, so there is no policy decision, evidence assessment, "
        "or approval state to report."
    ),
    AgentIntent.EVIDENCE: (
        "has no delegation yet, so there is no policy decision, evidence assessment, "
        "or approval state to report."
    ),
    AgentIntent.APPROVAL_STATUS: (
        "has no delegation yet, so there is no policy decision, evidence assessment, "
        "or approval state to report."
    ),
    AgentIntent.BLOCKERS: (
        "has no delegation yet, so no deterministic policy verdict is blocking it."
    ),
    AgentIntent.SESSION_STATUS: (
        "has no coding session on record, so there is no run state, verification result, "
        "or diff to report."
    ),
    AgentIntent.CODE_CHANGES: (
        "has no coding-session diff on record, so no changed files can be listed."
    ),
    AgentIntent.CODE_LOCATION: (
        "returned no repository match, so I cannot cite a file or line for it."
    ),
    AgentIntent.CODE_IMPACT: (
        "returned no repository dependency evidence, so I cannot describe an impact surface."
    ),
    AgentIntent.INVESTIGATE: (
        "has no delegation, session failure, or repository match to investigate yet."
    ),
    AgentIntent.SUMMARY: "has only the facts below on record.",
    AgentIntent.GENERAL: "has only the facts below on record.",
}


def resolve_intent(query: str, scope: dict[str, Any]) -> AgentIntent:
    """Deterministically classify a question. No model, no retrieval, no policy influence."""
    lowered = query.casefold()
    intent = AgentIntent.GENERAL
    for rule in INTENT_RULES:
        if rule.matches(lowered):
            intent = rule.intent
            break
    has_issue_context = bool(
        scope.get("issue_id") or scope.get("delegation_id") or scope.get("coding_session_id")
    )
    if scope.get("repository_id") and not has_issue_context and intent not in CODE_INTENTS:
        return AgentIntent.CODE_LOCATION
    if intent is AgentIntent.GENERAL and scope.get("coding_session_id"):
        return AgentIntent.SESSION_STATUS
    if intent is AgentIntent.GENERAL and has_issue_context:
        return AgentIntent.SUMMARY
    return intent


class AgentService:
    """Evidence-grounded assistance with no authority over policy or execution."""

    CODE_TERMS = {
        "authentication",
        "authorization",
        "call",
        "callers",
        "class",
        "classes",
        "code",
        "codebase",
        "declared",
        "defined",
        "depend",
        "dependency",
        "depends",
        "endpoint",
        "endpoints",
        "enforced",
        "file",
        "filename",
        "filenames",
        "files",
        "function",
        "functions",
        "handler",
        "handlers",
        "impact",
        "implement",
        "implemented",
        "implementation",
        "import",
        "imports",
        "method",
        "methods",
        "module",
        "modules",
        "package",
        "packages",
        "repo",
        "repository",
        "route",
        "routes",
        "service",
        "source",
        "symbol",
        "symbols",
    }
    MAX_FACT_CHARS = 900
    MAX_ANSWER_CHARS = 4_000
    MAX_SOURCES = 16
    ISSUE_BODY_CHARS = 500

    def __init__(
        self,
        db: Database,
        warrant: WarrantService,
        code: CodeIntelligenceService,
    ) -> None:
        self.db = db
        self.warrant = warrant
        self.code = code

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:16]}"

    def _issue(self, workspace_id: str, value: str) -> dict[str, Any]:
        row = self.db.one(
            "SELECT * FROM issues WHERE workspace_id=? AND (id=? OR external_key=?)",
            (workspace_id, value, value),
        )
        if row is None:
            raise NotFound("issue not found")
        return row

    def _session(self, workspace_id: str, value: str) -> dict[str, Any]:
        row = self.db.one(
            "SELECT * FROM coding_sessions WHERE workspace_id=? AND id=?", (workspace_id, value)
        )
        if row is None:
            raise NotFound("coding session not found")
        row["contract"] = Database.loads(row.pop("contract_json"), {})
        row["result"] = Database.loads(row.pop("result_json"), None)
        row["events"] = [
            {
                **event,
                "payload": Database.loads(event.pop("payload_json"), {}),
            }
            for event in self.db.all(
                "SELECT * FROM coding_session_events WHERE session_id=? ORDER BY seq", (value,)
            )
        ]
        row["diff"] = self.db.one("SELECT * FROM diff_artifacts WHERE session_id=?", (value,))
        if row["diff"]:
            row["diff"]["changed_files"] = Database.loads(row["diff"].pop("changed_files_json"), [])
        return row

    def _repository_id(self) -> str:
        return str(getattr(self.code.provider, "repository_id", ""))

    def _should_use_code(self, intent: AgentIntent, request: AgentQuery) -> bool:
        words = set(re.findall(r"[a-z_]+", request.query.casefold()))
        only_repository = bool(
            request.scope.repository_id
            and not request.scope.issue_id
            and not request.scope.delegation_id
            and not request.scope.coding_session_id
        )
        return bool(intent in CODE_INTENTS or only_repository or words & self.CODE_TERMS)

    ISSUE_REFERENCE = re.compile(r"\bthis (?:issue|ticket|bug|delegation)\b|\bthe issue\b")

    def _code_query_text(
        self, intent: AgentIntent, request: AgentQuery, issue: dict[str, Any] | None
    ) -> str:
        """Ground a code question that names no symbol in the issue's own stored terms."""
        if issue is None:
            return request.query
        lowered = request.query.casefold()
        references_issue = bool(
            self.ISSUE_REFERENCE.search(lowered)
            or str(issue.get("external_key", "")).casefold() in lowered
        )
        if intent is not AgentIntent.INVESTIGATE and not (
            intent in CODE_INTENTS and references_issue
        ):
            return request.query
        hints = Database.loads(issue.get("path_hints_json") or "[]", [])
        extra = " ".join([str(issue.get("title", "")), *(str(hint) for hint in hints)])
        return f"{request.query} {extra}".strip()[:1000]

    def query(self, workspace_id: str, request: AgentQuery) -> dict[str, Any]:
        scope = request.scope.model_dump(exclude_none=True)
        if request.scope.repository_id and request.scope.repository_id != self._repository_id():
            raise NotFound("repository not found")
        intent = resolve_intent(request.query, scope)
        sources: list[dict[str, Any]] = []
        facts: list[AgentFact] = []
        issue: dict[str, Any] | None = None
        detail: dict[str, Any] | None = None
        session: dict[str, Any] | None = None
        code_truncated = False

        if request.scope.delegation_id:
            detail = self.warrant.get_delegation(request.scope.delegation_id, workspace_id)
            issue = self._issue(workspace_id, detail["issue_id"])
        elif request.scope.issue_id:
            issue = self._issue(workspace_id, request.scope.issue_id)
            latest = self.db.one(
                "SELECT id FROM delegations WHERE workspace_id=? AND issue_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                (workspace_id, issue["id"]),
            )
            if latest:
                detail = self.warrant.get_delegation(latest["id"], workspace_id)
        if request.scope.coding_session_id:
            session = self._session(workspace_id, request.scope.coding_session_id)
            if issue is None:
                issue = self._issue(workspace_id, session["issue_id"])

        if issue:
            sources.append(
                {
                    "type": "issue",
                    "id": issue["id"],
                    "label": issue["external_key"],
                    "revision": issue["revision"],
                }
            )
            facts.append(
                AgentFact(
                    FactKind.ISSUE,
                    f"{issue['external_key']} — {issue['title']} (team {issue['team']}, "
                    f"priority {issue['priority']}). "
                    f"{issue['body_normalised'][: self.ISSUE_BODY_CHARS]}",
                )
            )
        if detail:
            decision = detail.get("decision") or {}
            risk = detail.get("risk_assessment") or {}
            sources.append(
                {
                    "type": "delegation",
                    "id": detail["id"],
                    "label": f"Delegation {detail['id']}",
                }
            )
            sources.append(
                {
                    "type": "policy_decision",
                    "id": detail["id"],
                    "label": decision.get("policy_version", "policy unavailable"),
                    "reason_codes": decision.get("reason_codes", []),
                }
            )
            verdict = decision.get("verdict", "UNKNOWN")
            reasons = ", ".join(decision.get("reason_codes", []))
            facts.append(
                AgentFact(
                    FactKind.DELEGATION,
                    "Delegation status is "
                    f"{detail['status']}; deterministic verdict is {verdict} because "
                    f"{reasons or 'no reason codes were stored'}. "
                    f"Evidence sufficiency is {risk.get('evidence_sufficiency', 'unknown')}.",
                )
            )
            if detail.get("warrant"):
                warrant = detail["warrant"]
                sources.append({"type": "warrant", "id": warrant["id"], "label": warrant["status"]})
                facts.append(
                    AgentFact(
                        FactKind.WARRANT,
                        f"Warrant {warrant['id']} is {warrant['status']} and is limited to "
                        f"{', '.join(warrant['scope_surfaces'])}.",
                    )
                )
            if detail.get("verification"):
                verification = detail["verification"]
                sources.append(
                    {
                        "type": "verification",
                        "id": detail["id"],
                        "label": verification["verdict"],
                    }
                )
                facts.append(
                    AgentFact(
                        FactKind.VERIFICATION,
                        f"Returned evidence verdict is {verification['verdict']}.",
                    )
                )
        if session:
            sources.append(
                {"type": "coding_session", "id": session["id"], "label": session["state"]}
            )
            latest = session["events"][-1] if session["events"] else None
            facts.append(
                AgentFact(
                    FactKind.SESSION,
                    f"Coding session {session['id']} is {session['state']} using "
                    f"{session['provider']}."
                    + (f" Latest event: {latest['event_type']}." if latest else ""),
                )
            )
            if session.get("error"):
                facts.append(
                    AgentFact(
                        FactKind.SESSION_ERROR,
                        f"The session failed because: {session['error']}.",
                    )
                )
            if session.get("diff"):
                diff = session["diff"]
                facts.append(
                    AgentFact(
                        FactKind.SESSION_DIFF,
                        f"The session changed {len(diff['changed_files'])} files "
                        f"(+{diff['additions']}/-{diff['deletions']}): "
                        f"{', '.join(item['path'] for item in diff['changed_files'])}.",
                    )
                )

        if self._should_use_code(intent, request):
            try:
                code = self.code.query(self._code_query_text(intent, request, issue))
            except RepositoryError as exc:
                facts.append(
                    AgentFact(
                        FactKind.CODE_UNAVAILABLE, f"Repository evidence is unavailable: {exc}."
                    )
                )
            else:
                code_truncated = code.truncated
                facts.append(AgentFact(FactKind.CODE, code.answer))
                sources.extend(
                    {
                        "type": "code",
                        "path": item.path,
                        "start_line": item.start_line,
                        "end_line": item.end_line,
                        "label": f"{item.path}:{item.start_line}-{item.end_line}",
                        "reason": item.reason,
                        "module": item.module,
                        "edge": item.edge,
                    }
                    for item in code.sources
                )

        if not facts:
            raise NotFound(
                "no supported issue, delegation, session, or repository context supplied"
            )

        subject = self._subject(issue, detail, session, request)
        answer, degraded = self._compose(intent, subject, facts)
        synthesized = False
        try:
            response = self.warrant.provider.answer(request.query, [answer])
        except ProviderError:
            pass
        else:
            candidate = response.value.answer.strip()
            if candidate:
                answer = candidate
                synthesized = True
        sources_truncated = len(sources) > self.MAX_SOURCES
        sources = sources[: self.MAX_SOURCES]
        answer_truncated = len(answer) > self.MAX_ANSWER_CHARS
        if answer_truncated:
            answer = answer[: self.MAX_ANSWER_CHARS].rstrip()

        now = self._now()
        conversation_id = request.conversation_id
        if conversation_id:
            conversation = self.db.one(
                "SELECT id FROM agent_conversations WHERE id=? AND workspace_id=?",
                (conversation_id, workspace_id),
            )
            if conversation is None:
                raise NotFound("agent conversation not found")
        else:
            conversation_id = self._id("conv")
            self.db.execute(
                "INSERT INTO agent_conversations VALUES (?,?,?,?,?)",
                (conversation_id, workspace_id, Database.dumps(scope), now, now),
            )
        self.db.execute(
            "INSERT INTO agent_messages VALUES (?,?,?,?,?,?)",
            (self._id("msg"), conversation_id, "user", request.query, "[]", now),
        )
        self.db.execute(
            "INSERT INTO agent_messages VALUES (?,?,?,?,?,?)",
            (
                self._id("msg"),
                conversation_id,
                "assistant",
                answer,
                Database.dumps(sources),
                self._now(),
            ),
        )
        self.db.execute(
            "UPDATE agent_conversations SET updated_at=? WHERE id=?", (self._now(), conversation_id)
        )
        return {
            "answer": answer,
            "sources": sources,
            "conversation_id": conversation_id,
            "authoritative": False,
            "authorising": False,
            "scope": scope,
            "intent": intent.value,
            "degraded": degraded,
            "context": {
                "answer_chars": len(answer),
                "source_count": len(sources),
                "answer_truncated": answer_truncated,
                "sources_truncated": sources_truncated,
                "code_truncated": code_truncated,
                "max_answer_chars": self.MAX_ANSWER_CHARS,
                "max_sources": self.MAX_SOURCES,
                "synthesized": synthesized,
                "provider": self.warrant.provider.name,
                "model": self.warrant.provider.model,
            },
        }

    @staticmethod
    def _subject(
        issue: dict[str, Any] | None,
        detail: dict[str, Any] | None,
        session: dict[str, Any] | None,
        request: AgentQuery,
    ) -> str:
        if issue:
            return str(issue["external_key"])
        if detail:
            return f"Delegation {detail['id']}"
        if session:
            return f"Coding session {session['id']}"
        if request.scope.repository_id:
            return f"Repository {request.scope.repository_id}"
        return "This scope"

    def _compose(
        self, intent: AgentIntent, subject: str, facts: list[AgentFact]
    ) -> tuple[str, bool]:
        """Select the intent's preferred facts, degrading explicitly and never returning empty."""
        trimmed = [
            AgentFact(fact.kind, fact.text.strip()[: self.MAX_FACT_CHARS])
            for fact in facts
            if fact.text.strip()
        ]
        everything = " ".join(fact.text for fact in trimmed).strip()
        preferred = PREFERRED_KINDS.get(intent, ())
        if not preferred:
            return (everything or self._last_resort(subject, intent)), False
        selected = [fact.text for fact in trimmed if fact.kind in preferred]
        required = REQUIRED_KINDS.get(intent, preferred)
        if selected and any(fact.kind in required for fact in trimmed):
            return " ".join(selected).strip(), False
        message = DEGRADATIONS.get(intent, "has only the facts below on record.")
        degraded_answer = f"{subject} {message}".strip()
        remainder = " ".join(selected) or everything
        if remainder:
            degraded_answer = f"{degraded_answer} {remainder}"
        return (degraded_answer.strip() or self._last_resort(subject, intent)), True

    @staticmethod
    def _last_resort(subject: str, intent: AgentIntent) -> str:
        return (
            f"{subject} produced no citable facts for a {intent.value} question, so there is "
            "nothing I can ground an answer in."
        )
