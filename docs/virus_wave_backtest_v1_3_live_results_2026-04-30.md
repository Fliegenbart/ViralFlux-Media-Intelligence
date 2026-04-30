# Virus Wave Backtest v1.3 Live Results 2026-04-30

## Scope

This document summarizes the first controlled live `v1.3` research backtest run.

The run is diagnostic only:

```text
budget_can_change=false
can_change_budget=false
no direct budget impact
```

## Method

- Product-safe mode: `historical_cutoff`
- Leakage guard: AMELAG `vorhersage` is not used in `historical_cutoff`
- Compared models:
  - `survstat_only`
  - `amelag_only`
  - `static_amelag_survstat_combo`
  - `evidence_v1_1_quality_weighted`
- Primary comparison: `evidence_v1_1_quality_weighted` vs `survstat_only`

## Canonical report

- Server path: `/app/data/processed/virus_wave_backtest_evaluation_report.md`
- Scope mode: `canonical`
- Pathogens:
  - `Influenza A+B`
  - `RSV`
  - `SARS-CoV-2`

Summary:

| Recommendation | Count |
|---|---:|
| go_for_simulation | 0 |
| review | 5 |
| no_go | 3 |

Notable result:

- There is no immediate candidate for simulation promotion.
- Several windows show timing gains but with phase accuracy tradeoffs.

## Legacy acceptance report

- Server path: `/app/data/processed/virus_wave_backtest_evaluation_report_legacy.md`
- Scope mode: `legacy`
- Pathogens:
  - `Influenza A`
  - `Influenza B`
  - `RSV A`
  - `SARS-CoV-2`

Summary:

| Recommendation | Count |
|---|---:|
| go_for_simulation | 0 |
| review | 7 |
| no_go | 4 |

Pathogen-season overview:

| Pathogen | Season | Recommendation | Onset Gain | Peak Gain | Phase Delta | Key Warning |
|---|---|---:|---:|---:|---:|---|
| Influenza A | 2023_2024 | review | 0.0 | 5.0 | -0.019231 | subtype clinical anchor review |
| Influenza A | 2024_2025 | no_go | 26.0 | 138.0 | -0.415094 | phase accuracy worse |
| Influenza A | 2025_2026 | no_go | 0.0 | 26.0 | -0.119048 | phase accuracy worse |
| Influenza B | 2023_2024 | review | 0.0 | 0.0 | 0.0 | subtype clinical anchor review |
| Influenza B | 2024_2025 | no_go | 26.0 | 138.0 | -0.415094 | phase accuracy worse |
| Influenza B | 2025_2026 | review | 0.0 | 0.0 | 0.0 | subtype clinical anchor review |
| RSV A | 2024_2025 | review | 0.0 | 0.0 | 0.0 | RSV mapping review |
| RSV A | 2025_2026 | review | 0.0 | 0.0 | 0.0 | RSV mapping review |
| SARS-CoV-2 | 2023_2024 | no_go | 0.0 | 138.0 | -0.403846 | phase accuracy worse |
| SARS-CoV-2 | 2024_2025 | review | 0.0 | 5.0 | -0.018868 | timing gain unclear |
| SARS-CoV-2 | 2025_2026 | review | 19.0 | 5.0 | -0.071429 | quality tradeoff review |

## Decision

Do not promote AMELAG+SurvStat evidence into budget-active Forecast Quality or
Viral Pressure yet.

Recommended next work:

- inspect phase accuracy degradation in high-gain windows
- confirm subtype clinical anchors for Influenza A/B
- confirm RSV A/B mapping before any RSV promotion decision
- keep `/health/ready` operationally green and keep `science_status=review`

