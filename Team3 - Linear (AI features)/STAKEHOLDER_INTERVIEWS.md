# Stakeholder & Client Interviews — Warrant

**Owner:** Priyanka Mohekar (Sales) — recruitment, consent, interviewing · **Synthesis:** Chirayu Gupta (PM) · **Demo operation:** Gaurav Yadav (Engineer)
**Version:** v3 · **Last revised:** 2026-09-11 · consolidates `linear_ai_product_rnd.html` §28, §33 and §34
**v3 changes:** the recovery plan now tests one assumption with a pre-fixed binary deciding score (see `USER_RESEARCH_EVIDENCE.md` §6); the recruitment funnel is corrected against a measured benchmark; one script question is relabelled as a preference-trap opinion probe.

---

## Status

| Required element | Status |
| --- | --- |
| Interview script | ✅ Complete. Authored 2026-08-27, unchanged since — it demonstrably predates any result |
| Consent language | ✅ Complete, verbatim, read before any notes are taken |
| Anonymised notes or summaries | **`EVIDENCE GAP / ACTION REQUIRED` — 0 interviews conducted** |
| Insights / synthesis | **`EVIDENCE GAP` — nothing to synthesise** |
| Evidence of what changed because of the interviews | **`EVIDENCE GAP`. What changed *instead*, and why that is not a substitute, is documented in §6** |
| Named interviewees (only with consent) | None named, because none exist |

> **As of 2026-09-11, zero stakeholder or client interviews have taken place.** No outreach was sent. The instrument below is complete and rehearsed; it has never been used.
>
> No anonymised note in this file is a paraphrase of a real conversation, because there are no real conversations. Nothing here is presented as a finding.

---

## 1. Stakeholder map

Built using the Week 3 *Stakeholder Mapping* method, whose step 6 is the one that matters commercially: **derive incentives — for each participant, name the condition under which they prefer the deal to fail.** A map of obligations cannot see a party whose interest is in silence.

| Stakeholder | Formal authority | Informal influence | What they gain | **When they would prefer this to fail** |
| --- | --- | --- | --- | --- |
| **Platform / DevProd lead** (P1) — the customer | Owns the tooling budget line and the "how we work" decision | High with engineers; moderate upward | Stops being the person who has to explain an unreviewed autonomous change | If the gate makes them the bottleneck engineers complain about. **A control that routes through them personally is worse than no control** |
| **Staff engineer / reviewer** (P2) — champion | None | Very high — can kill adoption socially in a week | Reviews the changes that matter instead of all of them | If the brief is another screen to read rather than a replacement for reading the diff. Silence from this person is a veto |
| **VP Eng / CTO** (P3) — economic approver | Signs | Decides priority | A quarterly page they can take to the board | If it surfaces a number that makes agent adoption look worse than they have already claimed it is. **A governance tool can produce an inconvenient truth, and this is the party it inconveniences** |
| **Security / compliance lead** (U-E) — potential blocker or sponsor | Can block procurement outright | High in regulated contexts | A decision log rather than an identity log | If it sits outside their existing control framework and creates a fourth thing to audit. **Consolidation at the identity layer is in their interest, not ours** |
| **Procurement / finance** | Approves spend above a threshold | Low but absolute | — | If the invoice has an unforecastable variable line. Directly addressed by the packaging choice in `PRICING_STRATEGY.md` |
| **Tracker vendor** (Linear, Jira, GitHub) | Controls the integration surface | Controls whether we exist | Enterprises say yes to agents more readily | If we look like a competitor rather than an integration. **Risk K8** |
| **Coding-agent vendor** | Controls the execution surface | Moderate | Easier enterprise adoption of their agent | If our per-agent quality measurement shows their agent underperforming. **They are partners until the scorecard ships** |

**The workflow question this map does not answer, and should.** Week 4's *Mapping the Real Operational Workflow* insists that ground truth is an event log, not a recalled process — *"The SOP is a ruler, not the truth"* — and its rung 6 is the one that applies to us: **"Every gap in an event log is filled by something."** Today, agent delegation at a real team *is* governed, just informally: a Slack thread, a pasted diff, a colleague's "looks fine", a `--yes` alias, a team norm about which directories not to touch. **Those are the existing controls, and we have never observed one.** The session's warning lands directly on a governance product: *"A workaround is evidence of a missing activity, not of a bad user"* — remove the informal control without first capturing what it was doing, and we ship a governance product that deletes the only governance there was. Section 3's workaround questions exist to find them; they have not been asked.

**The two entries that change the pitch.** P3 and the security lead are both parties whose incentive can point *away* from us, and neither is obvious from an organisation chart. Naming them was the point of running the exercise, and both are represented in the interview plan — U-C tests P3, U-E tests the security lead, and U-E exists specifically to surface the objection we have not thought of.

