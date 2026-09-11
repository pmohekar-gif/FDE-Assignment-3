# Business Model Canvas — Warrant

**Product:** Warrant — a delegation control plane for coding-agent work.
**Team 3 · Linear (AI features) category · Assignment 3**
**Canvas owner:** Chirayu Gupta (PM) · **Commercial input:** Priyanka Mohekar (Sales) · **Cost/feasibility input:** Gaurav Yadav (Engineer)
**Version:** v3 · **Last revised:** 2026-09-11 · supersedes the draft canvas in `linear_ai_product_rnd.html` §32
**v3 changes:** the evidence labels are **audited** against Week 4's source hierarchy — they collapse three orthogonal axes into one and carry **no freshness axis at all**; the gap is documented, and reconciling the scheme is a named post-submission action rather than something done here. The cost structure carries the corrected unit economics. A single business lever is now named, per Week 3's value-chain rule.

---

## How to read the evidence labels

Every claim on this canvas carries a label. The labels are not decoration — they decide which blocks we are allowed to defend in the pitch and which we must present as open.

| Label | Meaning | Discovery Evidence Ladder rung |
| --- | --- | --- |
| `VERIFIED` | First-party published source, read and dated by us, or a measurement produced by our own build | R6–R7 (controlled test / production evidence) |
| `SECONDARY` | Third-party research or survey; some vendor-sponsored and marked as such | R1–R2 (opinion / anecdote at scale) |
| `ASSUMPTION` | Our planning input. Arguable, not yet tested | below R1 |
| `HYPOTHESIS` | A falsifiable claim with a named test that has not run | test not yet at R3 |
| `EVIDENCE GAP` | Required by the rubric, not held. Action named | — |

The Discovery Evidence Ladder (Week 3, *The Discovery Evidence Ladder*) ranks evidence as
`Opinion → Anecdote → Interview → Observed behaviour → Prototype action → Controlled test → Production evidence`,
on the principle that *"the gap between stated preference and revealed behaviour is not measurement noise to be cleaned up — it is the subject of discovery."*

> **Known weakness in these labels, stated rather than quietly kept.** Week 4's *Build a source hierarchy you can trust* grades a claim on **three orthogonal axes**, not one: **status** (`CONFIRMED` / `UNVERIFIED` — *"CONFIRMED means a place you can open. It never means you feel sure"*), **tier** (1 documents that make the rules · 2 how the work is really done · 3 what the systems recorded · 4 named people on the record · 5 things written to explain — where *"a Tier 5 source can only ever make an UNVERIFIED claim"*), and **freshness** (a `half_life_days` per source type — vendor API references ~60 days, client policy ~30).
>
> Our single-label scheme collapses all three: `SECONDARY` is really a *tier*, `ASSUMPTION` and `HYPOTHESIS` are both *status* `UNVERIFIED` differing only in whether a settle-step exists, and **we carry no freshness axis whatsoever.** That last omission is the material one for this product: the competitor pricing in `PRICING_STRATEGY.md` §2 and the Linear capability claims below were read on **2026-08-27**, which is inside a 60-day half-life today and will not be for long — and none of those pages carried a last-updated date. Every row below should additionally carry a `location` a reader could open and a `settle-by` date; *"a claim with no settle step is one nobody will check."* Reconciling the scheme properly is a post-submission action, not a silent one.

> **The single most important disclosure on this canvas.** As of 2026-09-11 we hold **zero primary customer evidence**. No interview has been conducted, no demo has been shown to an external user, and no willingness-to-pay signal has been collected. Every block below that depends on a buyer conversation is labelled `HYPOTHESIS` or `EVIDENCE GAP`. See `USER_RESEARCH_EVIDENCE.md` and `STAKEHOLDER_INTERVIEWS.md` for the register and the recovery plan.

---

## 1. Customer segments

| Segment | Definition | Label |
| --- | --- | --- |
| **Primary** | Software organisations of **50–400 engineers** that have already enabled **write-capable coding agents** against a tracker. Sector-agnostic, skewed to fintech, health-tech and B2B SaaS selling to enterprise — because those teams already answer vendor security questionnaires. | `HYPOTHESIS` — segment definition is untested against a real buyer |
| **Secondary** | 400+ engineer organisations with both a platform team and a compliance function. Longer sale, larger contract. | `ASSUMPTION` |
| **Explicitly not served** | Teams under 20 engineers (no governance function, no budget line) and OSS maintainers (acute pain, no money). | `ASSUMPTION` — deliberately excluded to keep the segment behaviourally coherent |

