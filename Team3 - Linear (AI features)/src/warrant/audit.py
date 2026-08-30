from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .db import Database

GENESIS = "0" * 64


def _canonical(event: dict[str, Any]) -> str:
    return json.dumps(event, separators=(",", ":"), sort_keys=True, ensure_ascii=True)


class AuditLedger:
    def __init__(self, db: Database):
        self.db = db

    def append(
        self,
        workspace_id: str,
        event_type: str,
        actor_type: str,
        actor_id: str,
        subject_type: str,
        subject_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as connection:
            prior = connection.execute(
                "SELECT seq,hash FROM audit_events WHERE workspace_id=? ORDER BY seq DESC LIMIT 1",
                (workspace_id,),
            ).fetchone()
            seq = int(prior["seq"]) + 1 if prior else 1
            prev_hash = prior["hash"] if prior else GENESIS
            content = {
                "workspace_id": workspace_id,
                "seq": seq,
                "event_type": event_type,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "payload": payload,
                "created_at": created_at,
            }
            digest = hashlib.sha256((prev_hash + _canonical(content)).encode()).hexdigest()
            event_id = f"ae_{uuid4().hex[:16]}"
            connection.execute(
                "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event_id,
                    workspace_id,
                    seq,
                    event_type,
                    actor_type,
                    actor_id,
                    subject_type,
                    subject_id,
                    Database.dumps(payload),
                    prev_hash,
                    digest,
                    created_at,
                ),
            )
        return {"id": event_id, "seq": seq, "hash": digest, **content}

    def verify_detail(self, workspace_id: str) -> dict[str, Any]:
        previous = GENESIS
        for row in self.db.all(
            "SELECT * FROM audit_events WHERE workspace_id=? ORDER BY seq", (workspace_id,)
        ):
            content = {
                "workspace_id": row["workspace_id"],
                "seq": row["seq"],
                "event_type": row["event_type"],
                "actor_type": row["actor_type"],
                "actor_id": row["actor_id"],
                "subject_type": row["subject_type"],
                "subject_id": row["subject_id"],
                "payload": Database.loads(row["payload_json"], {}),
                "created_at": row["created_at"],
            }
            expected = hashlib.sha256((previous + _canonical(content)).encode()).hexdigest()
            if row["prev_hash"] != previous or row["hash"] != expected:
                return {"verified": False, "broken_at_seq": row["seq"]}
            previous = row["hash"]
        return {"verified": True, "broken_at_seq": None}

    def verify(self, workspace_id: str) -> bool:
        return bool(self.verify_detail(workspace_id)["verified"])
