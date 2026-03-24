# Live Readiness Blockers - Current

Snapshot basis:
- Live `/health/ready` snapshot checked at `2026-03-18T06:59:11.048441`
- Live `pilot-readout` snapshot for `brand=gelo`, `virus_typ=RSV A`, `horizon_days=7` generated at `2026-03-18T07:00:18.742581`
- Server: `fluxengine.labpulse.ai`

## Executive Verdict

Strictly inside `/health/ready`, there are currently **zero hard blockers** and **two warning components**:
- `forecast_monitoring`
- `regional_operational`

That is why `/health/ready` returns `status = degraded` with HTTP `200`, not `unhealthy`.

For the **PEIX / GELO pilot specifically**, the current true blocker is **not** the platform readiness endpoint. The true blocker is the **commercial evidence gate** in the live `pilot-readout`:
- `epidemiology_status = GO`
- `commercial_data_status = NO_GO`
- `budget_release_status = WATCH`
- `scope_readiness = WATCH`

So the strict interpretation is:
- Platform status: degraded because of warning-only readiness components
- PEIX / GELO pilot status: epidemiology is usable, budget release is still blocked by missing GELO outcome truth
- this blocks **Commercial GO**, not the narrower **Forecast-First** story

## Failing Readiness Checks

| Check | Live state | Exact source | Root cause | Blocks PEIX / GELO pilot use? | Smallest corrective action | Classification |
| --- | --- | --- | --- | --- | --- | --- |
| `forecast_monitoring` | `warning` | `/health/ready -> components.forecast_monitoring`; built in `backend/app/services/ops/production_readiness_service.py` via `_forecast_monitoring_component`; per-virus status comes from `backend/app/services/ml/forecast_decision_service.py::build_monitoring_snapshot` | All four national forecast stacks are still on `monitoring_status = warning`. Common causes live now: `accuracy_freshness_status = stale`, only `samples = 3`, promotion gate still `WATCH`, and effective lead time is non-positive in the latest market backtests. Influenza A, SARS-CoV-2, and RSV A also show active drift warnings. | No. This degrades global platform readiness, but it does not block the PEIX / GELO regional RSV A / h7 pilot path. | Refresh the national forecast monitoring chain: rerun accuracy monitoring and market backtests, then review why the national promotion gates still sit on `WATCH`. | Non-blocking warning |
| `regional_operational` | `warning` | `/health/ready -> components.regional_operational`; built in `backend/app/services/ops/production_readiness_service.py` via `_regional_operational_component` and `_regional_matrix_item`; pilot contract support comes from `backend/app/services/ml/forecast_horizon_utils.py` | The matrix is warning-only because every live scope currently has `source_freshness_status = warning`. Live source data are only available up to `2026-03-06`, so on `2026-03-18` the source age is `12` days. With the current defaults in `backend/app/core/config.py` (`READINESS_SOURCE_FRESH_DAYS = 7`, `READINESS_SOURCE_WARNING_DAYS = 14`), that is a warning. Additional warning rows come from non-pilot scopes with quality-gate failures, advisory SARS coverage warnings, and one unsupported scope (`RSV A / h3`). | Not directly. The active PEIX / GELO scope `RSV A / h7` is operationally `GO` on quality and promotion, but its row still inherits the source-freshness warning. | Refresh the upstream wastewater/source ingest so `latest_available_as_of` advances back into the fresh window. Do not retune the model first. | Non-blocking warning |

## True Pilot Blocker

This blocker is not emitted as a failing `/health/ready` component, but it **does** block PEIX / GELO budget activation right now.

