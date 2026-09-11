# User Research Evidence — Warrant

**Owner:** Chirayu Gupta (PM) — synthesis and hypothesis ledger · **Recruitment and interviewing:** Priyanka Mohekar (Sales) · **Demo operation:** Gaurav Yadav (Engineer)
**Version:** v3 · **Last revised:** 2026-09-11 · consolidates `linear_ai_product_rnd.html` §28 and §29
**v3 changes:** the recovery plan was refused by Week 3's *smallest credible experiment* as a **fused experiment** and is rewritten to test one assumption (H1) with a pre-fixed binary deciding score. Our own outreach funnel was optimistic by ~2.3×. A new §1a names the product's actual stage — the Prototype gate is unrun and the PoC gate unpassed.

---

## Status summary — read this before anything else

| Requirement (assignment §"Three to five real users") | Status |
| --- | --- |
| 3–5 real users observed | **0 of 5** — `EVIDENCE GAP / ACTION REQUIRED` |
| Consent-respecting observation records | Instrument ready, consent script written, **never used** |
| Decision traces in hypothesis → evidence → decision form | **7 complete traces exist**, all from secondary research and our own build. **None from a user.** |
| Negative findings reported honestly | Yes — four of the seven traces below record a result we did not want |

> **We have not spoken to a single external user.** No interview has been conducted, no demo has been shown outside the team, and no willingness-to-pay signal has been collected. This is stated first because the alternative — presenting internal build evidence in a way that reads like user evidence — would be the exact integrity failure the assignment prohibits.
>
> The five seeded identities in the demo workspace (`chirayu-gupta`, `priyanka-mohekar`, `kriti-developer`, `naresh-evaluator`, `gaurav-yadav-archive`) are **synthetic assignment actors used for local demo authorisation**. They are not users, not interviewees, and are not counted as evidence anywhere in this document.
>
> **Team change, 2026-09-11 — and the count does not move.** Kriti Meheta joined the team today, replacing Gaurav Yadav as the accountable engineer, and ran the demo independently on a clean machine. The team's initial intention was to treat her as *"our first external stakeholder"*; **that framing was corrected rather than banked.** She is a team member with aligned incentives, not the named buyer, so her contribution is registered below as a distinct **internal fresh-eyes review** class. **The user count remains 0 of 5.** Reasoning in `ROLE_EVIDENCE_Kriti_Meheta.md` §4. The seeded `kriti-developer` identity predates her arrival and is still not her.

What this document therefore contains: (1) the research design and its instrument, unchanged since 2026-08-27 so that it demonstrably predates its results; (2) the evidence we **do** hold, correctly placed on the evidence ladder; (3) seven complete decision traces from that evidence; (4) an honest register of the five empty user slots; (5) a recovery plan for the remaining days.

---

## 1. Where our evidence actually sits

The Discovery Evidence Ladder (Week 3) ranks evidence by how far it sits from the behaviour we care about, and therefore how much inference we must supply:

```
R1 Opinion → R2 Anecdote → R3 Interview → R4 Observed behaviour
  → R5 Prototype action → R6 Controlled test → R7 Production evidence
   (belief)   (one case)   (recalled)  (in context) (simulated stakes) (randomised) (at scale)
```

Our holdings, honestly placed:

| Evidence we hold | Rung | What it can support |
| --- | --- | --- |
| Linear / Jira / GitHub first-party documentation, read and dated 2026-08-27 | **R7 for the incumbent's behaviour** — it is a published product fact, not a claim about users | What incumbents do and do not ship. Nothing about demand |
| GitHub Octoverse 2025, DORA 2025, Stack Overflow 2025, Gravitee, Okta, 1Password | **R1–R2** — aggregate opinion and self-report, three vendor-sponsored | That a problem *space* plausibly exists. **Not that our specific customers have it** |
| Named practitioner statements (Torvalds, Stenberg, Zhou, Wilson, McQuaid) | **R2** — vivid anecdote from a self-selecting sample | That the mechanism is articulable by credible people |
| Our own 120-case policy evaluation (re-run 2026-09-10) | **R6 controlled test** — but of *our policy interpreter*, not of a user | Whether the gate behaves as specified |
| Our own live-provider run (2026-08-31) | **R6**, n=3 | Whether a specific provider configuration is viable |
| Driving 13 seeded tickets end to end (2026-09-10) | **R5 prototype action** — simulated stakes, but the operator was the team | Whether the flow survives contact with real use. **Not whether anyone wants it** |
| Internal fresh-eyes engineering review (Kriti Meheta, joined 2026-09-11) | **R5 for reproducibility and onboarding** — first-run demo execution on a clean machine. **R1 for any opinion of the product**, because the reviewer is a team member | Whether a competent engineer with no context can install, run and understand the system; whether two named features work. **Nothing about demand** |
| Interviews, demo reactions, WTP | **R3–R5 — absent** | — |

