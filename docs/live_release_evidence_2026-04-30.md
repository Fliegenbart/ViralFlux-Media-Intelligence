# Live Release Evidence 2026-04-30

## Purpose

This document records the accepted live state for `v1.2a Operational Readiness`
and the controlled `v1.3` research backtest kickoff.

The important separation is:

```text
Operational Readiness != Scientific Validation != Budget Permission
```

## Release identity

- Date: 2026-04-30
- Branch: `main`
- Live commit: `168900a60955dac70ee17dec7d9c484953903d54`
- Git tag: `v1.2a-layered-operational-readiness`
- Deployment host: `fluxengine.labpulse.ai`

## v1.2a accepted state

Live `/health/ready` returned:

```json
{
  "status": "healthy",
  "readiness_mode": "layered_operational_v1",
  "operational_status": "healthy",
  "science_status": "review",
  "forecast_monitoring_status": "warning",
  "budget_status": "diagnostic_only"
}
```

Public readiness stayed redacted:

- no public `components`
- no public `startup`
- no public raw `blockers`
- generic public reasons only:
  - `science_validation_requires_review`
  - `forecast_monitoring_warnings_present`

## Live checks

- `GET /health/live` -> `200`, `status=alive`
- `GET /health/ready` -> `200`, `status=healthy`
- `GET /cockpit` -> `200`
- Release smoke status: `pass`
- Login smoke: `pass`
- Regional forecast smoke: `pass`
- Regional allocation smoke: `pass`
- Campaign recommendations smoke: `pass`

## Known warnings

These warnings are visible but do not make the system operationally unhealthy:

- Influenza A h7 ECE/calibration review
- SARS-CoV-2 forecast monitoring drift
- RSV A forecast monitoring drift
- AMELAG evidence remains diagnostic-only and not budget-effective

## v1.3 research backtest kickoff

The live `virus_wave_backtest` path was exercised in product-safe mode:

- mode: `historical_cutoff`
- backtest safe: `true`
- evidence mode: `diagnostic_only`
- budget can change: `false`

Canonical scope report:

- output: `/app/data/processed/virus_wave_backtest_evaluation_report.md`
- scope mode: `canonical`
- scopes: 8 season windows
- go_for_simulation: 0
- review: 5
- no_go: 3

Legacy acceptance scope report:

- output: `/app/data/processed/virus_wave_backtest_evaluation_report_legacy.md`
- scope mode: `legacy`
- scopes: 11 season windows
- go_for_simulation: 0
- review: 7
- no_go: 4

## Interpretation

`v1.2a` is operationally accepted.

`v1.3` has produced research-only backtest evidence, but the result is not a
promotion signal yet. No Forecast Quality, Viral Pressure, Media Allocation,
Budget Gate or `global_status` behavior was changed.

