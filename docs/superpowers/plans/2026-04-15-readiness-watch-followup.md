# Readiness Follow-up Briefing

Date: 2026-04-15
Audience: Codex follow-up session
Scope: `/health/ready` remains `degraded` after fixing accuracy freshness

## Current Situation

The original readiness problem was split into two different issues:

1. A monitoring freshness problem.
2. A real forecast-quality problem.

The monitoring freshness problem is now fixed.

What is already done:

- Public `/health/ready` now exposes real reasons instead of hiding them.
- Startup catch-up now replays the full missed morning pipeline after late restarts.
- Upstream wastewater ingestion was refreshed manually on live and live forecasts started writing again.
- Accuracy monitoring no longer fails because of the old fixed 14-day window.
- Accuracy logs are fresh again and now get written with `3` comparison pairs per virus.

Live commit after the latest fix:

- `f4f411d` — `fix: widen readiness accuracy windows for sparse runs`

## Verified Live State

Checked on 2026-04-15 around 16:27 CEST:

- `/health/live` is healthy.
- Core business endpoints are healthy.
- `/health/ready` is still `degraded`.

Current readiness reasons:

- `Influenza A: forecast readiness WATCH.`
- `Influenza B: forecast readiness WATCH.`
- `SARS-CoV-2: forecast readiness WATCH.`

Important:

- `accuracy freshness expired` is gone.
- The remaining blocker is now forecast quality, not stale monitoring.

## Most Important Findings

### 1. Accuracy freshness is fixed

Fresh live accuracy logs now exist again. Latest live values:

- `Influenza A`: `samples=3`, `window_days=35`, `mape=75.4`, `drift_detected=True`
- `Influenza B`: `samples=3`, `window_days=35`, `mape=30.1`, `drift_detected=False`
- `SARS-CoV-2`: `samples=3`, `window_days=35`, `mape=308.9`, `drift_detected=True`
- `RSV A`: `samples=3`, `window_days=36`, `mape=35.6`, `drift_detected=True`

### 2. The remaining `WATCH` is real

Building a fresh live monitoring snapshot currently yields:

- `Influenza A`
  - `forecast_readiness=WATCH`
  - `drift_status=warning`
  - alerts include:
    - `Accuracy-Monitoring basiert auf sehr wenigen Paaren.`
    - `MAPE-Drift ist im Accuracy-Monitoring aktiv.`
    - `Forecast-Promotion-Gate steht aktuell auf WATCH.`
    - `Gelernte Event-Wahrscheinlichkeit ist nicht ausreichend kalibriert.`
    - `Effektive Vorlaufzeit ist nicht positiv.`
- `Influenza B`
  - `forecast_readiness=WATCH`
  - `drift_status=ok`
  - alerts still include:
    - very few pairs
    - promotion gate on WATCH
    - calibration not sufficient
    - effective lead time not positive
- `SARS-CoV-2`
  - same pattern as Influenza A, with very severe drift
- `RSV A`
  - also still on warning, but it is not currently listed in public readiness reasons

### 3. The live issue is now model quality and gate policy

The current health state is not caused by:

- dead containers
- stale readiness snapshots
- missing freshness logs
- missed startup jobs

It is now caused by:

- too few recent accuracy pairs (`3` is enough to compute a fresh log, but still weak evidence)
- high forecast error / active drift for multiple viruses
- promotion gate still on `WATCH`
- insufficient event calibration
- non-positive effective lead time

## What Was Changed In Code

Files changed in the last fix:

- `backend/app/services/ml/tasks.py`
- `backend/app/tests/test_ml_tasks_accuracy.py`

Behavior change:

- `compute_forecast_accuracy_task` no longer assumes a simple recent 14-day daily window.
- It now:
  - evaluates only the live `DE / horizon 7` scope used by readiness
  - accounts for sparse and irregular forecast runs
  - ignores forecast dates that cannot yet have matching actual observations
  - expands the window far enough to collect enough real comparable forecast dates

Verification already completed locally:

- `python -m pytest backend/app/tests/test_main_security_surface.py backend/app/tests/test_startup_singleton.py backend/app/tests/test_ml_tasks_accuracy.py -q`
- result: `27 passed`