**The gap in one sentence:** we hold good R6 evidence about whether the product *works* and effectively no evidence about whether anyone *wants* it. The first 25 rubric points are supported; the 15 evidence points and the 10 interview points are not.

---

## 1a. What stage this build is actually at

Week 3's *Prototype, PoC, Pilot & MVP* rules that these are **"not four sizes of the same thing — they are four different questions"**, each with a *what must be real*. Measured against it:

| Stage | Its question | What must be real | Ours |
| --- | --- | --- | --- |
| **Prototype** | *Will users delegate the choice?* | User reaction | ❌ **Gate unrun** |
| **PoC** | Can the mechanism complete the task? | **The core mechanism against the real target** | ❌ **Gate unpassed** — synthetic corpus, fixture provider by default, no verified real-agent run |
| **Pilot** | Will it survive a live workflow? | Environment and users | ❌ |
| **MVP** | Will use and value repeat? | Complete value loop | ❌ |

The session names our situation as **the assisted-construction trap**: *"Because building the PoC is now cheaper than running the prototype study, teams skip straight to a working agent. The demo is impressive, the meeting goes well, and the delegation question is still unanswered — now with sunk code defending it."*

The Prototype-stage question — ***will users delegate the choice?*** — **is our product thesis**, and it is the one thing synthetic data cannot reach. Its own rule: *"Skipping a stage does not remove the question."*

**Honest label for the build: a technical prototype produced at PoC cost, with the Prototype gate unrun and the PoC gate unpassed.**

---

## 2. Research design — who we need and why

Five slots, unchanged since 2026-08-27. The script is deliberately built so that a "no" is as easy to give as a "yes"; the failure mode we are guarding against is five polite confirmations.

| Slot | Profile | Why this person | Hypotheses tested |
| --- | --- | --- | --- |
| **U-A** | Platform / DevProd lead, 100–400 engineers, coding agents enabled | The archetypal buyer. If this person shrugs, the product is wrong | H1, H4, H6 |
| **U-B** | Engineering manager or tech lead, 20–80 engineers, agents enabled | Tests whether the pain survives at smaller scale, where there is no platform team to buy tooling | H1, H2, H7 |
| **U-C** | VP Engineering / CTO, any size, agents enabled or piloting | Economic buyer. Tests whether the trigger is real, and whether it is compliance- or throughput-shaped | H3, H6, H8 |
| **U-D** | Staff engineer who reviews agent output | Tests whether the evidence brief actually saves review time, and whether they would defend it internally | H5, H9 |
| **U-E** | Security / compliance-adjacent engineering leader, or a platform lead in a regulated context | **Deliberately included to be the sceptic.** The most likely source of a hard "no" | H2, H10 |

**Why U-E exists.** A research plan with no slot reserved for the person most likely to disagree is a confirmation exercise. If U-E's objection is fundamental, that is the most valuable finding available to us.

### Question hygiene — the rule we enforce on ourselves, and where our own script breaks it

Every question asks for a **past event** or a **current behaviour**, never for a prediction or an opinion about our idea. Banned phrasings, written down so we notice ourselves using them:

- *"would you find it useful if…"*
- *"wouldn't it be better if…"*
- *"how much would you pay for…"*
- *"do you think AI could…"*
- any sentence containing the word **"governance"** before the interviewee has used it first.

**Our own script fails this test in one place, and we are not quietly fixing it.** Section 2's fallback — *"if 'never': what would have to be true for you to allow it?"* — is a prediction about future behaviour. Week 3's *Design the evidence before the interview* names it exactly: **the preference trap**. The test it gives is *"could a competent observer have watched this happen?"*, and nobody can observe a hypothetical.