---

## 2. Consent protocol

Read **verbatim, before any notes are taken.** No exceptions.

> "Thanks for the time. Before we start — this is for a product-development exercise, not a sales call. I'd like to take written notes. Nothing you say will be attributed to you or your company without your written permission; the write-up will be anonymised to something like 'platform lead at a mid-size fintech'. Please don't share anything confidential about your systems or your clients — I'll actively steer away from specifics if we get near them. You can ask me to stop taking notes, skip a question, or delete anything afterwards at any point. Is that all right? And are you happy for me to note that consent was given verbally today?"

**Rules that follow from it:**

1. Consent is captured **before** notes begin, and the method and date are recorded in the register.
2. Anonymisation is to a **profile**, never a name: *"platform lead, mid-size fintech, ~180 engineers."*
3. A name appears **only** with separate written permission, requested after the conversation, never during it.
4. No client-confidential material enters any artefact. The interviewer actively steers away from system specifics.
5. Async written responses are acceptable **with recorded consent** — this is the K9 fallback channel.
6. Any participant may withdraw their material afterwards, and the register records the withdrawal rather than deleting the row silently.

---

## 3. Interview script

Authored 2026-08-27. **Every question asks for a past event or a current behaviour, never for a prediction or an opinion about our idea.** The banned phrasings are listed in `USER_RESEARCH_EVIDENCE.md` §2.

### Section 1 — Opening / context (3 questions)

1. Tell me how work gets from *"someone reports a problem"* to *"it's shipped"* on your team today. Walk me through the last one you remember.
2. Where do AI tools appear in that path at the moment, if anywhere?
3. Who decides which tools your engineers are allowed to use, and how does that decision get made?

### Section 2 — Problem discovery (5 questions)

1. Tell me about the last time an AI agent changed something in one of your repositories. What happened?
   *— if "never": **that is a finding.** Follow with: what would have to be true for you to allow it?*
2. Who knew that change was happening, and when?
3. How did you find out whether it worked?
4. Has anyone outside your team — security, compliance, a customer, an auditor — asked you a question about what your AI tools can do or have done? What did you tell them?
5. Think about the last time an agent's work turned out to be wrong. How did you find out, and what happened next?

### Section 3 — Current workarounds (3 questions)

1. What have you put in place — technical or social — to keep agents away from things you'd rather they didn't touch?
2. Has anyone on your team built or scripted anything for this? What does it do?
3. What do you do today when you need to know who authorised something?

### Section 4 — Severity & frequency (3 questions)

1. Roughly how many agent-authored changes land in a typical week? How has that moved in the last three months?
   *— **the single most load-bearing question in the whole instrument.** The revenue model is almost entirely a function of this number. See `PRICING_STRATEGY.md` §6.*
2. Of the things on your plate this quarter, where would *"we can't account for what our agents did"* sit — top five, or not on the list?
3. What have you chosen **not** to let agents do, and what did that decision cost you?

### Section 5 — Business value & budget (3 questions)

1. If this problem were solved, whose budget would pay for it — and would that be a new line, or something it displaces?
2. What's the last developer tool you bought, and what made you sign?
3. What would make this a *"not this year"* for you, even if you agreed with the problem?

**Pricing probes P1–P7 are in `PRICING_STRATEGY.md` §7 and are asked only after the demo, never before.** A price quoted before value is understood measures politeness, not willingness to pay.

### Section 6 — Prototype validation (demo call only)

1. Before I show you anything: what would you expect a system like this to do when it **isn't sure**?
2. *[show a DENY]* What's your reaction? Would your engineers accept that, or route around it?
3. *[show the approval brief]* Is there anything on this screen you'd have to go and look up anyway? What's missing?
4. *[show the audit export]* Who in your organisation would ask for this, and would this satisfy them?
5. What would you want to change before you'd put this in front of your team?
6. If I sent you an install link tomorrow, what would stop you?

**Demo sequencing rule:** show the **DENY first** — the strongest and most polarising screen — and capture reactions verbatim, including the dismissive ones. Then the approval brief, then the audit export. The failure path is demonstrated deliberately, because a demo that only shows success is discounted by the audience.

---

## 4. Interview register

| # | Anonymised profile | Date | Consent method | Duration | Demo shown | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | *(U-A) Platform / DevProd lead, 100–400 eng* | — | — | — | — | **Not conducted** |
| 2 | *(U-B) EM / tech lead, 20–80 eng* | — | — | — | — | **Not conducted** |
| 3 | *(U-C) VP Eng / CTO* | — | — | — | — | **Not conducted** |
| 4 | *(U-D) Staff engineer, agent-output reviewer* | — | — | — | — | **Not conducted** |
| 5 | *(U-E) Security / compliance-adjacent eng leader* | — | — | — | — | **Not conducted** |

