# Evidence-Backed Roadmap — Warrant

**Owner:** Chirayu Gupta (PM) · **Engineering sequencing:** Gaurav Yadav · **Commercial gating:** Priyanka Mohekar
**Version:** v3 · **Last revised:** 2026-09-11 · supersedes `linear_ai_product_rnd.html` §37
**v3 changes:** two framework citations were wrong and are corrected in place — the Goodhart claim inverted the session's own diagnostic tell, and *RICE is a hypothesis* was used to justify prose where it prescribes more instrumentation. Applying RICE properly puts every item at confidence **0.2** and makes the whole board **fragile**. The auto-approve refusal now carries all seven refusal rungs, including the **Expires when** condition it was missing. A new **N9** covers the eval set's missing regression and assurance slices.

---

## The sequencing rule

Every item names **the evidence that justifies it**, **its dependency**, and **how we would know it worked**. An item whose justifying evidence does not exist is marked conditional. A roadmap of things we would like is a wishlist, and it is sequenced by preference; this one is sequenced by **risk retired per unit of effort**.

Two risk classes are treated separately, because they behave differently:

| Risk class | Retired by | Current state |
| --- | --- | --- |
| **Product / demand risk** — does anyone want this? | Interviews, demo reactions, budget signals | **Almost entirely unretired.** 10 of 10 hypotheses open |
| **Technical / delivery risk** — does it work, safely, reproducibly? | Tests, evaluation, failure injection, walking the flow | **Substantially retired.** 445 tests passing, 0/120 unsafe allows, failure injection across the provider, embedding, judge and malformed-output paths |

**The consequence for sequencing is uncomfortable and it drives this whole document:** we have been retiring the cheaper risk. Every NEXT item below is therefore gated on evidence that does not exist yet, and the highest-priority item on the roadmap is not a feature at all.

---

## NOW — to 2026-09-15

Evidence-critical only. Everything here is either done or is the thing that unblocks the most.