We are keeping the question, because a "never" answer ends the past-event line and the follow-up is the only thing left to ask — but it is now labelled: **any answer to it is an opinion, is recorded as an opinion, and may not move a hypothesis row.** The session's stage-5 rule is the one that governs: *"A row with a hole in it does not ship. Either fill the cell, or restate the claim at the strength the evidence supports."*

The METR randomised study found developers' self-reported AI productivity was off by roughly **39 percentage points** against measured reality `SECONDARY` — a direct warning that what people *predict* about their own behaviour with AI tools is not evidence.

**The full consent script and question set are in `STAKEHOLDER_INTERVIEWS.md`.**

---

## 3. Hypothesis ledger

Ten hypotheses, each with the evidence that would settle it, the method, and the decision it drives. Written **2026-08-27, before any evidence existed** — which is the only reason it is worth anything.

| ID | Hypothesis | Evidence needed | Method | Result (2026-09-11) | Decision it drives |
| --- | --- | --- | --- | --- | --- |
| **H1** | Teams at 50–400 engineers have already delegated write-access work to coding agents | ≥3 of 5 describe a specific agent-authored change in the last 60 days | Interview Q4.1–4.3 | **Not collected** | Confirms, or triggers **K1** → pivot to a readiness gate |
| **H2** | They cannot currently answer *"who authorised this, and how do you know it worked?"* | ≥3 of 5 describe an ad-hoc or absent answer, unprompted | Interview Q4.2, Q4.3, Q6.3 | **Not collected** | The core value proposition stands or falls |
| **H3** | The buying trigger is **external** (audit, security review, customer questionnaire) rather than internal frustration | ≥2 of 5 name a specific external question they were asked | Interview Q4.4 | **Not collected** | Determines whether GTM leads with the audit export or with review-time savings. Reshapes the whole pitch |
| **H4** | A mandatory approval step on a minority of delegations is acceptable, not a blocker | ≥3 of 5 accept a ≤35% approval rate when shown the DENY and brief screens | Demo call Q2, Q3 | **Not collected** — *and our measured rate is 0.4364, above the acceptable band we intended to test* | Sets policy default tightness. Failure triggers **K3** |
| **H5** | The evidence brief measurably reduces review effort | U-D can name ≥2 things the brief saved them looking up | Demo call Q3 with U-D | **Not collected** | Whether the brief is a headline feature or a supporting detail |
| **H6** | A named budget owner exists for this class of spend | ≥3 of 5 name a role **and** a budget line | Interview Q7.1 | **Not collected** | Confirms, or triggers **K7** → open-source pivot |
| **H7** | The price metric "per governed delegation" is intuitive to the buyer | ≥3 of 5 restate the metric correctly and unprompted after one explanation | Pricing probe P1 | **Not collected** | Keep the metric, or fall back |
| **H8** | Buyers prefer a predictable platform fee with an allowance over pure usage billing | Forced choice between three structures, with reasons | Pricing probe P3 | **Not collected** | Final packaging decision |
| **H9** | The staff-engineer reviewer will champion this rather than resist it as a gate | U-D volunteers to show it to their lead, **without being asked** | Observed behaviour at end of demo call | **Not collected** | Whether the product is positioned to the reviewer or the platform lead |
| **H10** | The audit export is the right artefact — not a dashboard, not a Slack digest | U-C and U-E confirm the export would satisfy the person who asks them | Demo call Q4 | **Not collected** | Which surface gets polish in the final week |

**Ten of ten hypotheses are unresolved.** H4 is the only one on which we hold an indirect signal, and it is a discouraging one.

Each hypothesis follows the seven-part anatomy from Week 3 (*The Testable Hypothesis*) — target user, intervention, behaviour, metric, threshold, disconfirmation, pre-committed decision rule. The test of the whole thing is the question that framework poses: *"is there a number this experiment could return that would make us not ship?"* For H1 the answer is yes and it is written down: fewer than 3 of 5 confirming a real agent-authored change kills the product as scoped.

---

## 4. Decision traces

Seven complete traces. Four record a finding we did not want. **None of them is user evidence**, and each is labelled with the rung it actually sits on.

### DT-001 — The pivot away from triage, duplicate detection and semantic search
**Rung:** R7 (published incumbent behaviour) · **Date:** 2026-08-27 · **Owner:** Chirayu