**Outreach log**

| Wave | Planned date | Planned count | Sent | Replies | Conversations |
| --- | --- | --- | --- | --- | --- |
| Wave 1 | 2026-08-27 – 08-28 | 12 | **0** | 0 | 0 |
| Wave 2 | 2026-08-31 | 8 | **0** | 0 | 0 |
| **Total** | | **20** | **0** | **0** | **0** |

**Kriti Meheta (joined 2026-09-11) is not interview #1**, and the register above is unchanged by her arrival. She is a team member, not an external stakeholder; the reasoning is in `ROLE_EVIDENCE_Kriti_Meheta.md` §4, and her contribution is registered as an internal fresh-eyes review in `USER_RESEARCH_EVIDENCE.md` §1. She has, however, taken an action item to introduce anyone in her own network matching the U-A, U-B or U-D profiles by **12 September** — an introduction from her is a legitimate recruitment channel even though her own opinion is not evidence.

**The funnel we planned was optimistic by roughly 2.3×.** We assumed 20 approaches → ~8 replies → ~5 conversations. Week 3's *Design the evidence before the interview* gives a measured benchmark: **100 leads → 62 claim relevant experience → 23 completed the behaviour in the last 90 days → 11 can produce a contemporaneous artifact.** At that rate 20 approaches yields about **two** participants who can evidence the behaviour, not five. The session's framing is the correction: *"Losing eighty-nine of a hundred leads is not attrition; it is the measurement."*

The operational consequence, adopted for the remaining window: **the artifact is requested at recruitment, not at the end of the conversation.** Asking afterwards converts a participant who cannot evidence the behaviour into a transcript that looks like evidence.

No row above will be completed from imagination, including the "declined" and "no reply" rows — a fabricated rejection is as dishonest as a fabricated endorsement.

---

## 5. Synthesis

**Nothing to synthesise.** Zero interviews.

The synthesis format is pre-committed, so that it is applied to whatever arrives rather than fitted to it. Week 3's *From vivid quotes to defensible insights* gives the ladder of claims — **quotation → evidence unit → theme → insight** — where an insight is *"an explanation someone tried to kill and could not."*

**With zero sessions we hold zero evidence units, so nothing in this submission may be called a theme or an insight.** Every user-facing claim we hold is at best a named hypothesis. The session's one-line test — *"which unit, from which session, would have to be wrong for this to collapse? If nobody can answer, it is a slogan"* — has no answer for any of them. It also names the two failure modes nearest to us, **quote theatre** and **unsourced nuance**; a synthesis with no sources at all sits below both.

One rule to carry into whatever conversations happen: *"A vivid quote and a weak one cost the same to collect and are not equally likely to be true."* The gates are **1 atomize evidence · 2 code and compare · 3 preserve tension · 4 form the opportunity · 5 target the next uncertainty**, and gate 3 exists because the comfortable middle — averaging two contradictory participants into a moderate claim neither made — is the easiest way to lose the finding.

Per conversation:

- **Three findings** — each stated as a past event or observed behaviour, with the hypothesis it bears on
- **One surprise** — something we had not anticipated
- **One contradiction** — something that contradicted a belief we held. *If this field is empty, the interview was probably leading, and that is itself a finding about the interviewer*
- **Verbatim objections**, especially the dismissive ones
- **The hypothesis rows it moves**, and in which direction

Across conversations:

- Patterns held by ≥3 of 5, stated with the rung of evidence supporting them
- **Negative findings kept prominent rather than softened** — the format puts them first, not in a closing paragraph
- Hypotheses refuted, and the pre-committed decision each refutation triggers
- Anything that would fire a kill criterion, named explicitly with its ID

---

## 6. What changed because of the interviews

**Nothing, because there were no interviews.** That is the honest answer to the rubric line, and substituting something else for it would be the failure this section exists to avoid.

What changed for *other* reasons is documented elsewhere and is **not offered as a substitute**:

| Change | Driven by | Where |
| --- | --- | --- |
| Rejected AI triage, duplicate detection and semantic search as the core product; pivoted to the authorisation layer | Reading the incumbent's own published documentation, 2026-08-27 | `USER_RESEARCH_EVIDENCE.md` DT-001 |
| Ruled out the free live-model endpoint for the interactive gate | Our own measured latency, 2026-08-31 | DT-002 |
| Excluded fixture results from all live-model quality claims | Measured live verdict drift, 2026-08-31 | DT-003 |
| Published the approval-burden miss rather than loosening the policy to hide it | Our own evaluation, 2026-08-30 (re-run 2026-09-10) | DT-004 |
| Four execution defects fixed; 41 regression tests added | Walking 13 tickets through the flow, 2026-09-10 | DT-005 |
| Claimed no successful real-agent run | A failed sandbox smoke test | DT-006 |

