from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .agent import AgentService
from .coding import CodingAgentError, CodingSessionService
from .config import Settings
from .db import Database
from .repository import RepositoryError
from .schemas import AgentQuery, AgentScope, CodingSessionCreate, DelegationCreate
from .service import DomainError, WarrantService


class SlackVerificationError(RuntimeError):
    pass


def verify_slack_request(
    signing_secret: str, timestamp: str, raw_body: bytes, signature: str, now: int | None = None
) -> bool:
    try:
        value = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = int(time.time()) if now is None else now
    if abs(current - value) > 300:
        return False
    base = b"v0:" + timestamp.encode() + b":" + raw_body
    expected = "v0=" + hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@dataclass(frozen=True)
class SlackReply:
    channel: str
    thread_ts: str
    text: str


class SlackClient:
    def __init__(self, token: str | None) -> None:
        self.token = token

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.token:
            return {"ok": False, "error": "slack bot token is not configured"}
        request = urllib.request.Request(
            f"https://slack.com/api/{method}",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:  # noqa: S310
                return json.loads(response.read())
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": type(exc).__name__}

    def thread_context(self, channel: str, thread_ts: str | None) -> list[str]:
        if not thread_ts or not self.token:
            return []
        result = self._call("conversations.replies", {"channel": channel, "ts": thread_ts})
        messages = result.get("messages", []) if result.get("ok") else []
        return [str(item.get("text", ""))[:1000] for item in messages[-10:] if item.get("text")]

    def reply(self, reply: SlackReply) -> dict[str, Any]:
        return self._call(
            "chat.postMessage",
            {"channel": reply.channel, "thread_ts": reply.thread_ts, "text": reply.text},
        )


class SlackAdapter:
    ISSUE_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]{1,15}-\d+)\b")

    def __init__(
        self,
        db: Database,
        settings: Settings,
        warrant: WarrantService,
        agent: AgentService,
        coding: CodingSessionService,
        client: SlackClient | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.warrant = warrant
        self.agent = agent
        self.coding = coding
        self.client = client or SlackClient(settings.slack_bot_token)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _latest_delegation(self, workspace_id: str, issue_ref: str) -> dict[str, Any] | None:
        return self.db.one(
            "SELECT d.id,d.status FROM delegations d JOIN issues i ON i.id=d.issue_id "
            "WHERE d.workspace_id=? AND i.external_key=? ORDER BY d.created_at DESC LIMIT 1",
            (workspace_id, issue_ref),
        )

    def _issue_exists(self, workspace_id: str, issue_ref: str) -> bool:
        return bool(
            self.db.one(
                "SELECT id FROM issues WHERE workspace_id=? AND external_key=?",
                (workspace_id, issue_ref),
            )
        )

    def _answer(self, workspace_id: str, event: dict[str, Any]) -> str:
        text = re.sub(r"<@[^>]+>", "", str(event.get("text", ""))).strip()[:2000]
        if len(text) < 2:
            return (
                "Mention me with a question or an issue key, for example: "
                "@Warrant FDE Team3 WEB-4519 or start coding WEB-4519."
            )
        match = self.ISSUE_PATTERN.search(text.upper())
        issue_ref = match.group(1) if match else None
        lowered = text.casefold()
        if issue_ref and not self._issue_exists(workspace_id, issue_ref):
            return f"I could not find {issue_ref} in this workspace."

        if lowered.startswith("start coding") or " start coding " in f" {lowered} ":
            if not issue_ref:
                return "Include an issue key, for example: start coding WEB-4519."
            delegation = self._latest_delegation(workspace_id, issue_ref)
            if delegation is None:
                slack_user = str(event.get("user", ""))
                requester = (self.settings.slack_user_map or {}).get(slack_user, slack_user)
                try:
                    created = self.warrant.create_delegation(
                        workspace_id,
                        DelegationCreate(
                            issue_ref=issue_ref,
                            requester_id=requester,
                            target_agent_id="codex-cloud",
                            idempotency_key=f"slack-{uuid4().hex}",
                        ),
                        source="slack",
                        untrusted_origin=True,
                    )
                except DomainError as exc:
                    return f"Coding was not started: {exc}."
                delegation = {"id": created["id"], "status": created["status"]}
            detail = self.warrant.get_delegation(delegation["id"], workspace_id)
            if detail["decision"]["verdict"] == "DENY":
                return (
                    f"Coding was denied by deterministic policy for {issue_ref}: "
                    f"{', '.join(detail['decision']['reason_codes'])}."
                )
            if not detail.get("warrant") or detail["warrant"]["status"] != "active":
                return (
                    f"Approval is required before this coding session can start for {issue_ref}. "
                    f"Review: {self.settings.application_base_url}/delegations/{detail['id']}"
                )
            try:
                session = self.coding.start(
                    workspace_id,
                    CodingSessionCreate(
                        delegation_id=detail["id"],
                        source="slack",
                    ),
                    trusted_source="slack",
                )
            except (DomainError, RepositoryError, CodingAgentError) as exc:
                return f"The governed request is valid, but coding did not start: {exc}."
            return (
                f"Coding session {session['id']} is {session['state']} using "
                f"{session['provider']} ({session['provider_kind']}). "
                f"{self.settings.application_base_url}/coding-sessions/{session['id']}"
            )

        if lowered.startswith("status") and issue_ref:
            delegation = self._latest_delegation(workspace_id, issue_ref)
            if not delegation:
                return f"No governed delegation exists for {issue_ref}."
            status_session = self.db.one(
                "SELECT id,state,provider FROM coding_sessions WHERE delegation_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                (delegation["id"],),
            )
            if status_session:
                return (
                    f"{issue_ref}: coding session {status_session['id']} is "
                    f"{status_session['state']} using {status_session['provider']}."
                )
            return f"{issue_ref}: delegation is {delegation['status']}; no coding session exists."

        thread = self.client.thread_context(str(event.get("channel", "")), event.get("thread_ts"))
        contextual_query = text
        if thread:
            contextual_query += "\nThread context: " + " | ".join(thread)
        contextual_query = contextual_query[:2000]
        scope = AgentScope(issue_id=issue_ref) if issue_ref else AgentScope(repository_id="local")
        try:
            result = self.agent.query(workspace_id, AgentQuery(query=contextual_query, scope=scope))
        except (DomainError, RepositoryError) as exc:
            return f"I could not answer from grounded workspace evidence: {exc}."
        citations = ", ".join(source["label"] for source in result["sources"][:4])
        return (
            f"{result['answer']}\nSources: {citations or 'none'}\n"
            "Advisory only; this response cannot authorise work."
        )

    def handle(self, workspace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge", "")}
        event_id = str(payload.get("event_id", ""))
        if not event_id:
            raise SlackVerificationError("Slack event_id is required")
        prior = self.db.one("SELECT response_json FROM slack_events WHERE event_id=?", (event_id,))
        if prior:
            return {**Database.loads(prior["response_json"], {}), "deduplicated": True}
        event = payload.get("event") or {}
        if event.get("type") != "app_mention":
            response = {"ok": True, "ignored": True, "reason": "unsupported event type"}
        elif event.get("bot_id"):
            response = {"ok": True, "ignored": True, "reason": "bot event"}
        else:
            text = self._answer(workspace_id, event)
            reply = SlackReply(
                channel=str(event.get("channel", "")),
                thread_ts=str(event.get("thread_ts") or event.get("ts", "")),
                text=text,
            )
            delivery = (
                self.client.reply(reply)
                if self.settings.slack_bot_token
                else {
                    "ok": False,
                    "error": "bot token not configured",
                }
            )
            response = {
                "ok": True,
                "reply": {"channel": reply.channel, "thread_ts": reply.thread_ts, "text": text},
                "delivered": bool(delivery.get("ok")),
                "delivery_error": None if delivery.get("ok") else delivery.get("error"),
            }
        self.db.execute(
            "INSERT INTO slack_events VALUES (?,?,?,?,?)",
            (
                event_id,
                workspace_id,
                str(event.get("type", payload.get("type", "unknown"))),
                Database.dumps(response),
                self._now(),
            ),
        )
        return response
