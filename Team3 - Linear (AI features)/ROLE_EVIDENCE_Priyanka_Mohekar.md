# Role Evidence — Priyanka Mohekar

**Role:** Sales — accountable for stakeholder/client interviews, pricing, positioning, pipeline and pitch
**Team 3 · Linear (AI features) · Product: Warrant**
**Last revised:** 2026-09-11 · **v3** — the unit-economics model I signed off on was priced per *call*, not per *task*. Corrected in `PRICING_STRATEGY.md` v3; recorded as an error of mine in §6e below.

---

## Accountability statement

I own the commercial evidence: whether a real buyer has this problem, what they would pay, how we describe the product in their words, and whether the pitch is credible to someone who does not already agree with us.

**Of six deliverables I own, two are complete, one is complete-but-corrected, and three are empty — and the reason for all three empties is the same: no conversation happened.** This file states that first, because the assignment's integrity bar makes an honest null result worth more than an invented positive — and because the dossier pre-committed on day one to exactly this sentence if it turned out to be true.

The three-week critical path ran through my role twice: nothing about the problem could be validated without interviews, and nothing about pricing could be claimed without a buyer conversation. **Neither happened, and that is my accountability, not the team's.**

---

## 1. Scorecard, without softening

| Deliverable I own | Status | Evidence |
| --- | --- | --- |
| **Pricing** — packaging, price metric, unit economics, rejected alternative | 🟡 **Complete, and corrected on 2026-09-11.** Packaging, metric and two rejected alternatives are defensible. The unit-economics model **was wrong** — priced per call rather than per completed task — and the corrected version misses our own cost target. See §6d | `PRICING_STRATEGY.md` v3 |
| **Positioning** — one-liner, 30-second pitch, objection handling | ✅ **Complete** | `PITCH_DECK.md` Appendix A; `linear_ai_product_rnd.html` §33 |
| **Pitch deck** | ✅ **Complete**, 11 slides + objection appendix, integrated with the live demo | `PITCH_DECK.md` |
| **Willingness-to-pay evidence** | 🔴 **`EVIDENCE GAP / ACTION REQUIRED` — none obtained** | `PRICING_STRATEGY.md` §7 |
| **Stakeholder / client interviews** | 🔴 **`EVIDENCE GAP` — 0 of 5 conducted, 0 of 20 outreach messages sent** | `STAKEHOLDER_INTERVIEWS.md` §4 |
| **Pipeline** | 🔴 **`EVIDENCE GAP` — empty. No prospect was contacted** | §4 below |

---

## 2. What I decided