**Qualifying signal, askable in the first two minutes of a call:** the team (a) turned coding agents on in the last six months *and* (b) has been asked an external question about what those agents can change.

**Why this segment and not the adjacent ones.** Four personas plausibly touch this problem; only one has both the acute pain and the budget:

| Persona | Role in the model | Pain | Budget |
| --- | --- | --- | --- |
| **P1 · Platform / DevProd lead** (50–400 eng) | **The customer.** Feels the pain, owns the decision, can deploy in a week. | Controls are all-or-nothing: trust the agent or turn it off. The audit trail is a session transcript, not a decision record. | Owns or strongly influences the dev-tools line |
| **P2 · Staff engineer / involuntary reviewer** | **Champion, not buyer.** The product must be visibly *for* them. | "Almost right, but not quite" — the top named frustration at 66% `SECONDARY` (Stack Overflow 2025) | None |
| **P3 · VP Engineering / CTO** | **Economic approver.** Signs; rarely evaluates. Reached through P1. | Cannot evidence that agent leverage is either real or safe | Signs |
| **P4/P5 · Support–SRE lead, PM** | **Deferred.** Real adjacent pain, well served by incumbents (Linear Triage Intelligence, PagerDuty AIOps, incident.io, Enterpret). | — | — |

---

## 2. Jobs, pains and gains

### Jobs to be done (P1)

1. Let agents do real work without owning unbounded risk.
2. Answer *"what can your AI change, and who approved it?"* in one screen.
3. Know which agents are actually good — per team, in our codebase.
4. Keep reviewers' attention on the changes that need it.

### Pains

