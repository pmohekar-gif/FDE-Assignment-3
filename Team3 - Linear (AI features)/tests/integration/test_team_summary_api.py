"""Integration tests for GET /v1/summaries/team/{team}.

Covers every acceptance criterion from the feature spec:
  - happy path with delegations
  - admin/owner auth gate
  - read-only proof (snapshot before/after)
  - no model_usage rows created
  - telemetry written without raw prose
  - audit chain status in response
  - team filtering does not leak another team's delegations
  - unknown team → 404
  - authority boundary fields
"""

from __future__ import annotations

ADMIN_HEADER = {"X-Actor-ID": "priyanka-mohekar"}
OWNER_HEADER = {"X-Actor-ID": "chirayu-gupta"}
MEMBER_HEADER = {"X-Actor-ID": "kriti-developer"}
CSRF_HEADERS = {"X-CSRF-Token": "test-csrf"}


def _create_delegation(
    client, issue_ref: str, key: str, requester_id: str = "kriti-developer"
) -> dict:
    """Create a delegation through the public API so DB state is realistic."""
    return client.post(
        "/v1/delegations",
        headers=CSRF_HEADERS,
        json={
            "issue_ref": issue_ref,
            "requester_id": requester_id,
            "target_agent_id": "codex-cloud",
            "idempotency_key": key,
        },
    ).json()


def _count_rows(client, table: str) -> int:
    """Count rows in a table via the test client's underlying DB."""
    db = client.app.state.db
    row = db.one(f"SELECT COUNT(*) AS n FROM {table}")
    return int(row["n"]) if row else 0


def _summary(client, team: str, actor_header: dict | None = None) -> dict:
    """GET the team summary as a dict (includes status_code via response)."""
    headers = ADMIN_HEADER if actor_header is None else actor_header
    resp = client.get(f"/v1/summaries/team/{team}", headers=headers)
    return {"status_code": resp.status_code, **resp.json()}


# ------------------------------------------------------------------
# 1. Happy path: structured accountability fields present
# ------------------------------------------------------------------


def test_happy_path_with_delegations(client):
    # WEB-4519 is in team "Web" from seed data
    _create_delegation(client, "WEB-4519", "summary-happy-1")

    result = _summary(client, "Web")
    assert result["status_code"] == 200

    # Authority boundary
    assert result["authorising"] is False
    assert result["decision_source"] == "deterministic_policy"
    assert result["summary_may_change_verdict"] is False

    # Team overview
    assert result["team"] == "Web"
    assert result["issue_count"] > 0
    assert isinstance(result["priority_mix"], dict)

    # Delegation accountability
    assert result["delegation_count"] >= 1
    assert len(result["recent_delegations"]) >= 1
    delegation = result["recent_delegations"][0]
    assert "id" in delegation
    assert "status" in delegation
    assert "target_agent_id" in delegation
    assert "issue_ref" in delegation

    # Verdict counts
    assert isinstance(result["verdict_counts"], dict)

    # Pending approvals
    assert isinstance(result["pending_human_approvals"], int)

    # Warrant state
    for key in ("active_warrants", "expired_warrants", "revoked_warrants", "consumed_warrants"):
        assert isinstance(result[key], int)

    # Verification health
    assert isinstance(result["failed_verifications"], int)
    assert isinstance(result["inconclusive_verifications"], int)

    # Risk surfaces
    assert isinstance(result["risky_surfaces"], list)
    assert isinstance(result["protected_surfaces"], list)

    # Denied delegations
    assert isinstance(result["denied_delegations"], int)

    # Audit chain
    assert "audit_chain" in result
    assert isinstance(result["audit_chain"]["verified"], bool)


# ------------------------------------------------------------------
# 2. Admin/owner gate
# ------------------------------------------------------------------


