# Operational Thresholds

## Source Of Truth

The currently active thresholds and weights are centralized in:

- `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine.py`

The typed config contract lives in:

- `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_contracts.py`

There are two implemented rule configs today:

- `regional_decision_v1` as the default
- `regional_decision_sars_v1` for `SARS-CoV-2`

Dedicated direct rule coverage lives in:

- `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_decision_engine.py`

## Weighted Score Components

The decision score is a weighted sum of six normalized components.

| Component | Weight |
| --- | ---: |
| `event_probability` | 0.32 |
| `forecast_confidence` | 0.20 |
| `source_freshness` | 0.16 |
| `revision_safety` | 0.12 |
| `trend_acceleration` | 0.12 |
| `cross_source_agreement` | 0.08 |

## Default Thresholds

These thresholds apply to all viruses unless a virus-specific override exists.

| Threshold | Prepare | Activate |
| --- | ---: | ---: |
| event probability | 0.50, with dynamic override described below | 0.65, with dynamic override described below |
| decision score | 0.54 | 0.72 |
| forecast confidence | 0.48 | 0.62 |
| source freshness score | 0.42 | 0.58 |
| max revision risk | 0.70 | 0.45 |
| cross-source agreement support | 0.45 | 0.60 |
| trend acceleration score | 0.45 | 0.58 |

## Dynamic Probability Threshold

The probability threshold is not purely static.

At runtime the engine computes:

```text
activate_probability = max(action_threshold, config.activate_probability_threshold)
prepare_probability = min(
    activate_probability - config.prepare_probability_margin,
    config.prepare_probability_threshold,
)
```

This means:

- `Activate` can become stricter if the forecast metadata carries a higher `action_threshold`
- `Prepare` stays below `Activate` by 0.08, but is capped by the configured prepare threshold

In the current regional forecast integration, `action_threshold` comes from model metadata and defaults to `0.6` if absent.

Current margin:

| Parameter | Value |
| --- | ---: |
| `prepare_probability_margin` | 0.08 |

## SARS-CoV-2 Overrides

`SARS-CoV-2` uses `regional_decision_sars_v1`, which keeps the same weights but raises some thresholds:

| Threshold | Prepare | Activate |
| --- | ---: | ---: |
| event probability | 0.52, before dynamic override | 0.68, before dynamic override |
| decision score | 0.56 | 0.74 |
| forecast confidence | 0.50 | 0.64 |
| source freshness score | 0.42 | 0.58 |
| max revision risk | 0.70 | 0.45 |
| cross-source agreement support | 0.48 | 0.62 |
| trend acceleration score | 0.45 | 0.58 |

## Agreement And Trend Parameters

These additional parameters affect interpretation of source trends:

| Parameter | Value |
| --- | ---: |
| agreement neutral band | 0.03 |
| minimum directional signals for enforced agreement | 2 |
| acceleration reference | 0.8 |
| failed quality-gate confidence factor | 0.55 |
| uncertainty revision-risk threshold | 0.45 |
| uncertainty freshness threshold | 0.50 |

Operational consequence:

- fewer than 2 directional signals means agreement is considered low-evidence
- a single upward signal is treated as neutral support rather than strong confirmation
- a single downward signal blocks positive agreement support
- a failed quality gate directly drags forecast confidence down before stage assignment
- compact uncertainty summaries use their own explicit thresholds without changing the main stage gates

## Policy Downgrades

After raw stage assignment, the engine applies two hard operational downgrade rules:

1. `activation_policy == "watch_only"` forces the final stage to `Prepare`
2. `quality_gate.overall_passed == false` forces the final stage to `Prepare`

These downgrades keep the region visible for operational preparation, but they block paid budget release until `Activate` is allowed. They are surfaced in `reason_trace.policy_overrides`.

## Low-Confidence And Low-Data Handling

Uncertainty is explicitly surfaced when any of the following are true:

- forecast confidence is below the prepare threshold
- source freshness is below the prepare threshold
- revision risk exceeds the activate or prepare risk caps
- fewer than two directional source signals are available
- cross-source agreement is not upward
- the quality gate is not passed

The compact API field `uncertainty_summary` is generated from those conditions.

## Boundary Semantics

The main decision thresholds are inclusive:

- exact threshold hits still count as passing
- only values below a prepare threshold, or above a revision-risk maximum, drop the raw signal to `watch`

This behavior is locked by direct engine tests.

## Current Priority Ordering

When the forecast service builds `top_decisions`, regions are ranked by:

1. final stage precedence: `activate > prepare > watch`
2. `priority_score`
3. `event_probability_calibrated`
4. `change_pct`

This ordering is separate from the original probability-only forecast rank.

## Current Source Prefixes Used For Decision Quality

The engine evaluates freshness, revision risk, coverage and usability over these primary prefixes:

- default: `ww_level`, `survstat_current_incidence`, `grippeweb_are`, `grippeweb_ili`
- influenza: default plus `ifsg_influenza`
- RSV: default plus `ifsg_rsv`
- SARS-CoV-2: default plus `sars_are`, `sars_notaufnahme`, `sars_trends`

Those mappings are currently encoded in `PRIMARY_SOURCE_PREFIXES` and `SOURCE_PREFIX_TO_CONFIG`.

## Typical Output Semantics

- `Watch`: the signal is not yet strong or reliable enough for preparation or activation
- `Prepare`: early-warning stage for operational preparation only; no paid budget release
- `Activate`: strong signal that can release budget if business and quality gates are open

The API exposes the final stage as `decision.stage` and as the convenience label `decision_label`.
