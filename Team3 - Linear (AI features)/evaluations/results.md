# Warrant Evaluation Report

Status: **MEASURED_SYNTHETIC_POLICY_E2E_AND_RETRIEVAL**

Measured: 2026-09-03T11:43:42.215055+00:00

## Metrics and proposed targets

| Metric | Proposed target | Measured value | Status |
| --- | --- | --- | --- |
| `verdict_accuracy` | >= 0.90 | `1.0` | **within_target** |
| `unsafe_allow_count` | 0 | `0` | **within_target** |
| `unsafe_allow_rate` | 0 | `0.0` | **within_target** |
| `fail_closed_correctness` | 1.00 | `1.0` | **within_target** |
| `adversarial_non_allow_rate` | 1.00 | `1.0` | **within_target** |
| `approval_burden_standard_slice` | <= 0.35 (K3 triggers above 0.40) | `0.4364` | **outside_target** |
| `verdict_distribution` | diagnostic only; no threshold | `{"ALLOW": 40, "DENY": 21, "REQUIRE_APPROVAL": 59}` | **within_target** |
| `e2e_pipeline_safe_rate` | 1.00 (local conformance target) | `1.0` | **within_target** |
| `operational_adversarial_non_allow_rate` | 1.00 (local conformance target) | `1.0` | **within_target** |
| `risk_class_macro_f1` | >= 0.75 | `NOT_MEASURED` | **NOT_MEASURED** |
| `retrieval_recall_at_10` | >= 0.85 | `1.0` | **within_target** |
| `possible_duplicate_precision` | >= 0.85 | `1.0` | **within_target** |
| `semantic_search_recall_at_10` | >= 0.85 | `1.0` | **within_target** |
| `exact_key_search_success` | 1.00 | `1.0` | **within_target** |
| `brief_unsupported_authority_count` | 0 | `0` | **within_target** |
| `brief_contradiction_count` | 0 | `0` | **within_target** |
| `brief_required_fact_coverage` | 1.00 | `1.0` | **within_target** |
| `triage_team_accuracy` | >= 0.85 | `1.0` | **within_target** |
| `triage_priority_macro_f1` | >= 0.75 | `1.0` | **within_target** |
| `triage_label_precision` | >= 0.80 | `1.0` | **within_target** |
| `triage_label_recall` | >= 0.80 | `1.0` | **within_target** |
| `judge_precision_satisfied` | >= 0.85 | `NOT_MEASURED` | **NOT_MEASURED** |
| `p95_preflight_latency_ms` | < 12000 ms | `NOT_MEASURED` | **NOT_MEASURED** |
| `cost_per_delegation_usd` | < 0.06 USD | `NOT_MEASURED` | **NOT_MEASURED** |

The four labelled slices express cases in the same feature vocabulary consumed by the policy engine. Their `verdict_accuracy` is therefore a policy-interpreter conformance check, not a product-quality measure. The synthetic fixture-backed E2E pipeline slice is the only end-to-end signal in this run.

## Integrity notes

- This run measures deterministic policy behaviour on synthetic labelled cases.
- The E2E slice uses deterministic fixture extraction/judging and synthetic issues.
- Retrieval quality is measured only on a small synthetic labelled set; it is not evidence of production or customer-data quality.
- Semantic search uses deterministic token-hash vectors, not a production embedding model; its small synthetic search set is a regression signal only.
- Brief grounding is measured on fixture and deterministic fallback narratives; live-model grounding still requires separate evidence.
- Triage quality is measured on three synthetic demo issues and deterministic signals; it does not establish production routing quality.
- Live-model judge quality, production latency, and cost remain NOT_MEASURED.

Failures: **0**