- **Hypothesis.** "AI triage / duplicate detection / semantic search is a defensible product direction in the Linear category."
- **Evidence.** Linear documentation and changelog, read 2026-08-27: Triage Intelligence auto-applies labels, assignee, team and project on Business+; embedding-based similar-issue detection has been in production since 2023 on pgvector; hybrid semantic search shipped 2025-04-10. GitHub shipped issue duplicate detection 2026-06-18. Enterpret markets maintained, drift-aware feedback dedupe.
- **Interpretation.** All three capabilities are shipped — in one case for three years — by at least two well-resourced incumbents each. Any version built in nineteen days would be strictly worse, and differentiation would rest on claims we could not substantiate.
- **Decision.** **Rejected all three as the core product.** Retained retrieval as an internal evidence signal only.
- **Product change.** Scope shifted entirely to the authorisation and verification layer around agent delegation. Duplicate detection survives only as the deterministic concurrent-warrant rule R-007.
- **Cost of the decision.** The team's first four days of ideation were discarded. The honest lesson, and the one worth publishing: more of week one should have been spent reading the incumbent's documentation and less generating ideas.

### DT-002 — The live provider is not viable for an interactive gate
**Rung:** R6 (controlled test, n=3) · **Date:** 2026-08-31 · **Owner:** Gaurav · **Negative finding**

- **Hypothesis.** "A free hosted model endpoint can serve the pre-flight extraction path inside an interactive latency budget."
- **Evidence.** Three synthetic reference delegations run through OpenRouter `minimax/minimax-m3:free`, served by GMICloud (`evaluations/live-run-2026-08-31.json`). Latencies **50,578 ms / 70,419 ms / 49,064 ms**. Reported cost $0.00 (free-tier promotional). Token usage 1,060–1,116 in, 138–276 out.
- **Interpretation.** p50 pre-flight of ~50 seconds rules the endpoint out for a gate a human waits on. The $0.00 cost is promotional and carries no information about production unit economics.
- **Decision.** The endpoint is retained **only** as an experimental synthetic-data live check, never as a default or as a cost claim. The default provider remains the visibly labelled deterministic fixture.
- **Product change.** Hard data rule added to the README: the OpenRouter endpoint may receive synthetic data only. Any reported $0 cost is labelled free-endpoint evidence, not unit economics.
- **What it does not establish.** p95 latency and production cost remain `NOT_MEASURED`. Three calls cannot support a p95.

### DT-003 — Live extraction drifts, and it drifts fail-closed
**Rung:** R6 (n=3) · **Date:** 2026-08-31 · **Owner:** Gaurav · **Negative finding**

- **Hypothesis.** "Fixture-mode verdicts are representative of live-provider verdicts on the same reference issues."
- **Evidence.** Same live run. `PAY-4471` returned `REQUIRE_APPROVAL` as expected; `SEC-4502` returned `DENY` as expected; **`WEB-4519` was expected to be `ALLOW` and returned `REQUIRE_APPROVAL`.**
- **Interpretation.** Drift exists, and it is in the **fail-closed direction** — no unsafe allow was produced. But it means the approval burden a live provider imposes is **higher** than the fixture slice suggests, which is the wrong direction given that the fixture slice already breaches K3.
- **Decision.** Fixture results are permanently excluded from live-model quality claims, and the README states that the E2E fixture slice is the run's only end-to-end signal. Live risk-class macro-F1, judge precision on satisfied, p95 latency and cost per delegation are all reported as `NOT_MEASURED` rather than estimated. Retrieval and semantic-search Recall@10 *are* measured — both 1.0000 — but on a small synthetic labelled set, and they say nothing about live-model behaviour.
- **Product change.** Provider usage records now accept **nullable** token and cost fields rather than inventing unavailable values.

### DT-004 — The approval burden misses its own target, and we published the miss
**Rung:** R6 (controlled test on 120 labelled synthetic cases) · **Date:** 2026-08-30, re-run 2026-09-10 · **Owner:** Gaurav + Chirayu · **Negative finding**