| # | Item | Evidence justifying it | Dependency | Success metric | Status |
| --- | --- | --- | --- | --- | --- |
| **N0** | **Run one experiment against H1** in 2–5 stakeholder conversations | 10 of 10 hypotheses are unresolved; the commercial case rests on zero primary evidence; K1, K2, K5 and K7 cannot be evaluated | Outreach sent. Nothing else | **The H1 deciding score returned for ≥2 participants**, with consent recorded — a specific agent-authored repository change in the last 60 days, and where it is recorded. Everything else captured is explaining score. Design in `USER_RESEARCH_EVIDENCE.md` §6 | 🔴 **Not started — the single highest-priority item on this roadmap** |
| **N1** | Deterministic policy engine + rules over a consequence × reversibility matrix | Documented absence of any per-action agent policy across Linear, Jira and GitHub `VERIFIED` | None — the foundation | Unsafe-allow rate 0 on 120 cases | ✅ **Done.** 0/120 unsafe allows; exact verdict accuracy 1.0000; adversarial non-allow 1.0000 |
| **N2** | Evidence assembly — hybrid retrieval + schema-bound extraction | A policy cannot decide without facts, and issues are unstructured by nature | Seeded corpus | Risk-class macro-F1 ≥ 0.75; Recall@10 ≥ 0.85 | 🟡 **Partly measured.** Retrieval and semantic-search Recall@10 both **1.0000** on the labelled set; exact-key search and all four triage metrics **1.0000**. Risk-class macro-F1 remains `NOT_MEASURED`. **Possible-duplicate precision measures 0 against a ≥0.85 target — `outside_target`** |
| **N3** | Warrant issuance + approval brief | Practitioner evidence that reviewers can no longer assume author comprehension `SECONDARY` | N1 | Approval burden ≤ 0.35; time-to-decision p50 < 3 min | 🟠 **Built, target missed.** Burden measured **0.4364** — above K3's 0.40 kill threshold. p50 decision time `NOT_MEASURED` |
| **N4** | Evidence verification — deterministic gate 1, then a judge that may abstain | *"Almost right, but not quite"* is the top named practitioner frustration at 66% `SECONDARY` | Warrant contract | Judge precision on "satisfied" ≥ 0.85; abstention 0.05–0.25 | 🟡 **Partly measured.** Brief required-fact coverage 1.0000; unsupported-authority and contradiction counts both 0. Judge precision on satisfied remains `NOT_MEASURED` |
| **N5** | Immutable hash-chained audit ledger + CSV/JSON export | 85% report no formal agent accountability; tracker audit logs are Enterprise-only, 90 days, identity-scoped `VERIFIED` | All decisions flowing | Chain verifies; the export answers the demo's audit question in one query | ✅ **Done.** Append-only enforced by database trigger; exports gated to admin/owner |
| **N6** | Evaluation harness + CI gate | The rubric weights engineering rigour at 25 points, and the gate is the proof | Golden set labelled | Build fails on a deliberately-loosened policy, then passes | ✅ **Done.** 120 cases across standard, boundary, adversarial, degraded |
| **N7** | Governed coding sessions in isolated worktrees, with a mandatory reviewable diff | Follows from N1 — an authorisation with no enforcement at execution time is advice | Warrant + repository adapter | Every session produces a diff; out-of-scope writes rejected | ✅ **Done** (mock runner). ⚠️ Real Codex execution implemented but **never successfully smoke-tested** — sandbox denied the CLI |
| **N8** | Resolve K3 — the approval burden | Measured 0.4364 against a 0.40 kill threshold | **Blocked on N0.** H4 evidence decides whether to retune or to re-scope | Burden ≤ 0.35, or a documented decision to accept it with a customer-informed reason | 🔴 **Blocked.** Deliberately not executed — see below |
| **N9** | **Add a regression slice and a held-out assurance set to the golden set** | Week 1 *Building a representative evaluation dataset* prescribes a coverage budget of Normal 50–60% · Edge 20–25% · Adversarial 10–15% · **Regression, which grows forever and is never pruned** — plus a held-out assurance set. Our 120 cases are standard 55 (45.8%) · boundary 30 (25.0%) · adversarial 20 (16.7%) · degraded 15 (12.5%), with **no regression slice and no assurance set** | Golden set exists | Every fixed defect has a case; the assurance set is never used for tuning | 🟠 **Gap identified 2026-09-11.** Normal is slightly under budget and adversarial slightly over — both tolerable. The missing regression slice is not: the four defects fixed on 2026-09-10 gained 41 tests in `tests/`, but **none entered the golden set**, so the eval cannot regress on them |

**Why N8 is deliberately blocked rather than fixed.** K3's named fallback is to re-scope to protected surfaces only: gate 100% of touches to a declared protected set, auto-allow everything else. That is a narrower claim and still a true one. But executing it now means choosing a safety threshold with **zero user input** and then presenting the choice as a design decision. Tuning a governance product's tightness against nobody is how a governance product becomes theatre. The honest state is: measured, published as a miss, fallback pre-committed, execution gated on one conversation.

---

## NEXT — justified only if the MVP validates

Not one of these is scheduled. Each names the evidence that would move it into NOW, in the form *"we would build this when…"*, and none of that evidence exists today.