| Check | Live state | Exact source | Root cause | Blocks PEIX / GELO pilot use? | Smallest corrective action | Classification |
| --- | --- | --- | --- | --- | --- | --- |
| `commercial_evidence_gate` | `commercial_data_status = NO_GO`, `budget_release_status = WATCH`, `scope_readiness = WATCH` | `/api/v1/media/pilot-readout`; assembled in `backend/app/services/media/pilot_readout_service.py` via `_gate_snapshot`, `_missing_requirements`, and the scope-readiness logic; commercial validation logic lives in `backend/app/services/media/business_validation_service.py` | No GELO outcome truth is connected yet. Live missing requirements are: no commercial outcome data, no weekly media spend, no sales/orders/revenue metrics, fewer than two activation cycles, no holdout design, and no validated lift metrics. | Yes for **budget release / Commercial GO**. No for the narrower **Forecast-First** pilot story. Epidemiology is ready, commercial activation is not. | Start the real GELO outcome ingestion immediately through `POST /api/v1/media/outcomes/ingest` with weekly spend plus sales/orders/revenue and activation metadata. Full closure still requires `>= 26` weeks, `>= 2` activation cycles, explicit holdout groups, and validated lift metrics. | True commercial blocker |

## Root Cause Detail

### 1. `forecast_monitoring`

Live source:
- `/health/ready -> components.forecast_monitoring`
- `/api/v1/forecast/monitoring`

Live state:
- `summary.healthy = 0`
- `summary.warning = 4`
- `summary.critical = 0`

Current per-virus state:

| Virus | Monitoring status | Forecast readiness | Forecast freshness | Accuracy freshness | Backtest freshness |
| --- | --- | --- | --- | --- | --- |
| Influenza A | `warning` | `WATCH` | `fresh` | `stale` | `fresh` |
| Influenza B | `warning` | `WATCH` | `fresh` | `stale` | `fresh` |
| SARS-CoV-2 | `warning` | `WATCH` | `fresh` | `stale` | `fresh` |
| RSV A | `warning` | `WATCH` | `fresh` | `stale` | `fresh` |

Why the code marks this as warning:
- `build_monitoring_snapshot()` sets `warning = true` if any alerts exist, if `forecast_readiness != GO`, if accuracy freshness is stale, or if drift is active.
- Live now, all four viruses satisfy at least two of those conditions.

What matters for the pilot:
- This is a platform-wide national forecasting monitor.
- It is not the driver of the PEIX / GELO regional RSV A / h7 pilot decision.
- It should be fixed, but not ahead of the commercial truth connection.

### 2. `regional_operational`

Live source:
- `/health/ready -> components.regional_operational`

Live summary:
- `ready = 0`
- `warning = 12`
- `critical = 0`
- `unsupported = 1`
- `quality_gate_failures = 7`

Current live matrix summary:

| Scope | Pilot contract | Quality gate | Main warning reason |
| --- | --- | --- | --- |
| Influenza A / h3 | No | `WATCH` | Non-pilot scope, source freshness warning, quality failures |
| Influenza A / h5 | No | `GO` | Non-pilot scope, source freshness warning |
| Influenza A / h7 | Yes | `WATCH` | Source freshness warning plus `ece_passed` failed |
| Influenza B / h3 | No | `WATCH` | Non-pilot scope, source freshness warning, quality failures |
| Influenza B / h5 | No | `GO` | Non-pilot scope, source freshness warning |
| Influenza B / h7 | Yes | `WATCH` | Source freshness warning plus `ece_passed` failed |
| SARS-CoV-2 / h3 | No | `WATCH` | Non-pilot scope, source freshness warning, quality failures, advisory coverage warning |
| SARS-CoV-2 / h5 | No | `GO` | Non-pilot scope, source freshness warning, advisory coverage warning |
| SARS-CoV-2 / h7 | No | `WATCH` | Shadow-only scope, source freshness warning, quality failures, advisory coverage warning |
| RSV A / h3 | No | `UNSUPPORTED` | Unsupported scope by contract |
| RSV A / h5 | No | `WATCH` | Non-pilot scope, source freshness warning, quality failures |
| RSV A / h7 | Yes | `GO` | Source freshness warning only |

Current product interpretation:

- `h7` is the only actively prioritized horizon for productization and release communication.
- `h5` is paused and should not drive roadmap or release decisions.
- `h3` is reserve-only: Influenza A/B h3 are no longer treated as broken, but they are also not active release targets.

Why the code marks the component as warning:
- `_regional_matrix_item()` computes each row status as the worst of:
  - model availability
  - source freshness
  - forecast recency
  - model age
  - source coverage
  - quality gate
  - transition mode
