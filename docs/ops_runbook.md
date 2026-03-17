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

- database reachable
- broker reachable or explicitly tolerated
- startup schema summary available
- national forecast monitoring snapshot loaded
- regional model inventory checked
- source freshness checked
- forecast recency checked

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
cd /Users/davidwegener/Desktop/viralflux/backend
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
cd /Users/davidwegener/Desktop/viralflux/backend
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
- review blocker list
- confirm broker availability

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
cd /Users/davidwegener/Desktop/viralflux/backend
python scripts/smoke_test_release.py \
  --base-url https://your-backend.example.com \
  --require-ready \
  --check-regional-validation
```

Interpretation:

- non-zero exit code means release should be blocked
- `health_live` must be `200`
- `health_ready` must be `200` for strict production release
- regional validation must not return a server error

## Operational Notes

- container healthchecks intentionally use `/health/live`, not `/health/ready`
- release gating should use `/health/ready` plus the smoke script
- runtime schema updates remain acceptable for local development, but not for production release
