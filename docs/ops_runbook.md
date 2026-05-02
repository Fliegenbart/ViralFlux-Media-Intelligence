# Ops Runbook

## Scope

This runbook covers the operational backend path for:

- forecast
- decision
- allocation
- recommendation
- pilot reporting

It focuses on the release- and pilot-facing runtime controls added around startup, health, artifact availability and recompute workflows.

## Primary Runtime Signals

### 1. Liveness

Endpoint:

- `GET /health/live`

Meaning:

- the API process is up and answering requests

### 2. Readiness

Endpoint:

- `GET /health/ready`

Meaning:

- the system is technically deployable
- the API can serve the production core scope
- hard operational blockers are absent
- science and forecast warnings remain visible, but do not automatically block deployment

Current public readiness is layered:

- `operational_status`
- `science_status`
- `forecast_monitoring_status`
- `budget_status`

Important:

```text
Operational Readiness != Scientific Validation != Budget Permission
```

A green `/health/ready` does not mean that Forecast Quality, Viral Pressure or
budget automation are scientifically approved.

Expected v1.2a state:

```text
Operational: healthy
Science: review
Forecast Monitoring: warning
Budget: diagnostic_only
```

### 3. Startup audit trail

Startup now records a run metadata entry via `AuditLog` with action:

- `STARTUP_READINESS`

Operational scripts add:

- `BACKFILL_REGIONAL_MODEL_ARTIFACTS`
- `RECOMPUTE_OPERATIONAL_VIEWS`

## Common Failure Modes

### Database unavailable

Symptoms:

- `/health/ready` is `503`
- component `database.status=critical`

Action:

1. verify Postgres container / service is up
2. verify connection env vars
3. verify network reachability
4. retry readiness check

### Broker unavailable

Symptoms:

- `celery_broker.status=warning` or `critical`
- worker / beat healthchecks fail

Action:

1. verify Redis is up
2. verify `CELERY_BROKER_URL`
3. restart worker and beat after broker recovery

### Runtime schema gaps

Symptoms:

- startup fails in production
- readiness shows schema bootstrap warning or critical state

Meaning:

- a release depends on a missing migration or runtime-only schema patch

Action:

1. create or apply the missing Alembic migration
2. do not rely on runtime patching for production
3. restart backend after migration

### Missing regional model artifacts

Symptoms:

- `regional_operational.summary.missing_models > 0`
- validation endpoint returns `no_model`

Action:

1. run artifact backfill
2. verify horizon-specific directories exist
3. re-run readiness and smoke test

Command:

```bash
cd backend
python scripts/backfill_regional_model_artifacts.py --horizon 3 --horizon 5 --horizon 7
```

### Stale source data

Symptoms:

- `source_freshness_status=critical`
- readiness becomes unhealthy even when artifacts exist

Meaning:

- operational inputs are too old for a trustworthy pilot output

Action:

1. run ingestion / source update pipeline
2. confirm fresh wastewater rows exist
3. recompute models or operational views if new data materially changes `as_of`

### Forecast recency lag

Symptoms:

- `forecast_recency_status=critical`

Meaning:

- artifacts exist, but were trained on an older snapshot than the currently available source state

Action:

1. backfill regional artifacts
2. rerun operational recompute

Command:

```bash
cd backend
python scripts/recompute_operational_views.py --virus "Influenza A" --horizon 7
```

### Legacy transition mode still active

Symptoms:

- `artifact_transition_mode=legacy_default_window_fallback`

Meaning:

- `h7` is still backed by legacy artifacts instead of explicit horizon-specific artifacts

Action:

1. treat as a managed transition only
2. schedule explicit `h7` retraining before broad rollout
3. mention it in release communication

## Routine Checks

### Daily

- read `/health/ready`
- review `operational_status`, `science_status`, `forecast_monitoring_status` and `budget_status`
- confirm broker availability
- confirm `budget_status=diagnostic_only` unless a separate budget-release decision exists

### Before a pilot readout

1. run recompute for the relevant virus and horizon
2. call regional validation endpoint
3. call pilot reporting endpoint
4. archive the run metadata entry

### Before release

1. confirm production schema flags
2. confirm no runtime schema gaps
3. confirm no required model is missing
4. confirm smoke test passes

## Smoke Test

Run against the target environment:

```bash
cd backend
python scripts/smoke_test_release.py \
  --base-url https://your-backend.example.com \
  --virus "Influenza A" \
  --horizon 7 \
  --budget-eur 50000 \
  --top-n 3
```

Interpretation:

- non-zero exit code means release should be blocked
- `live_failed` means `/health/live` failed
- `business_smoke_failed` means Forecast / Allocation / Recommendation are not release-safe
- `ready_blocked` means the service lives, but the environment is not operationally freigegeben
- pure science warnings should not block release smoke when top-level readiness is `healthy`

