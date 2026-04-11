# Model Release Process

## Scope

This document describes how regional model artifacts move from training to operational release.

Relevant code paths:

- `backend/app/services/ml/regional_trainer.py`
- `backend/app/services/ml/regional_forecast.py`
- `backend/app/services/ops/production_readiness_service.py`
- `backend/app/services/ops/regional_operational_snapshot_store.py`
- `backend/scripts/backfill_regional_model_artifacts.py`
- `backend/scripts/recompute_operational_views.py`

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
- `quality_gate.overall_passed = true`
- `metric_semantics_version` is present and compatible with the live champion semantics
- `promotion_evidence.minimum_sample_count` is met
- `promotion_evidence.promotion_allowed = true`
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
cd backend
python scripts/backfill_regional_model_artifacts.py --horizon 3 --horizon 5 --horizon 7
```

This records an operational audit entry:

- `BACKFILL_REGIONAL_MODEL_ARTIFACTS`

Optional pre-release shadow check for the weather vintage slice:

- call the trainer with `weather_vintage_comparison=True`
- keep `weather_forecast_vintage_mode` unset if you want the current legacy mode to stay the primary training path
- review `weather_vintage_comparison` and `legacy_vs_vintage_metric_delta` before considering a broader rollout
- this is a benchmark-only comparison and not a global mode switch

Small end-to-end comparison runner:

```bash
cd backend
python scripts/run_weather_vintage_comparison.py --virus "Influenza A" --virus "SARS-CoV-2" --horizon 3 --horizon 7
```

This writes a compact JSON and Markdown report under `app/ml_models/weather_vintage_comparison/`.

Prospektiver Shadow-Betrieb für die operativ relevanten h7-Scopes:

```bash
cd backend
python scripts/run_weather_vintage_pilot_h7_shadow.py
```

Kombinierter Ops-Standardlauf für Shadow plus Health-Check:

```bash
cd backend
python scripts/run_weather_vintage_pilot_h7_ops.py
```

Dieser Lauf bleibt additiv und schreibt unter `app/ml_models/weather_vintage_prospective_shadow/`:

- `runs/<run_id>/summary.json`
- `runs/<run_id>/report.json`
- `runs/<run_id>/report.md`
- `runs/<run_id>/run_manifest.json`
- `aggregate_report.json`
- `aggregate_report.md`

Interpretation:

- der Pilot-Wrapper ist der produktionsnahe Standard-Startpunkt für regelmäßige Shadow-Läufe
- er markiert echte Regelbetriebsläufe standardmäßig als `run_purpose = scheduled_shadow`
- Smoke- oder manuelle Testläufe können explizit anders markiert werden, zum Beispiel mit `--run-purpose smoke`
- `run_timestamp_v1` bleibt experimentell; der Legacy-Standard ändert sich dadurch nicht
- `insufficient_identity`-Läufe werden archiviert, aber nicht als belastbare Vergleichsläufe gezählt
- für den operativen Takt sollte der Shadow-Lauf regelmäßig mit denselben Standard-Scopes laufen, zum Beispiel einmal pro Tag oder pro relevanten Trainingszyklus
- ein Review ist erst sinnvoll, wenn mehrere vergleichbare Shadow-Läufe vorliegen; intern nutzen wir dafür mindestens grob `6` vergleichbare Läufe pro Scope
- `review_ready` bedeutet nur: genug saubere Evidenz für eine manuelle Prüfung; es ist immer noch kein automatischer Rollout
- der echte Review-Report zählt standardmäßig nur `scheduled_shadow`-Läufe; Smoke- und manuelle Evaluationsläufe bleiben archiviert, verzerren die Review-Statistik aber nicht

Ops-taugliche Startbeispiele:

Manueller Ad-hoc-Start:

```bash
cd backend
python scripts/run_weather_vintage_pilot_h7_ops.py --run-purpose manual_eval
```

Cron-Beispiel:

```cron
15 3 * * * cd /path/to/viralflux/backend && ./.venv-backend311/bin/python scripts/run_weather_vintage_pilot_h7_ops.py >> /var/log/viralflux_weather_vintage_shadow.log 2>&1
```

Systemd-Timer-Beispiel:

Service `viralflux-weather-vintage-shadow.service`:

```ini
[Unit]
Description=ViralFlux Weather Vintage Pilot h7 Shadow

