# ViralFlux Repo Memory

## Purpose

ViralFlux exists to detect regional virus waves early enough to create a media lead.
The core question is:

`Which virus is likely to accelerate in which Bundesland in the next 3-7 days, and is the signal strong enough to justify action?`

The system is split into two layers:

1. Epidemiology layer
Predict future regional SurvStat wave behavior from AMELAG, SurvStat history, and contextual signals.

2. Activation layer
Decide whether any product, channel, or budget action is justified.
This layer must stay separate from the epidemiological forecast.

## Repo Map

- `backend/app/services/ml`
  Regional forecasting, training, backtests, portfolio logic, quality gates.
- `backend/app/services/data_ingest`
  Source imports, source-specific availability handling, raw signal updates.
- `backend/app/api`
  Public contracts for forecast, media, admin, and ingest workflows.
- `frontend/src/components/cockpit`
  Decision cockpit and wave/portfolio interpretation UI.
- `scripts`
  Deployment and operational entrypoints.
- `docs`
  Progressive context and longer-lived technical truth.

## Non-Negotiables

- No leakage:
  Features must only use data available at `as_of_date`.
- SurvStat is truth:
  AMELAG and other sources are lead indicators, not the primary target.
- Keep the two-stage design:
  Forecast quality and business activation readiness must remain separate.
- Virus models stay separate:
  Cross-virus signals are allowed, mixed targets are not.
- Shadow means shadow:
  `watch_only` or failed business validation must never silently allocate budget.
- Deploy only through the documented scripts:
  no ad hoc prod edits in the live checkout.

## Default Workflows

- Regional ML changes:
  update tests, run targeted backend pytest, keep manifests and payloads aligned.
- Cockpit changes:
  keep wording semantically correct, make freshness explicit, run targeted UI checks and build.
- Source onboarding:
  document `available_time` or explicit publication lag before using a new signal in the panel.
- Live deploy:
  use `scripts/deploy-live.sh`, then verify `/health` and the affected UI/API path.

## Key Commands

- Backend targeted checks:
  `CI=true ./.venv-backend311/bin/pytest backend/app/tests/test_regional_panel_math.py backend/app/tests/test_regional_forecast_service.py -q`
- Broader backend contract checks:
  `CI=true ./.venv-backend311/bin/pytest backend/app/tests/test_regional_experiments.py backend/app/tests/test_admin_ml_api.py backend/app/tests/test_ml_training_task_contract.py -q`
- Frontend cockpit build:
  `cd frontend && npm run build`
- Production deploy:
  `./scripts/deploy-live.sh`

## Where Truth Lives

- Architecture:
  [ARCHITECTURE.md](/Users/davidwegener/Desktop/viralflux/ARCHITECTURE.md)
- Production deploy:
  [DEPLOY.md](/Users/davidwegener/Desktop/viralflux/DEPLOY.md)
- Progressive context index:
  [docs/README.md](/Users/davidwegener/Desktop/viralflux/docs/README.md)
- Module-specific danger zones:
  local `CLAUDE.md` files in critical directories
- Reusable repo workflows:
  `.claude/skills/`