- **Hypothesis.** "Unsafe-allow can reach 0 with ≤35% of delegations landing in `REQUIRE_APPROVAL`." (Kill criterion **K3** fires above 0.40.)
- **Evidence.** 120-case policy evaluation: exact verdict accuracy 1.0000, unsafe-allow count **0/120**, fail-closed correctness 1.0000, adversarial non-allow rate 1.0000 — and **standard-slice approval burden 0.4364.** The same run records a second miss: **possible-duplicate precision 0 against a ≥0.85 target** (`outside_target`), on a capability we deliberately de-scoped from a product surface to an internal concurrency signal.
- **Interpretation.** Safety holds perfectly. The burden does not. **K3's threshold is breached.** The product as currently tuned risks being experienced as a tax rather than a control — which is the single most serious objection in the whole commercial case.
- **Decision.** The miss is reported in the README's evaluation table marked `outside_target`, and the build is **not** blocked on it — only a non-zero unsafe-allow count fails the evaluation command. We deliberately did not loosen the policy to hit the number.
- **Product change.** None yet, and that is the honest state. **K3's named fallback — re-scope to protected surfaces only, gating 100% of touches to a declared protected set and auto-allowing everything else — has not been executed.** It cannot responsibly be executed without H4 evidence: we would be tuning a safety threshold against no user input at all. This is the clearest example of a build decision that is blocked on the missing research.
- **Caveat we must state.** Exact verdict accuracy of 1.0000 is a **policy-interpreter conformance check, not a product-quality result** — those cases use the same feature vocabulary as the interpreter. It should not be quoted as an accuracy claim.

### DT-005 — Operating the product end to end found a defect the test suite did not
**Rung:** R5 (prototype action; operator was the team, stakes simulated) · **Date:** 2026-09-10 · **Owner:** Gaurav

- **Hypothesis.** "A suite of 388 passing tests means the approved-execution path works."
- **Evidence.** Thirteen seeded tickets driven end to end through approval, execution, diff and verification. The exercise surfaced a **reversed protected-surface scope match that made every approved protected-surface session fail** — the exact path a customer would use first. Also found: a card-PAN false positive firing on Git's own `index` metadata line, a missing scope-existence preflight, and an empty-diff failure that was undiagnosable from its error.
- **Interpretation.** The tests covered the units and missed the journey. A green suite is not evidence that the flow works; **walking the flow is.**
- **Decision.** Every fix was reproduced as a failing case first, then re-run. 41 regression tests added (388 → 429 passing; the suite now stands at 445 passed / 1 skipped). The pre-existing lint (49 findings) and mypy (41 findings) backlog was cleared in the same pass.
- **Product change.** Four defects fixed; a resumable Hold (defer) with a recorded decision surfaced in the UI; the supersede path for narrowing; approval audit events for approve and narrow.
- **Honest framing.** This is the closest thing to observed-behaviour evidence we hold, and it is still **the team observing itself**. It tells us the product works. It tells us nothing about whether it is wanted.

### DT-006 — We could not verify the real coding agent, so we claim nothing
**Rung:** R5 attempt, failed · **Date:** 2026-09-04 → 2026-09-10 · **Owner:** Gaurav · **Negative finding**

- **Hypothesis.** "The real Codex CLI adapter can be smoke-tested end to end in this environment."
- **Evidence.** The authenticated CLI was present, but its in-process app-server client failed under the execution sandbox with `Operation not permitted`. The requested unsandboxed retry was not approved. Separately, `make verify-agent-cli` reported **0 flags checked** on the verifying machine, and `gh auth status` reported no valid authentication with no compatible GitHub origin in the directory.
- **Interpretation.** The adapter is implemented and unit-tested; it is **not** verified against a real CLI, and the argv the runner builds is unconfirmed.
- **Decision.** **No successful real-agent run is claimed anywhere.** Real execution stays behind `EXTERNAL_CODING_AGENT_ENABLED=false`. Draft PR publication is implemented but explicitly reported as not exercised. The gated real-run E2E test remains available via `RUN_REAL_CODEX=1` in an authorised environment.
- **Why this is in a research document.** It is a decision trace about *what we are allowed to say*, and the same rule governs the user evidence: an instrument that was built but not used produces no findings, and saying so is the finding.

### DT-007 — Pending: the buying trigger, with both branches pre-committed
**Rung:** would be R3 · **Status:** **blocked on interviews** · **Owner:** Priyanka