def test_admin_owner_required(client):
    # Non-admin (member role) -> 403
    result = _summary(client, "Web", MEMBER_HEADER)
    assert result["status_code"] == 403

    # No actor header at all -> 403
    result = _summary(client, "Web", {})
    assert result["status_code"] == 403

    # Admin -> 200
    result = _summary(client, "Web", ADMIN_HEADER)
    assert result["status_code"] == 200

    # Owner -> 200
    result = _summary(client, "Web", OWNER_HEADER)
    assert result["status_code"] == 200


# ------------------------------------------------------------------
# 3. Read-only: counts unchanged before/after
# ------------------------------------------------------------------


def test_read_only_no_mutations(client):
    _create_delegation(client, "WEB-4519", "summary-readonly-1")

    # Snapshot counts before
    before = {
        "delegations": _count_rows(client, "delegations"),
        "warrants": _count_rows(client, "warrants"),
        "approvals": _count_rows(client, "approvals"),
        "evidence_bundles": _count_rows(client, "evidence_bundles"),
        "policy_decisions": _count_rows(client, "policy_decisions"),
        "issues": _count_rows(client, "issues"),
        "risk_assessments": _count_rows(client, "risk_assessments"),
    }

    _summary(client, "Web")

    # Snapshot counts after
    after = {
        "delegations": _count_rows(client, "delegations"),
        "warrants": _count_rows(client, "warrants"),
        "approvals": _count_rows(client, "approvals"),
        "evidence_bundles": _count_rows(client, "evidence_bundles"),
        "policy_decisions": _count_rows(client, "policy_decisions"),
        "issues": _count_rows(client, "issues"),
        "risk_assessments": _count_rows(client, "risk_assessments"),
    }

    assert before == after, f"Summary endpoint mutated state: {before} -> {after}"


# ------------------------------------------------------------------
# 4. No model_usage row created
# ------------------------------------------------------------------


def test_no_model_usage_row(client):
    usage_before = _count_rows(client, "model_usage")

    _summary(client, "Web")

    usage_after = _count_rows(client, "model_usage")
    assert usage_after == usage_before, "Summary endpoint should not create model_usage rows"


# ------------------------------------------------------------------
# 5. Telemetry written without raw prose
# ------------------------------------------------------------------


def test_telemetry_written_without_prose(client):
    _summary(client, "Web")

    db = client.app.state.db
    events = db.all(
        "SELECT * FROM telemetry_events WHERE name='team_summary_viewed' "
        "ORDER BY created_at DESC LIMIT 1"
    )
    assert len(events) >= 1, "Expected team_summary_viewed telemetry event"

    import json

    attrs = json.loads(events[0]["attributes_json"])

    # Must contain aggregate counts
    assert "team" in attrs
    assert "issue_count" in attrs
    assert "delegation_count" in attrs

    # Must NOT contain raw issue data or prose
    for forbidden_key in ("title", "body", "prose", "body_normalised", "summary"):
        assert forbidden_key not in attrs, f"Telemetry must not contain '{forbidden_key}'"


# ------------------------------------------------------------------
# 6. Audit chain status in response
# ------------------------------------------------------------------


def test_audit_chain_status_in_response(client):
    result = _summary(client, "Web")
    assert result["status_code"] == 200

    audit = result["audit_chain"]
    assert "verified" in audit
    assert isinstance(audit["verified"], bool)
    assert "broken_at_seq" in audit


# ------------------------------------------------------------------
# 7. Team filtering: no cross-team leak
# ------------------------------------------------------------------


def test_team_filtering_no_cross_leak(client):
    # Create delegation for Payments team
    pay_delegation = _create_delegation(client, "PAY-4471", "summary-leak-pay")
    pay_delegation_id = pay_delegation["id"]

    # Create delegation for Web team
    _create_delegation(client, "WEB-4519", "summary-leak-web")

    # Fetch summary for Web only
    web_summary = _summary(client, "Web")
    assert web_summary["status_code"] == 200

    # Payments delegation must NOT appear in Web's summary
    web_delegation_ids = [d["id"] for d in web_summary["recent_delegations"]]
    assert pay_delegation_id not in web_delegation_ids, (
        "Payments delegation leaked into Web team summary"
    )