## Virus Wave Backtest v1.3

The virus wave backtest is research-only. It compares SurvStat-only against
AMELAG+SurvStat variants and must never change live budget decisions.

Safe product-relevant mode:

```text
historical_cutoff
```

Manual run inside the backend container:

```bash
python - <<'PY'
from app.db.session import get_db_context
from app.services.media.cockpit.virus_wave_backtest import run_all_virus_wave_backtests

with get_db_context() as db:
    result = run_all_virus_wave_backtests(
        db,
        mode="historical_cutoff",
        scope_mode="canonical",
        seasonal_windows=True,
    )
    db.commit()
    print(result)
PY
```

Legacy acceptance scopes can be run separately when individual Influenza A/B
and RSV A checks are needed:

```bash
python - <<'PY'
from app.db.session import get_db_context
from app.services.media.cockpit.virus_wave_backtest import run_all_virus_wave_backtests

with get_db_context() as db:
    result = run_all_virus_wave_backtests(
        db,
        mode="historical_cutoff",
        scope_mode="legacy",
        seasonal_windows=True,
    )
    db.commit()
    print(result)
PY
```

Generate operator-readable reports:

```bash
python - <<'PY'
from app.db.session import get_db_context
from app.services.media.cockpit.virus_wave_backtest_report import write_virus_wave_backtest_evaluation_report

with get_db_context() as db:
    write_virus_wave_backtest_evaluation_report(db, mode="historical_cutoff", scope_mode="canonical")
    write_virus_wave_backtest_evaluation_report(
        db,
        mode="historical_cutoff",
        scope_mode="legacy",
        output_path="/app/data/processed/virus_wave_backtest_evaluation_report_legacy.md",
    )
PY
```

Required invariant:

```text
budget_can_change=false
```

## Tri-Layer Research GPU Jobs

Tri-Layer Evidence Fusion backtests are research-only. They do not change live
readiness, allocation, recommendations, or media budget permission.

Primary research route:

```text
/cockpit/tri-layer
```

Important operator copy:

```text
Early Warning is not Budget Approval.
Sales Relevance is not inferred from epidemiology alone.
Budget Permission remains blocked/shadow-only unless Sales Calibration and Budget Isolation pass.
This module does not alter live allocation or campaign recommendation outputs.
```

Snapshot check:

```bash
curl -i \
  "https://your-backend.example.com/api/v1/media/cockpit/tri-layer/snapshot?virus_typ=Influenza%20A&horizon_days=7"
```

Latest completed backtest metadata:

```bash
curl -i \
  "https://your-backend.example.com/api/v1/media/cockpit/tri-layer/backtest/latest?virus_typ=Influenza%20A&horizon_days=7"
```

This `latest` endpoint is read-only. It must not trigger backtest computation.

Start a research backtest only from a worker-backed environment:

```bash
curl -i -X POST \
  "https://your-backend.example.com/api/v1/media/cockpit/tri-layer/backtest" \
  -H "Content-Type: application/json" \
  -d '{
    "virus_typ": "Influenza A",
    "brand": "gelo",
    "horizon_days": 7,
    "start_date": "2024-10-01",
    "end_date": "2026-04-30",
    "mode": "historical_cutoff",
    "include_sales": false
  }'
```

Operational rules:

- keep `include_sales=false` unless a real brand-level sell-out source exists and is approved for research use
- if Sales is not connected, expect Sales Calibration to be `not_available`
- generated Tri-Layer reports under processed data/artifact directories must not be committed
- failed or missing artifacts should produce blocked/shadow-only research states, not live readiness changes

CPU is the default and should remain the conservative production setting:

```bash
REGIONAL_XGBOOST_DEVICE=cpu
```

Experimental GPU workers can opt in with the same runtime switch used by the
regional XGBoost stack:

```bash
REGIONAL_XGBOOST_DEVICE=cuda docker compose up worker
```

or in `.env`:

```bash
REGIONAL_XGBOOST_DEVICE=cuda
```

Multi-GPU hosts may pin a worker to one CUDA device:

```bash
REGIONAL_XGBOOST_DEVICE=cuda:0
```

The Tri-Layer research code reuses `resolve_xgboost_runtime_config`, so CUDA
adds `device="cuda"` or `device="cuda:<index>"` and keeps
`tree_method="hist"`. CI and local development do not require NVIDIA runtime;
leave the variable unset or set to `cpu`.

Production-conservative operating rule:

```text
Do not enable GPU on request-serving web containers for Tri-Layer experiments.
Run heavy Tri-Layer backtests only as Celery research jobs, and keep
budget_can_change=false unless a future explicit sales+isolation validation
gate is approved.
```

## Operational Notes

- container healthchecks intentionally use `/health/live`, not `/health/ready`
- release gating should use `/health/ready` plus the smoke script
- runtime schema updates remain acceptable for local development, but not for production release