- **Hypothesis.** H3 — the buying trigger is external (audit / security review) rather than internal frustration.
- **Evidence needed.** ≥2 of 5 interviewees name a specific external question they were asked about AI agent capability or activity.
- **Interpretation.** Pending — no interviews conducted.
- **Decision, pre-committed on 2026-08-27 before any evidence:**
  - **If confirmed** → the pitch leads with the audit export; U-E-style security-adjacent buyers become the primary segment; pricing anchors on compliance spend (probe P6 decides the budget line).
  - **If refuted** → the pitch leads with review-time savings; the evidence brief becomes the hero screen; pricing anchors on engineering hours saved.
- **Why it is written this way.** Pre-committing both branches *before* the evidence arrives is what makes this a decision rather than a rationalisation. The branch is still executable — it needs one conversation, not four days.

---

## 5. User register — the five empty slots

Nothing goes in these cards that did not come out of a real conversation.

| Slot | Profile target | Outreach | Scheduled | Consent | Key finding | Decision it drove |
| --- | --- | --- | --- | --- | --- | --- |
| **U-A** | Platform / DevProd lead, 100–400 eng | **Not sent** | — | — | **Not collected** | **Not collected** |
| **U-B** | EM / tech lead, 20–80 eng | **Not sent** | — | — | **Not collected** | **Not collected** |
| **U-C** | VP Eng / CTO | **Not sent** | — | — | **Not collected** | **Not collected** |
| **U-D** | Staff engineer / agent-output reviewer | **Not sent** | — | — | **Not collected** | **Not collected** |
| **U-E** | Security / compliance-adjacent eng leader | **Not sent** | — | — | **Not collected** | **Not collected** |

**Planned outreach maths, not executed:** 20 approaches → ~8 replies → ~5 conversations, sent in two waves (12 on 27–28 Aug, 8 on 31 Aug) so that a poor first-wave response rate would be visible before it became fatal. **Zero approaches were sent.**

**Kill criterion K9** — *we cannot get in front of relevant people*: fewer than 3 interviews booked by 2026-09-01 despite 20+ outreach attempts. **K9's condition was not met on its own terms** — the trigger requires 20+ attempts, and none were made. The honest reading is that K9 did not fire because the activity it measures never started, which is a worse state than K9 firing.

---

## 6. Recovery plan — 2026-09-11 to 2026-09-15

Four days remain. **Rewritten 2026-09-11** against Week 3's *The smallest credible experiment*, whose governing rule for exactly this situation is:

> *"'We can't afford the full environment.' → **Then you cannot afford the verdict. Reduce the number of tasks, not the realism — narrow the sample, not the mechanism.**"*

The previous version of this plan broke the session's other rule — **"one experiment, one assumption"** — by trying to answer H1, H2 and a demo reaction in the same four days. The session calls that *the fused experiment*, and says it *"produces an uninterpretable result."* So the plan now runs **one experiment against one assumption**, and treats everything else as secondary capture.

**The assumption under test.** Ranked by the session's stage-2 grid of *uncertainty × consequence-if-false*, one item sits in the **TEST FIRST** quadrant:

> **H1 — teams at 50–400 engineers have already delegated write-access work to coding agents.**

Maximum uncertainty (zero observations) and maximum consequence: if false, **K1 fires** and the product as scoped is wrong. H2, H4, H6 and the pricing probes all sit in INVESTIGATE or DEFER for a four-day window.

**The deciding score — binary, mechanically checkable, fixed before any conversation.** The session insists on a score that *"a motivated member of this team"* could not move without something a customer would notice:

> **PASS** — the participant names a **specific** agent-authored change to one of their repositories in the last 60 days **and** can say where it is recorded (a PR number, a session log, a ticket). **FAIL** — they cannot, or the most recent example is older than 60 days, or it turns out to be an assistive completion rather than an agent-authored change.

The *"and can say where it is recorded"* clause is what makes it non-gameable. It is drawn from Week 3's *Design the evidence before the interview*, whose funnel ends not at people who claim the experience but at people who **can produce a contemporaneous artifact** — and which requires that artifact be requested **at recruitment, not at the end**.

**The explaining score** — objections, budget language, reactions to the DENY screen, anything about price — is captured richly and is **structurally unable to overrule the deciding score.** A warm conversation with no dated example is a FAIL.

**What must stay real, and what may shrink.** Narrow the sample from five to two. Do **not** narrow: the participant-behaviour match (a platform lead who has actually turned agents on — *"the quality of an answer cannot exceed the quality of the participant–behaviour match"*), the past-event framing, the consent protocol, or the artifact request.