## Recommended Next Step Order

### Step 1: Inspect why the promotion gate stays on `WATCH`

This is now the highest-value next investigation.

Look at:

- `backend/app/services/ml/forecast_decision_service.py`
- `backend/app/services/ml/backtester_metrics.py`
- any code that produces `forecast_quality.promotion_gate`
- any code that produces `effective_lead_days`
- any code that produces `calibration_passed`

Goal:

- determine which exact gate fields keep `forecast_readiness` at `WATCH` for:
  - `Influenza A`
  - `Influenza B`
  - `SARS-CoV-2`

### Step 2: Decide whether the gate policy is correct

There are two different possibilities:

1. The forecast models really are not good enough yet.
2. The gate is stricter than the current pilot product actually needs.

Do not relax the gate blindly.
First measure:

- which exact gate field fails
- whether failure comes from low sample count only
- whether failure comes from drift only
- whether failure comes from calibration only
- whether failure comes from lead time only

### Step 3: Increase evidence depth

`3` pairs are enough to remove freshness expiry, but not enough for strong confidence.

Investigate whether we can safely backfill or accumulate more valid comparison points for:

- `Influenza A`
- `Influenza B`
- `SARS-CoV-2`
- `RSV A`

The next Codex should check:

- whether more historical `DE/h7` forecast dates can be reconstructed consistently
- whether missing older weekly scopes are absent because they were never produced
- whether the current backfill window should be larger than `14` days

### Step 4: Re-evaluate model quality after more evidence

After more valid pairs exist:

- rerun accuracy
- refresh monitoring snapshot
- check whether drift still holds
- check whether calibration still fails
- check whether effective lead time remains non-positive

Only then decide whether retraining or recalibration is needed.

## Concrete Live Commands

Use these commands on the live host:

```bash
ssh root@5.9.106.75
cd /opt/viralflux-media-intelligence-clean
git rev-parse HEAD
curl -s http://127.0.0.1:8000/health/ready
```

Rebuild the current live monitoring view:

```bash
docker exec virusradar_backend python - <<'PY'
from app.db.session import SessionLocal
from app.services.ml.forecast_decision_service import ForecastDecisionService

viruses = ["Influenza A", "Influenza B", "SARS-CoV-2", "RSV A"]
db = SessionLocal()
service = ForecastDecisionService(db)
for virus in viruses:
    snapshot = service.build_monitoring_snapshot(virus_typ=virus)
    print("\n" + virus)
    print(snapshot["monitoring_status"])
    print(snapshot["forecast_readiness"])
    print(snapshot["alerts"])
db.close()
PY
```

Inspect latest accuracy logs:

```bash
docker exec virusradar_backend python - <<'PY'
from app.db.session import SessionLocal
from app.models.database import ForecastAccuracyLog

db = SessionLocal()
rows = db.query(ForecastAccuracyLog).order_by(ForecastAccuracyLog.computed_at.desc()).limit(12).all()
for row in rows:
    print(row.virus_typ, row.computed_at, row.samples, row.window_days, row.mape, row.drift_detected)
db.close()
PY
```

Rerun the live monitoring chain if needed:

```bash
docker exec virusradar_backend python - <<'PY'
from app.services.ml.tasks import (
    backfill_recent_forecast_history_task,
    compute_forecast_accuracy_task,
    refresh_regional_operational_snapshots_task,
)

print(backfill_recent_forecast_history_task.apply().get())
print(compute_forecast_accuracy_task.apply().get())
print(refresh_regional_operational_snapshots_task.apply().get())
PY
```

## Success Criteria For The Next Session

The next Codex session should count as successful only if it can answer these questions clearly:

1. Which exact gate fields still force `forecast_readiness=WATCH` for each affected virus?
2. Are those gate failures caused by real model weakness or by policy thresholds?
3. Do we need more backfilled evidence, retraining, recalibration, or a gate-policy change?
4. What is the smallest honest change that can move `/health/ready` from `degraded` to healthy?

## Short Plain-English Summary

The broken monitoring pipe is fixed.

The system is still yellow because the forecasts themselves are not yet convincing enough for the readiness gate.

The next job is no longer infrastructure repair.
The next job is to inspect and improve the forecast-quality gate.
