# Role Evidence — Chirayu Gupta

**Role:** PM — accountable for problem framing, business model, user research synthesis, decision log and roadmap
**Team 3 · Linear (AI features) · Product: Warrant**
**Last revised:** 2026-09-11 · **v3** — I had cited two Week 3 frameworks without reading them and got both wrong. Both are corrected in `EVIDENCE_BACKED_ROADMAP.md` and recorded as errors of mine in §4e below.

---

## Accountability statement

I own what we chose to build and why, what evidence would tell us we were wrong, and whether the team acted on that evidence when it arrived. The artefacts that carry my accountability are the hypothesis ledger, the kill criteria, the decision traces, the business model canvas and the roadmap.

**Two of those are strong and two are hollow**, and the split is the honest summary of my quarter: the framing, the falsifiable hypotheses and the pre-committed kill criteria were written on day one and have held up well. The synthesis and the evidence-to-decision conversion never happened, because the evidence never arrived — and I did not escalate that fast enough.

---

## 1. What I decided

| # | Decision | Date | Rejected alternative | Evidence | Outcome |
| --- | --- | --- | --- | --- | --- |
| **1** | **Reject AI triage, duplicate detection and semantic search as the core product** | 2026-08-27 | Build a better triage or duplicate-detection feature — the assignment's own starting challenge | Linear documentation read and dated: Triage Intelligence auto-applies labels, assignee, team and project; embedding-based similar-issue detection in production since 2023; hybrid semantic search shipped 2025-04-10. GitHub shipped duplicate detection 2026-06-18 | Correct, and the single most consequential call. Any version we built in 19 days would have been strictly worse than shipped incumbent features, and differentiation would have rested on claims we could not substantiate. Recorded as **DT-001** |
| **2** | **Take the authorisation and verification layer instead** | 2026-08-27 | Three other candidates scored and discarded; two expected to lose, and their loss was informative | Linear's own Agent Interaction Guidelines state *"an agent cannot be held accountable"* — the incumbent naming its own boundary. Cross-checked against Jira/Rovo (lifecycle audit, not per-action), GitLab (merge-request-scoped composite identity), Okta (identity, not authorisation) | Held. No incumbent shipped a pre-action approval gate during the window (**K8** not triggered as of 2026-09-11) |
| **3** | **Retain duplicate detection as a deterministic policy rule, not an ML feature** | 2026-08-27 | Drop it entirely; or build it as a product surface | "Deny a second concurrent warrant on overlapping surfaces" is cheap, deterministic and genuinely novel, where semantic duplicate detection is commoditised | Shipped as rule R-007. It is the beat in the demo where the audience realises the system knew something they would not have checked |
| **4** | **Write ten falsifiable hypotheses and nine kill criteria before any evidence existed** | 2026-08-27 | Write them retrospectively, when they would fit whatever we found | The discipline itself: an artefact reconstructed on 14 September is worth a fraction of one that predates its results | The ledger is the strongest artefact I own, and it is strong precisely because every Result cell still reads *Not collected* rather than being back-filled |
| **5** | **Pre-commit both branches of the H3 buying-trigger decision before the evidence arrived** | 2026-08-27 | Decide after seeing the data | Pre-committing both branches is what makes it a decision rather than a rationalisation | Recorded as **DT-007**. Still executable — it needs one conversation, not four days |
| **6** | **Publish the approval-burden miss rather than tune the policy to hide it** | 2026-08-30 | Loosen the ALLOW rules until the burden fell below 0.35 | 0.4364 measured against a ≤0.35 target and a 0.40 kill threshold. The number can be moved in an afternoon while making the product worse — Goodhart in its purest form | Miss published in the README's evaluation table as `outside_target`. The eval command still fails only on a non-zero unsafe-allow count |
| **7** | **Do not execute K3's fallback without user evidence** | 2026-09-11 | Re-scope to protected surfaces only, hit the target, and present it as a design decision | Choosing a safety threshold with zero user input, then reporting the choice as design, is how a governance product becomes theatre | Documented in `EVIDENCE_BACKED_ROADMAP.md` as item **N8 — blocked**, with the reasoning visible rather than the block silent |
| **8** | **Refuse an "auto-approve when confident" mode permanently** | 2026-08-27, reaffirmed 2026-09-11 | Add a confidence threshold above which the model may auto-allow | It is the feature we most expect to be asked for and it would dismantle the product's only guarantee by handing authorisation back to a model. The right answer to the underlying need is to widen the ALLOW rules through policy, in the open, with the simulator | Listed under *Explicitly not on the roadmap, at any horizon* |

---

## 2. Artefacts I own