| Item | Evidence that would justify it | Dependency | Success metric |
| --- | --- | --- | --- |
| **Second tracker adapter (GitHub Issues)** | **Needed:** ≥2 of 5 interviewees run agents across more than one tracker | Adapter interface stable *(it is — built for two, shipping one)* | One policy governing two trackers in one workspace; a single export covering both |
| **Policy simulator on customer history** | **Needed:** prospects state they will not enable a gate they cannot pre-test. This is the most likely direct answer to the "engineers will route around it" objection | ≥100 stored delegations | >60% of new workspaces run a simulation before activating a policy |
| **Per-agent quality scorecard** | **Needed:** ≥2 interviewees ask *"which agent is better for us?"* unprompted | Verification verdicts at volume | Scorecard viewed in ≥50% of active workspaces monthly |
| **Unwarranted-delegation (bypass) detection** | Follows directly from our own stated limitation — Warrant cannot physically prevent a bypass. Likely to be raised by U-E | Issue-update webhooks | Bypass rate reported, and trending down in ≥1 workspace |
| **PostgreSQL 16 + pgvector migration, with RLS** | **Needed:** a real multi-tenant deployment. Today's SQLite/FTS5 + local deterministic vectors is an honest local adapter, not the deployment target | A customer, or a hosted demo with more than one tenant | Parity on the golden set; row-level isolation tested |
| **Live-model extraction and judging evaluation** | **Needed:** a provider that is fast enough. The one we tested has p50 pre-flight of ~50s | A viable provider configuration | Macro-F1, judge precision, p95 latency and cost per delegation all move from `NOT_MEASURED` to measured |
| **Async webhook ACK + worker / lease / DLQ** | **Needed:** volume. Coding sessions currently run on local background threads with no durable queue | Deployment target chosen | Signed webhook ACK inside the documented window under load |
| **SSO / SAML + audit streaming** | **Needed:** a specific enterprise deal blocked on it. **Never built speculatively** | A named opportunity | One enterprise security review passed |
| **Surface-map auto-discovery from CODEOWNERS** | **Needed:** onboarding friction observed in ≥2 installs | Repository read access, opt-in | Time-to-first-warrant under 30 minutes |

---

## LATER — expansion, only with a proven core

| Item | Reason to believe | Why not sooner | Success metric |
| --- | --- | --- | --- |
| **Cross-customer agent benchmark** (aggregated, anonymised, opt-in) | The one asset no single vendor can build: neutral comparative quality data on coding agents | Needs many workspaces and a very careful privacy and consent design. Premature disclosure would be a breach of trust — and trust is the only asset this product has | A published benchmark cited by a buyer we never contacted |
| **Governance for non-code agents** (support, sales, ops) | The consequence × reversibility model is domain-agnostic; support agents already act on customers | Diffuses focus before the core segment is proven. Different buyer, different sales motion | One non-engineering workspace retained 3 months |
| **Self-hosted / VPC deployment** | Regulated buyers will require it, and a Postgres-only architecture makes it genuinely feasible | Support burden before product-market fit is a trap | One regulated customer live in their own VPC |
| **Local / open-weight models** | Air-gapped buyers; removes the sub-processor conversation entirely | Adds GPU-shaped operational cost for a benefit only some buyers need | Eval parity within 5% of hosted on the golden set |
| **Identity-layer integration** (agent SSO) | Okta shipped agent identity in August 2026. Identity answers *"who"*; we answer *"may they, and did it work"* | Requires a partnership, not just engineering | A joint reference architecture published |
| **External audit anchoring** | The hash chain detects ordinary in-database mutation but is not an external trust anchor — we say so | Only matters once a customer's auditor asks, and none has | Chain anchored to an external, independently verifiable record |

---

## Explicitly not on the roadmap, at any horizon

- Our own coding agent.
- Our own issue tracker.
- AI-authored policy changes.
- **An "auto-approve when confident" mode.**

The last one deserves a full refusal record rather than a paragraph, because it is the feature we most expect to be asked for.

Week 3's *Saying no without losing trust* gives refusal seven rungs — **1 split the ask from the need · 2 say the need back first · 3 make the constraint checkable · 4 price what leaves · 5 answer the need not the ask · 6 hand the decision back · 7 write down what would change your answer** — and says if you can only do three, do 1, 3 and 5. An earlier version of this section did rung 5 alone. Here is the whole thing, with the gap named.

