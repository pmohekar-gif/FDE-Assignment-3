# Pricing Strategy — Warrant

**Owner:** Priyanka Mohekar (Sales) · **Unit-economics inputs:** Gaurav Yadav (Engineer) · **Review:** Chirayu Gupta (PM)
**Version:** v3 · **Last revised:** 2026-09-11 · consolidates and supersedes `linear_ai_product_rnd.html` §30 and §31
**v3 changes:** the cost model was rebuilt against Week 1 *A $0.036 call is not a $0.036 task* — it previously stopped at step 3 of six and understated fully loaded cost by ~1.8×. Base cost now misses its own <$0.06 target and the unfavourable case breaches K5. A customer-side human-review cost line was added; it is ~4× our list price.

---

## The honest headline, first

> **We hold zero willingness-to-pay evidence.** No price has been put to a buyer. No prospect has reacted to a number. Every price in this document is a **hypothesis anchored on published competitor pricing**, and it is labelled as such on every line.
>
> This is the position the R&D dossier pre-committed to on 2026-08-27: *"If interviewees do not engage with price, the submission will say 'no willingness-to-pay evidence was obtained; the pricing model remains a hypothesis anchored on published competitor benchmarks'."* That sentence is now the true one, and it is written here rather than replaced with an invented figure.
>
> Kill criterion **K7** exists for exactly this case. Its status is **not evaluated** — it cannot fire without at least one buyer conversation.

What *is* defensible in this document: the **choice of price metric**, the **packaging structure**, the **rejected alternatives with their reasons**, the **cost model**, and a set of **measured cost inputs** produced by our own build. Those are commercial reasoning, and they stand on their own. What is not defensible is any specific dollar figure, and none is presented as more than an anchor.

---

## 1. Price metric

**Chosen metric: one *governed delegation*.**

A governed delegation is one request to hand a unit of work to a coding agent that passes through Warrant's policy engine and receives a verdict — `ALLOW`, `REQUIRE_APPROVAL` or `DENY` — whether or not a warrant is subsequently issued.

Applying the metric-tree discipline from Week 3 (*Building an Outcome and Metric Tree*), step 1 is *"name the thing you get paid for"* and step 8 is *"write the tree into the contract — the billable node, its window, and who computes it."* Both are answered:

| Metric-tree layer | Warrant's node |
| --- | --- |
| **Business outcome** | An organisation can let agents work on its backlog and produce a defensible authorisation decision and verified close-out for every delegation, with zero unsafe auto-allows |
| **User behaviour** | A platform lead widens agent autonomy on low-risk surfaces instead of turning agents off |
| **Product signal (billable node)** | **Governed delegations** — counted at policy-verdict emission |
| **Guardrail node, priced** | Unsafe-allow count. Contractual target: **0**. This is a node on the tree, not a footnote |

**Billing definition, pre-committed so it cannot drift:** counted once per delegation record at the moment the policy engine emits a verdict; a re-delegation of an unchanged issue revision inside the cache window is **not** a new billable unit; denied delegations **are** billable, because the denial is the work. Computed by Warrant, exported in the audit CSV, and reconcilable by the customer from their own ledger export.

That last clause matters. Step 5 of the metric-tree ladder names the failure mode directly: *"the vendor's invoice and the client's dashboard disagree by 93 contacts per 1,000, and both are correctly computed."* A governance product cannot survive an unreconcilable invoice, so the meter ships with an export the customer can recompute from.

---

## 2. What the market actually charges — verified benchmarks

All figures from vendor pricing pages accessed **2026-08-27**. `VERIFIED`. No page carried a last-updated date, so these are a point-in-time read.

