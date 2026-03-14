# Regional Forecast Debug

## Use When

- regional scores look wrong
- quality gates changed unexpectedly
- a virus line regressed after feature or threshold changes

## Workflow

1. Inspect the affected service in `backend/app/services/ml/`.
2. Check whether the issue is feature construction, label definition, calibration, or rollout metadata.
3. Confirm `as_of_date` and source availability behavior before touching model logic.
4. Reproduce with targeted tests first, not a full retrain.
5. Keep payload contracts aligned with `regional_forecast.py`.

## Minimum Checks

- `./.venv-backend311/bin/python -m py_compile backend/app/services/ml/regional_panel_utils.py backend/app/services/ml/regional_features.py backend/app/services/ml/regional_trainer.py backend/app/services/ml/regional_forecast.py`
- `CI=true ./.venv-backend311/bin/pytest backend/app/tests/test_regional_panel_math.py backend/app/tests/test_regional_forecast_service.py -q`

