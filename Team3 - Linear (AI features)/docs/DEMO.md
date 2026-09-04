# Warrant Demo — 4 to 6 Minutes

## Reset

```bash
cd "Session/Tasks/Week3/Team3 - Linear (AI features)"
make demo-reset
make dev
```

Open <http://127.0.0.1:8000>. Point out **SIMULATED / FIXTURE AI** and the
synthetic-data notice. Do not describe fixture inference as live AI.

## 1. Operator inbox and explicit identities

The first screen is an operator queue: work needing a decision, the searchable issue
inbox, then evaluation integrity. Show the requester and target-agent selectors. The
requester options expose declared code-owner paths so ownership is visible before work
is delegated.

Choose **Devin Reyes** and **Codex Cloud**, filter to `PAY-4471`, then click **Run
governed delegation**. Point out the visible nine-stage progress state while the request
runs.

## 2. Deterministic decision before approval

On the delegation page show:

- the intake → record pipeline trace;
- evidence sufficiency against the labelled 0.70 threshold;
- missing information, affected surfaces, and retrieved precedents;
- plain-English reason and rule explanations linked to the active YAML;
- the exact allowed and never-grantable tools before the human acts.

Say: “The provider described the work. Its schema cannot grant authority. Policy
`v1`, identified by this SHA, returned `REQUIRE_APPROVAL`.”

## 3. Real human approval control

Leave only the first scope checkbox selected, enter a short rationale, and click
**Narrow**. Confirm the narrowing. Show the resulting warrant, allowed/denied tools,
relative expiry, and evidence contract.

Switch **Acting as** to Devin before approval on another payment delegation to show the
inline self-approval warning and the server's explanatory 403. Switch back to Casey
Admin. There is no force or override control.

## 4. Evidence failure and correction

Open **Return synthetic evidence**, add an out-of-scope filename, and submit. The 422
panel shows each gate-1 check, names the bad file, and states that the nonce remains
unconsumed. Remove the bad file and use **Resubmit corrected evidence**. Show the final
verification verdict; keep calling the evidence and fixture judge simulated.

## 5. Terminal denial

Return to the inbox and run `SEC-4502`. Show the injection reason, terminal security
rule, `DENY`, explanatory “What would have to change” panel, and absence of any approval
or warrant action.

## 6. Policy workbench — executable YAML

Open **Policy**. Show the active version/SHA, ordered rules, and the consequence ×
reversibility matrix. In the editor:

1. change `version: v1` to a fresh immutable version;
2. make one rule stricter—for example change `R-002` from `REQUIRE_APPROVAL` to `DENY`;
3. click **Simulate** and inspect persisted-delegation diffs plus the adversarial guard;
4. activate only after `can_activate` passes;
5. re-delegate `PAY-4471` and show the changed verdict.

To demonstrate a later relaxation, create another fresh version restoring
`REQUIRE_APPROVAL`, simulate it, and activate it. The UI never bypasses simulation and
never offers an override; line-level 422 and adversarial 409 failures render inline.

## 7. Audit questions and evaluation honesty

With Casey Admin acting, open **Audit**. Filter by Codex, Casey, a billing surface, and
`REQUIRE_APPROVAL`. Show grouped delegation stories, expandable payloads, re-verification,
cursor navigation, and a CSV export that retains the active filters. Switch to a
non-admin actor and revisit Audit to demonstrate the 403 boundary.

Open **Evaluation**. State precisely: “On 120 synthetic, labelled policy cases, unsafe
allows are zero and fail-closed correctness is 100%. Approval burden is 43.64%, outside
the 35% target and above K3's 40% threshold. Verdict accuracy is interpreter conformance,
not product quality; the fixture-backed E2E slice is the only end-to-end signal.”

## 8. Agent, code grounding, and execution artifact

Return to the `WEB-4519` delegation. In **Ask Agent**, ask “Why was this allowed?” and
then “Where is delegation approval enforced in code?” Show that issue/policy answers
cite workspace records while code answers cite actual paths and line ranges. Point out
the advisory/non-authorising label.

Choose **mock (simulated)** and start the coding session. The mock is the reproducible
demo path, not a claim of real agent intelligence. Open the session and show:

- immutable issue/policy/warrant/base-revision contract;
- explicit provider kind and state/event timeline;
- isolated worktree and `agent/*` branch;
- host verification result;
- changed-file summary and mandatory unified diff;
- draft-PR unavailability reason when the feature/auth/origin gate is closed.

For an authorised host with a working CLI and Git checkout, opt into a real runner with
`EXTERNAL_CODING_AGENT_ENABLED=true`; never enable it merely to make a demo claim.

## Optional Slack contract demo

Use a correctly signed fixture request against `/v1/integrations/slack/events` to show
URL verification, an `app_mention` summary, deduplication, and a `start coding PAY-4471`
response that stops for approval. Do not claim live Slack delivery without a real app
installation and bot token.

## Optional degraded path

```bash
FIXTURE_FAILURE=extract make demo-reset
FIXTURE_FAILURE=extract make dev
```

The top bar names the injected degradation. A normally safe delegation moves toward
human involvement, demonstrating that failure does not increase autonomy.

## Close

“Nothing routed through Warrant proceeds without a reproducible policy decision,
scoped authority, and accountability record. AI builds the case; code makes the call.”
