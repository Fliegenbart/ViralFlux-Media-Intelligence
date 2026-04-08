# Wave Prediction v1

## Target Definition

Stage 1 predicts two separate targets:

- `target_regression`: regional SurvStat activity for the epidemiological week containing `t + horizon_days`
- `target_wave14`: binary label for `wave start within next 14 days`

The wave label is rule-based and configurable:

- absolute burden threshold
- seasonal z-score threshold against historical week-of-year behavior
- sustained positive growth over multiple future observations

The label is intentionally explicit instead of heuristic so that the classifier learns against a traceable event definition.

## Feature Families

The daily as-of panel is built at Bundesland level and uses only information known at prediction time.

Feature groups in v1:

- truth signal lags and rolling summaries
- wastewater lags and momentum
- symptom burden from GrippeWeb and ARE consultation
- virus-specific IfSG signal where available
- calendar and school holiday features
- observed weather and, when explicitly available as forecast, future weather context
- interpretable interactions such as `wastewater_x_humidity`
- static population metadata when available

Weekly sources are aligned by their effective availability date, not by the observation week itself. This prevents the model from learning from values that were not yet published on the as-of date.

Exogenous semantics are now explicit and machine-checkable:

- observed-only signals such as trends and pollen may only contribute up to `as_of`
- deterministic calendar signals such as school holidays may cover the future target window
- future weather context is only allowed when the row carries issue-time forecast semantics
- realized future exogenous values are forbidden

For weather forecasts there is now also a first vintage slice:

- `legacy_issue_time_only` keeps the existing small issue-time path for compatibility
- `run_timestamp_v1` selects the latest weather forecast run that was already visible at the historical `as_of`
- if a weather forecast row has no stable run/issue identity, the vintage path degrades safely instead of pretending historical reproducibility

New weather ingest batches now persist their own stable run identity:

- `forecast_run_timestamp`
- `forecast_run_id`
- `forecast_run_identity_source`
- `forecast_run_identity_quality`

This means new weather forecast rows can be grouped by the exact persisted forecast batch that was visible at the time.
Older rows without these fields stay usable on the legacy path, but should be interpreted as incomplete for vintage benchmarking.

Für den Weather-Vintage-Re-Test ist deshalb wichtig:

- aktuelle Re-Ingests verbessern nur die Coverage für neue Forecast-Fenster
- ein historischer 900-Tage-Backtest bleibt trotzdem `inconclusive`, wenn die Forecast-Runs damals nicht wirklich historisch sichtbar gespeichert wurden
- der Vergleichs-Runner berichtet deshalb jetzt getrennt `coverage_overall`, `coverage_train`, `coverage_test`, `coverage_by_fold`, `first_available_run_identity_date` und `last_available_run_identity_date`
- wenn diese Coverage im echten Backtest-Fenster zu niedrig bleibt, ist das ein Datenverfügbarkeitsproblem und kein Urteil gegen `run_timestamp_v1`

## Validation Approach

Validation uses rolling-origin / walk-forward splits only.

- training rows always come strictly before validation rows
- no shuffle split is used
- the classifier is calibrated on a time-ordered holdout taken from the tail of the training window

Reported metrics:

- regression: `MAE`, `RMSE`, safe `MAPE`
- classification: `ROC-AUC`, `PR-AUC`, `Brier`, `precision`, `recall`, `F1`
- calibration: `ECE` when calibrated probabilities exist
- operations: false alarm rate and mean lead time

## Why Probabilities Are Calibrated

Raw boosting outputs are not automatically trustworthy probabilities.

In v1, the field name is strict:

- `wave_probability` is only returned when an explicit calibration object was fitted and used
- otherwise the service returns `wave_score`

This avoids overstating model confidence and keeps the downstream API honest.

## Current Pilot Scope

As of 2026-03-16, the operational pilot scope is intentionally restricted to:

- pathogens: `Influenza A`, `SARS-CoV-2`
- start regions: `BY`, `HH`

The current error-analysis track is:

- `NW` for the pilot pathogens
- `RSV A` across evaluated regions

The detailed decision note lives in [wave_prediction_pilot_scope.md](./wave_prediction_pilot_scope.md).

## Known Limitations

- v1 is a tabular gradient-boosting baseline, not a sequence model
- the regression target is tied to weekly SurvStat truth, even though the panel is daily as-of
- optional context sources degrade safely when unavailable, but this can reduce accuracy
- demographic metadata is limited to currently available population data
- top features are global feature importances, not local explanations
- no API route is added yet; the service is callable from the backend and ready for later endpoint wrapping