**The distinction matters.** Every one of those is a decision changed by *evidence*. Not one is a decision changed by a *customer*. The assignment asks for both, and we can currently demonstrate only the first.

**What is blocked on interviews right now, concretely:**

1. **K3's fallback cannot be executed.** The approval burden is 0.4364, above its own 0.40 kill threshold. The named remedy is to re-scope to protected surfaces only. We will not tune a safety threshold against zero user input — doing so would be guessing at what a customer finds acceptable and then reporting it as a design decision.
2. **DT-007 cannot be closed.** Both branches of the H3 buying-trigger decision are pre-committed and dated. Either branch rewrites the pitch's opening, the primary segment and the price anchor. It needs one conversation.
3. **The pricing model stays a hypothesis.** K7 cannot even be evaluated without a buyer conversation.

---

## 7. Recovery plan — 2026-09-11 to 2026-09-15

Four days. Scoped to what four days can actually produce, and — **rewritten 2026-09-11** — scoped to **one assumption**, not several. Week 3's *The smallest credible experiment* names a multi-assumption plan **the fused experiment** and says it *"produces an uninterpretable result"*; the previous version of this table was one. The full experiment design, including the pre-fixed binary deciding score, is in `USER_RESEARCH_EVIDENCE.md` §6 and governs this table.

| When | Action | Owner |
| --- | --- | --- |
| **11 Sep, today** | Send 15–20 outreach messages. Opening line is a question about their experience, not a pitch — a pitch contaminates the answer | Priyanka |
| **11 Sep** | Open the K9 fallback immediately rather than waiting for warm intros to fail again: platform-engineering communities, second-degree contacts, and **written async interviews with recorded consent** | Priyanka |
| **12–14 Sep** | Run whatever lands. **H1 only** — problem-first, no demo, no price on the first pass. Score each PASS/FAIL against the pre-fixed criterion within 24 hours | Priyanka + Chirayu |
| **13–14 Sep** | Any demo call: DENY screen first, pricing probes only after, verbatim capture including dismissals | Priyanka + Gaurav |
| **14 Sep** | Update this file, the register, the hypothesis ledger and DT-007 — **or record the null result explicitly** | Chirayu |

**Minimum credible outcome for the remaining window:** two conversations, with **the H1 deciding score returned for both** — *does this person name a specific agent-authored repository change in the last 60 days, and can they say where it is recorded?* Everything else captured in those conversations (objections, budget language, any reaction to the DENY screen, anything about price) is **explaining score**: recorded richly, and structurally unable to overrule the deciding score. A warm conversation with no dated, locatable example is a **FAIL**.

**What that would and would not license.** Two PASSes license running H2 and H4 next — *"a passed experiment licenses the next experiment and nothing further."* They would not validate the product, unblock N8, or justify anything in the roadmap's NEXT column. The session's named failure mode here is **reading attention as demand**, and a booked call is attention.

**Pre-committed integrity rule.** If the window closes with fewer than three conversations, this document says so in these words, the register keeps every "Not conducted" row, and the pitch presents the hypothesis ledger with its unresolved rows visible. No profile will be invented, no secondary source re-described as a stakeholder, and no quote written that nobody said.

---

## 8. Lesson

The instrument was finished on day one and never used. The dossier had already identified the cause and written down the remedy: *"Priyanka's highest-leverage single act is sending twelve outreach messages on 27 August… An interview on 12 September is a transcript; an interview on 2 September is a decision."*

That sentence was correct, it was written in advance, and it was not acted on. The lesson is not about interview technique — the script is good. It is that **the research artefact that mattered was the outreach list, and it was treated as the easy part of the work rather than the gating one.**

---

## Sources

- `linear_ai_product_rnd.html` §28 User Research Plan, §33 Positioning & GTM, §34 Role Dashboards — authored 2026-08-27
- `USER_RESEARCH_EVIDENCE.md` — hypothesis ledger and decision traces DT-001 to DT-007
- `PRICING_STRATEGY.md` §7 — pricing probes P1–P7
- FDE session material, **Week 3**: *Design the evidence before the interview* (five gates, the recruitment funnel, the preference trap, the evidence matrix and "a row with a hole in it does not ship"); *From vivid quotes to defensible insights* (quotation → evidence unit → theme → insight); *The smallest credible experiment* (narrow the sample, not the mechanism; deciding vs explaining score); *Stakeholder Mapping* (step 6, derive incentives); *Reconstruct the system people actually operate*; *Saying no without losing trust*
- FDE session material, **Week 4**: *Mapping the Value Chain and Stakeholder Incentives* (seven rungs; rung 6 "the condition under which they prefer the deal to fail"); *Mapping the Real Operational Workflow* ("a workaround is evidence of a missing activity, not of a bad user")
