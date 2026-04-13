# H7 Science Contract

This document defines the canonical mathematical contract for the current ViralFlux forecast champion.

## Scope

The active champion scope in phase 1 is limited to:

- `Influenza A / h7`
- `Influenza B / h7`
- `RSV A / h7`

`SARS-CoV-2 / h7` remains shadow/watch-only in this phase.  
`h3` and `h5` remain benchmark/debug scopes and are not active champion targets.

## Target Definition

For each `virus_typ`, `bundesland`, and `as_of_date`, the core target is:

- `Y(t+7)`: `current_known_incidence` at `as_of_date + 7 days`

The canonical operational target semantics are stored as:

- `forecast_target_semantics = current_known_incidence_at_as_of_plus_horizon_days`

## Event Definition

The forecast champion uses a separate learned event model for:

- `P(E(t+7) = 1 | F(t))`

The event definition is versioned through:

- `event_definition_version`

Phase-1 training keeps the existing virus-specific event contract and does not silently relabel heuristic scores as probabilities.

## Quantile Contract

The champion predicts the following canonical quantiles for `Y(t+7)`:

- `0.025`
- `0.1`
- `0.25`
- `0.5`
- `0.75`
- `0.9`
- `0.975`

The quantile grid is versioned through:

- `quantile_grid_version = canonical_quantile_grid_v1`

No second parallel quantile grid is allowed in the champion path.

## Feature Visibility Contract

Training and backtesting must be leakage-safe:

- only features visible at the historical `as_of` may be used
- exogenous weather features must respect vintage/run-identity semantics
- calibration must be fit on out-of-fold predictions only
- quantiles must remain monotonic

These guarantees are carried in metadata and promotion evidence via:

- `weather_vintage_discipline_passed`
- `oof_calibration_only`
- `quantile_monotonicity_passed`
- `calibration_mode`
- `calibration_evidence_mode`

## Champion Model Family

The active champion model family is:

- `regional_pooled_panel`

The old direct forecasting stack with Holt-Winters, Ridge, and Prophet remains:

- benchmark
- debug
- legacy admin path

It must not be described as the main mathematical production core.

## Promotion Rules

Promotion is decided lexicographically.

1. active champion scope
2. leakage/vintage contract passed
3. WIS improves without CRPS regression
4. coverage does not regress beyond tolerance
5. event calibration does not regress
6. operational utility does not regress

The evidence payload is versioned and stored with:

- `metric_semantics_version`
- `event_definition_version`
- `quantile_grid_version`
- `science_contract_version`
- `promotion_gate_sequence`

## Required Metrics

Every active h7 champion scope must be evaluated with:

- `WIS`
- `CRPS` approximation
- coverage `50/80/95`
- pinball loss
- `Brier`
- `ECE`
- `PR-AUC`
- operational utility metrics

## Response And Artifact Metadata

The regional probabilistic path should surface these metadata fields consistently:

- `champion_model_family`
- `metric_semantics_version`
- `event_definition_version`
- `quantile_grid_version`
- `science_contract_version`
- `forecast_quantiles`
- `calibration_mode`
- `calibration_evidence_mode`

This keeps live responses, registry entries, and monitoring snapshots on the same mathematical vocabulary.