# ------------------------------------------------------------------
# 8. Unknown team -> 404
# ------------------------------------------------------------------


def test_unknown_team_returns_404(client):
    result = _summary(client, "NonExistentTeam")
    assert result["status_code"] == 404


# ------------------------------------------------------------------
# 9. Authority boundary fields present
# ------------------------------------------------------------------


def test_authority_boundary_fields(client):
    result = _summary(client, "Web")
    assert result["status_code"] == 200

    assert result["authorising"] is False
    assert result["decision_source"] == "deterministic_policy"
    assert result["summary_may_change_verdict"] is False


# ------------------------------------------------------------------
# 10. Regression: aggregates cover ALL delegations, not just recent 20
# ------------------------------------------------------------------


def test_aggregates_cover_all_delegations_not_just_recent(client):
    # The FDE seed is intentionally curated, not padded with random Web issues.
    # Create one delegation per available Web ticket and verify the aggregate is not tied
    # to the rendered recent list.
    db = client.app.state.db
    web_issues = db.all(
        "SELECT external_key FROM issues WHERE workspace_id='ws-demo' AND team='Web' "
        "ORDER BY external_key"
    )
    assert len(web_issues) >= 3, "Seed data should include multiple Web demo issues"

    for i, issue in enumerate(web_issues):
        _create_delegation(client, issue["external_key"], f"agg-regression-{i}")

    result = _summary(client, "Web")
    assert result["status_code"] == 200

    assert result["delegation_count"] >= len(web_issues)
    assert len(result["recent_delegations"]) == min(20, result["delegation_count"])

    total_verdicts = sum(result["verdict_counts"].values())
    assert total_verdicts >= len(web_issues)


# ------------------------------------------------------------------
# 11. Regression: unswept expired warrants counted as expired
# ------------------------------------------------------------------


def test_unswept_expired_warrant_counted_as_expired(client, headers):
    # Create a delegation that yields a warrant (WEB-4519 = safe auto-allow for chirayu-gupta)
    delegation = _create_delegation(client, "WEB-4519", "expiry-regression", "chirayu-gupta")
    assert delegation.get("warrant"), "Expected warrant to be issued"
    warrant_id = delegation["warrant"]["id"]

    # Set expires_at to a past timestamp while leaving expired_at NULL
    db = client.app.state.db
    db.execute(
        "UPDATE warrants SET expires_at='2020-01-01T00:00:00+00:00', expired_at=NULL "
        "WHERE id=?",
        (warrant_id,),
    )

    # Verify the row really has expired_at NULL
    row = db.one("SELECT expired_at, expires_at FROM warrants WHERE id=?", (warrant_id,))
    assert row["expired_at"] is None, "expired_at should be NULL for this test"
    assert row["expires_at"] <= "2021-01-01", "expires_at should be in the past"

    result = _summary(client, "Web")
    assert result["status_code"] == 200

    # The warrant must be counted as expired, not active
    assert result["expired_warrants"] >= 1, (
        f"expired_warrants={result['expired_warrants']} should count the unswept warrant"
    )

    # Verify the endpoint did NOT mutate expired_at (read-only)
    # Verify the endpoint did NOT mutate expired_at (read-only)
    row_after = db.one("SELECT expired_at FROM warrants WHERE id=?", (warrant_id,))
    assert row_after["expired_at"] is None, (
        "Summary endpoint must not mutate expired_at (read-only)"
    )


# ------------------------------------------------------------------
# 12. Caching and non-authorising prose lifecycle
# ------------------------------------------------------------------