| Pain | Evidence | Label |
| --- | --- | --- |
| Controls are all-or-nothing: trust the agent, or turn it off | Linear's Agent Interaction Guidelines state plainly that *"an agent cannot be held accountable"*; hard boundaries are OAuth scopes plus install-time team scoping (read 2026-08-27) | `VERIFIED` |
| No record joining an action to an authorisation | Linear's Enterprise audit log covers *"account access, subscriptions, and settings changes"* for 90 days — an identity log, not a decision log. Rovo's audit log records agent *lifecycle*, not per-action decisions | `VERIFIED` |
| Review load rising while review capacity is flat | GitHub Octoverse 2025: PRs created **+20.4%** (47.5M vs 39.5M) while comments on PRs and issues moved **+0.35%** | `SECONDARY` (platform owner's own data; GitHub does not disaggregate, so flat comments could also mean better PRs) |
| The review trust model itself has broken | DORA names the **"verification tax."** DORA 2025 (~5,000 respondents): 90% use AI at work, 30% report little or no trust in AI-generated code | `SECONDARY` (self-reported) |
| Accountability is formally undefined in most organisations | Gravitee (2026-06-15, 750 senior tech leaders): **85% have no formal accountability for AI agent behaviour**; only 7.2% have a named accountable individual. Okta (2026-08-24): only 34% apply the same security controls to agents as to humans | `SECONDARY · vendor-sponsored` — three independent vendors converge, but all three sell the remedy |
| No way to compare agents or justify the spend | No vendor publishes neutral per-agent quality data; a tracker vendor has no incentive to report that a third-party agent underperforms | `ASSUMPTION` (argued from incentives, not measured) |

### Gains

1. A defensible answer for security, audit and the board.
2. Confidence to *widen* agent autonomy on low-risk surfaces — the product's growth story is permission, not restriction.
3. Human attention concentrated where consequence is real.
4. Evidence that an agent's work actually met the acceptance criteria written beforehand.
5. Agent-quality numbers no single vendor will supply.

> **Where we must not overclaim.** There is no credible current public statistic for the share of tracker issues that are duplicates, and we obtained zero verifiable review-site quotes. Neither appears anywhere in this canvas or the pitch.

---

## 3. Value proposition

> **"Nothing gets delegated to an agent without a warrant."**

A deterministic authorisation decision on every delegation; a scoped, expiring warrant naming a human authority; verification of returned evidence against a contract written beforehand; and an immutable record — across every tracker the customer uses.

**AI builds the case; code makes the call.**

Three differentiators, in order of defensibility:

1. **The authorisation decision is deterministic code, not a model output.** The LLM produces features and evidence; a versioned rules engine produces the verdict. The extraction schema contains **no field that could carry an authorisation**, so a successful prompt injection can at most produce a wrong description that deterministic checks then contradict. `VERIFIED` — implemented and tested; 0/120 unsafe allows and 100% adversarial non-allow on the policy evaluation (re-run 2026-09-10).
2. **The warrant is an artefact, not a log line.** A scoped, expiring authorisation naming a human, reviewable months later, with a hash-chained ledger behind it. `VERIFIED` — implemented; append-only enforced by database trigger, not convention.
3. **It is cross-tracker by construction.** Linear's governance can only ever be Linear's. A platform team running Linear *and* GitHub Issues *and* Jira otherwise carries three policies and three answers for its auditor. `ASSUMPTION` for demand; the adapter interface is built for two trackers, only one adapter ships in the MVP.

**What the product does *not* claim.** Warrant governs only delegations routed through it; it cannot physically prevent a bypass in another tool. Stating that limitation unprompted is a deliberate part of the pitch.

---

## 4. Channels

| Channel | Why it reaches this segment | Label |
| --- | --- | --- |
| **Founder-led / warm introduction** | The only channel that works inside three weeks, and the one the team actually has: Grid Dynamics delivery and client engineering leadership | `ASSUMPTION` — **and the one that has not yet produced a single conversation.** See §"Known weaknesses" |
| **Agent integration directories** | Teams already browse these for agents; a governance listing sits well beside them | `HYPOTHESIS` |
| **Technical content** | Publish the policy model and the eval methodology; the audience is engineers who recognise the problem on sight | `ASSUMPTION` |
| **Platform-engineering / DevProd communities** | Where P1 congregates; also the K9 fallback channel if warm intros fail | `ASSUMPTION` |
| **Later: delivery/consulting partnership** | A partner embedding governance into agent rollouts at enterprise clients | `HYPOTHESIS` |

**Channel-to-segment coherence.** The segment is a *named individual* reachable by warm introduction and technical credibility, not by advertising. All four active channels reach exactly that person and none requires a marketing budget we do not have.

---

## 5. Customer relationships

| Relationship | Mechanism | Label |
| --- | --- | --- |
| **Self-serve install, free tier** | The product must be trialable without a call. `make setup && make demo` is the verified one-command path today | `VERIFIED` (the run path exists) / `HYPOTHESIS` (that self-serve converts) |
| **Hands-on first-workspace policy authoring** | The initial surface map *is* the onboarding work, and it is consultative by nature | `ASSUMPTION` |
| **Quarterly audit-export review** | The recurring, non-annoying reason to be in the account — the export answers the question the customer's security team asked them | `ASSUMPTION` |
| **Public eval methodology and changelog** | A governance vendor that is opaque about its own quality is a contradiction. Our own evaluation publishes its **misses** (approval burden 0.4364 against a ≤0.35 target) | `VERIFIED` — the practice is already in force in this repository |

---

## 6. Key activities

1. **Maintaining the policy engine and the consequence × reversibility taxonomy.** The verdict matrix is the product's only hard correctness requirement.
2. **Growing and curating the evaluation set.** This *is* the product's quality — 120 labelled cases today across standard, boundary, adversarial and degraded slices.
3. **Tracker adapters**, maintained as trackers change their agent protocols.
4. **Security posture and sub-processor transparency.**
5. **Continuous customer research.** The policy defaults are a research output, not an engineering one. *This activity is currently not being performed — see `USER_RESEARCH_EVIDENCE.md`.*

**Build / buy placement, per Week 1's *Build, Buy, or Combine*.** Its rule is *"clear the hard constraints first, then compare total cost per successful task"*, through four gates asked in order — **1 data boundary · 2 runtime control · 3 governance plane · 4 operating capability** — where the first YES decides the shape and a NO on gate 4 means **BLOCKED**. Our answers **for the segment we are actually serving**: gates 1, 2 and 3 are all **NO** — no regulated buyer exists yet, we need no special runtime control, and we are not required to operate our own governance plane — so the first YES never arrives and the shape is **managed API (Buy)**. Gate 4 is then the *capability veto* rather than the shape-setter, and it is the one we would fail: three part-time people cannot carry a self-hosted inference platform, and a NO on gate 4 means **BLOCKED**, not "build anyway". That is why the cost structure below deliberately contains no GPU line. **Gate 1 flips to YES the moment a regulated buyer appears** — which is precisely why self-hosted/VPC deployment sits on the LATER roadmap rather than sooner, and why it would arrive as a constraint rather than as a preference. The session's own caution applies to us twice over: *"Hybrid is never an economic win"* — choose it for compliance, never for price — and the crossover `V* = F/(um − us)` is not worth computing until a regulated buyer exists to force gate 1.

---

## 7. Key resources

| Resource | Why it is defensible | Label |
| --- | --- | --- |
| **The evaluation dataset and its labels** | Hardest asset to copy; encodes what "unsafe" means across four risk slices | `VERIFIED` — 120 cases exist and run in CI |
| **The consequence × reversibility taxonomy** | Refined against real customer surface maps over time | `VERIFIED` as built / `ASSUMPTION` that it generalises beyond the synthetic seed |
| **Accumulated audit data as a cross-customer agent benchmark** (aggregated, never raw) | The one asset no single vendor can build | `HYPOTHESIS` — requires many workspaces and a careful consent design |
| **Engineering credibility** | Published eval methodology, 14-mode failure-injection suite, an honest limitations register, and a CI gate that is demonstrated *failing* on a deliberately-loosened policy | `VERIFIED` |
| **Team capacity** | Three people, part-time, over 19 days | `VERIFIED` — and the binding constraint on everything above |

---

## 8. Key partners

| Partner | Relationship | Label |
| --- | --- | --- |
| **Tracker platforms** (Linear, Jira, GitHub) | We are an integration, and a well-behaved one. Agent protocols are documented and stable | `VERIFIED` (protocols) / `ASSUMPTION` (that they stay open — this is risk K8) |
| **Coding-agent vendors** | **Partners, not competitors.** Warrant makes it easier for an enterprise to say yes to their agent. That framing matters commercially | `ASSUMPTION` |
| **Model and embedding providers** | Named sub-processors. Currently OpenAI-compatible and an experimental OpenRouter path; a Grid Dynamics Bifrost gateway client is implemented but **never called** | `VERIFIED` |
| **Delivery / consulting partners** | Rolling agents out at enterprise clients; a natural distribution partner given the team's context | `HYPOTHESIS` |
| **Identity vendors** (longer term) | Okta-style agent identity answers *"who"*; we answer *"may they, and did it work"* | `HYPOTHESIS` |

---

## 9. Cost structure

**Variable**

| Item | Value | Label |
| --- | --- | --- |
| **Fully loaded cost per governed delegation** | ≈ **$0.071** base case (range $0.023–$0.248) | `ASSUMPTION` — corrected 2026-09-11; the earlier ≈$0.040 priced a call rather than a completed task. See the note below the table |
| — of which model inference per attempt | ≈ $0.040 | `ASSUMPTION`, partly grounded by the measured token counts below |
| — of which retries, machine ops, support and fixed allocation | ≈ $0.031 | `ASSUMPTION` — the three steps the earlier model omitted |
| Embeddings | Negligible; one per issue revision, reused | `ASSUMPTION` |
| Hosting at MVP scale | $60–$300 / month | `ASSUMPTION` |

**Measured input, added 2026-09-11.** The live check on 2026-08-31 (3 synthetic delegations through OpenRouter `minimax/minimax-m3:free`, served by GMICloud) recorded real extraction token counts: **1,060–1,116 input tokens and 138–276 output tokens per call** (`evaluations/live-run-2026-08-31.json`). That is roughly **one third of the ~3.5k-in / 300-out assumption** the cost model was built on, which pushes the cost estimate *down*, not up. It is n=3, one model, synthetic data — it replaces a guess with a small measurement, not with a fact. Reported cost read **$0.00** because the endpoint is free-tier promotional pricing and is explicitly **not** production unit economics.

**Fixed**

- Engineering time — **dominant**.
- Security review and penetration testing, before any enterprise sale.
- SOC 2 readiness, as a later gate.

**Deliberately absent:** no GPUs, no vector-database licence, no Kubernetes platform cost, no sales team in year one.

**Cost-to-value coherence.** We claim to sell trustworthy decisions, and the cost base is dominated by engineering, evaluation and assurance rather than inference. That is the correct shape for a governance product. A product claiming rigour while spending most of its revenue on tokens would be an LLM wrapper with a policy skin.

**Correction carried from `PRICING_STRATEGY.md` v3 (2026-09-11).** The ≈$0.040 figure above was a per-*attempt* inference price, not a per-delegation cost. Rebuilt against Week 1's *A $0.036 call is not a $0.036 task* — adding failed attempts charged to the completion, machine operations, support and fixed allocation — the fully loaded figure is **≈$0.071 base, range $0.023–$0.248**. That **misses our own <$0.06 target**, and the unfavourable case **breaches kill criterion K5** and cuts the margin at our list price from 67% to **29%** — still profitable, but below the ~50% median AI gross margin `SECONDARY`.

**And the largest economic consequence appears in no block of this canvas.** At the measured 0.4364 approval burden, the product creates roughly **$1.09 per governed delegation of human review time on the customer's side — about 4× our own list price.** The session's rule is the one to carry: *"Escalation policy is a pricing decision, not just a quality one."* The value proposition in §3 — *"human attention concentrated where consequence is real"* — is arithmetically true only if the review time removed exceeds the review time created, and **neither side has been measured.** This is now the sharpest untested claim on the canvas and it maps to hypothesis H5.

---

## 10. Revenue streams

| Stream | Structure | Label |
| --- | --- | --- |
| **Primary** | Platform fee + a **dollar-denominated allowance** of governed delegations, with per-delegation overage. Hypothesised: Team $0 / Growth $499 / Enterprise from $1,800, overage $0.35 per governed delegation | `HYPOTHESIS` — every figure is an anchoring guess derived from published competitor benchmarks. **No willingness-to-pay evidence exists.** Full reasoning in `PRICING_STRATEGY.md` |
| **Expansion** | Volume growth as the customer's own agent adoption grows; additional trackers; longer audit retention | `HYPOTHESIS` |
| **Enterprise uplift** | SSO, custom retention, sub-processor review, deployment in customer VPC | `ASSUMPTION` |
| **Not pursued** | Per-seat (rejected — see `PRICING_STRATEGY.md` §Rejected alternative); outcome-based / per-prevented-incident (rejected as structurally wrong); professional services as a revenue line (would consume the engineering capacity that *is* the product) | `VERIFIED` as a decision |

**Price metric:** one **governed delegation** — exactly one unit of the thing the product does. Revenue therefore rises with the value delivered rather than with the customer's headcount.

---

## Coherence arguments — the joins a marker will check

**1. Cost-to-value.** Sells trustworthy decisions; spends on engineering, evaluation and assurance rather than inference. Coherent. ✔

**2. Channel-to-segment.** Segment is one named individual reachable by warm intro and technical credibility; channels are warm intro, integration directories, technical content and practitioner communities. All three reach that person; none needs a budget we lack. Coherent — **but see weakness 1 below.** ✔ / ⚠

**3. Price-metric-to-value-proposition.** The value proposition is *per delegation governed*; the price metric is *per delegation governed*. A customer who governs more pays more and gets more. Coherent. ✔

**3a. The single business lever.** Week 3's *Mapping User Value to Business Value* runs a seven-link chain — user struggle → product intervention → behaviour change → operational effect → **business lever** → strategic consequence → causal test — and insists on **one** lever from Revenue · Cost · Risk · Retention · Speed, because *"claiming all five levers is how a value story becomes unfalsifiable."* Our lever is **Risk** — a defensible authorisation record where none existed. Not Cost: the arithmetic above shows the product *adds* review time at the current approval burden. Not Speed: it gates, by design.

**The arrow we are least sure of** (the artefact's required field) is link 3 → 4: that a platform lead shown a denial and a brief actually changes what their team delegates, rather than routing around the gate. That is hypothesis **H4**, and it is unresolved. The session's rule dates this document: *"Written before the work starts, it is a hypothesis. Written after the result, it is a rationalisation."* — this chain is written before, and has no result.

**4. Relationship-to-segment.** Self-serve trial matches a platform lead who will not take a sales call before seeing the product run; consultative first-workspace onboarding matches the fact that the surface map is genuinely their knowledge, not ours. Coherent. ✔

---

## Known weaknesses — stated rather than papered over

| # | Weakness | Consequence if true | Status |
| --- | --- | --- | --- |
| 1 | **The primary channel has produced nothing.** Warm introduction was the entire GTM plan, and as of 2026-09-11 zero interviews have taken place. | The segment definition, both pain rankings, every revenue figure and the early-adopter profile are all untested. This is the largest single hole in the commercial case. | `EVIDENCE GAP / ACTION REQUIRED` — recovery plan in `STAKEHOLDER_INTERVIEWS.md` §Recovery |
| 2 | **Free-tier conversion path is unvalidated.** A platform lead who installs it, likes it, and never exceeds the allowance is a plausible and unprofitable outcome. | Free tier becomes a cost centre with no conversion mechanism. | Open assumption |
| 3 | **Delegation volume per workspace is the load-bearing number and we do not know it.** Ten a week and there is no business at any price; two thousand a month and the model works comfortably. | The entire revenue side collapses or holds on this one input. | `EVIDENCE GAP` — interview question 6.1 exists solely to attack it |
| 4 | **The approval burden currently misses its own target.** Measured 0.4364 against a ≤0.35 proposed target and a 0.40 kill threshold (K3). | If the product is experienced as a tax rather than a control, the value proposition inverts. | `VERIFIED` miss — visible in the eval output and the README, not suppressed |
| 5 | **Segment exclusion is an assumption, not a finding.** We ruled out sub-20-engineer teams and OSS maintainers without speaking to either. | We may have excluded the segment with the most acute pain. | Open assumption |

---

## What would change this canvas

| Finding | Blocks it rewrites |
| --- | --- |
| Fewer than 3 of 5 interviewees confirm a real agent-authored repository change in 60 days (**K1**) | Customer segments, value proposition — pivot to a readiness gate for human-bound work |
| 3+ of 5 state a standing no-agent-write policy with no plan to change (**K2**) | Value proposition — pivot to an advisory evidence brief; drop enforcement |
| The buying trigger proves **external** (audit, security review, questionnaire) rather than internal frustration (**H3**) | Channels, relationships, segment priority (security-adjacent leaders become primary), and the price anchor moves to compliance spend |
| The buying trigger proves **internal** | The evidence brief becomes the hero surface and the price anchors on engineering hours saved |
| 0 of 5 can name a budget owner, or none engages with price at all (**K7**) | Revenue streams — reposition as open-source tooling with a paid hosted ledger |

---

## Sources

- `linear_ai_product_rnd.html` §06 Customer Problems, §07 Personas & JTBD, §30 Pricing, §31 Unit Economics, §32 Business Model Canvas, §33 Positioning & GTM — the team's R&D dossier, dated 2026-08-27
- `README.md`, `docs/ENGINEERING_REPORT.md`, `docs/LIMITATIONS.md`, `AI_COLLABORATION.md` — build and measurement evidence
- `evaluations/results.json`, `evaluations/live-run-2026-08-31.json` — measured evaluation and live-provider data
- Linear developer documentation and Agent Interaction Guidelines (read 2026-08-27); GitHub Octoverse 2025; DORA 2025 and *Balancing AI tensions* (2026-03-10); Stack Overflow Developer Survey 2025; Gravitee (2026-06-15); Okta (2026-08-24); vendor pricing pages accessed 2026-08-27
- FDE session material, **Week 1**: *Build, Buy, or Combine* (four constraint gates; "hybrid is never an economic win"); *A $0.036 call is not a $0.036 task* (the six-step cost decomposition behind the corrected cost structure)
- FDE session material, **Week 3**: *The Discovery Evidence Ladder*; *Mapping User Value to Business Value* (seven-link chain, one lever, "the arrow you are least sure of"); *Opportunity Sizing Without False Precision*
- FDE session material, **Week 4**: *Build a source hierarchy you can trust* (status / tier / freshness, `location`, `settle-by`); *Mapping the Value Chain and Stakeholder Incentives*; *The Domain Knowledge Canvas* — which is a **separate artefact from this one** and is not yet written; see the gap note below

**Deliverable gap identified 2026-09-11.** Week 4's *Domain Knowledge Canvas* is about the *client's operational domain* (ten slots: actors, goals, workflows, entities, rules, systems, economics, risks, metrics, **open_questions**), every row quoted and sourced, and is explicitly **not** substitutable by a Business Model Canvas, which is about *our* business. For a product whose entire substance is executable decision logic, Week 4 also implies a **living glossary** (*delegation, approval, warrant, scope, consequence, reversibility, approver* mean different things to Security, Platform Engineering and the intercepted engineer) and a **domain model** with entity lifecycles and write-time invariants. None of the three exists. They are outside this assignment's required deliverable list, and they are the right next artefacts if this product continues.

**Companion documents:** `PRICING_STRATEGY.md` · `USER_RESEARCH_EVIDENCE.md` · `STAKEHOLDER_INTERVIEWS.md` · `EVIDENCE_BACKED_ROADMAP.md` · `PITCH_DECK.md`