| # | Decision | Rejected alternative | Reasoning | Status |
| --- | --- | --- | --- | --- |
| **1** | **Price metric = one governed delegation** | Per engineering seat; per repository; per active agent | It is exactly one unit of the thing the product does, so revenue rises with value delivered rather than with the customer's headcount. Gaming is self-correcting: batching many changes into one delegation means a broader warrant, which means a wider blast radius and *more* approvals | Held. H7 would test whether a buyer finds it intuitive — untested |
| **2** | **Reject per-seat pricing** | Adopt the familiar, easily-approved seat | Three reasons: it prices the wrong thing (the premise of agents is that output stops tracking headcount, so a seat price bets against our own thesis); the seat is already owned (Linear $16, GitHub $19 — we would be a third charge for the same engineer, the easiest procurement "no" in the world); and it punishes the behaviour we want (govern more, pay the same) | Held, **with the counter-evidence stated fairly**: Sentry Seer ran per-run AI pricing and reverted to a per-active-contributor seat in January 2026. Our structure is a deliberate hedge against that finding, and the revisit trigger is written down |
| **3** | **Reject outcome pricing (per prevented incident)** | Charge per unsafe action blocked — the most compelling narrative available to us | **Structurally** wrong, not merely commercially awkward. The counterfactual is unmeasurable, and it creates an incentive to tighten policy in order to bill more. **A governance vendor billing itself for its own alarms** is disqualifying for a product whose only asset is trust | Held |
| **4** | **Copy Zendesk's dollar-denominated allowance** | A unit-count allowance | It decouples the customer's entitlement from the unit price, so the unit can be repriced without repapering contracts — which matters a great deal when the underlying cost is an inference bill that will fall | Held |
| **5** | **Ask pricing probes only after the demo, never before** | Ask WTP early, while the prospect is engaged | A price quoted before value is understood measures politeness, not willingness to pay | **Never tested.** No demo was shown |
| **6** | **Design P3 as two questions, not one** — *"easiest to get approved"* vs *"what you personally prefer"* | Ask a single preference question | These are often opposite answers, and **the gap between them is the finding** — it separates procurement friction from personal preference | **Never asked** |
| **7** | **Pre-commit to publishing a null WTP result** | Present the anchored hypothesis figures as though validated | Written on 2026-08-27, before any evidence: *"If interviewees do not engage with price, the submission will say 'no willingness-to-pay evidence was obtained'."* | **Honoured.** The sentence is now the true one, and it is written rather than replaced |
| **8** | **Lead the demo with the DENY screen** | Lead with the happy path | The DENY is the strongest and most polarising screen. A demo showing only success is discounted by the audience, and refusing an injection attempt deterministically is the most persuasive thirty seconds we have | Built into the demo script. **Never delivered to an external audience** |
| **9** | **Credit competitors accurately rather than dismissing them** | Position incumbents as behind | A knowledgeable audience already knows the prior art — GitLab's composite identity, Sentry's stop-after-X ceilings, Linear's genuinely excellent delegation semantics. Accuracy is more persuasive than dismissal, and the honest framing (*"Linear provides the mechanics; its own guidelines name the boundary"*) is stronger than a claim of superiority | Held throughout `PITCH_DECK.md` §9 and Appendix A |

---

## 3. Positioning — what I wrote, and what has not been tested against a buyer

**One line:** *Warrant is the delegation control plane for AI agents: every piece of work an agent touches is authorised by policy, scoped by a warrant, and verified on return.*

**The differentiating sentence:** *AI builds the case; code makes the call.*

**Objection handling** — seven objections written with answers, including the two that go against us:

- *"Isn't this just another approval queue that engineers will route around?"* — the most serious objection, and **our own measured number currently supports it**: 43.6% approval burden against a ≤35% target. The answer names the number rather than avoiding it, then gives three design responses (the simulator proves the rate on the customer's own history first; approvals arrive with a brief rather than a raw ticket; routing around it is visible). **Strengthened 2026-09-11:** Week 1's *Guardrails & Approval Boundaries* sets no numeric approval-rate target anywhere and does not treat a lower ASK rate as better — *"the middle category is what keeps the third one credible."* Its failure mode for over-gating is **alert fatigue**, not a rate: *"within ten minutes the human is clicking approve without reading… alert fatigue is a security failure, not a UX one."* So the right question is whether approvals still carry information, not whether 0.4364 exceeds 0.35 — and the observables for that are approval dwell time and approve-without-narrowing rate, neither of which we instrument.
- *"We don't let agents write to anything, so this is irrelevant."* — treated as a **research input, not a sales obstacle.** The follow-up question is the valuable one: *what would have to be true for you to allow it?* If three of five hold that position with no plan to change, K2 fires and we pivot.

**Honest limitation of all of the above:** positioning is supposed to be written in the buyer's words. Mine is written in ours, because no buyer has spoken. The plan called for positioning to be *rewritten from actual objection language* in the 7–13 September window. That revision has not happened and cannot without a conversation.

---

## 4. Outreach log and pipeline

**Outreach log**

| Wave | Planned date | Planned count | Sent | Replies | Conversations |
| --- | --- | --- | --- | --- | --- |
| Wave 1 | 2026-08-27 – 08-28 | 12 | **0** | 0 | 0 |
| Wave 2 | 2026-08-31 | 8 | **0** | 0 | 0 |
| **Total** | | **20** | **0** | **0** | **0** |

**Pipeline** — placeholder profiles from the plan, not invented people. No row is completed from imagination, including the declines: a fabricated rejection is as dishonest as a fabricated endorsement.

| Prospect profile | Problem fit | Interview | Demo | Pricing signal | Next step |
| --- | --- | --- | --- | --- | --- |
| Platform lead, mid-size fintech | Unknown | Not sent | — | — | Send outreach |
| VP Eng, B2B SaaS | Unknown | Not sent | — | — | Send outreach |
| EM, health-tech | Unknown | Not sent | — | — | Send outreach |
| Staff engineer, internal delivery team | Unknown | Not sent | — | — | Send outreach |
| Security engineering leader, regulated client | Unknown | Not sent | — | — | Send outreach |

**Kill criterion K9** — *fewer than 3 interviews booked by 2026-09-01 despite 20+ outreach attempts*. **K9 did not fire, because its precondition — 20+ attempts — was never met.** That is a worse state than K9 firing: a kill criterion is silent because the activity it measures never started. I read the silence as neutral at the time. It was not.

---

## 5. Commercial evidence I can and cannot defend

**Can defend:**

- **Verified competitor benchmarks**, seven vendors, pricing pages accessed and dated 2026-08-27, each with the specific lesson drawn from it.
- **The price-metric choice**, argued against two alternatives on six criteria, with the strongest counter-argument to my own position (Sentry's reversal) stated rather than omitted.
- **The unit-economics model as a formula**, with three scenarios rather than a point estimate, the load-bearing assumption identified (delegation volume per workspace) and a sensitivity ranking that names which assumption to test first. **With the correction of 2026-09-11 applied** — the version I first published priced a call rather than a completed task, and I state that rather than presenting the formula as though it had always been right.
- **Two measured cost inputs** that replaced pure assumptions: real extraction token counts of 1,060–1,116 in / 138–276 out, and a measured approval burden of 0.4364.
- **Positioning and objection handling**, including the objections that go against us.

**Cannot defend, and will not pretend to:**

- Any dollar figure. Every price is an anchor derived from competitor pricing, labelled `HYPOTHESIS` on every line.
- The segment definition — 50–400 engineers with agents enabled is a plausible construction, not a validated finding.
- That a budget owner exists (H6), that the price metric is intuitive (H7), or that buyers prefer a fee-plus-allowance structure (H8). All three untested.
- **K7** — *no credible commercial signal* — cannot even be evaluated, because evaluating it requires a buyer conversation.

---

## 6. What I got wrong

**a. I treated outreach as the easy part of the work rather than the gating part.** The dossier named my highest-leverage single act on day one: *"sending twelve outreach messages on 27 August."* It also gave the reason: *"an interview on 12 September is a transcript; an interview on 2 September is a decision."* I read that, agreed with it, and did not do it. Everything downstream — the pivot checkpoint on 4 September, the pricing section, the positioning revision, the pitch's evidence slide — was gated on that one action.

**b. I spent the time on analysis instead.** The benchmark table, the metric comparison, the probe design and the objection handling are genuinely good work, and all of it is the kind of work that can be done alone. That is exactly why it got done. **Analysis was the comfortable substitute for the uncomfortable ask**, and I should recognise that pattern faster next time.

**c. I did not open the fallback channel early.** K9's named fallback — public platform-engineering communities and **written async interviews with recorded consent** — was available from day one and costs almost nothing. I held it in reserve for a warm-intro process that was not actually running. The fallback should have opened on 31 August, when wave 1 had produced nothing.

**d. The cost model I presented was priced per call, not per task — and the correction is not in our favour.** Week 1's *A $0.036 call is not a $0.036 task* decomposes cost in six steps — **call → attempt → cache → retry → operations → fleet** — and reports an **11.6× gap** between the naive and the loaded number on its worked example. Our model stopped at step 3. Adding the missing three moves base cost **$0.040 → $0.071**, which now misses our own <$0.06 target, and moves the unfavourable case to **$0.248**, which breaches kill criterion **K5** and cuts the margin at our list price from 67% to **29%** — below the ~50% median AI gross margin benchmark. The session names the exact error: *"the denominator quietly changes here from attempts started to tasks completed — this is where most internal cost models silently understate."*

The larger miss is commercial rather than arithmetic, and it is the one I should have caught. In the session's worked example **human review is 47.2% of variable cost at a 5% review rate.** Warrant's approval burden is **0.4364 — roughly nine times that rate** — and every one of those approvals consumes a named human's time by design. At two minutes and a $75/hour loaded rate that is **≈$1.09 per delegation**, about **4× our own list price**, borne by the customer. It appeared nowhere in the pricing document I wrote, because I was modelling our inference bill rather than the buyer's total cost. The rule I should have been working from: ***"Escalation policy is a pricing decision, not just a quality one."***

This reorganises the commercial argument in a way I would rather have found before writing the pitch. Arguing on our $0.35 concedes the wrong comparison; the defensible frame is review hours displaced versus review hours created — and **we have measured neither side.** It also means K3's approval burden is not only an engineering-tuning question, which is how the roadmap treats it, but the single largest lever on the customer's economics.

**e. I did not flag the stall loudly enough internally.** The team's checkpoints on 4 September and 10 September both depended on evidence I had not collected. I let them pass as scheduling events rather than escalating that the commercial track had not started.

---

## 7. Cross-functional contributions

**Where I influenced the product:**

- Argued the DENY screen into the demo's opening position and the injection case into the failure path. That sequencing decision shapes how the entire product reads to a non-technical audience — it demonstrates the security model, proves the architecture claim concretely, and makes the point that *not interrupting a human* is itself a feature.
- Pushed for the honest limitation to be stated unprompted in the pitch (*"we cannot physically prevent a bypass, so we detect it"*). Stating a limitation before being asked is the moment a technical audience starts believing everything else.
- Supported the engineering decision to publish the approval-burden miss rather than tune the policy to hide it, on the commercial grounds that a governance vendor caught flattering its own metrics has nothing left to sell.

**Where I was wrong, or where I would defer:**

- I initially framed the audit export as the hero surface, on the assumption that the buying trigger is external. **That assumption is hypothesis H3 and it is untested.** DT-007 pre-commits both branches; if the trigger turns out to be internal frustration, the evidence brief becomes the hero screen, the pitch's opening changes, and the price anchors on engineering hours rather than compliance spend. I would rather have the branch written than the assumption defended.
- I underestimated how much of the pitch's credibility would come from the engineering evidence rather than from the market narrative. The strongest slides are the ones with measured numbers on them, including the failing one.

---

## 8. Recovery plan — 2026-09-11 to 2026-09-15

Four days remain. **Rewritten 2026-09-11** against Week 3's *The smallest credible experiment*: one assumption, not several — a multi-assumption plan is *the fused experiment*, which *"produces an uninterpretable result."* The assumption is **H1**, the deciding score is binary and fixed before any conversation, and the full design is in `USER_RESEARCH_EVIDENCE.md` §6.

| When | Action | Minimum acceptable outcome |
| --- | --- | --- |
| **11 Sep, today** | Send 15–20 outreach messages. Opening line is a question about their experience, not a pitch — a pitch contaminates the answer | Messages sent and logged with timestamps, **including the non-responses** |
| **11 Sep** | Open the K9 fallback immediately: platform-engineering communities, second-degree contacts, written async interviews with recorded consent | Two additional channels active |
| **12–14 Sep** | Run whatever lands. **H1 only** — problem-first, no demo, no price on the first pass. Score PASS/FAIL within 24 hours | **The H1 deciding score returned for ≥2 people**: a specific agent-authored repository change in the last 60 days, and where it is recorded |
| **13–14 Sep** | Any demo call: DENY first, pricing probes P1–P7 only after, verbatim capture including dismissals — all of it **explaining score**, none of it deciding | One verbatim reaction to the DENY screen, recorded as secondary |
| **14 Sep** | Update the interview register, the pipeline table and DT-007 — **or record the null result explicitly** | A truthful final state |

**One correction to my own funnel maths.** I planned 20 approaches → ~8 replies → ~5 conversations. Against the measured benchmark in Week 3's *Design the evidence before the interview* — 100 leads → 62 claiming relevant experience → 23 who did the behaviour in the last 90 days → **11 who can produce a contemporaneous artifact** — 20 approaches yields about **two** usable participants, not five. I was optimistic by roughly 2.3×, and the operational fix is to **request the artifact at recruitment rather than at the end of the call**.

**Pre-committed integrity rule.** If the window closes with fewer than three conversations, every table above keeps its zeroes, the pricing section keeps its null result, and the pitch presents the hypothesis ledger with its unresolved rows visible. **No profile will be invented, no quote written that nobody said, and no secondary source re-described as a stakeholder.**

---

## 9. Community posts

| Week | Required | Status |
| --- | --- | --- |
| Week 3 (by 2026-08-30) | Role plan, problem hypothesis, interview plan, first decision trace | **`EVIDENCE GAP / ACTION REQUIRED` — no post link recorded in this repository** |
| Week 4 (by 2026-09-06) | Alpha/build evidence, user feedback, one decision changed by evidence | **`EVIDENCE GAP` — no link recorded** |
| Week 5 (by 2026-09-13) | Validation result, remaining risk, launch/pitch readiness | **Not yet due at time of writing (2026-09-11)** |

**Action required before submission:** paste the permalinks into this table, or state explicitly that a post was not published. They are not recoverable from the repository and will not be invented here.

**Planned Week 5 content:** the WTP null result and why it is published rather than filled; the K9 non-firing as the signal I misread; what four days of late outreach did and did not produce; and the lesson in one line — *the commercial artefact that mattered was the outreach list, and I treated it as the easy part of the work.*

---

## 10. Evidence index

| Claim | Where to verify it |
| --- | --- |
| Price metric, packaging, rejected alternatives, unit economics | `PRICING_STRATEGY.md` |
| Verified competitor benchmarks, seven vendors, dated 2026-08-27 | `PRICING_STRATEGY.md` §2 |
| Pricing probes P1–P7, and the record that none was asked | `PRICING_STRATEGY.md` §7 |
| Interview script, consent protocol, stakeholder map | `STAKEHOLDER_INTERVIEWS.md` |
| Interview register and outreach log, all zeroes | `STAKEHOLDER_INTERVIEWS.md` §4 |
| Pitch deck, 11 slides, with the objection appendix | `PITCH_DECK.md` |
| Positioning and objection handling source | `linear_ai_product_rnd.html` §33 |
| The margin sign error I published and corrected the same day (−29% → +29%) | §6d, and `PRICING_STRATEGY.md` §6 |
| Measured inputs behind the cost model | `evaluations/live-run-2026-08-31.json`, `evaluations/results.json` |
| The six-step cost decomposition and the customer-side review-cost line | `PRICING_STRATEGY.md` §6, corrected 2026-09-11 |

**AI collaboration disclosure:** AI assistance was used to draft and structure the commercial documents in this repository. It **did not generate users, interviews, quotes, willingness-to-pay evidence or customer feedback** — `AI_COLLABORATION.md` records that no such evidence exists, and this file's zeroes are the consequence. Competitor pricing figures were read from vendor pricing pages on 2026-08-27 and are cited with that date. **Total AI spend: `NOT_MEASURED`** — no provider billing data was available to this work.