| Vendor | Seat price | AI unit | AI unit price | What it teaches us |
| --- | --- | --- | --- | --- |
| **Linear** | Basic $10, Business $16 /user/mo billed yearly | Prepaid workspace-pooled credits, opt-in | Tokens at provider rates **with no markup**; sandbox $0.25 / 20-min block; Loops $0.07–$0.20 per run | The incumbent sets the anchor for what "AI in your tracker" costs — and passes model cost through at **zero margin**, so it is not monetising AI directly |
| **GitHub Copilot** | Business $19, Enterprise $39 /seat/mo | AI credit | **$0.01** /credit overage; 1,900 / 3,900 credits included per user | GitHub and Atlassian have converged on the same $0.01 credit, which makes credits comparable across vendors for the first time |
| **Atlassian Rovo** | Bundled into Jira Standard/Premium/Enterprise | Rovo credits, 10 per agent request | **Overage not currently billed**, 90 days' notice promised | A deliberate choice to suppress the meter and buy adoption data first |
| **Sentry Seer** | Team $26, Business $80 /mo, unlimited users | *Active contributor* (≥2 PRs to a Seer-enabled repo) | $40 /active contributor/mo. Legacy per-run model ($1.00/issue fix, ~$0.003/scan) **deprecated January 2026** | **The most important row.** A vendor ran per-run AI consumption pricing and reverted to a per-active-user seat. Cite this against any "usage-based is inevitable" assumption |
| **Intercom Fin** | Essential $29 → Expert $132 /seat/mo | Fin **outcome** | $0.99 resolution / handoff / disqualification; $9.99 qualification; one outcome per conversation | Outcome pricing works where the outcome is unambiguous and observable — and the 10.1× value-differentiated tier is elegant |
| **Zendesk** | Support Team $19 → Suite Prof. $115 /agent/mo yearly | Automated resolution | Per-resolution price **not published**; allowance is **dollar-denominated** at $2 / $5 / $10 per agent seat/mo, $5,000/yr cap | A dollar-denominated allowance decouples entitlement from unit price, so the unit can be repriced without repapering contracts. **We are copying this construct** |
| **Governance / observability** | Langfuse, Braintrust, Arize: **$0 per seat**. LangSmith: $39/seat | Units, spans, traces, scores | Langfuse $8/100k units; Braintrust $1.50–$2.50/1k scores; LangSmith $1.50/LCU | Three of four governance vendors charge nothing per seat and meter volume. **The category we sit closest to has already de-seated** |

**Analyst context** `SECONDARY`: Growth Unhinged's 2026 monetisation report (n=230+, published 2026-05-13) finds 37% of B2B software companies on hybrid pricing (up from 25%), AI-credit adoption at 29% with a further 33% planning to introduce credits, and a **median target AI gross margin of about 50%**, with only 12% aiming for 80%+. This is analyst research, not a vendor price, and is labelled accordingly.

---

## 3. Candidate metrics evaluated

Three genuinely different structures, scored against six criteria.

| Criterion | **A · Per engineering seat** | **B · Platform fee + governed delegations** ✅ | **C · Per prevented incident / outcome** |
| --- | --- | --- | --- |
| Metric | Monthly price × engineers in workspace | Monthly platform fee including a dollar-denominated allowance; overage per delegation | Charge per unsafe action blocked, or a share of review hours saved |
| Buyer fit | Platform lead; familiar, easy to approve | Platform lead / VP Eng — predictable base, variable component that grows with adoption | CFO-friendly in theory; irresistible narrative |
| Value alignment | **Poor** — our value scales with *agent* activity, which is decoupling from headcount by design | **Strong** — a governed delegation is exactly one unit of the thing we do | **Superficially perfect** |
| Predictability | Excellent | Good — the fee anchors the invoice, the allowance caps surprise | **Terrible** |
| Gross margin | Excellent at low usage, **inverts badly** at high usage: a heavy agent user pays the same while costing ~20× more | Controllable — cost per delegation is measurable and cacheable, so margin is a known function | **Unknowable** — revenue uncorrelated with cost; a quiet month costs the same and earns nothing |
| Gaming risk | Low | Moderate and **self-correcting**: batching many changes into one delegation is possible, but a broader warrant means a wider blast radius and more approvals | **Severe** — we would control both the meter and the definition of the event we bill for |
| Expansion path | Only via hiring — the slowest possible vector | Automatic, as customer agent adoption grows | None reliable |
| **Verdict** | **REJECTED** (§5) | **RECOMMENDED** | **REJECTED** (§6) |

---

## 4. Recommended packaging

`HYPOTHESIS — no WTP evidence. Every figure is an anchoring guess derived from §2.`

| Tier | Price | Included | Retention | Purpose |
| --- | --- | --- | --- | --- |
| **Team** | **$0 / mo** | 200 governed delegations, single workspace | 30 days | Adoption vehicle, not a revenue tier. The product must be trialable without a call |
| **Growth** | **$499 / mo** | **$400 of governed delegations** (≈ 1,143 at the overage rate), policy simulator, audit export | 400 days | The target tier |
| **Enterprise** | from **$1,800 / mo** | Pooled allowance, SSO, custom retention, sub-processor review, named support | Custom | Uplift sold on security review, not features |
| **Overage** | **$0.35** per governed delegation beyond the allowance | — | — | — |

