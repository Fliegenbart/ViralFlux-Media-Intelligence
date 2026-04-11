# Nowcast / Revision Layer

## Scope

This document describes the implemented nowcast and revision layer in:

- `backend/app/services/ml/nowcast_revision.py`
- `backend/app/services/ml/nowcast_contracts.py`
- `backend/app/services/ml/regional_features.py`
- `backend/app/models/database.py`
- `backend/alembic/versions/c3f2a1b4d5e6_add_source_nowcast_snapshots.py`

The goal of the layer is practical and transparent:

- quantify how fresh a source observation is
- estimate whether recent values are still revision-prone
- optionally inflate raw values when the source is known to be incomplete early
- decide whether the observation is usable for forecasting
- expose the result as explicit feature columns in the regional panel

This is not a statistical nowcasting model. It is a deterministic heuristic layer that makes source timing and revision behavior explicit.

## Main Contracts

### Input

The runtime input contract is `NowcastObservation`:

- `source_id`
- `signal_id`
- `region_code`
- `reference_date`
- `as_of_date`
- `raw_value`
- `effective_available_time`
- `timing_provenance`
- `coverage_ratio`
- `metadata`

The frame-based adapter `evaluate_frame(...)` derives that observation from a pandas frame and is the normal bridge from source data into the regional feature builder.

### Output

The runtime output contract is `NowcastResult`:

- `raw_observed_value`
- `revision_adjusted_value`
- `revision_risk_score`
- `source_freshness_days`
- `usable_confidence_score`
- `usable_for_forecast`
- `coverage_ratio`
- `correction_applied`
- `metadata`

Important semantic rule:

- `raw_observed_value` is what was actually visible at `as_of_date`
- `revision_adjusted_value` is only different when the source config has `correction_enabled=True` and the observation is still inside its configured revision window

## Source Configs

Every source uses an explicit `NowcastSourceConfig` in `NOWCAST_SOURCE_CONFIGS`.

Per source, the config defines:

- whether early values are corrected
- how long revisions matter
- which revision buckets apply
- how quickly stale data should be penalized
- the confidence threshold required for forecast usability
- the expected publication cadence
- the snapshot lookback used for append-only capture

This means the layer does not silently treat all sources the same. `survstat_kreis`, `grippeweb`, `ifsg_*` and similar weekly feeds are revision-aware. `wastewater`, `weather`, `google_trends`, `pollen` and `notaufnahme` are treated as raw-only sources.

## Scoring Method

Given a `NowcastObservation`, the layer computes:

### 1. Age and freshness

- `age_days = as_of_date - reference_date`
- `freshness_days = as_of_date - effective_available_time`

`freshness_score` is linear:

- `1.0` when the source is fully fresh
- decreases toward `0.0` as `freshness_days` approaches `max_staleness_days`
- clamps at `0.0` beyond the staleness limit

### 2. Revision bucket

If the source has `correction_enabled=True` and `age_days` is still inside `revision_window_days`, the layer selects the first matching `RevisionBucket`:

- `max_age_days`
- `completeness_factor`
- `revision_risk`

If no bucket applies:

- `completeness_factor = 1.0`
- `revision_risk = 0.0`
- no correction is applied

### 3. Revision-adjusted value

If correction is active:

`revision_adjusted_value = raw_value / completeness_factor`

Otherwise:

`revision_adjusted_value = raw_value`

The result is clamped at `>= 0.0`.

### 4. Usable confidence

The layer computes:

`usable_confidence_score = coverage_ratio * freshness_score * (1 - revision_risk)`

An observation is `usable_for_forecast=True` only if:

- `usable_confidence_score >= confidence_threshold`
- `freshness_days <= max_staleness_days`

This makes low coverage, stale data and high revision risk visible in one compact score.

## Missing Observations

Missing data is not silent.

`evaluate_missing(...)` returns a fully explicit fallback:

- values become `0.0`
- `usable_for_forecast=False`
- `coverage_ratio=0.0`
- `source_freshness_days=max_staleness_days`
- `revision_risk_score=1.0` for revision-aware sources
- `revision_risk_score=0.0` for raw-only sources
- `metadata.missing_observation=True`

This keeps downstream features deterministic and makes missingness auditable.

## Frame Adapter Behavior

`evaluate_frame(...)` is the main bridge from source tables into the feature stack.

It:

- drops rows whose `reference_date` lies after `as_of_date`
- also drops rows whose `available_time` lies after `as_of_date`
- picks the latest visible row
- computes `coverage_ratio` over the configured `coverage_window_days`

Coverage is:

`observed_unique_points / expected_points_from_cadence`

and then clamped to `[0, 1]`.

## Feature Stack Outputs

`RegionalFeatureBuilder._nowcast_feature_family(...)` turns a `NowcastResult` into explicit feature columns.

For a given prefix, the current feature family is:

- `{prefix}_raw`
- `{prefix}_nowcast`
- `{prefix}_revision_risk`
- `{prefix}_freshness_days`
- `{prefix}_usable_confidence`
- `{prefix}_usable`
- `{prefix}_coverage_ratio`

Examples in the regional panel:

- `survstat_current_incidence_raw`
- `survstat_current_incidence_nowcast`
- `ww_level_revision_risk`
- `grippeweb_are_freshness_days`
- `sars_trends_usable_confidence`

Operational rule:

- downstream model features can choose raw or adjusted values
- the decision layer and allocation layer consume the quality metadata such as freshness, revision risk and usable confidence

## Preferred Value Semantics

`preferred_value(result, use_revision_adjusted=...)` exists so the regional pipeline can explicitly choose between:

- raw visible value
- revision-adjusted value

Current behavior is deliberate:

- if `use_revision_adjusted=True` and `correction_applied=True`, the adjusted value is used
- otherwise the raw value is used

There is no hidden fallback that silently invents adjusted values for raw-only sources.

## Snapshot Layer

`NowcastSnapshotService` persists append-only source snapshots into `source_nowcast_snapshots`.

The table is defined in:

- `backend/app/models/database.py`

and created by:

- `backend/alembic/versions/c3f2a1b4d5e6_add_source_nowcast_snapshots.py`

Each snapshot record stores:

- `source_id`
- `signal_id`
- `region_code`
- `reference_date`
- `effective_available_time`
- `raw_value`
- `snapshot_captured_at`
- `timing_provenance`
- `metadata`

The purpose is revision auditing, not serving inference directly. The snapshots make it possible to compare what was visible at capture time versus what later became final.

## Current Limits

The layer is intentionally simple and has known boundaries:

- revision correction is bucket-based, not learned from historical revision curves
- coverage is cadence-based and does not inspect source-specific completeness beyond visible points
- missing observations currently map to zero-valued fallbacks, which is operationally convenient but not the same as a true estimate
- `usable_confidence_score` is a heuristic quality score, not a calibrated probability
- the snapshot layer is append-only and audit-oriented; it does not itself compute revision deltas over time

## Direct Test Coverage

Direct unit coverage now lives in:

- `backend/app/tests/test_nowcast_revision.py`

The suite covers:

- freshness scoring
- revision risk scoring
- usable-confidence logic
- revision-adjusted versus raw values
- source-specific config behavior
- frame visibility and coverage behavior

This is the intended production-ready guardrail for the nowcast/revision layer.
