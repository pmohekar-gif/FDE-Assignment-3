# Role Evidence — Kriti Meheta

**Role:** Engineer — inherits accountability for implementation, reliability, tests, deployment and telemetry from Gaurav Yadav
**Team 3 · Linear (AI features) · Product: Warrant**
**Joined:** 2026-09-11 · **Last revised:** 2026-09-11 · **v1**

---

## Accountability statement

I joined this team on **2026-09-11**, four days before the submission deadline of 15 September, replacing Gaurav Yadav as the accountable engineer. This file is short because my tenure is short, and it separates three things that are easy to blur when someone joins late:

1. **What I have actually done** — one item.
2. **What I have been handed and have not yet done** — three items, with acceptance criteria.
3. **What my presence on this team does and does not count as evidence** — the section that matters most, because the honest answer limits how my feedback may be used.

I did not build Warrant. Attributing the engineering artefact to me would be false, and `ROLE_EVIDENCE_Gaurav_Yadav.md` is retained unchanged as the record of who did. What I own from today is whether the handover is real, whether Gaurav's last two changes actually work, and whether the system can be observed from the inside.

---

## 1. Onboarding record — 2026-09-11

| What was covered | By whom | Artefact |
| --- | --- | --- |
| Walkthrough of the three integrations built so far — **Slack, GitHub, Linear** | Team | `docs/features/` adapter and feasibility notes; `README.md` environment table |
| Internal working of the product and a **live demo of Warrant** | Team | `docs/DEMO.md`, `docs/DEMO_SCRIPT_LIVE.md` |
| **Git repository access** granted, with instructions to run the demo independently | Team | Seeded as `KRIT-4101` |
| Documentation handover for deeper reference | Team | `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` (30 entries), `docs/LIMITATIONS.md`, `docs/ENGINEERING_REPORT.md` |
| Flagged: two changes Gaurav shipped on **2026-09-10**, handed to me for validation | Team | Seeded as `GAU-3204` |
| Flagged: Gaurav's next planned task — **observability logging** — reassigned to me | Team | Seeded as `KRIT-4103` |

The handover is recorded in the demo workspace as four seeded tickets: `GAU-3204` (the handoff), `KRIT-4101` (onboard and rerun the demo), `KRIT-4102` (test pass), `KRIT-4103` (observability logging). Those are **synthetic seed records in `src/warrant/seed.py`**, not a production tracker — they document the handover, they do not evidence that the work is complete.

> **A naming collision worth stating once.** The demo workspace has always contained a seeded identity `kriti-developer` / "Kriti" with role `lead`, created before I joined. **That synthetic actor is not me.** It is one of the five seeded assignment identities used for local demo authorisation, and — exactly as `USER_RESEARCH_EVIDENCE.md` §Status says of all five — it is not a user, not an interviewee, and is not evidence of anything. My real observations appear in this file and nowhere in the seed data.

---

## 2. What I have completed

### ✅ `KRIT-4101` — ran the end-to-end demo locally, independently

I ran the demo myself on a machine that had never seen this repository, rather than watching someone else drive it.

**Why this is worth recording as more than an onboarding chore.** `ROLE_EVIDENCE_Gaurav_Yadav.md` §7 names *"one-command run verified on a machine that has never seen the repo"* as owed evidence, and `docs/REVIEW_2026-09-10.md` lists reproducibility among the engineering claims that must hold at submission. Until today that claim had been verified only by the person who wrote the setup. A first run by someone with no prior context is the only way it gets tested properly — every assumption the author cannot see is still in place.

| Field | Value |
| --- | --- |
| Date | 2026-09-11 |
| Path exercised | `make setup && make demo` (the verified one-command path in `README.md`) |
| Prior exposure to the repo | None |
| Outcome | **Demo run completed** |
| Detailed findings | 🔴 **`EVIDENCE GAP / ACTION REQUIRED` — not yet captured** |

**The findings are not written here because they have not been recorded yet, and I will not reconstruct them from memory into a submission artefact.** This is the same standard the rest of this submission holds itself to. The capture template below is ready; it needs filling in by me, from the actual run, before 15 September.

#### Capture template — first-run observations (to be completed)