**Three structural choices, each traceable to a benchmark:**

1. **Dollar-denominated allowance, not a unit count.** Copied from Zendesk. It decouples the customer's entitlement from the unit price, so the per-delegation price can be revised without repapering a contract — which matters a great deal for a product whose unit cost is an inference bill that will fall.
2. **Free tier with a real allowance, not a trial.** Copied from the governance/observability cohort, three of four of which charge $0 per seat. Our buyer will not take a sales call before seeing the product run against their own surface map.
3. **No seat charge at any tier.** See §5.

---

## 5. Rejected alternative — per-engineering-seat pricing

**This is the assignment's required rejected alternative, and it is rejected for three independent reasons.**

**Reason 1 — it prices the wrong thing.** The entire premise of coding agents is that output stops tracking headcount. A seat price is therefore a bet *against our own thesis*: if agents work, the customer's agent activity grows while their engineer count does not, and our revenue is flat precisely in the scenario where we are most valuable. Worse, the margin inverts — a team running 5,000 delegations a month pays the same as a team running 50 while costing roughly 100× more to serve.

**Reason 2 — the seat is already owned.** Linear holds the tracker seat at $16 and GitHub holds the developer seat at $19. Adding a third per-engineer charge for the same engineer is the easiest procurement "no" in the world, and it puts us in a comparison we cannot win: a governance tool priced against a tool the engineer uses every hour.

**Reason 3 — it punishes the behaviour we want.** A team that governs *more* delegations pays nothing more. Our revenue would be uncorrelated with the value delivered, and our commercial incentive would be to sell seats rather than to make the gate good enough to widen.

**The strongest argument *for* the seat, stated fairly.** Sentry Seer ran per-run AI consumption pricing and **deprecated it in January 2026** in favour of a $40 per-active-contributor seat. That is a real vendor reversing a real decision in our adjacent category, and it is the single best evidence that usage pricing for AI developer tooling can fail in practice — buyers dislike unpredictable invoices and finance teams dislike unforecastable lines. We are not dismissing it.

**Why we still reject it, and what would change our minds.** Sentry's unit is *a contributor who pushed ≥2 PRs* — a proxy for human activity, in a product whose value genuinely does scale with humans. Ours does not. But the structure we chose is deliberately a hedge against Sentry's finding: the platform fee gives the buyer the predictable base they reverted to Sentry for, and the dollar-denominated allowance caps the surprise. **Revisit trigger:** if ≥2 of 5 interviewees state that a variable line cannot be approved in their organisation at all (pricing probe **P3**, which deliberately separates "easiest to get approved" from "what you personally prefer"), we fall back to a per-repository or per-active-agent seat — *not* a per-engineer seat, which fails reasons 1 and 2 regardless.

### Also rejected — outcome pricing (per prevented incident)

Rejected for a **structural** reason rather than a commercial one, and the distinction matters.

The counterfactual is unmeasurable: nobody can prove the blocked action *would* have caused harm. Intercom and Zendesk can price outcomes because a resolved support conversation is observable and mutually agreed; a prevented incident is neither. Worse, it creates a direct incentive to tighten policy in order to bill more — **a governance vendor billing itself for its own alarms.** For a product whose only asset is trust, that is not merely commercially awkward, it is disqualifying.

This is also the Goodhart's Law case (Week 3, *Goodhart's Law*) in its purest form: the moment the blocked-action count becomes the revenue target, it stops being a safety measure.

---

## 6. Unit economics

Expressed as formulas so the assumptions are visible and arguable, per the Week 3 discipline that *"a number carried to two decimal places is not more accurate than a range — it is more confident, which is worse."*

### Cost model

```
cost_per_delegation =
      (1 − cache_hit_rate) × extract_cost
    + verify_rate          × judge_cost
    + brief_rate           × brief_cost
    + embed_cost_amortised
    + infra_cost_per_delegation
```