| Rung | |
| --- | --- |
| **1 · Ask vs need** | **Ask:** auto-approve when the model is confident. **Need (hypothesised):** the approval queue is too slow or too frequent to live with. ⚠️ **Rung 1 is unrun.** No user has requested this and no need has been confirmed — the "need" is our inference about a user we have not met |
| **2 · Say the need back** | Cannot be performed. There is no requester to check it with. Rung 2's question — *"Have I got it?"* — has nobody to answer it |
| **3 · Constraint, checkable** | **CLAIM:** a model-scored confidence threshold cannot be the authority. **MECHANISM:** the verdict must be reproducible, attributable and injection-resistant; a confidence score is none of the three, and it re-opens the exact path the extraction schema closes. **OWNER:** the engineering owner of the policy interpreter — *not the author of this roadmap*. **EVIDENCE:** `evaluations/results.json` adversarial non-allow rate 1.0000; `SEC-4502` injection case. **IF CHANGED:** if a confidence signal could be shown to be reproducible across runs and unmovable by ticket text, the constraint weakens |
| **4 · Price what leaves** | What the customer gives up by our refusing: the delegations that would have been auto-allowed keep costing approval time — at 0.4364 burden, roughly **$1.09 per delegation of human review** (`PRICING_STRATEGY.md` §6). That is a real, quantified loss and it belongs in their currency, not ours |
| **5 · Answer the need** | Three options, ours named. **(a) Widen the ALLOW rules through policy** — in the open, with the simulator, provable against their own delegation history before anything is switched on. ← **our recommendation.** **(b) Declare a protected-surface set and auto-allow everything outside it** — this is K3's own pre-committed fallback; cheaper than (a) and a visibly narrower claim. **(c) Raise the concurrency and ownership thresholds only** — the smallest change, and the least likely to satisfy the need. All three cost less than the request; none has been costed against a real surface map, which the session warns is itself a trust risk: *"Never offer an alternative you have not costed."* |
| **6 · Hand the decision back** | The policy is the customer's to author. We supply the matrix, the simulator and the ledger; the tightness is theirs |
| **7 · Expires when** | **Asked:** — · **Need:** hypothesised, unconfirmed · **Decided:** no confidence-gated auto-approval · **Declined:** 2026-09-11 · **Because:** authority must be reproducible and injection-resistant · **Decided by:** the team, with no customer input · **Expires when:** a confidence signal is demonstrated reproducible across runs *and* unmovable by attacker-controlled ticket text, **or** three or more interviewees independently name the queue as their blocking objection — at which point options (a) and (b) get costed against a real surface map and this is re-decided |

The session calls *"Expires when"* **"the line everyone omits and the only one that ages well."** We had omitted it. A permanent no from a team with no users is not a principle; it is an untested preference wearing one.

**A second, independent argument for the same refusal** — stronger because it does not depend on us: Week 3's *Is AI Actually the Right Solution?* names three landing zones (**A deterministic software · B assistive AI · C bounded automation**) and rules that *"moving from Zone B to Zone C is an economic decision about who absorbs the loss — not a technical milestone."* Confidence-gated auto-approval is precisely a B→C move, and it silently transfers the loss from the vendor's gate to the customer's incident. That is the customer's decision to make explicitly, not ours to make implicitly with a threshold.

---

## Sequencing logic — why this order

> **Correction, 2026-09-11.** An earlier version of this section cited Week 3's *RICE is a hypothesis, not a verdict* to justify **arguing** the ordering in prose instead of scoring it. That inverts what the session says. Its remedy for a falsely-objective score is **more instrumentation, not less**: a reach contract of *population · filter · window*, an evidence class on every impact number, a published confidence rung, ranges propagated rather than multiplied, and a fragility rule written before the numbers are seen. Its rule is blunt — *"Bring this table, not the score. A bet that cannot fill every column is not ready to be ranked against one that can."* Arguing in prose fills none of the columns.

Applying it properly produces a more uncomfortable answer than the prose did.

