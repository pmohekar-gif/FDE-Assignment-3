# Warrant Evaluation Report

Status: **MEASURED_SYNTHETIC_POLICY_AND_E2E**

Measured: 2026-08-31T05:06:36.473477+00:00

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
| `retrieval_recall_at_10` | >= 0.85 | `NOT_MEASURED` | **NOT_MEASURED** |
| `judge_precision_satisfied` | >= 0.85 | `NOT_MEASURED` | **NOT_MEASURED** |
| `p95_preflight_latency_ms` | < 12000 ms | `NOT_MEASURED` | **NOT_MEASURED** |
| `cost_per_delegation_usd` | < 0.06 USD | `NOT_MEASURED` | **NOT_MEASURED** |

The four labelled slices express cases in the same feature vocabulary consumed by the policy engine. Their `verdict_accuracy` is therefore a policy-interpreter conformance check, not a product-quality measure. The synthetic fixture-backed E2E pipeline slice is the only end-to-end signal in this run.

## Integrity notes

- This run measures deterministic policy behaviour on synthetic labelled cases.
- The E2E slice uses deterministic fixture extraction/judging and synthetic issues.
- Live-model quality, labelled retrieval quality, production latency, and cost remain NOT_MEASURED.

Failures: **0**