def test_team_summary_caching_and_prose(client, headers):
    db = client.app.state.db

    # Start clean for "Web" team
    db.execute("DELETE FROM team_summaries WHERE team='Web'")

    # 1. GET miss does not write cache
    usage_before = _count_rows(client, "model_usage")
    get1 = _summary(client, "Web")
    assert get1["status_code"] == 200
    assert get1["cache_status"] == "miss"
    assert get1["refresh_required"] is True
    assert get1["prose"] is None
    
    cache_row = db.one("SELECT * FROM team_summaries WHERE team='Web'")
    assert cache_row is None, "GET miss must not write cache"
    assert _count_rows(client, "model_usage") == usage_before, "No model usage on GET"

    # 2. POST refresh requires CSRF and admin/owner
    no_csrf = client.post("/v1/summaries/team/Web/refresh", headers=ADMIN_HEADER)
    assert no_csrf.status_code == 400

    no_admin = client.post(
        "/v1/summaries/team/Web/refresh",
        headers={**CSRF_HEADERS, **MEMBER_HEADER}
    )
    assert no_admin.status_code == 403

    # 3. POST refresh writes cache + audit + minimal telemetry
    audit_before = _count_rows(client, "audit_events")
    telemetry_before = _count_rows(client, "telemetry_events")
    
    refresh = client.post(
        "/v1/summaries/team/Web/refresh",
        headers={**CSRF_HEADERS, **ADMIN_HEADER}
    ).json()
    
    assert refresh["cache_status"] == "refreshed"
    assert refresh["refresh_required"] is False
    assert refresh["prose_source"] == "model"
    assert refresh["provider"] == "fixture"
    assert isinstance(refresh["prose"], str)
    assert _count_rows(client, "model_usage") == usage_before + 1, "Model usage recorded on POST"

    # Prose contains explicit non-authorising disclaimer
    assert "It cannot approve or deny delegations" in refresh["prose"]
    
    # Cache was written
    cache_row = db.one("SELECT * FROM team_summaries WHERE team='Web'")
    assert cache_row is not None
    assert cache_row["facts_hash"] == refresh["facts_hash"]
    
    # Audit event created
    assert _count_rows(client, "audit_events") == audit_before + 1
    last_audit = db.one("SELECT * FROM audit_events ORDER BY seq DESC LIMIT 1")
    assert last_audit["event_type"] == "team_summary_refreshed"
    assert "facts_hash" in last_audit["payload_json"]
    assert '"prose":' not in last_audit["payload_json"]
    assert "It cannot approve" not in last_audit["payload_json"]
    
    # Telemetry created
    assert _count_rows(client, "telemetry_events") >= telemetry_before + 1
    last_telemetry = db.one(
        "SELECT * FROM telemetry_events WHERE name='team_summary_refreshed' "
        "ORDER BY rowid DESC LIMIT 1"
    )
    assert last_telemetry["name"] == "team_summary_refreshed"
    assert '"prose":' not in last_telemetry["attributes_json"]

    # 4. Subsequent GET is cache hit — returns provider/model provenance
    get2 = _summary(client, "Web")
    assert get2["cache_status"] == "hit"
    assert get2["refresh_required"] is False
    assert get2["prose"] == refresh["prose"]
    assert get2["provider"] == "fixture"
    assert get2["model"] is not None

    # 5. Creating a new delegation makes cache stale
    _create_delegation(client, "WEB-4519", "stale-cache-test", "chirayu-gupta")
    
    get3 = _summary(client, "Web")
    assert get3["cache_status"] == "stale"
    assert get3["refresh_required"] is True
    assert get3["prose"] == refresh["prose"]


def test_team_summary_get_miss_provenance(client):
    """GET cache miss returns provider and model as None."""
    db = client.app.state.db
    db.execute("DELETE FROM team_summaries WHERE team='Web'")
    get1 = _summary(client, "Web")
    assert get1["cache_status"] == "miss"
    assert get1["provider"] is None
    assert get1["model"] is None