| When | Action | Owner | Minimum acceptable outcome |
| --- | --- | --- | --- |
| **11 Sep, immediately** | Send 15–20 outreach messages. Opening line is a **question about their experience**, not a description of Warrant. **Ask for the artifact at this point**, not later. Accept written async responses with recorded consent — the K9 fallback | Priyanka | Messages sent and logged with timestamps, including non-responses |
| **11–13 Sep** | Widen to platform-engineering communities and second-degree contacts per the K9 fallback | Priyanka | Any 2 conversations booked |
| **12–14 Sep** | Run them. **H1 only.** Problem-first, no demo, no price on the first pass. Score each PASS/FAIL against the criterion above within 24 hours | Priyanka + Chirayu | **The deciding score returned for ≥2 participants** |
| **13–14 Sep** | Only if a conversation reaches a demo: **DENY screen first**, pricing probes after, verbatim capture including dismissals — all of it explaining score, none of it deciding | Priyanka + Gaurav | One verbatim reaction, recorded as secondary |
| **14 Sep** | Update this file, the ledger and DT-007 — or record the null result explicitly | Chirayu | Truthful final state |

**What a PASS licenses, and what it does not.** Per the session's stage 5: *"A passed experiment… licenses the next experiment and nothing further."* Two PASSes would license running H2 and H4 — they would **not** validate the product, unblock N8, or justify anything in the NEXT column of the roadmap. The session's named failure mode here is *"reading attention as demand"*, and a scheduled call is attention.

**A correction to our own funnel arithmetic.** The original plan assumed 20 approaches → ~8 replies → ~5 conversations. Against the session's measured funnel — 100 leads → 62 claiming relevant experience → 23 who completed the behaviour in the last 90 days → **11 who can produce a contemporaneous artifact** — 20 approaches yields roughly **two** artifact-capable participants, not five. The original target was optimistic by about 2.3×, and the session's framing is the right one: *"Losing eighty-nine of a hundred leads is not attrition; it is the measurement."*

**Pre-committed integrity rule.** If fewer than three conversations happen, this document will say so in exactly these terms and the pitch will present the hypothesis ledger with ten unresolved rows. **No slot will be filled from imagination, and no secondary source will be re-described as a user.** A documented null result is worth more than a fabricated positive and is also, by some distance, the more useful finding for whoever picks this up next.

---

## 7. What a marker should conclude

**Supported by evidence:** that the incumbents do not ship a per-action agent authorisation gate; that a problem space is described in published research and by named practitioners; that our policy engine does what it claims on 120 labelled cases with zero unsafe allows; that a live provider path drifts and is too slow; that walking the flow finds defects a green test suite hides.

**Not supported by evidence:** that any real team has this problem; that the segment definition is right; that the approval burden is acceptable; that the price metric is intuitive; that a budget owner exists; that the audit export is the right artefact. All six are the subject of hypotheses H1–H10, and all ten are open.

**The single sentence that describes our position:** we built a product that works and we did not find out whether anyone wants it.

---

## Sources

- `linear_ai_product_rnd.html` §06, §07, §28, §29 — research plan and hypothesis ledger, authored 2026-08-27
- `evaluations/results.json` (re-run 2026-09-10; first measured 2026-08-30) · `evaluations/live-run-2026-08-31.json` (2026-08-31)
- `docs/ENGINEERING_REPORT.md` · `docs/LIMITATIONS.md` · `docs/DECISIONS.md` · `AI_COLLABORATION.md` · `README.md`
- Linear developer documentation and changelog (read 2026-08-27); GitHub Octoverse 2025; DORA 2025 and *Balancing AI tensions*; Stack Overflow Developer Survey 2025; Gravitee (2026-06-15); Okta (2026-08-24); METR randomised study `SECONDARY`
- FDE session material, Week 3: *The Discovery Evidence Ladder*, *The Testable Hypothesis*, *Design the evidence before the interview*, *From vivid quotes to defensible insights*, *From confidence to evidence*

**Companion documents:** `STAKEHOLDER_INTERVIEWS.md` (script, consent, synthesis) · `BUSINESS_MODEL_CANVAS.md` · `PRICING_STRATEGY.md` · `EVIDENCE_BACKED_ROADMAP.md` · `PITCH_DECK.md`