| Artefact | Status | Where |
| --- | --- | --- |
| Problem framing and product selection | ✅ Complete, dated, with rejected candidates scored | `linear_ai_product_rnd.html` §01–§11; `USER_RESEARCH_EVIDENCE.md` DT-001 |
| Hypothesis ledger — 10 falsifiable hypotheses | ✅ Written 2026-08-27, **10 of 10 results still open** | `USER_RESEARCH_EVIDENCE.md` §3 |
| Kill criteria — 9, each with threshold, check date, owner and named fallback | ✅ Written 2026-08-27. **5 cannot be evaluated (K1, K2, K4, K5, K7), 1 breached (K3), 1 indicative breach (K6)** | `EVIDENCE_BACKED_ROADMAP.md` §Kill criteria |
| Decision traces | ✅ **7 complete** (DT-001 to DT-007), 4 of them negative findings | `USER_RESEARCH_EVIDENCE.md` §4 |
| Business Model Canvas | ✅ v3, every block evidence-labelled, with coherence arguments and 5 stated weaknesses | `BUSINESS_MODEL_CANVAS.md` |
| Evidence-backed roadmap | ✅ v3, Now/Next/Later, every item naming its justifying evidence and success metric | `EVIDENCE_BACKED_ROADMAP.md` |
| Interview synthesis | 🔴 **`EVIDENCE GAP`** — nothing to synthesise | `STAKEHOLDER_INTERVIEWS.md` §5 |
| One decision changed by *user* evidence | 🔴 **`EVIDENCE GAP`** — decisions changed by *measurement* exist; none changed by a customer | `STAKEHOLDER_INTERVIEWS.md` §6 |
| Product/commercial decision log (D-001…D-008 as planned) | 🔴 **Missing as a standalone dated log.** `decision-log.md` and `research/hypotheses.md` were specified and never created. The engineering log `docs/DECISIONS.md` is complete (30 entries, `D-ENG-*`) and covers engineering only; the *product and commercial* decisions are recorded across the R&D dossier, this file §1, and the seven decision traces in `USER_RESEARCH_EVIDENCE.md` §4 — dated and with rejected alternatives, but not in one append-only file | `docs/DECISIONS.md`; `USER_RESEARCH_EVIDENCE.md` §4; §1 above |

---

## 3. Decisions changed by evidence

The rubric asks for at least one decision changed because of evidence. **Four belief-reversals exist** — the four below, each of which overturned something we held. `STAKEHOLDER_INTERVIEWS.md` §6 tabulates six *changes* in total; the two not listed here (the four execution defects, and the refusal to claim a real Codex run) are corrections and refusals rather than reversals of a belief. **None of the six came from a user**, and I state that distinction rather than blurring it.

| Belief held | Evidence | What changed | Cost |
| --- | --- | --- | --- |
| AI triage / duplicate detection / semantic search is an open problem in this category | Incumbent documentation, 2026-08-27 | Entire product direction. Scope shifted to the authorisation layer | The team's first days of ideation were discarded |
| Fixture-mode verdicts are representative of live-provider verdicts | Live run 2026-08-31: `WEB-4519` drifted `ALLOW` → `REQUIRE_APPROVAL` | Fixture results permanently excluded from live-model quality claims; five metrics reported as `NOT_MEASURED` rather than estimated | We lost the ability to quote any live quality number |
| A free hosted endpoint can serve the interactive pre-flight path | p50 pre-flight 50,578 ms | Endpoint demoted to an experimental synthetic-data check only; a hard data rule added to the README | We have no viable measured production provider configuration |
| A passing test suite means the approved-execution path works | 13 tickets walked end to end, 2026-09-10, with 388 tests green | Four defects fixed, 41 regression tests added, and "walk the flow" adopted as a distinct verification activity | A day of remediation, and the discovery that our primary path had been broken for some time |

**The reversal I owe and cannot supply:** one decision changed because a customer told us something. That was the Week 4 requirement, and we do not have it.

---

## 4. Where I was wrong

**a. I let the research track slip without escalating.** The plan named Priyanka's highest-leverage single act — twelve outreach messages on 27 August — and stated the reasoning: *"an interview on 12 September is a transcript; an interview on 2 September is a decision."* I wrote that sentence and then did not enforce it. The K1/K2 pivot checkpoint on 4 September passed with no evidence to evaluate, and I did not treat a checkpoint that cannot run as a failure requiring immediate re-planning. **That is the single largest process failure in this project and it is mine**, because the schedule and the checkpoints were my artefacts.

**b. I under-weighted a kill criterion that could not fire on its own terms.** K9 measures *"<3 interviews booked by 1 September despite 20+ outreach attempts."* Zero attempts were made, so the precondition was never met and K9 never fired. I read the non-firing as neutral. It was the most alarming signal available — a kill criterion silent because its activity never started is worse than one that fires.

**c. I allowed the team to retire the risk it was comfortable with.** Technical risk is now substantially retired; product risk is almost entirely unretired. The roadmap format I chose exists precisely to prevent building by preference, and I did not apply it to the *team's own time allocation* until it was too late to change the outcome.

**d. I cited two frameworks I had not read, and misused both.** In the roadmap I wrote that *"the metric most tempting to optimise is the approval burden, because it is the one currently failing."* Week 3's *Goodhart's Law* says the opposite — its diagnostic tell is a proxy *"improving smoothly, quarter on quarter, with unusually low variance… a number that goes up cleanly and never surprises anyone is usually being produced rather than measured."* A metric that is visibly missing its target is behaving like a measurement. The supportable claim was available and I did not make it: the session's field-guide question 3 asks *"what is the cheapest way to move this number?"*, and loosening the policy is a cheaper route than improving it — which is the real finding. Its remedy is also not the one I implied: *"Do not replace the proxy. Keep it, publish its validity range, and add a witness with a different cheapest route."* We never wrote down a validity range for approval burden before setting a 0.35 target, and we have no independent witness.