| # | Question | Observation |
| --- | --- | --- |
| 1 | Did `make setup` succeed on the first attempt? If not, what failed and what was the fix? | *pending* |
| 2 | Time from clone to a working demo at `127.0.0.1:8000` | *pending* |
| 3 | Was `make doctor` needed? Did the stale-`.venv` remedy work as documented? | *pending* |
| 4 | Which Python version was used? *(the project floor is 3.11; the last recorded suite run used 3.10 — see §5)* | *pending* |
| 5 | Did any documented command fail or behave differently from the README? | *pending* |
| 6 | Which of the three reference cases (`PAY-4471`, `SEC-4502`, `WEB-4519`) behaved as `docs/DEMO.md` describes? | *pending* |
| 7 | What was confusing on first contact — before anyone explained it? **This decays fastest and is the most valuable row in the table.** | *pending* |
| 8 | What did I have to ask a teammate that the docs should have answered? | *pending* |

**Why row 7 and row 8 matter more than the rest.** They are observable only once. `BUSINESS_MODEL_CANVAS.md` §5 lists *"hands-on policy authoring for the first workspace"* as consultative onboarding work and labels the assumption untested; my first-run confusion is the closest thing this team has to data on how hard onboarding actually is, and it is unrecoverable after I become fluent.

---

## 3. What I have been assigned and have not yet done

### `KRIT-4102` — test pass on Gaurav's 2026-09-10 changes

Two changes shipped the day before I joined, neither of which has been validated by anyone other than their author:

| Change | Surface | What I must confirm |
| --- | --- | --- |
| **Ticket-creation → Coding Session routing, with a notification trigger** | `src/warrant/main.py`, `src/warrant/coding.py`, `templates/delegation.html` | That routing fires only after a valid warrant exists; that the notification cannot leak issue content, secrets or scope detail to an unauthorised recipient; that a denied or pending delegation routes nowhere |
| **Rerun coding session control inside the delegation view** | `src/warrant/coding.py`, `templates/delegation.html` | **The highest-risk item in the handover, and the reason I would not sign this off casually** |

**Why the rerun control needs the most scrutiny.** A rerun is a second execution against an authorisation that was granted for the first one. Four specific failure modes follow from the architecture as documented, and each is a test I owe:

1. **Warrant re-validation.** `docs/DECISIONS.md` records that a warrant is re-verified immediately before the runner is invoked, because it can be revoked mid-session (`WarrantNoLongerValid`). A rerun must re-run that check, not inherit the original result. A rerun against a revoked or expired warrant would be an unauthorised execution.
2. **Nonce semantics.** Warrant nonces are hashed, **single-use** and expiry-bound. A rerun must not consume, replay or bypass a nonce that the first run already spent.
3. **Scope immutability.** The execution contract is immutable, enforced by a database trigger on `contract_json`. A rerun must execute the *same* narrowed scope the approver authorised — not the policy's original, wider proposal. A rerun that silently re-widens scope would convert "a human may narrow but never widen" into a false claim, and that sentence appears in the pitch.
4. **Audit distinguishability.** The ledger must show a rerun as a distinct, attributable event, not as an indistinguishable repeat of the first. An accountability product whose own ledger cannot tell two executions apart has a hole in exactly the thing it sells.

**Acceptance for this ticket:** each of the four has a test that fails against the defect it describes before it passes. That is the standard `AI_COLLABORATION.md` records for the 2026-09-10 defect pass — *"every fix reproduced as a failing case first, then re-run"* — and I am holding the handover to it.

### `KRIT-4103` — privacy-safe observability logging

Gaurav's next planned task, reassigned to me as a way to learn the implementation from the inside. Structured logs around delegation creation, policy decision, warrant issuance, coding-session start and rerun, notification dispatch, and verification failure — **without logging secrets or raw private data.**

**Two constraints that are not negotiable**, because the product's own claims depend on them:

- Repository snippets, coding logs and diffs already redact secret-like values, and `D-ENG-027/028/029` record a provenance split between an introduced secret, a carried one and a test fixture. **New log lines must not become the path that bypasses that redaction.**
- `docs/ARCHITECTURE.md` and `AI_COLLABORATION.md` state that audit records the rule, version and reasons **rather than raw prompts**, and that no authoring-assistant activity is written to any product table. Observability logging must not quietly widen what is retained.

**What I intend to instrument beyond the brief, and why it is the highest-value thing I can add in four days.**

`EVIDENCE_BACKED_ROADMAP.md` concludes that the right question about the 0.4364 approval burden is **not** whether it exceeds the 0.35 target, but whether approvals still carry information — the alert-fatigue failure mode, where *"the prompt still appears, but it has stopped carrying information."* It then states plainly that the observables for that are **approval dwell time** and the **approve-without-narrowing rate**, and that neither is instrumented. `EVIDENCE_BACKED_ROADMAP.md` also lists **bypass rate** as an indicator with no instrumentation behind it.

So three counters that cost very little to add would each convert a currently unanswerable argument into a measurable one:

| Counter | What it settles |
| --- | --- |
| **Time from approval request to decision** | `N3`'s stated target of *time-to-decision p50 < 3 min*, currently `NOT_MEASURED` — and one of the two alert-fatigue observables |
| **Share of approvals granted without narrowing scope** | The other alert-fatigue observable. A high rate is the signature of rubber-stamping, which would matter far more than the burden figure |
| **Delegations that reached execution without a warrant** | The bypass rate. Warrant's own stated limitation is that it *"cannot physically prevent a bypass… so we detect it"* — and detection is currently asserted rather than built |

I am flagging this as a proposal rather than a completed decision, because it extends the ticket as written and the team should agree it before I spend the time.

**What this cannot fix.** `docs/ENGINEERING_REPORT.md` records that OpenTelemetry tracing and alerting are not implemented. Structured logs are not traces, and I will not describe them as such.

---

## 4. What my feedback counts as — and what it does not

This is the section I would most want a marker to read, because the team's initial framing needs correcting and I would rather correct it myself.

**The team's stated intention was to treat me as "our first external stakeholder."** The seed data records the same framing. **I do not think that holds, and counting it would damage the submission rather than help it.**

| Why not | |
| --- | --- |
| **I am not external** | I joined the team today. My incentives are aligned with this product succeeding, which is the precise bias the Discovery Evidence Ladder warns about — *"agreement is the cheapest signal in the building. It costs the person giving it nothing, which is exactly why so much of it is available."* |
| **I am not the buyer** | The named customer is a platform or DevProd lead at a 50–400 engineer organisation who has turned agents on and been asked an external question about them. I am an engineer joining a student project. *"The quality of an answer cannot exceed the quality of the participant–behaviour match"* — and mine is zero for the demand question |
| **Counting me would move a number dishonestly** | The user count is **0 of 5** across ten documents. Recording me as stakeholder interview #1 would move it to 1 on the strength of a colleague's opinion. `USER_RESEARCH_EVIDENCE.md` already refuses to count the five seeded identities as users; counting me would be the same error with a real person attached |

**What my feedback legitimately is:** an **internal fresh-eyes engineering review** — a distinct and genuinely useful evidence class, and one this project has none of. It is good evidence for a specific and narrow set of questions:

- Can a competent engineer with no context install, run and understand this? *(reproducibility, onboarding friction, documentation quality)*
- Do Gaurav's last two changes behave as claimed? *(defect-finding)*
- Is the system observable from the inside? *(the logging task)*

It is **not** evidence for: whether anyone has this problem, whether the segment is right, what anyone would pay, whether the approval burden is acceptable to a real team, or whether the audit export is the right artefact. Those remain hypotheses **H1–H10, all ten open.**

### Placement on the evidence ladder, honestly

| My contribution | Rung | Supports |
| --- | --- | --- |
| First-run demo execution on a clean machine | **R5 — prototype action**, simulated stakes, operator is a team member | Reproducibility and onboarding friction. Nothing about demand |
| Test pass on the routing and rerun changes | **R6 — controlled test** of specific behaviours | Whether two named features work |
| My opinion of the product | **R1 — opinion**, from an aligned party | Effectively nothing, and it should be labelled that way wherever it is quoted |

### The one way I might produce real external evidence

The team's remaining gap is **primary evidence from people outside it**, and the deciding experiment is already designed and waiting in `USER_RESEARCH_EVIDENCE.md` §6 — one assumption, **H1**, with a pre-fixed binary score: *does this person name a specific agent-authored repository change in the last 60 days, and can they say where it is recorded?*

**Action I own from today:** review my own professional network for anyone matching the U-A, U-B or U-D profiles — a platform or DevProd lead, an engineering manager, or a staff engineer who reviews agent output, at a team that has agents enabled. If any exist, introduce them by end of **12 September**, so a conversation can happen before the window closes. An introduction from me is a legitimate channel; my own opinion is not a substitute for theirs.

**If that produces nothing, it produces nothing**, and the register keeps its zeroes.

---

## 5. Handover risks I have inherited

Stated on day one, while I can still see them clearly.

