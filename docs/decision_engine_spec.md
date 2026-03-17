# Regional Decision Engine Spec

## Scope

This document describes the currently implemented regional decision layer in:

- `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_forecast.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/api/forecast.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_decision_engine.py`

The engine is a deterministic, audit-ready rule layer that maps regional forecast output to one of three operational stages:

- `Watch`
- `Prepare`
- `Activate`

This step does not include truth-layer gating or media allocation logic.

## Source Of Truth

The operational rule contract is now explicit in `RegionalDecisionRuleConfig` inside:

- `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_contracts.py`

The runtime defaults and virus-specific overrides are instantiated in:

- `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine.py`

Direct unit coverage for the rule engine lives in:

- `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_decision_engine.py`

## Integration Points

The decision engine is called directly from `RegionalForecastService.predict_all_regions(...)`.

Per region, the forecast service first builds a prediction payload with calibrated event probability, prediction interval, current incidence, quality gate metadata, and contextual fields. It then calls:

```python
self.decision_engine.evaluate(
    virus_typ=virus_typ,
    prediction=prediction,
    feature_row=row.to_dict(),
    metadata={"aggregate_metrics": metadata.get("aggregate_metrics") or {}},
)
```

The resulting decision object is attached to every region in the response as:

- `decision`
- `decision_label`
- `priority_score`
- `reason_trace`
- `uncertainty_summary`
- `decision_rank`

The regional forecast payload also exposes:

- `decision_policy_version`
- `decision_summary`
- `top_decisions`

The same enriched payload is returned by:

- `GET /api/v1/forecast/regional`
- `GET /api/v1/forecast/regional/predict`
- `GET /api/v1/forecast/regional/decisions`

## Inputs Used By The Engine

### Forecast inputs

From the per-region prediction object:

- `event_probability_calibrated`
- `prediction_interval.lower`
- `prediction_interval.upper`
- `expected_next_week_incidence`
- `current_known_incidence`
- `quality_gate`
- `activation_policy`
- `action_threshold`
- `horizon_days`

From regional aggregate metadata:

- `aggregate_metrics.ece`
- `aggregate_metrics.brier_score`
- `aggregate_metrics.pr_auc`

### Feature-row inputs

The engine reads already available feature columns from the inference panel, especially:

- `*_freshness_days`
- `*_revision_risk`
- `*_usable_confidence`
- `*_coverage_ratio`
- trend features such as `ww_acceleration7d`, `survstat_momentum_2w`, `grippeweb_are_momentum_1w`

The source prefixes are virus-specific. For example:

- default: `ww_level`, `survstat_current_incidence`, `grippeweb_are`, `grippeweb_ili`
- influenza: default plus `ifsg_influenza`
- RSV: default plus `ifsg_rsv`
- SARS-CoV-2: default plus `sars_are`, `sars_notaufnahme`, `sars_trends`

## Decision Logic

The implemented engine computes six normalized component scores:

1. `event_probability`
2. `forecast_confidence`
3. `source_freshness`
4. `revision_safety`
5. `trend_acceleration`
6. `cross_source_agreement`

These are combined into a weighted `decision_score`.

### 1. Event probability

`event_probability` is the calibrated regional outbreak probability from the forecast model, clamped to `[0, 1]`.

### 2. Forecast confidence

`forecast_confidence` is the mean of:

- interval tightness derived from prediction interval width
- calibration quality if available via `ece`
- probabilistic quality if available via `brier_score`
- ranking quality if available via `pr_auc`
- quality gate factor: `1.0` if the regional quality gate passes, otherwise `0.55`
- live data usability factor from freshness, usable-share and coverage

### 3. Source freshness

For the configured primary source prefixes, the engine computes a freshness score from `*_freshness_days` relative to the configured maximum staleness per source. The score is averaged across the available primary sources.

### 4. Revision safety

`revision_safety = 1 - revision_risk`, where `revision_risk` is the average of the available `*_revision_risk` values across primary sources.

### 5. Trend acceleration

The engine uses acceleration features already present in the panel:

- `ww_acceleration7d`
- `national_ww_acceleration7d`
- `sars_trends_acceleration_7d`

If multiple signals exist, the first is primary and the rest are blended in with a 70/30 weighting. For `SARS-CoV-2`, a small positive adjustment is added when secondary acceleration signals exist.

### 6. Cross-source agreement

The engine reads virus-specific directional trend features and checks whether they point up, down or flat using the configured neutral band.

If fewer than two directional source signals are available, agreement is treated as low-evidence:

- a single positive signal yields neutral support
- a single negative signal yields no upward support
- no directional signal yields no support

If at least two directional signals are present, the engine uses the dominant direction share as agreement strength. Only upward alignment contributes positive support toward `Prepare` or `Activate`.

## Stage Assignment

The engine first determines a raw `signal_stage`:

- `activate`
- `prepare`
- `watch`

`Activate` requires all configured activate thresholds to pass at once:

- decision score
- event probability
- forecast confidence
- freshness
- revision risk maximum
- trend acceleration
- agreement support, unless there are too few directional signals to enforce agreement

`Prepare` uses the same pattern with lower thresholds.

All threshold comparisons are inclusive:

- `>=` for score, probability, confidence, freshness, trend and agreement support
- `<=` for revision risk

If neither set passes, the region is classified as `watch`.

## Policy Overlay

After raw signal classification, the engine applies an explicit policy layer:

- If `activation_policy == "watch_only"`, any non-watch stage is downgraded to `watch`.
- If `quality_gate.overall_passed` is false, any non-watch stage is downgraded to `watch`.

The final operational output is stored as `decision.stage`, while the raw pre-policy result remains available as `decision.signal_stage`.

This distinction is directly tested so threshold tuning can change rule values without hiding policy downgrades.

## Output Contract

The engine returns a typed `RegionalDecision` object with at least:

- `signal_stage`
- `stage`
- `decision_score`
- `event_probability`
- `forecast_confidence`
- `source_freshness_score`
- `source_freshness_days`
- `source_revision_risk`
- `trend_acceleration_score`
- `cross_source_agreement_score`
- `usable_source_share`
- `source_coverage_score`
- `explanation_summary`
- `uncertainty_summary`
- `components`
- `thresholds`
- `reason_trace`
- `metadata`

The API additionally exposes convenience fields:

- `decision_label`: title-cased final stage
- `priority_score`: identical to `decision_score`
- `reason_trace`
- `uncertainty_summary`
- `decision_rank`

## Reason Trace And Auditability

Every decision includes a structured `reason_trace`:

- `why`: positive rule justifications
- `contributing_signals`: top weighted component contributions
- `uncertainty`: remaining weaknesses or ambiguity
- `policy_overrides`: explicit post-rule downgrades

This keeps the operational recommendation explainable without relying on non-deterministic logic.

## Compact Uncertainty Thresholds

The engine also emits a compact `uncertainty_summary`. These thresholds are now explicit configuration fields rather than scattered inline constants:

- `failed_quality_gate_confidence_factor`
- `uncertainty_revision_risk_threshold`
- `uncertainty_freshness_threshold`
- `min_agreement_signal_count`

They affect summary wording and confidence interpretation, but they do not replace the main stage thresholds above.

## Direct Test Coverage

The dedicated engine suite covers the critical operational behaviors directly:

- `Watch`, `Prepare`, `Activate`
- low-confidence and sparse-data handling
- quality-gate downgrade
- `watch_only` activation-policy downgrade
- `signal_stage` versus final `stage`
- reason-trace and uncertainty payload presence
- inclusive threshold-boundary behavior
- SARS-specific stricter config selection

## Ranking In Forecast Output

The regional forecast response keeps the original probability-based `rank`, but also adds a decision-centric `decision_rank`.

`decision_rank` is sorted by:

1. stage priority: `activate > prepare > watch`
2. `priority_score`
3. `event_probability_calibrated`
4. `change_pct`

This allows dashboards to prioritize operational actions without changing the core forecast payload shape.
