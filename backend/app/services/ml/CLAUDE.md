# ML Module Context

## Purpose

This module owns the epidemiological forecast layer:
regional panel features, event definitions, training, backtests, inference, portfolio ranking, and gating.

## Hidden Complexity

- `as_of_date` correctness matters more than model cleverness.
- Regional targets are future SurvStat behavior.
- AMELAG is a lead indicator, not the truth target.
- `quality_gate`, `rollout_mode`, and `activation_policy` are contract-level behavior, not display-only metadata.

## Non-Negotiables

- Never use future source values in training or inference features.
- New sources must define `available_time` or an explicit source lag.
- Backtests must remain walk-forward and leakage-safe.
- Keep epidemiological readiness and business activation readiness separate.
- For weaker lines such as SARS/RSV, preserve shadow/watch behavior unless validation truly improves.

## Default Checks

- `./.venv-backend311/bin/python -m py_compile backend/app/services/ml/regional_panel_utils.py backend/app/services/ml/regional_features.py backend/app/services/ml/regional_trainer.py backend/app/services/ml/regional_forecast.py`
- `CI=true ./.venv-backend311/bin/pytest backend/app/tests/test_regional_panel_math.py backend/app/tests/test_regional_forecast_service.py -q`
- When contracts change:
  `CI=true ./.venv-backend311/bin/pytest backend/app/tests/test_regional_experiments.py backend/app/tests/test_admin_ml_api.py backend/app/tests/test_ml_training_task_contract.py -q`

