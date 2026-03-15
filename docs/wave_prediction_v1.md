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

## Known Limitations

- v1 is a tabular gradient-boosting baseline, not a sequence model
- the regression target is tied to weekly SurvStat truth, even though the panel is daily as-of
- optional context sources degrade safely when unavailable, but this can reduce accuracy
- demographic metadata is limited to currently available population data
- top features are global feature importances, not local explanations
- no API route is added yet; the service is callable from the backend and ready for later endpoint wrapping