> ### ⚠️ Correction, 2026-09-11 — this formula prices a *call*, not a *task*
>
> Week 1's *A $0.036 call is not a $0.036 task* decomposes cost in **six steps — call → attempt → cache → retry → operations → fleet** — and reports an **11.6× gap between the naive and the loaded number** on its worked example. Measured against that ladder, the formula above stops at **step 3**. It is a per-attempt inference price wearing a per-delegation label.
>
> The session names precisely the error: *"Failed attempts bill in full. The denominator quietly changes here from attempts started to tasks completed — this is where most internal cost models silently understate."*
>
> Three lines were missing, in ascending order of how much they matter.

**Step 4 — charge failed work to the completion.** Extraction can fail, return malformed output, or exhaust retry/repair; the embedding circuit breaker can trip. Every one of those consumes tokens and returns no billable delegation.

```
attempts_per_completion = Σ (1 − p_fail)·p_fail^(k)  over k = 0..retry_cap
model_cost_per_completed_delegation = attempts_per_completion × cost_per_attempt
```

**Step 5 — add machine and human operations.** This is the line whose omission most distorts the model.

```
ops_cost = machine_ops + support_cost_allocated
```

**Step 6 — allocate fixed cost across completed volume.**

```
fully_loaded = (variable_per_completion × monthly_completions + monthly_fixed)
               ÷ monthly_completions
```

**The denominator, stated once and not moved again:** every figure below is **per governed delegation that reached a policy verdict**, which is also the billable node defined in §1. Where a number uses a different denominator it says so on the line.

```
gross_margin = (price_per_delegation − fully_loaded_cost_per_delegation)
               ÷ price_per_delegation

contribution_per_workspace =
      platform_fee
    + max(0, delegations − included_allowance) × overage_price
    − delegations × fully_loaded_cost_per_delegation
    − support_cost_per_workspace
```

### Inputs

| Input | Low (favourable) | **Base** | High (unfavourable) | Basis | Label |
| --- | ---: | ---: | ---: | --- | --- |
| Extraction cost / call | $0.006 | **$0.012** | $0.030 | Originally ~3.5k in / 300 out at mid-tier hosted rates | `ASSUMPTION` — **now partly measured, see below** |
| Judge cost / call | $0.008 | **$0.018** | $0.040 | ~4k in / 400 out | `ASSUMPTION` |
| Brief cost / call | $0.002 | **$0.005** | $0.010 | ~1.5k in / 250 out | `ASSUMPTION` |
| Cache hit rate | 0.45 | **0.30** | 0.10 | Re-delegation of unchanged issue revisions | `ASSUMPTION` |
| Verify rate | 0.70 | **0.85** | 1.00 | Not every warrant returns evidence — some expire | `ASSUMPTION` |
| Brief rate (= approval burden) | 0.20 | **0.32** | 0.45 | Target ≤0.35; **K5/K3** thresholds | `VERIFIED` at **0.4364** on the synthetic policy slice — worse than base |
| Embedding, amortised | $0.0001 | **$0.0004** | $0.0010 | One embedding per issue revision, reused | `ASSUMPTION` |
| Infra / delegation | $0.002 | **$0.006** | $0.020 | $60–$300/mo hosting ÷ volume | `ASSUMPTION` |
| **Inference cost per attempt** | **≈ $0.014** | **≈ $0.040** | **≈ $0.117** | The step-3 number — what the old model called "cost per delegation" | Derived |
| *Step 4* — attempts per completion | 1.05 | **1.11** | 1.25 | Extraction failure, malformed output, repair exhaustion, embedding breaker trip. Retry cap 2 | `ASSUMPTION` |
| *Step 5* — machine ops / completion | $0.001 | **$0.004** | $0.012 | Worktree creation, verification subprocess, diff capture, audit write | `ASSUMPTION` |
| *Step 5* — support allocated / completion | $0.002 | **$0.008** | $0.030 | Support cost ÷ completions. Consultative first-workspace onboarding makes this real, not nominal | `ASSUMPTION` |
| *Step 6* — fixed allocated / completion | $0.005 | **$0.015** | $0.060 | Engineering, security review, SOC 2 readiness ÷ monthly completions | `ASSUMPTION` |
| **Fully loaded cost per governed delegation** | **≈ $0.023** | **≈ $0.071** | **≈ $0.248** | Target < $0.06 · **K5 kills above $0.15** | Derived |
| **Margin at $0.35 / delegation** | **93%** | **80%** | **29%** | Base still clears the ~50% median AI gross margin target `SECONDARY`; **the unfavourable case falls well below it** — still profitable, but not at a software margin | Derived |