- The live source freshness warning is enough to keep even otherwise-good scopes at `warning`.

Important nuance for PEIX / GELO:
- `RSV A / h7` is the relevant pilot scope.
- Live now it has:
  - `pilot_contract_supported = true`
  - `quality_gate.forecast_readiness = GO`
  - `quality_gate_failed_checks = []`
  - `source_coverage_required_status = ok`
  - `forecast_recency_status = ok`
  - `status = warning` only because `source_freshness_status = warning`

This means the pilot scope is not blocked by model quality anymore. It is only inheriting a platform freshness warning.

### 3. Commercial evidence gate

Live source:
- `/api/v1/media/pilot-readout?brand=gelo&virus_typ=RSV%20A&horizon_days=7&weekly_budget_eur=120000`

Current gate snapshot:
- `scope_readiness = WATCH`
- `epidemiology_status = GO`
- `commercial_data_status = NO_GO`
- `holdout_status = WATCH`
- `budget_release_status = WATCH`
- `validation_status = pending_truth_connection`

Missing requirements live now:
- `No GELO commercial outcome data is connected yet.`
- `Weekly media spend is not yet present in the GELO outcome layer.`
- `Sales, orders, or revenue metrics are still missing from the GELO outcome layer.`
- `At least two clearly labeled activation cycles are still required.`
- `A test/control or holdout design is still missing.`
- `Validated incremental lift metrics are still missing.`

Why the code blocks spend:
- `BusinessValidationService.evaluate()` only sets `validated_for_budget_activation = true` when all of these are true:
  - truth layer passes
  - at least `26` coverage weeks
  - at least `2` activation cycles
  - explicit holdout structure
  - lift metrics available
- `_overall_scope_readiness()` in `PilotReadoutService` only returns `GO` when:
  - forecast scope is `GO`
  - business validation is ready for budget activation
  - live evaluation archive is `GO`
  - retained winner is `true`

Live now, only the epidemiology half is green.

## Cosmetic / Informational Issues

These are not active blockers:

| Item | Live state | Why it is informational |
| --- | --- | --- |
| `startup.run_metadata.status = degraded` | Present inside `/health/ready -> startup.run_metadata` | This reflects the startup snapshot recorded in light mode, where deep checks were intentionally skipped (`startup_light_mode`). It is historical metadata, not an active readiness component failure. |
| `blockers = []` while status is degraded | Present at top level of `/health/ready` | This is expected. `ProductionReadinessService` only puts components with `status = critical` into `blockers`. Warning-only degradation therefore produces an empty blocker list by design. |

## Ordered Remediation Plan

1. **Connect the GELO outcome layer now.**
   This is the only current item that truly blocks PEIX / GELO budget activation.
   Smallest action: start sending real GELO batches to `POST /api/v1/media/outcomes/ingest` with weekly spend plus sales/orders/revenue and activation metadata.

2. **Refresh the upstream wastewater/source ingest.**
   This is the only current `/health/ready` warning that still touches the active pilot scope `RSV A / h7`.
   Smallest action: run or repair the source update path so `latest_available_as_of` moves back within the `<= 7` day fresh window.

3. **Refresh national monitoring artifacts, but do not prioritize this over the pilot blocker.**
   `forecast_monitoring` is warning because the older national forecast stack still has stale accuracy logs, thin sample counts, drift alerts, and WATCH-level promotion gates.
   Smallest action: rerun accuracy monitoring and market backtests for the national forecast stack, then reassess.

4. **Do not soften global readiness.**
   The current degraded state is truthful. The problem is not that readiness is too strict; the problem is that platform-wide warnings and pilot-specific commercial gating are different things.
   If product clarity is needed later, add a separate pilot-facing readiness summary without weakening `/health/ready`.

## Bottom Line

Strict blocker report:
- `/health/ready` currently has **0 critical blockers**
- `/health/ready` is degraded because of **2 warning components**
- The only **true PEIX / GELO pilot blocker** is the missing commercial truth connection and validation path

So the next move is not more model tuning. The next move is:
- connect GELO outcome ingestion
- refresh the upstream source data cadence