| # | Risk | Why it matters now |
| --- | --- | --- |
| 1 | **Two changes have never been validated by anyone but their author**, and they touch the execution path — the surface where a governance product's claims are either true or false | `KRIT-4102`. Four days to deadline |
| 2 | **The last recorded suite run (445 passed) used CPython 3.10**, below the project's own `requires-python = ">=3.11"` floor, with `uv sync` bypassed | `AI_COLLABORATION.md` says explicitly: *"Re-run `make check` on a 3.11+ interpreter before submitting."* **This has not been done, and it is now mine.** The count may move |
| 3 | **The golden set has no regression slice.** The four defects fixed on 2026-09-10 gained 41 unit tests and **zero evaluation cases**, so `make eval` cannot regress on the failures that reached the primary path | Roadmap item `N9`. If I fix anything under `KRIT-4102`, it must enter the golden set, or I will have repeated the same omission |
| 4 | **Bus factor.** The engineer who built the system left the day before I arrived, with no overlap beyond a handover call | `docs/DECISIONS.md` (30 entries) and `docs/LIMITATIONS.md` are unusually complete, which is why this is a risk rather than a crisis. It is worth naming that the documentation is the reason the handover is survivable |
| 5 | **`.env` is present in the repository root** (8.4 KB) and the assignment prohibits it in the archive | `make package` claims to refuse excluded paths and key-shaped strings. **Verify before zipping** — this is a submission-blocking item, not a nice-to-have |

---

## 6. What I will and will not claim on 15 September

**Will claim:** that I ran the demo independently on a clean machine and recorded what happened; whatever the test pass on `KRIT-4102` actually finds, including "no defects found" if that is the result; whatever logging I complete, with its limits stated.

**Will not claim:** authorship of Warrant; that my feedback constitutes user or stakeholder evidence; that the observability work amounts to tracing; or that a test pass completed in four days by one person substitutes for the validation this product has not had.

**If I find nothing wrong with Gaurav's changes, I will say so plainly** rather than manufacturing findings to justify the handover. A clean test pass on a well-built feature is a real result.

---

## 7. Community posts

| Week | Required | Status |
| --- | --- | --- |
| Week 3 (by 2026-08-30) | Role plan, problem hypothesis, interview plan, first decision trace | **Not applicable — I joined on 2026-09-11.** I will not back-date a post I did not write |
| Week 4 (by 2026-09-06) | Alpha/build evidence, user feedback, one decision changed by evidence | **Not applicable — same reason** |
| Week 5 (by 2026-09-13) | Validation result, remaining risk, launch/pitch readiness | 🔴 **`ACTION REQUIRED` — due in two days, and this one is mine.** No link recorded yet |

**Planned Week 5 content:** the handover itself as the subject — what a four-day engineering takeover can and cannot verify; the first-run findings from `KRIT-4101`, which are the most useful thing I have to offer and which no continuing team member could have produced; the result of the `KRIT-4102` test pass, defects or none; and the argument in §4 above, that a new teammate is not an external stakeholder and why the team corrected that framing rather than banking the number.

**Action required before submission:** paste the Week 5 permalink into this table once published. It will not be invented here.

---

## 8. Evidence index

| Claim | Where to verify it |
| --- | --- |
| Handover tickets and their acceptance criteria | `src/warrant/seed.py` — `GAU-3204`, `KRIT-4101`, `KRIT-4102`, `KRIT-4103` |
| The two changes I am validating | `src/warrant/coding.py`, `src/warrant/main.py`, `src/warrant/templates/delegation.html` |
| Warrant lifecycle constraints the rerun control must respect | `docs/DECISIONS.md` (`D-ENG-013`, `D-ENG-019`, `D-ENG-021`), `docs/ARCHITECTURE.md` |
| Redaction and secret-provenance rules the logging task must not bypass | `docs/DECISIONS.md` (`D-ENG-027`, `D-ENG-028`, `D-ENG-029`) |
| Test-count provenance and the 3.10 interpreter caveat | `AI_COLLABORATION.md` §Verification performed on 2026-09-10 |
| Golden-set composition and the missing regression slice | `evaluations/golden.json`; `EVIDENCE_BACKED_ROADMAP.md` item `N9` |
| Uninstrumented observables I propose to add | `EVIDENCE_BACKED_ROADMAP.md` §Leading and lagging indicators |
| The engineering work I did **not** do | `ROLE_EVIDENCE_Gaurav_Yadav.md` — retained unchanged |
| Why I am not counted as a user or stakeholder | `USER_RESEARCH_EVIDENCE.md` §1, §5; `STAKEHOLDER_INTERVIEWS.md` §4 |

**AI collaboration disclosure:** I have contributed no code to this repository as of 2026-09-11, so none of the existing codebase is attributable to me or to any assistant acting on my behalf. The three-pass authoring history of the code I have inherited is recorded in `AI_COLLABORATION.md` under *Division of work*. Any AI assistance I use on `KRIT-4102` or `KRIT-4103` will be recorded there before submission, to the same standard. **Total AI spend attributable to me: $0** — no provider call has been made on my behalf.