**Confidence, on the session's published ladder:** 0.8 = direct customer evidence · 0.5 = observational or analogous · **0.2 = argued from first principles, with no observation.** With zero interviews and ten of ten hypotheses unresolved, **every item on this roadmap sits at 0.2.** There is no item we can honestly score higher.

**The fragility rule**, stated before any ranking: `fragile = winProbability < 0.7 || margin < 0.25`. **We cannot evaluate it**, because no item on this board has a reach contract, an impact evidence class, or an effort range — the inputs the rule runs on do not exist. That is not a reprieve; it is the session's disqualifier stated another way: *"A bet that cannot fill every column is not ready to be ranked against one that can."* An unrankable board is treated as **FRAGILE**, and the session is explicit about what that means: *"Fragile — do not rank; name the leader's weakest assumption, buy the cheapest evidence that resolves it, and set the date the ranking is re-read."* And: *"Fragile is not indecision. It is a decision: spend the next increment on evidence rather than capacity."*

| Leader | Its weakest assumption | Cheapest evidence that resolves it | Ranking re-read on |
| --- | --- | --- | --- |
| **N0** — conversations | That anyone reachable has delegated write work to an agent (H1) | 15–20 outreach messages; 2 conversations | 2026-09-14 |
| Second tracker adapter | That teams run agents across more than one tracker | One question in any of those conversations | 2026-09-14 |
| Policy simulator | That a pre-testable gate is a purchase precondition | One question, post-demo | 2026-09-14 |
| Per-agent scorecard | That buyers ask "which agent is better for us?" unprompted | Observation — it must be **unprompted**, so it cannot be asked for | 2026-09-14 |

So the ordering below is not a ranking. It is the pre-committed consequence of being fragile: **the next increment buys evidence, not capacity.** That is why N0 is first, and it is a stronger reason than the one this section used to give.

1. **N0 before everything.** Every NEXT item is gated on evidence that only conversations produce. Building any of them first means choosing what to build by preference, which is precisely what this roadmap format exists to prevent. N0 is also the cheapest item on the board — it costs messages, not sprints.
2. **Safety before breadth.** N1, N5, N6 and N7 came first because a governance product that cannot demonstrate its own gate has nothing to sell. This sequencing is vindicated by the result: 0/120 unsafe allows, and a CI gate we can demonstrate *failing* on a deliberately-loosened policy.
3. **Measurement before claims.** N2 and N4 are built but unmeasured, and they are reported as `NOT_MEASURED` rather than estimated. They sit in NOW rather than NEXT because the measurement — not more building — is what is owed.
4. **Depth before a second tracker.** A second adapter doubles the surface area and proves nothing we do not already know. It moves only on direct evidence that customers are multi-tracker.
5. **Enterprise features last, and only against a named opportunity.** SSO built speculatively is the classic way a small team spends its remaining capacity on a deal that does not exist.

### Leading and lagging indicators

Week 3 (*Leading & Lagging Indicators*) warns against writing a rung-5 sentence on rung-3 evidence. Our indicators, honestly rated:

| Indicator | Type | Current value | Rung it licenses |
| --- | --- | --- | --- |
| Unsafe-allow count | **Lagging**, and the one that matters | 0 / 120 | Strong — it is a controlled test with a hard binary gate |
| Approval burden | **Leading** — predicts whether the product is experienced as a tax | 0.4364 | Moderate — synthetic cases, not customer behaviour |
| Delegations per workspace per month | **Leading**, and the load-bearing one | **Unknown** | None. We have no value at all |
| Bypass rate | **Leading** — process leakage | Not yet instrumented | None |
| Possible-duplicate precision | **Lagging** | **0** against a ≥0.85 target | A measured miss on a capability we deliberately de-scoped to an internal signal — reported rather than removed from the target list |
| Time-to-decision p50 | **Leading** — reviewer experience | `NOT_MEASURED` | None |

### Goodhart's Law, applied to ourselves — corrected 2026-09-11