def test_team_summary_provider_failure_fallback(client_factory):
    client = client_factory("team_summary")
    db = client.app.state.db
    db.execute("DELETE FROM team_summaries WHERE team='Web'")
    
    usage_before = _count_rows(client, "model_usage")
    refresh = client.post(
        "/v1/summaries/team/Web/refresh",
        headers={**CSRF_HEADERS, **ADMIN_HEADER}
    ).json()
    
    assert refresh["prose_source"] == "structured_fallback"
    assert refresh["provider"] is None
    # Failed provider call still records a model_usage row
    assert _count_rows(client, "model_usage") == usage_before + 1
    failed_row = db.one(
        "SELECT * FROM model_usage "
        "WHERE operation='team_summary' ORDER BY rowid DESC LIMIT 1"
    )
    assert failed_row["success"] == 0
    assert failed_row["error_class"] is not None


def test_team_summary_malformed_fallback(client_factory):
    client = client_factory("malformed")
    db = client.app.state.db
    db.execute("DELETE FROM team_summaries WHERE team='Web'")
    
    usage_before = _count_rows(client, "model_usage")
    refresh = client.post(
        "/v1/summaries/team/Web/refresh",
        headers={**CSRF_HEADERS, **ADMIN_HEADER}
    ).json()
    
    assert refresh["prose_source"] == "structured_fallback"
    assert refresh["provider"] is None
    # Malformed provider call still records a model_usage row
    assert _count_rows(client, "model_usage") == usage_before + 1
    failed_row = db.one(
        "SELECT * FROM model_usage "
        "WHERE operation='team_summary' ORDER BY rowid DESC LIMIT 1"
    )
    assert failed_row["success"] == 0
    assert failed_row["error_class"] is not None


def test_team_summary_openrouter_block(client_factory):
    client = client_factory()
    db = client.app.state.db
    import dataclasses
    patched_settings = dataclasses.replace(
        client.app.state.settings, ai_provider="openrouter"
    )
    # Patch both app.state.settings and the service's own settings reference
    client.app.state.settings = patched_settings
    client.app.state.service.settings = patched_settings
    
    # Ensure there is a linear issue
    issue = db.one(
        "SELECT id, workspace_id FROM issues "
        "WHERE external_key='WEB-4519'"
    )
    db.execute(
        "INSERT OR IGNORE INTO linear_issue_links "
        "(issue_id, workspace_id, external_id, external_key, source, url, "
        "external_created_at, external_updated_at, description_sha256, state, team_key, "
        "imported_at) "
        "VALUES (?, ?, 'ext-1', 'WEB-4519', 'linear', 'url', "
        "'now', 'now', 'hash', 'open', 'WEB', 'now')",
        (issue["id"], issue["workspace_id"])
    )
    
    usage_before = _count_rows(client, "model_usage")
    refresh_blocked = client.post(
        "/v1/summaries/team/Web/refresh",
        headers={**CSRF_HEADERS, **ADMIN_HEADER}
    ).json()
    
    assert refresh_blocked["prose_source"] == "structured_fallback"
    # Provider skipped by policy — no model_usage recorded at all
    assert _count_rows(client, "model_usage") == usage_before


def test_chatcompletions_team_summary_parses_correctly():
    """ChatCompletionsProvider._call parses team_summary as TeamSummaryProse."""
    import json

    from warrant.providers import ChatCompletionsProvider
    from warrant.schemas import TeamSummaryProse

    class MockProvider(ChatCompletionsProvider):
        name = "mock"

        def __init__(self):
            self.api_key = "mock"
            self.base_url = "http://localhost"
            self.model = "test-model"
            self.structured_output_mode = "json_object"
            self.timeout_seconds = 5
            self.extra_headers = {}
            self.include_usage = False
            self.reasoning = None

        def _post_chat_completions(self, payload):
            return {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "prose": "some valid model summary"
                        })
                    }
                }],
                "model": "test-model",
            }

    provider = MockProvider()
    response = provider.team_summary({"team": "Web", "active_warrants": 1})
    assert isinstance(response.value, TeamSummaryProse)
    assert response.value.prose == "some valid model summary"
    assert response.provider == "mock"