**What the correction did.** Base cost moves **$0.040 → $0.071**, which now **misses the <$0.06 target** it previously cleared. The unfavourable case moves $0.117 → **$0.248**, which **breaches K5's $0.15 kill threshold** and cuts the margin from 67% to 29% — still profitable, but below the ~50% median AI gross margin `SECONDARY`, and a long way from the software margin the earlier model implied. Neither was visible while the model stopped at step 3.

> **A second defect, inherited rather than introduced.** The step-3 figures of $0.014 / $0.040 / $0.117 **do not reproduce from the input table above them.** Evaluating the formula at the stated inputs gives **$0.011 / $0.032 / $0.093**. The three published numbers came from the R&D dossier and were carried forward without being recomputed; they are conservative — each overstates cost by 20–26% — so nothing downstream is flattered by them, and we have kept them rather than silently restating the model's conclusions on quietly better numbers. **The formula, not the table, is the thing to trust.** Separately, the model still evaluates brief rate at the planning value **0.32** when the measured value is **0.4364**; substituting the measured rate raises base cost by roughly a further $0.0006 of inference and, far more significantly, is what drives the customer-side review cost below.

This is a worse picture than the one in the R&D dossier, and it is the correct one. A system-to-call ratio of **1.8×** here is still far below the session's worked example of **11.6×** — because our per-delegation work is one or two schema-bound calls rather than a multi-turn agent loop — but it is not 1.0×, and the earlier model implied it was.

### Measured inputs added since the dossier (2026-09-11)

Two of the inputs above are no longer pure guesses. Both come from our own build, and both are reported with their limits.

| What was measured | Result | Source | What it changes | What it does **not** establish |
| --- | --- | --- | --- | --- |
| **Extraction token counts** | 1,060–1,116 input tokens, 138–276 output tokens per call (n=3) | `evaluations/live-run-2026-08-31.json`, OpenRouter `minimax/minimax-m3:free`, served by GMICloud | Roughly **one third** of the assumed 3.5k-in / 300-out volume, so the extraction-cost assumption is conservative and the base case likely overstates cost | n=3, one model, synthetic issues, one prompt shape. Not a distribution |
| **Approval burden (brief rate)** | **0.4364** on the 120-case synthetic policy slice | `evaluations/results.json`, re-run 2026-09-10 | Worse than the 0.32 base and worse than the 0.45 unfavourable case is close to. Pushes base cost up and, more importantly, **breaches K3's 0.40 kill threshold** | Policy-interpreter conformance on synthetic labelled cases, not customer behaviour |
| **Live provider cost** | **$0.00 reported** | Same live run | Nothing. Free-tier promotional pricing | **Explicitly not production unit economics.** Must not be presented as satisfying the <$0.06 target |
| **Live provider latency** | p50 preflight **50,578 ms** | Same live run | Rules this endpoint out for an interactive gate entirely — a cost input that is free but 50 seconds slow is not a viable production configuration | p95 remains `NOT_MEASURED`; three calls cannot support a p95 |

### Illustrative workspace contribution — Growth tier

```
2,000 delegations/mo · platform fee $499 · allowance $400 · overage $0.35

allowance covers          400 ÷ 0.35   ≈ 1,143 delegations
overage        (2,000 − 1,143) × $0.35  =  $300
revenue                      $499 + $300 =  $799
fully loaded cost  ($0.071 base × 2,000) =  $142
                                          -------
contribution                             ≈  $657   ·  margin ≈ 82%
```

Support and fixed allocation are now **inside** the $0.071 and are not added again as a separate line — the previous version's separate $60 support row was the same money counted once, so the contribution figure barely moves even though the cost model roughly doubled. That coincidence is worth naming, because it is exactly how an understated unit cost hides inside a healthy-looking contribution line.

**Illustrative only.** The volume, the fee and the overage price are all unvalidated. This demonstrates the *shape* of the model, not a forecast.

### The cost line that is not on our P&L — and matters more than the ones that are

Week 1's cost session ends on a finding we had missed entirely:

> *"A 5% human review rate costs more than every token in the task. **Escalation policy is a pricing decision, not just a quality one.**"*

In the session's worked example human review is **47.2% of variable cost** at a 5% review rate. **Warrant's measured approval burden is 0.4364 — roughly nine times that rate**, and every one of those approvals consumes a named human's attention by design. That cost lands on the *customer's* P&L, not ours, which is precisely why it was absent from a model that only tracked our inference bill.

