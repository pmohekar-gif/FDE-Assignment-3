def create_payment(client, headers, key="ui-payment"):
    return client.post(
        "/v1/delegations",
        headers=headers,
        json={
            "issue_ref": "PAY-4471",
            "requester_id": "engineer-demo",
            "target_agent_id": "codex-cloud",
            "idempotency_key": key,
        },
    ).json()


def test_dashboard_filters_paginates_and_exposes_identity_controls(client):
    page = client.get("/?q=PAY-4471&team=Payments")
    assert page.status_code == 200
    assert "PAY-4471" in page.text
    assert "SEC-4502" not in page.text
    assert "Requester" in page.text
    assert "Target agent" in page.text
    assert "lead-web" in page.text
    assert "Not yet measured (5)" in page.text
    assert "outside_target" in page.text

    second_page = client.get("/?page=2")
    assert second_page.status_code == 200
    assert "page 2 of" in second_page.text
    assert client.get("/static/favicon.svg").status_code == 200


def test_delegation_page_shows_full_preapproval_contract_and_pipeline(client, headers):
    delegation = create_payment(client, headers)
    page = client.get(f"/delegations/{delegation['id']}")
    assert page.status_code == 200
    assert "Tools that would be granted" in page.text
    assert "open_draft_pr" in page.text
    assert "Never grantable" in page.text
    assert "merge_pr" in page.text
    assert "Optional rationale" in page.text
    assert "Warrant scope" in page.text
    assert "ALLOW threshold 0.70" in page.text
    assert "intake" in page.text and "record" in page.text
    assert "/policy#rule-" in page.text
    assert "existing single-charge path and add a regression test for double-submit." in page.text
    candidates = delegation["retrieval"]["candidates"][:4]
    titles = [item["title"] for item in candidates]
    assert len(titles) == len(set(titles))
    assert len(set(item["semantic_score"] for item in candidates)) > 1

    long_criterion = (
        "Expected: "
        + "the delegated worker preserves every invariant " * 6
        + "without ambiguity."
    )
    extraction = client.app.state.db.one(
        "SELECT result_json FROM extractions WHERE delegation_id = ?",
        (delegation["id"],),
    )
    extraction_payload = client.app.state.db.loads(extraction["result_json"])
    extraction_payload["acceptance_criteria"] = [long_criterion]
    client.app.state.db.execute(
        "UPDATE extractions SET result_json = ? WHERE delegation_id = ?",
        (client.app.state.db.dumps(extraction_payload), delegation["id"]),
    )

    rerendered = client.get(f"/delegations/{delegation['id']}")
    assert rerendered.status_code == 200
    assert 'class="truncated"' in rerendered.text
    assert f'title="{long_criterion}"' in rerendered.text
    assert "…" in rerendered.text


def test_policy_and_evaluation_pages_render_operator_views(client):
    policy = client.get("/policy")
    assert policy.status_code == 200
    assert "Policy workbench" in policy.text
    assert "Authority matrix" in policy.text
    assert "Edit, simulate, activate" in policy.text
    assert "id=\"rule-R-001\"" in policy.text
    css = client.get("/static/app.css").text
    assert ".policy-layout .table-wrap" in css
    assert "overflow-x:auto" in css
    assert "@media(max-width:1100px)" in css
    assert ".empty,.empty.inline" in css
    assert "font-size:13px" in css

    evaluation = client.get("/evaluation")
    assert evaluation.status_code == 200
    assert "Metrics and proposed targets" in evaluation.text
    assert "outside_target" in evaluation.text
    assert "Raw JSON" in evaluation.text


def test_audit_filters_cursor_and_actor_identity_boundary(client, headers):
    delegation = create_payment(client, headers, "ui-audit")
    admin = {"X-Actor-ID": "admin-demo"}
    filtered = client.get(
        "/v1/audit?agent_id=codex-cloud&verdict=REQUIRE_APPROVAL&limit=2",
        headers=admin,
    )
    assert filtered.status_code == 200
    body = filtered.json()
    assert body["chain_verified"] is True
    assert body["events"]
    assert all(item["agent_id"] == "codex-cloud" for item in body["events"])
    assert all(item["verdict"] == "REQUIRE_APPROVAL" for item in body["events"])
    if body["next_cursor"]:
        older = client.get(
            f"/v1/audit?cursor={body['next_cursor']}&limit=2", headers=admin
        )
        assert older.status_code == 200
        assert all(item["seq"] < body["next_cursor"] for item in older.json()["events"])

    mismatch = client.post(
        f"/v1/delegations/{delegation['id']}/decision",
        headers={**headers, "X-Actor-ID": "engineer-demo"},
        json={"action": "approve", "approver_id": "admin-demo"},
    )
    assert mismatch.status_code == 403