> An earlier version of this section said *"the metric most tempting to optimise is the approval burden, because it is the one currently failing."* That **inverts the session's diagnostic tell** and cannot be cited to it. Week 3's *Goodhart's Law* says the opposite: *"The proxy is improving smoothly, quarter on quarter, with unusually low variance… A number that goes up cleanly and never surprises anyone is usually being produced rather than measured."* A metric sitting at 0.4364 and **missing** its target is behaving like a measurement, not a produced number.

What the session actually supports, via field-guide question 3 — *"What is the cheapest way to move this number? If the cheapest route and the intended route differ, you have already found the gaming strategy"*:

| | |
| --- | --- |
| **Proxy** | Standard-slice approval burden, 0.4364 |
| **Intended route to move it** | Make the policy better-targeted — fewer false escalations, same safety |
| **Cheapest route to move it** | Loosen the ALLOW rules. An afternoon's work |
| **Verdict** | The two routes differ, so the gaming strategy exists and is cheap |

**The session's remedy is not a better proxy, and not a looser threshold.** It is explicit: *"Do not replace the proxy… Keep it, publish its validity range, and add a witness with a different cheapest route."* And: *"You cannot fix a Goodhart failure by choosing a better proxy — the next proxy has a turnover point too."*

Three things follow, and two of them are admissions:

1. **The validity range was never written down.** We set a ≤0.35 target without stating the range in which approval burden is an informative proxy for "is this a control or a tax." The session names that as failure mode 2 — *"the first person to ask 'why not 12 an hour?' wins the argument"* — and it is exactly how we ended up unable to defend 0.35 against 0.4364 on anything but assertion.
2. **We have no independent witness.** Every number we hold about gate quality comes from the same 120-case set that the policy interpreter is written against. A witness with a different cheapest gaming route would be, for example, **blind re-review of a sample of auto-allowed delegations by someone who cannot see the policy** — cheap to describe, and not built.
3. **Keeping the proxy and publishing the miss was the right call**, and is the one thing this section had right. The eval command fails only on a non-zero unsafe-allow count; the burden is reported as a visible miss rather than a build blocker.

**A reframe that is stronger than the numeric argument.** Week 1's *Guardrails & Approval Boundaries* — the session closest to this product — sets **no numeric approval-rate target anywhere**, and does not treat a lower ASK rate as better. Its position is the reverse: *"Consequence × reversibility maps to Skip, Forbidden, or NeedsApproval. **The middle category is what keeps the third one credible.**"* Its failure mode for over-gating is not a rate at all but **alert fatigue**: *"Every command prompts. Within ten minutes the human is clicking approve without reading… alert fatigue is a security failure, not a UX one."*

So the question K3 should be asking is not *"is 0.4364 above 0.35?"* but *"have approvals stopped carrying information?"* — and the observable for that is approval dwell time and the rate of approve-without-narrowing, neither of which we instrument.

**And the target itself is suspect.** Week 2's *AI-Specific Metrics and SLOs* classes a metric like this as a **GUARDRAIL**, not a USER SLO — *"an engineering or commercial limit you set for yourself… watched, reviewed, never paged on alone"*, and explicitly *"allowed to be breached."* It also prescribes how targets are set: *"from four weeks of your own history… the level you actually achieved in the better three of those four weeks, rounded down. **A target you have never once met produces a permanently burning budget, which trains everyone to ignore the alert.**"* Our 0.35 was taken from the R&D dossier's ambition, not from measured history, and we have never once met it.

**What we are not doing, and why.** The same session forbids the convenient fix: *"Tune targets, not thresholds"* only after a shadow period, and never as a response to a miss. So we are not relabelling 0.4364 as acceptable. The honest position is: the target was constructed wrongly, the proxy is sound, the validity range is missing, the witness is missing, and **the resolution needs H4 evidence** — which is N8, and which is blocked on N0.

---

## Kill criteria — current status

