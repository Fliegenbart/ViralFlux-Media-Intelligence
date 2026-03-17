# Model Release Process

## Scope

This document describes how regional model artifacts move from training to operational release.

Relevant code paths:

- `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_trainer.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_forecast.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/services/ops/production_readiness_service.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/services/ops/regional_operational_snapshot_store.py`
- `/Users/davidwegener/Desktop/viralflux/backend/scripts/backfill_regional_model_artifacts.py`
- `/Users/davidwegener/Desktop/viralflux/backend/scripts/recompute_operational_views.py`

## Release Unit

The release unit is not a single generic model.

Regional artifacts are released per:

- virus
- horizon

Supported production horizons:

- `3`
- `5`
- `7`

Support is explicit per virus/horizon scope.

Current documented production exception:

- `RSV A / h3` is intentionally marked unsupported because the pooled regional panel does not currently have enough stable training rows for a production-grade h3 artifact.

Artifact path pattern:

- `backend/app/ml_models/regional_panel/<virus_slug>/horizon_<n>/`

Expected artifact bundle:

- `classifier.json`
- `regressor_median.json`
- `regressor_lower.json`
- `regressor_upper.json`
- `calibration.pkl`
- `metadata.json`
- `dataset_manifest.json`
- `point_in_time_snapshot.json`
- `backtest.json`
- `threshold_manifest.json`

## Release Preconditions

Before promotion:

- artifacts exist for the required virus/horizon combinations
- `metadata.horizon_days` matches the requested horizon
- `quality_gate` is present
- `dataset_manifest` is present
- `point_in_time_snapshot` is present
- no silent `load_error` exists

## Release Flow

### Step 1. Train or backfill

Backfill all required horizons:

Production-like path:

```bash
docker exec viralflux_celery_worker python /app/scripts/backfill_regional_model_artifacts.py --horizon 3 --horizon 5 --horizon 7
```

Local dev path:

```bash
cd /Users/davidwegener/Desktop/viralflux/backend
python scripts/backfill_regional_model_artifacts.py --horizon 3 --horizon 5 --horizon 7
```

This records an operational audit entry:

- `BACKFILL_REGIONAL_MODEL_ARTIFACTS`

### Step 2. Validate artifact inventory

Check readiness:

- `GET /health/ready`
- `GET /api/v1/forecast/regional/validation?virus_typ=Influenza%20A&brand=gelo&horizon_days=7`
- `GET /api/v1/forecast/regional/benchmark?horizon_days=7`

Required release signals:

- no missing required model
- no unsupported scope that is still being sold as supported
- no critical source freshness issue
- no critical forecast recency lag on the latest operational snapshot
- no unexpected metadata mismatch

### Step 3. Recompute operational outputs

Recompute operational layers on top of the newly available artifacts:

Production-like path:

```bash
docker exec viralflux_celery_worker python /app/scripts/recompute_operational_views.py --horizon 3 --horizon 5 --horizon 7
```

Local dev path:

```bash
cd /Users/davidwegener/Desktop/viralflux/backend
python scripts/recompute_operational_views.py --virus "Influenza A" --horizon 7
```

This records:

- `RECOMPUTE_OPERATIONAL_VIEWS`
- `REGIONAL_OPERATIONAL_SNAPSHOT` per virus/horizon scope

### Step 4. Smoke test the running backend

```bash
cd /Users/davidwegener/Desktop/viralflux/backend
python scripts/smoke_test_release.py \
  --base-url http://127.0.0.1:8000 \
  --virus "Influenza A" \
  --horizon 7 \
  --budget-eur 50000 \
  --top-n 3
```

### Step 5. Sign off

Minimum sign-off inputs:

- readiness output
- regional validation output
- benchmark output
- smoke test output
- audit entries for backfill / recompute

## Transition Mode Policy

Current explicit transition mode:

- `legacy_default_window_fallback`

Meaning:

- the system can still serve `h7` from a legacy artifact directory if no dedicated `horizon_7/` artifact exists

Policy:

- acceptable only as a documented transition
- not acceptable as a silent long-term production state
- should be removed by explicit horizon-specific retraining

## Rollback Guidance

If a new artifact release is not acceptable:

1. stop promotion
2. keep the previous artifact directory available
3. rerun readiness checks
4. recompute operational outputs against the last known good artifact set

This is intentionally simple. The current repo does not implement a separate artifact registry service or automatic promotion ring.

## What This Process Does Not Do

It does not:

- auto-promote models
- auto-publish recommendations to ad platforms
- hide degraded quality or stale data conditions
- treat legacy fallback as invisible

The goal is a transparent release process, not a black-box MLOps layer.