[Service]
Type=oneshot
WorkingDirectory=/path/to/viralflux/backend
ExecStart=/path/to/viralflux/.venv-backend311/bin/python scripts/run_weather_vintage_pilot_h7_ops.py
```

Timer `viralflux-weather-vintage-shadow.timer`:

```ini
[Unit]
Description=Run ViralFlux Weather Vintage Pilot h7 Shadow daily

[Timer]
OnCalendar=*-*-* 03:15:00
Persistent=true

[Install]
WantedBy=timers.target
```

Hinweise für den Betrieb:

- der taegliche Standardbefehl ist `python scripts/run_weather_vintage_pilot_h7_ops.py`
- der reine Shadow-Lauf bleibt `python scripts/run_weather_vintage_pilot_h7_shadow.py`
- der reine Health-Check bleibt `python scripts/check_weather_vintage_shadow_health.py`
- der Wrapper setzt standardmäßig `run_purpose = scheduled_shadow`
- ein Lockfile verhindert versehentliche Parallelstarts auf demselben Host
- bei Lock-Konflikt endet der Wrapper mit Exit-Code `2`
- bei sonstigen Laufzeitfehlern endet er mit Exit-Code `1`
- der kombinierte Ops-Wrapper gibt bei erfolgreichem Shadow-Lauf direkt den Exit-Code des Health-Checks weiter
- stdout und stderr sollten im Scheduler in ein Logfile oder Job-Artefakt umgeleitet werden

Monitoring-Check für den Shadow-Betrieb:

```bash
cd backend
python scripts/check_weather_vintage_shadow_health.py
```

Der Check liest die vorhandenen Archivläufe und meldet:

- `ok`: der Shadow-Betrieb läuft regelmäßig und liefert weiterhin brauchbare Vergleichsläufe
- `warning`: es gibt erste Betriebsprobleme, zum Beispiel zu viele `insufficient_identity`-Läufe oder zu lange keine brauchbaren Vergleichsläufe
- `critical`: der Shadow-Betrieb ist akut unzuverlässig, zum Beispiel weil gar keine aktuellen `scheduled_shadow`-Läufe mehr vorliegen oder der letzte Lauf komplett fehlgeschlagen ist

Für Scheduler oder Monitoring ist der Exit-Code gedacht:

- `0` = `ok`
- `1` = `warning`
- `2` = `critical`

Standardmäßig überwacht der Check nur echte `scheduled_shadow`-Läufe. Smoke- und manuelle Läufe bleiben archiviert, zählen aber nicht in die Betriebsbewertung hinein.

Warm-up-Regel:

- vor dem ersten echten `scheduled_shadow`-Lauf meldet der Health-Check bewusst `critical`
- das ist in der Bootstrap-Phase erwartbar und kein Modellproblem
- für den Alltag sollte deshalb der kombinierte Ops-Wrapper genutzt werden: erst Shadow-Lauf, dann Health-Check

CI-Schedule-Beispiel:

```bash
cd backend
./.venv-backend311/bin/python scripts/run_weather_vintage_pilot_h7_ops.py >> weather_vintage_shadow.log 2>&1
```

Alarm-Regel in einfachen Worten:

- bei Exit-Code `0` kein Alarm
- bei Exit-Code `1` beobachten und zeitnah prüfen
- bei Exit-Code `2` Alarm auslösen

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
cd backend
python scripts/recompute_operational_views.py --virus "Influenza A" --horizon 7
```

This records:

- `RECOMPUTE_OPERATIONAL_VIEWS`
- `REGIONAL_OPERATIONAL_SNAPSHOT` per virus/horizon scope

### Step 4. Smoke test the running backend

```bash
cd backend
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
- treat the rule-based fallback as invisible

The goal is a transparent release process, not a black-box MLOps layer.
