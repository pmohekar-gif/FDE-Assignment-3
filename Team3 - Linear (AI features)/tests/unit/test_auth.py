from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest

from warrant.auth import (
    SESSION_COOKIE_NAME,
    AuthService,
    is_html_path,
    is_open_path,
    safe_next_path,
    token_digest,
)
from warrant.config import Settings
from warrant.db import Database
from warrant.seed import reset_and_seed

DEMO_PASSWORD = "warrant-demo"
SESSION_SECRET = "unit-session-secret-that-is-at-least-64-bytes-long-for-jwt-tests!!"


def build_settings(tmp_path: Path, **overrides) -> Settings:
    base = dict(
        database_path=tmp_path / "auth-unit.db",
        ai_provider="fixture",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4.1-mini",
        webhook_secret="test-webhook-secret",
        csrf_token="test-csrf",
        warrant_ttl_minutes=240,
        allow_sufficiency_threshold=0.70,
        fixture_failure=None,
        debug=False,
        auth_enabled=True,
        demo_password=DEMO_PASSWORD,
        session_secret=SESSION_SECRET,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def auth(tmp_path):
    settings = build_settings(tmp_path)
    reset_and_seed(settings)
    service = AuthService(Database(settings.database_path), settings)
    service.ensure_credentials()
    return service


def test_credentials_are_provisioned_as_salted_hashes_never_plaintext(auth):
    rows = auth.db.all("SELECT user_id,salt,password_hash,algorithm FROM user_credentials")
    assert len(rows) == 12
    assert {row["algorithm"] for row in rows} == {"scrypt-n16384-r8-p1"}
    # No plaintext anywhere, and every user gets an independent salt.
    assert all(DEMO_PASSWORD not in row["password_hash"] for row in rows)
    assert all(DEMO_PASSWORD not in row["salt"] for row in rows)
    assert len({row["salt"] for row in rows}) == len(rows)
    assert len({row["password_hash"] for row in rows}) == len(rows)


def test_ensure_credentials_is_idempotent_and_reprovisions_on_password_change(tmp_path):
    settings = build_settings(tmp_path)
    reset_and_seed(settings)
    db = Database(settings.database_path)
    service = AuthService(db, settings)
    assert service.ensure_credentials() == 12
    assert service.ensure_credentials() == 0

    rotated = AuthService(db, build_settings(tmp_path, demo_password="another-demo-password"))
    assert rotated.ensure_credentials() == 12
    assert rotated.verify_credentials("admin-demo", "another-demo-password") is not None
    assert rotated.verify_credentials("admin-demo", DEMO_PASSWORD) is None


def test_verify_credentials_accepts_seeded_user_and_rejects_everything_else(auth):
    actor = auth.verify_credentials("admin-demo", DEMO_PASSWORD)
    assert actor == {"id": "admin-demo", "display_name": "Casey Admin", "role": "admin"}
    assert auth.verify_credentials("admin-demo", "wrong") is None
    assert auth.verify_credentials("admin-demo", "") is None
    assert auth.verify_credentials("no-such-user", DEMO_PASSWORD) is None
    assert auth.verify_credentials("", "") is None
    # Role comes from the users table, so authority is unchanged by signing in.
    assert auth.verify_credentials("engineer-demo", DEMO_PASSWORD)["role"] == "member"


def test_session_issue_verify_and_revoke(auth):
    token, session = auth.issue_session("lead-web")
    stored = auth.db.one("SELECT * FROM sessions WHERE id=?", (session["id"],))
    assert stored["user_id"] == "lead-web"
    # The bearer/cookie token is never persisted, only its digest.
    assert stored["token_hash"] not in token
    assert len(stored["token_hash"]) == 64
    assert stored["token_hash"] == token_digest(token)

    header = jwt.get_unverified_header(token)
    claims = jwt.decode(
        token,
        SESSION_SECRET,
        algorithms=["HS256"],
        audience="warrant-api",
        issuer="warrant",
    )
    assert header == {"alg": "HS256", "typ": "JWT"}
    assert claims["sub"] == "lead-web"
    assert claims["jti"] == session["id"]
    assert claims["workspace_id"] == "ws-demo"
    assert claims["role"] == "lead"
    assert claims["iat"] <= claims["nbf"] <= claims["exp"]

    verified = auth.verify_session(token)
    assert verified["actor"] == {
        "id": "lead-web",
        "display_name": "Morgan Okafor",
        "role": "lead",
    }
    assert auth.revoke_session(session["id"]) is True
    assert auth.verify_session(token) is None
    assert auth.revoke_session("sess_missing") is False


def test_session_verification_rejects_tampering_and_foreign_signatures(auth, tmp_path):
    token, session = auth.issue_session("admin-demo")
    header, payload, signature = token.split(".")

    assert auth.verify_session(None) is None
    assert auth.verify_session("") is None
    assert auth.verify_session("not-a-jwt") is None
    assert auth.verify_session(f"{header}.{payload}.deadbeef") is None
    assert auth.verify_session(f"{header}.{payload}x.{signature}") is None

    # A cookie signed with a different SESSION_SECRET must not verify.
    other = AuthService(
        auth.db,
        build_settings(tmp_path, session_secret="other-session-secret-at-least-32-bytes"),
    )
    forged, _ = other.issue_session("admin-demo")
    assert auth.verify_session(forged) is None

    # A valid signature over a session row that no longer matches is still rejected.
    auth.db.execute("UPDATE sessions SET token_hash=? WHERE id=?", ("0" * 64, session["id"]))
    assert auth.verify_session(token) is None


def test_session_verification_uses_current_database_role_not_role_claim(auth):
    token, _ = auth.issue_session("engineer-demo")
    claims = jwt.decode(
        token,
        SESSION_SECRET,
        algorithms=["HS256"],
        audience="warrant-api",
        issuer="warrant",
    )
    assert claims["role"] == "member"

    auth.db.execute("UPDATE users SET role='lead' WHERE id='engineer-demo'")
    verified = auth.verify_session(token)
    assert verified is not None
    assert verified["actor"]["role"] == "lead"


def test_session_verification_rejects_wrong_issuer_audience_and_algorithm(auth):
    now = int(datetime.now(timezone.utc).timestamp())
    base = {
        "sub": "admin-demo",
        "jti": "sess_forged",
        "workspace_id": "ws-demo",
        "role": "admin",
        "iat": now,
        "nbf": now,
        "exp": now + 300,
    }
    invalid_boundaries = (
        {"iss": "other", "aud": "warrant-api"},
        {"iss": "warrant", "aud": "other"},
    )
    for overrides in invalid_boundaries:
        assert (
            auth.verify_session(
                jwt.encode({**base, **overrides}, SESSION_SECRET, algorithm="HS256")
            )
            is None
        )
    wrong_algorithm = jwt.encode(
        {**base, "iss": "warrant", "aud": "warrant-api"},
        SESSION_SECRET,
        algorithm="HS384",
    )
    assert auth.verify_session(wrong_algorithm) is None


def test_expired_sessions_are_rejected(auth):
    token, session = auth.issue_session("admin-demo")
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    auth.db.execute("UPDATE sessions SET expires_at=? WHERE id=?", (past, session["id"]))
    assert auth.verify_session(token) is None


def test_cookie_flags_and_ttl_follow_configuration(tmp_path):
    settings = build_settings(tmp_path, session_ttl_minutes=30)
    reset_and_seed(settings)
    service = AuthService(Database(settings.database_path), settings)
    assert service.cookie_name == SESSION_COOKIE_NAME
    assert service.ttl_seconds == 1800
    assert service.cookie_secure is True

    debug_service = AuthService(
        Database(settings.database_path), build_settings(tmp_path, debug=True)
    )
    assert debug_service.cookie_secure is False


def test_demo_credentials_expose_every_seeded_user_with_the_shared_password(auth):
    credentials = auth.demo_credentials()
    assert len(credentials) == 12
    assert credentials[0]["username"] == "admin-demo"
    assert {item["password"] for item in credentials} == {DEMO_PASSWORD}
    assert {item["username"] for item in credentials} >= {
        "admin-demo",
        "lead-web",
        "lead-payments",
        "engineer-demo",
    }


def test_auth_events_append_to_the_existing_hash_chain(auth):
    token, session = auth.issue_session("admin-demo")
    auth.record_login({"id": "admin-demo", "role": "admin"}, session["id"])
    auth.record_login_failure("admin-demo")
    auth.record_login_failure("attacker")
    auth.record_logout("admin-demo", session["id"])
    events = auth.db.all("SELECT event_type,actor_id,actor_type FROM audit_events ORDER BY seq")
    assert [event["event_type"] for event in events] == [
        "auth_login_succeeded",
        "auth_login_failed",
        "auth_login_failed",
        "auth_logout",
    ]
    assert events[1]["actor_type"] == "user"
    assert events[2]["actor_type"] == "anonymous"
    assert auth.audit.verify("ws-demo") is True
    # The session cookie value is never recorded in the ledger.
    payloads = auth.db.all("SELECT payload_json FROM audit_events")
    assert all(token not in row["payload_json"] for row in payloads)


def test_open_html_and_next_path_classification():
    assert is_open_path("/healthz") and is_open_path("/login") and is_open_path("/logout")
    assert is_open_path("/v1/auth/token")
    assert is_open_path("/static/app.css")
    assert is_open_path("/v1/hooks/tracker") and is_open_path("/v1/integrations/slack/events")
    assert not is_open_path("/") and not is_open_path("/v1/audit")

    assert is_html_path("/") and is_html_path("/audit") and is_html_path("/policy")
    assert is_html_path("/delegations/dg_1") and is_html_path("/coding-sessions/cs_1")
    assert not is_html_path("/v1/delegations/dg_1") and not is_html_path("/metrics")

    assert safe_next_path("/audit?verdict=DENY") == "/audit?verdict=DENY"
    assert safe_next_path(None) == "/"
    assert safe_next_path("https://evil.example/x") == "/"
    assert safe_next_path("//evil.example") == "/"
    assert safe_next_path("/login") == "/"