| ID | Condition | Check by | Owner | Status |
| --- | --- | --- | --- | --- |
| **K1** | <3 of 5 confirm a real agent-authored repository change in 60 days | 2026-09-04 | Priyanka | **Cannot be evaluated — no interviews** |
| **K2** | ≥3 of 5 state a standing no-agent-write policy with no plan to change | 2026-09-04 | Priyanka | **Cannot be evaluated** |
| **K3** | Unsafe-allow cannot reach 0 without >40% landing in `REQUIRE_APPROVAL` | 2026-09-10 | Gaurav | 🔴 **BREACHED at 0.4364.** Fallback pre-committed, execution blocked on H4 |
| **K4** | Risk-class macro-F1 < 0.65 on the golden set | 2026-09-08 | Gaurav | **`NOT_MEASURED`** — cannot be evaluated |
| **K5** | Measured cost per governed delegation > $0.15 | 2026-09-10 | Gaurav + Priyanka | **`NOT_MEASURED`.** The only live cost reading was $0 promotional and carries no information |
| **K6** | p95 pre-flight latency > 20s | 2026-09-08 | Gaurav | ⚠️ **Indicative breach.** p50 measured at 50,578 ms on the tested endpoint; p95 `NOT_MEASURED`. Mitigated by design — that endpoint is not the default |
| **K7** | 0 of 5 can name a budget owner, or none engages with price | 2026-09-11 | Priyanka | **Cannot be evaluated** |
| **K8** | An incumbent ships an admin-configurable pre-action agent approval gate before 2026-09-13 | Continuous | Chirayu | Not observed as of 2026-09-11 |
| **K9** | <3 interviews booked by 2026-09-01 despite 20+ outreach attempts | 2026-09-01 | Priyanka | **Did not fire on its own terms** — 0 attempts were made, so the 20+ precondition was never met. Functionally worse than a fire |

**Five of nine kill criteria cannot be evaluated at all** — K1, K2, K4, K5 and K7. Four of the five (K1, K2, K5, K7) are blocked on the same missing input; K4 is blocked on an unmeasured model metric. That is the roadmap's real finding.

---

## Sources

- `linear_ai_product_rnd.html` §12 Kill Criteria, §37 Roadmap, §38 Risk Register
- `evaluations/results.json` (re-run 2026-09-10; first measured 2026-08-30) · `evaluations/live-run-2026-08-31.json` (2026-08-31)
- `README.md` · `docs/ENGINEERING_REPORT.md` · `docs/LIMITATIONS.md` · `docs/DECISIONS.md` · `AI_COLLABORATION.md`
- `USER_RESEARCH_EVIDENCE.md` (hypothesis ledger, DT-001 to DT-007) · `STAKEHOLDER_INTERVIEWS.md` · `PRICING_STRATEGY.md`
- FDE session material, **Week 1**: *Building a representative evaluation dataset* (coverage budget, regression slice, "a suite that stays at 100% is telling you about its own blind spots"); *From One Bad Answer to a Release Gate* (BLOCK/CANARY/SHIP, slices named before the run, pass@k vs pass^k); *Guardrails & Approval Boundaries* ("the middle category is what keeps the third one credible"; alert fatigue as the real over-gating failure)
- FDE session material, **Week 2**: *AI-Specific Metrics and Service-Level Objectives* (GUARDRAIL vs USER SLO vs DIAGNOSTIC; setting targets from measured history; "a permanently violated SLO is functionally identical to having no SLO")
- FDE session material, **Week 3**: *RICE is a hypothesis, not a verdict* (confidence ladder 0.8/0.5/0.2, reach contract, fragility rule); *Goodhart's Law* (six-rung ladder, validity range, independent witness); *Saying no without losing trust* (seven rungs, CLAIM/MECHANISM/OWNER/EVIDENCE/IF-CHANGED, "Expires when"); *Is AI Actually the Right Solution?* (Zones A/B/C); *Leading & Lagging Indicators*; *The smallest credible experiment*; *Prototype, PoC, Pilot & MVP*