```
customer_review_cost_per_delegation
  = approval_burden × review_minutes × loaded_rate_per_minute
  = 0.4364 × 2 min × $1.25/min          ($75/hr loaded senior engineer)
  ≈ $1.09 per governed delegation
```

| Line | Per governed delegation | Borne by |
| --- | ---: | --- |
| Our fully loaded cost | $0.071 | Us |
| Our list price | $0.35 | Customer |
| **Human approval time the product creates** | **≈ $1.09** | **Customer** |

`ASSUMPTION` — review minutes and loaded rate are planning inputs, never measured. Our own target for time-to-decision is p50 < 3 min and it is `NOT_MEASURED`; 2 minutes is the favourable end of our own claim.

**Three consequences, and they reorganise the commercial argument.**

1. **The product must displace more review time than it creates.** At 0.4364 it adds roughly $1.09 per delegation of human attention. The value proposition — *"human attention concentrated where consequence is real"* — is only true if the attention it *removes* from the other 56% exceeds that. **We have never measured either side.** This is the sharpest untested claim in the whole business case, and it is not on the hypothesis ledger. It should be: it is effectively H5 (does the brief reduce review effort?) stated as an arithmetic rather than an opinion.
2. **Our price is small relative to the cost we impose.** $0.35 against ~$1.09 of induced review time means a buyer evaluating total cost of ownership is looking at a number roughly 4× our invoice. Arguing on our price alone concedes the wrong comparison; the honest frame is review-hours displaced, which is also the branch DT-007 would select if the buying trigger proves internal.
3. **K3 is a pricing problem, not only a quality one.** Every point of approval burden is a line in the customer's cost model. `EVIDENCE_BACKED_ROADMAP.md` treats N8 as a safety-tuning question blocked on user evidence; it is *also* the largest single lever on customer-side economics, and that argument was missing from both documents.

### The load-bearing assumption

**Delegation volume per workspace per month.** Everything else is second-order. The cost side is bounded and cheap; the revenue side is almost entirely a function of how many delegations a real team actually produces — and we do not know. **Ten a week and there is no business at any price; two thousand a month and the model works comfortably.**

Sensitivity, per the Week 3 opportunity-sizing procedure (*"the purpose of sizing is not to produce a large number — it is to find the assumption that must be tested next"*):

| Rank | Assumption | Why it moves the decision | Test |
| --- | --- | --- | --- |
| **1** | Monthly delegation volume per workspace | Swings contribution from negative to $657 | Interview Q6.1 — *"roughly how many agent-authored changes land in a typical week, and how has that moved in the last three months?"* |
| **2** | Approval burden / brief rate | Drives our cost, the customer's **~$1.09/delegation** of induced review time, and whether the product is experienced as a control or a tax. Measured 0.4364, above its own kill threshold | Demo call Q2/Q3 (H4), plus policy tuning |
| **2=** | Review minutes displaced vs created | Decides whether the value proposition is arithmetically true at all. Entirely unmeasured on both sides | H5, restated as an arithmetic rather than an opinion |
| **3** | Whether a variable line can be approved at all | Decides packaging, not price | Pricing probe P3 |
| 4 | Attempts per completion (retry multiplier) | Second-order at our call volume, but it is the step most cost models omit | Telemetry at volume |
| 5 | Cache hit rate | Second-order on cost only | Telemetry at volume |

**If volume comes back in single digits**, the honest conclusion is that the market is early. The right response is to say so in the submission and reposition toward the largest, highest-volume teams — not to inflate the model.

---

## 7. How willingness-to-pay would be collected

The instrument exists and is rehearsed. It has not been used. Asked **after the demo, never before** — a price quoted before value is understood only measures politeness.

| ID | Question | What it actually measures |
| --- | --- | --- |
| **P1** | "How would you expect something like this to be priced, if you were designing the invoice?" | Whether "per governed delegation" is discoverable **without prompting**. Tests H7 cleanly, because they answer before hearing our metric |
| **P2** | "What's the last developer or security tool you bought, and roughly what band was it in — per seat, per month, per year?" | Their reference price, without asking them to value ours |
| **P3** | "Three structures: flat monthly fee; fee plus usage allowance; pure usage. Which would be easiest to get **approved** in your organisation, and which would you personally **prefer**?" | Tests H8, and separates procurement friction from personal preference. **These are often opposite answers, and the gap is the finding** |
| **P4** | "At what monthly number does this stop being a tooling decision and start needing someone else's signature?" | The approval threshold — far more actionable than a WTP figure, and much harder to answer politely |
| **P5** | "If you had this and it governed a thousand delegations next month, what would you expect that to cost?" | An implied unit price in their own words, anchored on volume rather than on our number |
| **P6** | "What would have to be included for it to come out of the **security** budget rather than the **engineering** budget?" | Which budget line we compete in — the single biggest determinant of achievable price |
| **P7** | "If I told you this was $499 a month, what's your first reaction?" *(asked last, only if P1–P6 are answered)* | A **reaction test, not a WTP measurement.** Recorded as a reaction and reported as such |

