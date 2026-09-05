"""Both identity modes: the header-driven default and the session-bound demo gate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from warrant.auth import SESSION_COOKIE_NAME
from warrant.config import Settings
from warrant.main import create_app
from warrant.seed import reset_and_seed

DEMO_PASSWORD = "warrant-demo"
SESSION_SECRET = "integration-session-secret-at-least-32-bytes"
CSRF = {"X-CSRF-Token": "test-csrf"}


def build_client(tmp_path, *, auth_enabled: bool, debug: bool = True, **overrides) -> TestClient:
    settings = Settings(
        database_path=tmp_path / f"auth-gate-{auth_enabled}-{debug}.db",
        ai_provider="fixture",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4.1-mini",
        webhook_secret="test-webhook-secret",
        csrf_token="test-csrf",
        warrant_ttl_minutes=240,
        allow_sufficiency_threshold=0.70,
        fixture_failure=None,
        # debug=True keeps the cookie non-Secure so it survives http:// in TestClient.
        debug=debug,
        auth_enabled=auth_enabled,
        demo_password=DEMO_PASSWORD,
        session_secret=SESSION_SECRET,
        **overrides,
    )
    reset_and_seed(settings)
    return TestClient(create_app(settings))


@pytest.fixture
def open_client(tmp_path):
    return build_client(tmp_path, auth_enabled=False)


@pytest.fixture
def gated_client(tmp_path):
    return build_client(tmp_path, auth_enabled=True)


def sign_in(client: TestClient, username: str, password: str = DEMO_PASSWORD):
    return client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": "test-csrf"},
        follow_redirects=False,
    )


def issue_token(client: TestClient, username: str, password: str = DEMO_PASSWORD):
    return client.post(
        "/v1/auth/token",
        json={"username": username, "password": password},
    )


# --- AUTH_ENABLED=false: today's behaviour, unchanged ---------------------------------


def test_disabled_mode_keeps_the_header_actor_path_and_switcher(open_client):
    assert open_client.get("/").status_code == 200
    assert open_client.get("/v1/audit", headers={"X-Actor-ID": "admin-demo"}).status_code == 200
    assert open_client.get("/v1/audit", headers={"X-Actor-ID": "engineer-demo"}).status_code == 403
    assert open_client.get("/audit?actor_id=admin-demo").status_code == 200

    dashboard = open_client.get("/").text
    assert 'id="actor-switcher"' in dashboard
    assert "Sign out" not in dashboard


def test_disabled_mode_has_no_sign_in_gate(open_client):
    redirected = open_client.get("/login", follow_redirects=False)
    assert redirected.status_code == 303
    assert redirected.headers["location"] == "/"
    posted = open_client.post("/login", data={"username": "admin-demo"}, follow_redirects=False)
    assert posted.status_code == 303
    assert SESSION_COOKIE_NAME not in posted.headers.get("set-cookie", "")


# --- AUTH_ENABLED=true: the session is the only identity -------------------------------


def test_unauthenticated_html_redirects_and_api_returns_typed_401(gated_client):
    home = gated_client.get("/", follow_redirects=False)
    assert home.status_code == 303
    assert home.headers["location"] == "/login"

    audit_page = gated_client.get("/audit?verdict=DENY", follow_redirects=False)
    assert audit_page.status_code == 303
    assert audit_page.headers["location"] == "/login?next=/audit%3Fverdict%3DDENY"

    api = gated_client.get("/v1/audit", headers={"X-Actor-ID": "admin-demo"})
    assert api.status_code == 401
    assert api.json() == {"error": "authentication required", "type": "Unauthorized"}
    assert api.headers["www-authenticate"] == "Bearer"

    mutation = gated_client.post(
        "/v1/delegations",
        headers=CSRF,
        json={
            "issue_ref": "WEB-4519",
            "requester_id": "lead-web",
            "target_agent_id": "codex-cloud",
            "idempotency_key": "unauthenticated",
        },
    )
    assert mutation.status_code == 401


def test_health_login_and_static_stay_open(gated_client):
    assert gated_client.get("/healthz").status_code == 200
    login = gated_client.get("/login")
    assert login.status_code == 200
    assert gated_client.get("/static/app.css").status_code == 200
    # The login page has to publish the demo credentials; a grader must be able to get in.
    for expected in ("admin-demo", "lead-web", "engineer-demo", DEMO_PASSWORD):
        assert expected in login.text
    assert "demo identity gate" in login.text


def test_successful_sign_in_issues_a_session_cookie_and_resolves_the_actor(gated_client):
    response = sign_in(gated_client, "lead-payments")
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=43200" in cookie
    assert gated_client.cookies.get(SESSION_COOKIE_NAME).count(".") == 2

    page = gated_client.get("/")
    assert page.status_code == 200
    assert "Samira Lind" in page.text
    assert "Sign out" in page.text
    assert 'id="actor-switcher"' not in page.text
    assert '"lead-payments"' in page.text


def test_wrong_password_and_unknown_user_are_rejected_without_a_session(gated_client):
    for username, password in (("admin-demo", "not-the-password"), ("ghost", DEMO_PASSWORD)):
        response = sign_in(gated_client, username, password)
        assert response.status_code == 401
        assert SESSION_COOKIE_NAME not in response.headers.get("set-cookie", "")
        assert "Sign-in failed" in response.text
    assert gated_client.get("/", follow_redirects=False).status_code == 303
    assert gated_client.get("/v1/audit").status_code == 401


def test_login_requires_the_demo_csrf_token(gated_client):
    response = gated_client.post(
        "/login",
        data={"username": "admin-demo", "password": DEMO_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert response.json()["error"] == "missing or invalid CSRF token"


def test_forged_actor_header_cannot_escalate_to_admin(gated_client):
    assert sign_in(gated_client, "engineer-demo").status_code == 303

    forged = gated_client.get("/v1/audit", headers={"X-Actor-ID": "admin-demo"})
    assert forged.status_code == 403
    assert forged.json()["type"] == "Forbidden"

    forged_page = gated_client.get("/audit?actor_id=admin-demo")
    assert forged_page.status_code == 403

    forged_policy = gated_client.post(
        "/v1/policies/simulate",
        headers={**CSRF, "X-Actor-ID": "admin-demo"},
        json={"yaml_source": "version: v1"},
    )
    assert forged_policy.status_code == 403

    # The header is ignored, not merged: the session user is still the actor.
    assert (
        "Signed in as <b>Devin Reyes"
        in gated_client.get("/", headers={"X-Actor-ID": "admin-demo"}).text
    )

    # Authority follows the session, so the admin session succeeds where the header failed.
    gated_client.post("/logout", data={"csrf_token": "test-csrf"})
    assert sign_in(gated_client, "admin-demo").status_code == 303
    assert gated_client.get("/v1/audit", headers={"X-Actor-ID": "engineer-demo"}).status_code == 200


def test_body_declared_actor_must_match_the_session(gated_client):
    assert sign_in(gated_client, "engineer-demo").status_code == 303
    created = gated_client.post(
        "/v1/delegations",
        headers=CSRF,
        json={
            "issue_ref": "PAY-4471",
            "requester_id": "engineer-demo",
            "target_agent_id": "codex-cloud",
            "idempotency_key": "declared-actor",
        },
    ).json()
    impersonated = gated_client.post(
        f"/v1/delegations/{created['id']}/decision",
        headers=CSRF,
        json={"action": "approve", "approver_id": "admin-demo"},
    )
    assert impersonated.status_code == 403
    assert impersonated.json()["error"] == "declared actor must match the authenticated session"


def test_approval_under_a_session_records_the_authenticated_user_as_authority(gated_client):
    assert sign_in(gated_client, "lead-payments").status_code == 303
    created = gated_client.post(
        "/v1/delegations",
        headers=CSRF,
        json={
            "issue_ref": "PAY-4471",
            "requester_id": "engineer-demo",
            "target_agent_id": "codex-cloud",
            "idempotency_key": "session-approval",
        },
    ).json()
    assert created["status"] == "awaiting_approval"
    approved = gated_client.post(
        f"/v1/delegations/{created['id']}/decision",
        headers={**CSRF, "X-Actor-ID": "admin-demo"},
        json={"action": "approve", "approver_id": "lead-payments"},
    )
    assert approved.status_code == 200
    assert approved.json()["warrant"]["authority_user_id"] == "lead-payments"

    db = gated_client.app.state.db
    issued = db.one(
        "SELECT actor_id FROM audit_events WHERE event_type='warrant_issued' ORDER BY seq DESC"
    )
    assert issued["actor_id"] == "lead-payments"
    assert db.one("SELECT approver_id FROM approvals LIMIT 1")["approver_id"] == "lead-payments"
    assert gated_client.app.state.service.audit.verify("ws-demo") is True


def test_login_failure_and_logout_are_recorded_in_the_audit_chain(gated_client):
    sign_in(gated_client, "admin-demo", "wrong-password")
    assert sign_in(gated_client, "admin-demo").status_code == 303
    ledger = gated_client.get("/v1/audit").json()
    assert ledger["chain_verified"] is True
    recorded = [event["event_type"] for event in ledger["events"]]
    assert "auth_login_failed" in recorded
    assert "auth_login_succeeded" in recorded
    session_cookie = gated_client.cookies.get(SESSION_COOKIE_NAME)
    assert all(session_cookie not in str(event["payload"]) for event in ledger["events"])

    logout = gated_client.post("/logout", data={"csrf_token": "test-csrf"}, follow_redirects=False)
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"


def test_logout_revokes_the_session_server_side(gated_client):
    assert sign_in(gated_client, "admin-demo").status_code == 303
    cookie = gated_client.cookies.get(SESSION_COOKIE_NAME)
    assert gated_client.get("/v1/audit").status_code == 200

    assert (
        gated_client.post(
            "/logout", data={"csrf_token": "test-csrf"}, follow_redirects=False
        ).status_code
        == 303
    )
    assert gated_client.get("/v1/audit").status_code == 401
    # Replaying the old cookie value cannot resurrect the revoked session.
    replayed = gated_client.get("/v1/audit", headers={"Cookie": f"{SESSION_COOKIE_NAME}={cookie}"})
    assert replayed.status_code == 401
    assert (
        gated_client.app.state.db.one(
            "SELECT revoked_at,revoke_reason FROM sessions ORDER BY created_at DESC LIMIT 1"
        )["revoke_reason"]
        == "signed_out"
    )


def test_tampered_and_expired_cookies_are_rejected(gated_client):
    assert sign_in(gated_client, "admin-demo").status_code == 303
    good = gated_client.cookies.get(SESSION_COOKIE_NAME)
    claims = jwt.decode(
        good,
        SESSION_SECRET,
        algorithms=["HS256"],
        audience="warrant-api",
        issuer="warrant",
    )
    header, payload, signature = good.split(".")

    tampered = f"{header}.{payload}x.{signature}"
    assert (
        gated_client.get(
            "/v1/audit", headers={"Cookie": f"{SESSION_COOKIE_NAME}={tampered}"}
        ).status_code
        == 401
    )

    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    gated_client.app.state.db.execute(
        "UPDATE sessions SET expires_at=? WHERE id=?", (past, claims["jti"])
    )
    assert gated_client.get("/v1/audit").status_code == 401


def test_token_endpoint_uses_shared_password_and_returns_distinct_roles(gated_client):
    expected_roles = {"admin-demo": "admin", "lead-web": "lead", "engineer-demo": "member"}
    for username, role in expected_roles.items():
        response = issue_token(gated_client, username)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"
        payload = response.json()
        assert payload["token_type"] == "bearer"
        assert payload["expires_in"] == 43_200
        assert payload["user"]["id"] == username
        assert payload["user"]["role"] == role
        claims = jwt.decode(
            payload["access_token"],
            SESSION_SECRET,
            algorithms=["HS256"],
            audience="warrant-api",
            issuer="warrant",
        )
        assert claims["sub"] == username
        assert claims["role"] == role


def test_bearer_auth_me_role_authorization_and_invalid_precedence(gated_client):
    admin_token = issue_token(gated_client, "admin-demo").json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    assert gated_client.get("/v1/auth/me", headers=admin_headers).json()["user"] == {
        "id": "admin-demo",
        "display_name": "Casey Admin",
        "role": "admin",
    }
    assert gated_client.get("/v1/audit", headers=admin_headers).status_code == 200

    member_token = issue_token(gated_client, "engineer-demo").json()["access_token"]
    assert (
        gated_client.get(
            "/v1/audit", headers={"Authorization": f"Bearer {member_token}"}
        ).status_code
        == 403
    )

    # An explicitly supplied invalid bearer token cannot fall back to a valid cookie.
    assert sign_in(gated_client, "admin-demo").status_code == 303
    invalid = gated_client.get("/v1/audit", headers={"Authorization": "Bearer invalid.token.value"})
    assert invalid.status_code == 401
    assert invalid.headers["www-authenticate"] == "Bearer"


def test_bearer_logout_revokes_token_immediately(gated_client):
    token = issue_token(gated_client, "admin-demo").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert gated_client.get("/v1/audit", headers=headers).status_code == 200
    logout = gated_client.post("/v1/auth/logout", headers=headers)
    assert logout.status_code == 204
    replay = gated_client.get("/v1/audit", headers=headers)
    assert replay.status_code == 401
    assert replay.headers["www-authenticate"] == "Bearer"


def test_token_endpoint_rejects_bad_credentials(gated_client):
    response = issue_token(gated_client, "admin-demo", "wrong")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"error": "invalid credentials", "type": "Unauthorized"}


def test_existing_token_loads_current_role_from_database(gated_client):
    token = issue_token(gated_client, "admin-demo").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert gated_client.get("/v1/audit", headers=headers).status_code == 200

    gated_client.app.state.db.execute("UPDATE users SET role='member' WHERE id='admin-demo'")
    response = gated_client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "member"
    assert gated_client.get("/v1/audit", headers=headers).status_code == 403


def test_session_cookie_is_secure_outside_debug(tmp_path):
    client = build_client(tmp_path, auth_enabled=True, debug=False)
    response = sign_in(client, "admin-demo")
    assert response.status_code == 303
    assert "Secure" in response.headers["set-cookie"]
