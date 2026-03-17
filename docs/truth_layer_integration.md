# Truth Layer Integration

## Purpose

This document describes the current integration of the optional commercial truth/outcome layer into the regional operational path.

Relevant files:

- `/Users/davidwegener/Desktop/viralflux/backend/app/services/media/truth_layer_service.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/services/media/truth_layer_contracts.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_forecast.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_truth_layer_service.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_forecast_service.py`

## Separation Of Concerns

The integration deliberately keeps two truth concepts separate:

- forecast truth:
  epidemiological target construction, forecast quality, backtests and the regional decision engine
- outcome truth:
  commercial response signals such as spend, visits, sales, orders, revenue or lift evidence

The Truth Layer does not replace the regional decision engine.

It is applied only as an additional commercial validation overlay in:

- media allocation output
- portfolio output

This keeps `decision.stage`, `decision.signal_stage`, `decision_score` and the epidemiological explanation path unchanged.

## Integration Point

The canonical regional path stays:

`predict_all_regions() -> decision output -> allocation / portfolio`

The Truth Layer is attached after the epidemiological output already exists.

Current implementation in `RegionalForecastService`:

- `generate_media_allocation(...)`
- `generate_media_activation(...)`
- `build_portfolio_view(...)`

For each regional scope, the service now evaluates an optional truth overlay across:

- `region_code`
- one or more mapped products
- a rolling commercial lookback window ending at the target week

## Scope And Time Window

The current truth integration uses:

- `lookback_weeks = 26`
- `window_start = target_week_start - 26 weeks`
- `window_end = target_week_start + 6 days`

This window is intentionally commercial and historical. It is not a forecast target definition.

## Signal Context Passed Into Truth

The Truth Layer receives a compact signal context derived from the existing regional output:

- `decision_stage` or `decision_label`
- `event_probability_calibrated`
- `decision.forecast_confidence` when available
- allocation confidence when available
- derived `signal_present`

This lets the outcome layer evaluate whether historical commercial response supports the currently observed epidemiological signal, without changing the signal itself.

## New Operational Fields

### Allocation recommendations

Each recommendation now exposes:

- `truth_layer_enabled`
- `truth_scope`
- `outcome_readiness`
- `evidence_status`
- `evidence_confidence`
- `signal_outcome_agreement`
- `spend_gate_status`
- `budget_release_recommendation`
- `commercial_gate`
- `truth_assessments`

### Portfolio opportunities

Each portfolio opportunity now exposes the same truth overlay fields:

- `truth_layer_enabled`
- `truth_scope`
- `outcome_readiness`
- `evidence_status`
- `evidence_confidence`
- `signal_outcome_agreement`
- `spend_gate_status`
- `budget_release_recommendation`
- `commercial_gate`
- `truth_assessments`

### Top-level rollup

Allocation and portfolio responses now also expose a compact truth rollup:

- `truth_layer.enabled`
- `truth_layer.lookback_weeks`
- `truth_layer.scopes_evaluated`
- `truth_layer.evidence_status_counts`
- `truth_layer.spend_gate_status_counts`
- `truth_layer.budget_release_recommendation_counts`

## Spend Gate Semantics

The new commercial fields are intentionally separate from the existing epidemiological and business gates.

Current mapping:

- `released` / `release`
  operational action is active and the truth layer is commercially validated
- `guarded_release` / `limited_release`
  operational action is active and the truth layer is supportive, but not fully validated
- `manual_review_required` / `manual_review`
  operational action is active, but the truth layer is only observational, explorative or missing
- `blocked_operational_gate` / `hold`
  the existing operational gate already blocks spend
- `prioritize_only` / `hold`
  portfolio priority exists, but not an operational spend release
- `not_applicable` / `hold`
  no active recommendation exists

Important rule:

- the Truth Layer influences commercial guidance
- it does not rewrite the epidemiological decision stage

## Product Handling

Where multiple products are mapped to a virus, the integration evaluates each product scope separately and exposes them in `truth_assessments`.

The top-level commercial fields on a recommendation currently use the first product in the mapped list as the primary product for dashboard simplicity.

This keeps the payload compact while preserving product-level detail for later expansion.

## Optional Behavior And Fallbacks

The Truth Layer remains optional.

If no database session is available:

- `truth_layer_enabled = false`
- a synthetic `no_truth` assessment is returned
- the system keeps running

If a database session exists but the requested region/product/window has no outcome data:

- `evidence_status = "no_truth"`
- `outcome_readiness.status = "missing"`
- `signal_outcome_agreement.status = "no_outcome_support"` if a signal exists
- operational forecasts and allocation still render normally

If truth evaluation raises an error:

- the exception is logged
- the service falls back to a synthetic `no_truth` assessment for that scope

There is no silent skip.

## What This Layer Does Not Do

This integration intentionally does not:

- alter `predict_all_regions(...)` decision scoring
- modify the regional decision thresholds
- merge commercial outcomes into epidemiological model training
- claim causal lift from simple observational outcome history
- replace the existing business gate / truth readiness summary

## Test Coverage

Direct truth service behavior remains covered in:

- `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_truth_layer_service.py`

Operational integration behavior is covered in:

- `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_forecast_service.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_forecast_api.py`

The integration tests cover:

- truth-backed allocation release guidance
- stable behavior when no scoped truth data exists
- portfolio exposure of the commercial overlay
- API passthrough of the new truth fields
