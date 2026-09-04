"""Mock demo authentication: a local identity gate, not a production identity provider.

Scope, stated plainly so nobody mistakes this for real auth:

* Credentials are a single shared `DEMO_PASSWORD` applied to every seeded demo user.
  Nothing here provisions humans, verifies email, resets passwords, or federates.
* There is no OAuth, SSO, MFA, self-registration, rate limiting or lockout.
* What it *does* provide is an HS256 JWT bound to a server-side session. Passwords are
  stored only as a per-user salt plus a stdlib scrypt derivation. Session rows make
  sign-out and revocation immediate for both browser cookies and API bearer tokens.

Authority is unchanged: signing in establishes *who* the actor is. Role checks in
`service.py` and the versioned policy still decide what that actor may do.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
from fastapi import Request
from jwt import PyJWTError

from .audit import AuditLedger
from .config import Settings
from .db import Database

SESSION_COOKIE_NAME = "warrant_session"
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "warrant"
JWT_AUDIENCE = "warrant-api"
CREDENTIAL_ALGORITHM = "scrypt-n16384-r8-p1"
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024
_SCRYPT_DKLEN = 32

# Paths that stay reachable without a session so the gate cannot lock out liveness
# checks, the sign-in flow itself, or static assets.
OPEN_PATHS = frozenset({"/healthz", "/login", "/logout", "/v1/auth/token"})
OPEN_PREFIXES = ("/static/",)
# These two endpoints carry their own independent cryptographic authentication (HMAC
# request signatures verified in security.py / slack.py). They are machine-to-machine and
# have no browser session, so the session gate would only break them.
SIGNED_ENDPOINTS = frozenset({"/v1/hooks/tracker", "/v1/integrations/slack/events"})
# Server-rendered operator pages. Unauthenticated requests here get a redirect to the
# sign-in form; everything else is treated as API and gets a typed 401 JSON body.
HTML_PATHS = frozenset(
    {
        "/",
        "/policy",
        "/audit",
        "/evaluation",
        "/delegations",
        "/coding-sessions",
        "/code",
        "/integrations",
    }
)
HTML_PREFIXES = ("/delegations/", "/coding-sessions/")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def derive_password_hash(password: str, salt: bytes) -> str:
    """Salted scrypt derivation. Stdlib only: no new dependency for a demo gate."""
    return hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        maxmem=_SCRYPT_MAXMEM,
        dklen=_SCRYPT_DKLEN,
    ).hex()


def token_digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def is_open_path(path: str) -> bool:
    return path in OPEN_PATHS or path.startswith(OPEN_PREFIXES) or path in SIGNED_ENDPOINTS


def is_html_path(path: str) -> bool:
    return path in HTML_PATHS or path.startswith(HTML_PREFIXES)


def safe_next_path(candidate: str | None) -> str:
    """Only allow same-origin, single-slash paths as post-login redirect targets."""
    if not candidate or not candidate.startswith("/") or candidate.startswith("//"):
        return "/"
    if candidate.startswith("/login") or candidate.startswith("/logout"):
        return "/"
    return candidate[:300]


def session_actor(request: Request) -> dict[str, Any] | None:
    """The authenticated user for this request, or None when auth is disabled."""
    return getattr(request.state, "actor", None)


def session_actor_id(request: Request) -> str | None:
    actor = session_actor(request)
    return str(actor["id"]) if actor else None


class AuthService:
    """Credential verification, session lifecycle, and demo credential disclosure."""

    def __init__(self, db: Database, settings: Settings, audit: AuditLedger | None = None):
        self.db = db
        self.settings = settings
        self.audit = audit or AuditLedger(db)

    @property
    def enabled(self) -> bool:
        return self.settings.auth_enabled

    @property
    def cookie_name(self) -> str:
        return SESSION_COOKIE_NAME

    @property
    def ttl_seconds(self) -> int:
        return max(60, self.settings.session_ttl_minutes * 60)

    @property
    def cookie_secure(self) -> bool:
        """Secure outside debug; a plain-HTTP local demo would otherwise drop the cookie."""
        return not self.settings.debug

    # -- credential store ---------------------------------------------------------

    def _write_credential(self, user_id: str) -> None:
        salt = secrets.token_bytes(16)
        self.db.execute(
            "INSERT INTO user_credentials VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET algorithm=excluded.algorithm,"
            "salt=excluded.salt,password_hash=excluded.password_hash,"
            "updated_at=excluded.updated_at",
            (
                user_id,
                CREDENTIAL_ALGORITHM,
                salt.hex(),
                derive_password_hash(self.settings.demo_password, salt),
                _now().isoformat(),
            ),
        )

    def _credential(self, user_id: str) -> dict[str, Any] | None:
        row = self.db.one(
            "SELECT salt,password_hash,algorithm FROM user_credentials WHERE user_id=?",
            (user_id,),
        )
        if row is None or row["algorithm"] != CREDENTIAL_ALGORITHM:
            # `make demo-reset` drops the credential rows with the rest of the database, so
            # provision on demand rather than locking the demo out until a restart.
            self._write_credential(user_id)
            row = self.db.one(
                "SELECT salt,password_hash,algorithm FROM user_credentials WHERE user_id=?",
                (user_id,),
            )
        return row

    def ensure_credentials(self) -> int:
        """Provision or refresh the demo credential hash for every seeded user.

        Configuration is the source of truth: if `DEMO_PASSWORD` changed, the stored hash
        no longer verifies and is replaced with a freshly salted derivation. Called only
        when auth is enabled, so the default demo path pays no hashing cost.
        """
        provisioned = 0
        for user in self.db.all(
            "SELECT id FROM users WHERE workspace_id=? ORDER BY id",
            (self.settings.workspace_id,),
        ):
            row = self.db.one(
                "SELECT salt,password_hash,algorithm FROM user_credentials WHERE user_id=?",
                (user["id"],),
            )
            if row and row["algorithm"] == CREDENTIAL_ALGORITHM:
                expected = derive_password_hash(
                    self.settings.demo_password, bytes.fromhex(row["salt"])
                )
                if hmac.compare_digest(row["password_hash"], expected):
                    continue
            self._write_credential(user["id"])
            provisioned += 1
        return provisioned

    def demo_credentials(self) -> list[dict[str, str]]:
        """Seeded sign-in identities shown on the login page. This is a demo, on purpose."""
        if not self.db.one("SELECT user_id FROM user_credentials LIMIT 1"):
            self.ensure_credentials()
        return [
            {
                "username": row["id"],
                "display_name": row["display_name"],
                "role": row["role"],
                "password": self.settings.demo_password,
            }
            for row in self.db.all(
                "SELECT u.id,u.display_name,u.role FROM users u "
                "JOIN user_credentials c ON c.user_id=u.id "
                "WHERE u.workspace_id=? ORDER BY CASE u.role WHEN 'admin' THEN 0 "
                "WHEN 'owner' THEN 1 WHEN 'lead' THEN 2 ELSE 3 END, u.id",
                (self.settings.workspace_id,),
            )
        ]

    def verify_credentials(self, username: str, password: str) -> dict[str, Any] | None:
        """Return the user row on success, None on any failure. Constant-time compare."""
        candidate = (username or "").strip()[:80]
        user = self.db.one(
            "SELECT id,display_name,role FROM users WHERE id=? AND workspace_id=?",
            (candidate, self.settings.workspace_id),
        )
        credential = self._credential(candidate) if user else None
        if user is None or credential is None:
            # Spend comparable work on unknown usernames so the response is not a
            # trivially timeable user oracle.
            derive_password_hash(password or "", b"\x00" * 16)
            return None
        expected = derive_password_hash(password or "", bytes.fromhex(credential["salt"]))
        if not hmac.compare_digest(credential["password_hash"], expected):
            return None
        return {"id": user["id"], "display_name": user["display_name"], "role": user["role"]}

    # -- session lifecycle --------------------------------------------------------

    def issue_session(self, user_id: str) -> tuple[str, dict[str, Any]]:
        """Create a server-side session and return its HS256 JWT."""
        now = _now()
        expires_at = now + timedelta(seconds=self.ttl_seconds)
        session_id = f"sess_{uuid4().hex[:16]}"
        actor = self.db.one(
            "SELECT id,workspace_id,display_name,role FROM users WHERE id=? AND workspace_id=?",
            (user_id, self.settings.workspace_id),
        )
        if actor is None:
            raise ValueError("cannot issue a session for an unknown workspace user")
        issued_at = int(now.timestamp())
        token = jwt.encode(
            {
                "iss": JWT_ISSUER,
                "aud": JWT_AUDIENCE,
                "sub": actor["id"],
                "jti": session_id,
                "workspace_id": actor["workspace_id"],
                # This claim is descriptive. Authorization always loads the current
                # users.role value during verification.
                "role": actor["role"],
                "iat": issued_at,
                "nbf": issued_at,
                "exp": int(expires_at.timestamp()),
            },
            self.settings.session_secret,
            algorithm=JWT_ALGORITHM,
            headers={"typ": "JWT"},
        )
        self.db.execute("DELETE FROM sessions WHERE expires_at<?", (now.isoformat(),))
        self.db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)",
            (
                session_id,
                self.settings.workspace_id,
                user_id,
                token_digest(token),
                now.isoformat(),
                expires_at.isoformat(),
                None,
                None,
            ),
        )
        return token, {
            "id": session_id,
            "user_id": user_id,
            "expires_at": expires_at.isoformat(),
        }

    def verify_session(self, token: str | None) -> dict[str, Any] | None:
        """Validate JWT and server-side state. Return current DB identity on success."""
        if not token:
            return None
        try:
            claims = jwt.decode(
                token,
                self.settings.session_secret,
                algorithms=[JWT_ALGORITHM],
                audience=JWT_AUDIENCE,
                issuer=JWT_ISSUER,
                options={
                    "require": [
                        "iss",
                        "aud",
                        "sub",
                        "jti",
                        "workspace_id",
                        "role",
                        "iat",
                        "nbf",
                        "exp",
                    ]
                },
            )
        except PyJWTError:
            return None
        session_id = claims.get("jti")
        user_id = claims.get("sub")
        workspace_id = claims.get("workspace_id")
        identity_claims = (session_id, user_id, workspace_id)
        if not all(isinstance(value, str) and value for value in identity_claims):
            return None
        row = self.db.one(
            "SELECT s.id,s.workspace_id,s.user_id,s.token_hash,s.expires_at,s.revoked_at,"
            "u.display_name,u.role FROM sessions s JOIN users u "
            "ON u.id=s.user_id AND u.workspace_id=s.workspace_id "
            "WHERE s.id=? AND s.workspace_id=? AND s.user_id=?",
            (session_id, self.settings.workspace_id, user_id),
        )
        if row is None or row["revoked_at"]:
            return None
        if workspace_id != row["workspace_id"] or workspace_id != self.settings.workspace_id:
            return None
        if _parse(row["expires_at"]) <= _now():
            return None
        if not hmac.compare_digest(row["token_hash"], token_digest(token)):
            return None
        return {
            "session_id": row["id"],
            "expires_at": row["expires_at"],
            "actor": {
                "id": row["user_id"],
                "display_name": row["display_name"],
                "role": row["role"],
            },
        }

    def revoke_session(self, session_id: str, reason: str = "signed_out") -> bool:
        result = self.db.one("SELECT id FROM sessions WHERE id=?", (session_id,))
        if result is None:
            return False
        self.db.execute(
            "UPDATE sessions SET revoked_at=?,revoke_reason=? WHERE id=? AND revoked_at IS NULL",
            (_now().isoformat(), reason[:120], session_id),
        )
        return True

    # -- audit --------------------------------------------------------------------

    def record_login(self, actor: dict[str, Any], session_id: str) -> None:
        """Append to the existing hash-chained ledger. The cookie value is never recorded."""
        self.audit.append(
            self.settings.workspace_id,
            "auth_login_succeeded",
            "user",
            str(actor["id"]),
            "session",
            session_id,
            {"role": actor.get("role"), "mechanism": "demo_password", "mock_auth": True},
        )

    def record_login_failure(self, username: str) -> None:
        candidate = (username or "").strip()[:80]
        known = bool(
            self.db.one(
                "SELECT id FROM users WHERE id=? AND workspace_id=?",
                (candidate, self.settings.workspace_id),
            )
        )
        self.audit.append(
            self.settings.workspace_id,
            "auth_login_failed",
            "user" if known else "anonymous",
            candidate or "unknown",
            "session",
            "none",
            {"reason": "invalid_credentials", "known_user": known, "mock_auth": True},
        )

    def record_logout(self, actor_id: str, session_id: str) -> None:
        self.audit.append(
            self.settings.workspace_id,
            "auth_logout",
            "user",
            actor_id,
            "session",
            session_id,
            {"mechanism": "demo_password", "mock_auth": True},
        )
