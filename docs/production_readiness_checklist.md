# Production Readiness Checklist

## Scope

This checklist is the release gate for the operational ViralFlux stack used for customer pilot scopes.

Relevant runtime files:

- `backend/app/main.py`
- `backend/app/db/session.py`
- `backend/app/core/celery_app.py`
- `backend/app/services/ops/production_readiness_service.py`
- `backend/scripts/backfill_regional_model_artifacts.py`
- `backend/scripts/recompute_operational_views.py`
- `backend/scripts/smoke_test_release.py`

## Release Gate

The stack is only release-ready when all P1 items below are green.

### P1 Infrastructure

- Database is reachable.
- Redis / Celery broker is reachable.
- `/health/live` returns `200`.
- `/health/ready` returns `200`.
- Production startup does not rely on runtime schema mutation.

### P1 Schema and Migrations

- Required tables exist before release.
- Runtime schema gaps are empty.
- `DB_ALLOW_RUNTIME_SCHEMA_UPDATES=false` in production.
- Any warning that runtime schema updates were applied is treated as a release blocker until an explicit migration exists.

### P1 Model Availability

- Regional artifacts exist for supported horizons `3`, `5`, `7`.
- No requested production path depends on missing artifacts.
- `artifact_transition_mode` is empty for release candidates.
- If `legacy_default_window_fallback` is still present for `h7`, it must be explicitly accepted as a transition risk and documented in the release note.

### P1 Source Freshness and Forecast Recency

- Wastewater source freshness is within the configured readiness window.
- Regional point-in-time snapshot is not lagging materially behind latest available source data.
- National forecast monitoring does not report `critical`.
- Regional validation endpoints do not silently degrade into `no_model`.

### P1 Security / Config

- Production secrets are injected via environment, not hardcoded.
- Production runs with `ENVIRONMENT=production`.
- Production runs with strict startup readiness enabled.
- Allowed origins are explicitly configured.

### P1 Operational Evidence

- `BACKFILL_REGIONAL_MODEL_ARTIFACTS` runs are auditable.
- `RECOMPUTE_OPERATIONAL_VIEWS` runs are auditable.
- Startup readiness writes an audit trail entry.

## Recommended Release Sequence

1. Verify schema and migrations.
2. Backfill all required regional artifacts.
3. Recompute forecast/allocation/recommendation outputs.
4. Check `/health/ready`.
5. Run smoke test against the live backend.
6. Review regional validation and benchmark outputs.
7. Sign off release.

## Commands

### 1. Backfill regional artifacts

```bash
cd backend
python scripts/backfill_regional_model_artifacts.py --horizon 3 --horizon 5 --horizon 7
```

### 2. Recompute operational views

```bash
cd backend
python scripts/recompute_operational_views.py --virus "Influenza A" --horizon 7 --weekly-budget-eur 50000
```

### 3. Smoke test a running backend

```bash
cd backend
python scripts/smoke_test_release.py \
  --base-url http://127.0.0.1:8000 \
  --virus "Influenza A" \
  --horizon 7 \
  --budget-eur 50000 \
  --top-n 3
```

## Health Endpoint Expectations

### `/health/live`

Purpose:

- confirms the process is serving requests

Expected:

- `200`
- lightweight payload

### `/health/ready`

Purpose:

- verifies dependency availability
- verifies forecast monitoring status
- verifies regional artifact availability
- verifies source freshness
- verifies forecast recency
- exposes startup schema summary and run metadata

Expected:

- `200` for healthy or degraded-but-operational states
- `503` for unhealthy states

## Release Blockers

Do not release if any of these are true:

- database unavailable
- broker unavailable in production
- missing production tables
- runtime schema gaps remain
- missing regional model artifacts for required virus/horizon combinations
- source freshness critical
- forecast recency critical
- smoke test fails

## Sign-Off Template

Use this minimal sign-off block in the release note:

- schema verified: yes/no
- broker reachable: yes/no
- health ready: yes/no
- horizons available: 3/5/7 yes/no
- legacy fallback active: yes/no
- smoke test passed: yes/no
- release approved by engineering: yes/no
- release approved by product/ops: yes/no