Second: I cited *RICE is a hypothesis, not a verdict* to justify arguing the roadmap order **in prose instead of scoring it**. The session prescribes the opposite — more instrumentation, not less: a reach contract of *population · filter · window*, an evidence class on every impact number, a published confidence ladder (**0.8** direct customer evidence · **0.5** observational · **0.2** first principles with no observation), propagated ranges, and a fragility rule fixed before the numbers are seen. Applying it properly is worse for us and more useful: **every item sits at 0.2**, the board is **fragile** on the session's own test, and *"fragile is not indecision — it is a decision: spend the next increment on evidence rather than capacity."* That is a far better argument for putting N0 first than the one I wrote.

**e. I never named the stage we were building for.** Week 3's *Prototype, PoC, Pilot & MVP* names our situation precisely — the **assisted-construction trap**, where *"building the PoC is now cheaper than running the prototype study, [so] teams skip straight to a working agent… and the delegation question is still unanswered, now with sunk code defending it."* The Prototype-stage question is *"will users delegate the choice?"* — **our product thesis** — and synthetic data cannot touch it. Deciding what stage we were building for was mine, and I never named one.

**f. The product decision log is not a single dated file.** I specified `decision-log.md` and `research/hypotheses.md` as living files. Neither exists in the repository; the content lives in the R&D dossier and in the deliverables. The content survived, the discipline of a dated append-only log did not, and I would rather note that than claim a file that is not there.

---

## 5. Cross-functional work

**With Engineering (Gaurav):** agreed that the evaluation gate fails only on a non-zero unsafe-allow count and reports the approval-burden miss visibly — protecting the metric that matters from the metric that is easiest to move. Supported the decision to publish `NOT_MEASURED` for five metrics rather than estimate them. Backed the refusal to claim a real Codex run.

**With Sales (Priyanka):** wrote the hypothesis-to-question mapping so that every interview question traces to a hypothesis and a decision, rather than being a list of interesting things to ask. Wrote the banned-phrasings list, including the rule that the word *"governance"* may not be used before the interviewee uses it first. Both are good instruments and neither has been used.

**Where I helped least:** I did not put myself on outreach. The role boundaries say interviews are Priyanka's, but *"roles identify accountable owners, not silos"* is in the assignment brief, and the correct response to a stalled critical path was to send messages myself rather than to keep tracking that they had not been sent.

---

## 6. Community posts

| Week | Required | Status |
| --- | --- | --- |
| Week 3 (by 2026-08-30) | Role plan, problem hypothesis, interview plan, first decision trace | **`EVIDENCE GAP / ACTION REQUIRED` — no post link recorded in this repository** |
| Week 4 (by 2026-09-06) | Alpha/build evidence, user feedback, one decision changed by evidence | **`EVIDENCE GAP` — no link recorded.** Build evidence and a changed decision exist; user feedback does not |
| Week 5 (by 2026-09-13) | Validation result, remaining risk, launch/pitch readiness | **Not yet due at time of writing (2026-09-11)** |

**Action required before submission:** paste the permalinks into this table, or state explicitly that a post was not published. They are not recoverable from the repository and will not be invented here.

**Planned Week 5 content, and it will lead with the uncomfortable part:** the validation result is *no validation*. Ten hypotheses open, four kill criteria unevaluable, one breached. The lesson is the one the dossier predicted on day one — that the artefact which mattered most was the outreach list, and it was treated as the easy part of the work rather than the gating one.

---

## 7. Evidence index

| Claim | Where to verify it |
| --- | --- |
| Product selection, rejected candidates, opportunity scoring | `linear_ai_product_rnd.html` §08–§10 |
| Hypothesis ledger, 10 rows, all open | `USER_RESEARCH_EVIDENCE.md` §3 |
| Seven decision traces, four negative | `USER_RESEARCH_EVIDENCE.md` §4 |
| Kill criteria with current status | `EVIDENCE_BACKED_ROADMAP.md` §Kill criteria |
| Business model canvas with evidence labels and coherence arguments | `BUSINESS_MODEL_CANVAS.md` |
| Roadmap sequenced by risk retired, not preference | `EVIDENCE_BACKED_ROADMAP.md` |
| Engineering decision log (30 entries) | `docs/DECISIONS.md` |
| Gap review that triggered this deliverable set | `docs/REVIEW_2026-09-10.md` |

**AI collaboration disclosure:** the product, market, pricing and user-research content is recorded in `AI_COLLABORATION.md` as *"produced by neither"* of the code-generating assistant passes. AI assistance was used in drafting and structuring the business deliverables in this repository; it **did not generate users, interviews, quotes, willingness-to-pay evidence, customer feedback, live-model scores, latency numbers or cost numbers**, and no such evidence exists. **Total AI spend: `NOT_MEASURED`** — no provider billing data was available to this work.