**Willingness-to-pay evidence held as of 2026-09-11: none.**

| Probe | Asked of | Result |
| --- | --- | --- |
| P1–P7 | 0 of 5 planned users | `EVIDENCE GAP / ACTION REQUIRED` |

---

## 8. Hypotheses this document depends on

| ID | Hypothesis | Evidence that would settle it | Result | Decision it drives |
| --- | --- | --- | --- | --- |
| **H6** | A named budget owner exists for this class of spend | ≥3 of 5 name a role **and** a budget line | `Not collected` | Confirms, or triggers **K7** → open-source pivot |
| **H7** | "Per governed delegation" is intuitive to the buyer | ≥3 of 5 restate the metric correctly and unprompted after one explanation (P1) | `Not collected` | Keep the metric, or fall back to per-repo / per-active-agent |
| **H8** | Buyers prefer a predictable platform fee with an included allowance over pure usage billing | Forced choice between three structures, with reasons (P3) | `Not collected` | Final packaging decision |

**Kill criterion K7** — *no credible commercial signal*: 0 of 5 interviewees can name a budget owner, **or** 0 of 5 engage with a price range at all. Check by 2026-09-11. Owner: Priyanka. **Current status: cannot be evaluated — no interviews conducted.** If triggered: reposition as open-source developer tooling with a paid hosted ledger, and report the negative finding prominently.

---

## 9. What we would do differently

Stated plainly, because the pricing section is where the process failure is most visible.

The pricing instrument was finished on 2026-08-27 and has not been used once in the fifteen days since. The dossier identified the cause in advance and named it correctly: *"an interview on 12 September is a transcript; an interview on 2 September is a decision."* Outreach was the gating activity for the entire commercial track and it did not happen at the start of the window, so every downstream commercial artefact — this one included — is anchored on competitor pricing rather than on a buyer.

The correct lesson is not "we should have guessed better." It is that **the pricing work that mattered was sending twelve messages on day one**, and no amount of benchmark analysis substitutes for it.

---

## Sources

- `linear_ai_product_rnd.html` §30 Pricing, §31 Unit Economics — team R&D dossier, 2026-08-27
- Vendor pricing pages accessed 2026-08-27: Linear, GitHub Copilot, Atlassian Rovo, Sentry Seer, Intercom Fin, Zendesk, Langfuse, Braintrust, Arize, LangSmith
- Growth Unhinged 2026 monetisation report (n=230+, published 2026-05-13) `SECONDARY`
- `evaluations/results.json` (re-run 2026-09-10; first measured 2026-08-30) · `evaluations/live-run-2026-08-31.json` (2026-08-31) — our own measurements
- `docs/ENGINEERING_REPORT.md`, `AI_COLLABORATION.md` — measurement provenance and the explicit statement that no WTP evidence exists
- FDE session material, **Week 1**: *A $0.036 call is not a $0.036 task* (the six-step call → attempt → cache → retry → operations → fleet decomposition, the 11.6× loaded/naive gap, and "escalation policy is a pricing decision"); *Build, Buy, or Combine* (crossover `V* = F/(um − us)`; `effective_unit = list_unit / success_rate`); *Model selection, from first principles*
- FDE session material, **Week 3**: *Building an Outcome and Metric Tree (Sierra and Outcome-based Pricing)* (the eight-step ladder, and step 8 "write the tree into the contract"); *Opportunity Sizing Without False Precision*; *Goodhart's Law*

**Companion documents:** `BUSINESS_MODEL_CANVAS.md` · `USER_RESEARCH_EVIDENCE.md` · `STAKEHOLDER_INTERVIEWS.md` · `EVIDENCE_BACKED_ROADMAP.md` · `PITCH_DECK.md`
