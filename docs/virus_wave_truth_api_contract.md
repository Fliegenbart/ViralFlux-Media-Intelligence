# Virus Wave Truth API Contract

`virusWaveTruth` is the first epidemiology wave-evidence block exposed by
`GET /api/v1/media/cockpit/media-spending-truth`.

## Purpose

The block turns existing SurvStat and AMELAG time series into wave diagnostics.
AMELAG is treated as the first-class early-warning, timing, trend, onset and
peak-lead signal. SurvStat remains the confirmed reporting anchor.

This block is not a standalone budget decision. In v1.1, AMELAG evidence is
diagnostic only and cannot change approved media budget recommendations.
Media spending still depends on the existing gates: forecast quality, live data
quality, baseline superiority, decision backtest, and business constraints.

## Feature Flags

```text
VIRUS_WAVE_TRUTH_ENABLED=true
VIRUS_WAVE_TRUTH_RUNTIME_MODE=true
```

`VIRUS_WAVE_TRUTH_ENABLED=false` keeps the API alive but returns a disabled
diagnostic block instead of calculating wave signals.

`VIRUS_WAVE_TRUTH_RUNTIME_MODE=false` disables live runtime calculation. It is
valid only when materialized mode has a fresh successful snapshot, or when the
caller intentionally wants a disabled/missing diagnostic response.

Materialized v1.2 read mode:

```text
VIRUS_WAVE_TRUTH_MATERIALIZED_MODE=false
VIRUS_WAVE_TRUTH_ALLOW_RUNTIME_FALLBACK=true
```

`VIRUS_WAVE_TRUTH_MATERIALIZED_MODE=true` reads the newest successful
materialized `virusWaveTruth` snapshot from the database. If no successful run
exists and `VIRUS_WAVE_TRUTH_ALLOW_RUNTIME_FALLBACK=true`, the API falls back to
the runtime v1.1 calculation. If fallback is disabled, the API returns
`status: materialized_missing`.

## Current v1.1/v1.2 Computation

The current runtime implementation reads:

```text
survstat_weekly_data
survstat_kreis_data
wastewater_aggregated
```

It computes:

```text
SurvStat phase
AMELAG phase
onset date
peak date
wave strength
1-week and 2-week growth
lead/lag days
correlation
alignment score
divergence score
AMELAG quality scores
source roles
base weights
quality multipliers
effective weights
evidence coverage
```

SurvStat is treated as the confirmed clinical reporting signal. AMELAG is
treated as the wastewater early-signal layer. Both sources are compared on
weekly aligned series.

AMELAG signal selection uses this order:

```text
vorhersage > viruslast_normalisiert > viruslast
```

`signal_mode` is `current_runtime`. `backtest_safe` is `false`, because the
runtime signal may use currently available smoothed values. v1.3 therefore
adds a separate research backtest mode for historical cutoff-safe evaluation.

## v1.7 Canonical Backtest Comparison Pairs

The product backtest defaults now use canonical comparison pairs instead of
subtype-specific AMELAG signals against broader clinical anchors:

```text
Influenza A+B -> SurvStat Influenza, saisonal
RSV           -> AMELAG RSV A+B and SurvStat RSV
SARS-CoV-2    -> AMELAG SARS-CoV-2 and SurvStat COVID-19
```

Legacy research scopes remain available for manual review:

```text
Influenza A
Influenza B
RSV A
SARS-CoV-2
```

The default backtest `scope_mode` is `canonical`. Reports can filter to
`scope_mode=canonical` so old legacy subtype runs do not mix with the current
product-facing evidence report.

## Lead/Lag Semantics

`lead_lag_days` uses this convention:

```text
negative value = AMELAG leads SurvStat
zero           = broadly synchronized
positive value = SurvStat leads AMELAG
```

Example:

```json
{
  "lead_lag_days": -7,
  "amelag_lead_days": 7,
  "status": "amelag_leads_survstat"
}
```

This means the AMELAG curve is roughly one week ahead of the SurvStat curve.

## Evidence Model

The API root stays `virusWaveTruth` for compatibility. New v1.1 semantics live
under `virusWaveTruth.evidence`.

Source roles:

```json
{
  "amelag": "early_warning_trend_signal",
  "survstat": "confirmed_reporting_signal",
  "syndromic": "planned_population_symptom_signal",
  "severity": "planned_healthcare_burden_signal"
}
```

Missing planned sources are not interpreted as low disease burden. They are
reported as `planned_unavailable` and excluded from effective weights.

Each profile separates:

```text
base_weights          = fachliche Zielgewichtung
quality_multipliers   = Datenqualitaet je Quelle
effective_weights     = normalisierte tatsaechliche Gewichtung
evidence_coverage     = Vollstaendigkeit der Evidenzlage
```

Formula:

```text
raw_effective_weight[source] =
  base_weight[source] * quality_multiplier[source] * availability[source]

effective_weight[source] =
  raw_effective_weight[source] / sum(raw_effective_weights)

evidence_coverage =
  sum(raw_effective_weights) / sum(base_weights)
```

The v1.1 base profiles are:

```json
{
  "early_warning": {
    "amelag": 0.65,
    "survstat": 0.20,
    "syndromic": 0.15,
    "severity": 0.00
  },
  "phase_detection": {
    "amelag": 0.50,
    "survstat": 0.35,
    "syndromic": 0.15,
    "severity": 0.00
  },
  "confirmed_burden": {
    "amelag": 0.15,
    "survstat": 0.45,
    "syndromic": 0.25,
    "severity": 0.15
  },
  "severity_pressure": {
    "amelag": 0.05,
    "survstat": 0.15,
    "syndromic": 0.20,
    "severity": 0.60
  }
}
```

Confidence values are heuristic in v1.1. They are therefore always marked with:

```json
{
  "confidence_method": "heuristic_v1"
}
```

## Budget Isolation

The evidence block must always expose:

```json
{
  "budget_impact": {
    "mode": "diagnostic_only",
    "can_change_budget": false,
    "reason": "awaiting_backtest_validation"
  }
}
```

This is intentional. AMELAG is now more important for diagnosis and timing, but
not yet budget-effective.

## Example v1.1 Payload

```json
{
  "schema": "virus_wave_truth_v1",
  "engine_version": "virus_wave_truth_runtime_v1_1",
  "algorithm_version": "virus-wave-evidence-runtime-v1.1",
  "scope": {
    "virus": "Influenza A",
    "region": "DE",
    "lookback_weeks": 156
  },
  "sourceStatus": {
    "survstat_points": 759456,
    "survstat_weekly_points": 60270,
    "survstat_wave_points": 155,
    "amelag_points": 913,
    "amelag_wave_points": 125,
    "wave_feature_tables_present": false,
    "computation_mode": "runtime_from_existing_timeseries"
  },
  "survstat_phase": "decline",
  "amelag_phase": "post_wave",
  "lead_lag_days": -7,
  "amelag_lead_days": 7,
  "alignment_status": "amelag_leads_survstat",
  "alignment_score": 0.759125,
  "survstat": {
    "phase": "decline",
    "onset_date": "2025-10-06",
    "peak_date": "2026-01-26",
    "confidence": 0.519028
  },
  "amelag": {
    "phase": "post_wave",
    "onset_date": "2025-11-12",
    "peak_date": "2026-01-28",
    "confidence": 0.533333
  },
  "alignment": {
    "status": "amelag_leads_survstat",
    "lead_lag_days": -7,
    "correlation": 0.86893,
    "alignment_score": 0.759125,
    "divergence_score": 0.05316
  },
  "evidence": {
    "mode": "diagnostic_only",
    "algorithm_version": "virus-wave-evidence-runtime-v1.1",
    "early_warning_signal": {
      "primary_source": "amelag",
      "phase": "post_wave",
      "confidence": 0.82,
      "confidence_method": "heuristic_v1",
      "reason": "amelag_leads_survstat"
    },
    "weight_profiles": {
      "early_warning": {
        "base_weights": {
          "amelag": 0.65,
          "survstat": 0.20,
          "syndromic": 0.15,
          "severity": 0.00
        },
        "quality_multipliers": {
          "amelag": 0.84,
          "survstat": 0.72,
          "syndromic": 0.00,
          "severity": 0.00
        },
        "effective_weights": {
          "amelag": 0.79,
          "survstat": 0.21,
          "syndromic": 0.00,
          "severity": 0.00
        },
        "evidence_coverage": 0.69,
        "missing_sources": ["syndromic", "severity"]
      }
    },
    "amelag_quality": {
      "freshness_score": 0.9,
      "coverage_score": 0.8,
      "site_count_score": 0.8,
      "uncertainty_score": 0.75,
      "lod_loq_score": 0.9,
      "cross_site_consistency_score": 0.7,
      "signal_basis": "vorhersage",
      "signal_mode": "current_runtime",
      "backtest_safe": false,
      "quality_flags": []
    },
    "budget_impact": {
      "mode": "diagnostic_only",
      "can_change_budget": false,
      "reason": "awaiting_backtest_validation"
    }
  }
}
```

## Important Interpretation Notes

`sourceStatus.survstat_points` is the full raw SurvStat district-level row
count. It is not the number of weekly points used for one national virus curve.

`sourceStatus.survstat_wave_points` is the filtered weekly series used for the
current virus and region wave calculation.

## Materialized v1.2 Tables

v1.2 persists the runtime v1.1 output into four migration-managed tables:

```text
virus_wave_feature_runs
virus_wave_features
virus_wave_alignment
virus_wave_evidence
```

The runtime algorithm remains the calculator. Materialization snapshots its
result so backtests can later answer exactly which Wellenphase, AMELAG lead,
source availability and effective weights were visible at a point in time.

`virus_wave_feature_runs` stores the run metadata and a full `snapshot_json` of
the API block. `run_key` is deterministic for the same pathogen, region,
algorithm version and latest source dates, so repeated materialization of the
same inputs updates the same run instead of creating duplicates.

`virus_wave_features` stores one row per source:

```text
source
source_role
pathogen
region_code
season
phase
onset_date
peak_date
wave_strength
growth_rate
latest_observation_date
signal_basis
quality_flags_json
confidence_score
algorithm_version
```

`virus_wave_alignment` stores the AMELAG↔SurvStat comparison:

```text
raw_lead_lag_days
early_source_lead_days
alignment_status
alignment_score
divergence_score
correlation_score
algorithm_version
```

`virus_wave_evidence` stores one row per weighting profile:

```text
profile_name
primary_source
base_weights_json
quality_multipliers_json
effective_weights_json
source_availability_json
evidence_coverage
evidence_mode
budget_can_change
confidence_score
confidence_method
quality_flags_json
algorithm_version
```

Important: Materialized v1.2 is still diagnostic only. `budget_can_change` must
stay `false` until a later validated backtest explicitly promotes these signals
into Forecast Quality, Viral Pressure or budget gates.

Manual trigger:

```python
from app.services.media.cockpit.virus_wave_materialization import materialize_all_virus_wave_truth

with get_db_context() as db:
    materialize_all_virus_wave_truth(db)
```

Celery trigger:

```text
materialize_virus_wave_truth_task
```

## Research Backtest v1.3

v1.3 adds a diagnostic/research-only backtest. It compares:

```text
survstat_only
amelag_only
static_amelag_survstat_combo
evidence_v1_1_quality_weighted
```

The central product question is:

```text
Does AMELAG + SurvStat detect wave onset, peak timing and phase changes earlier
or more robustly than SurvStat alone?
```

It does not change:

```text
Forecast Quality
Viral Pressure
Media budget recommendations
Decision gates
global_status
```

Backtest budget impact remains:

```json
{
  "mode": "diagnostic_only",
  "can_change_budget": false,
  "reason": "backtest_research_only"
}
```

### Backtest Modes

`historical_cutoff` is the product-relevant mode. It avoids AMELAG smoothing
leakage by selecting AMELAG signal values in this order:

```text
viruslast_normalisiert > viruslast > value
```

`retrospective_descriptive` is only descriptive. It may use retrospectively
smoothed/current AMELAG fields in this order:

```text
vorhersage > viruslast_normalisiert > viruslast > value
```

The report exposes:

```json
{
  "mode": "historical_cutoff",
  "backtest_safe": true
}
```

or:

```json
{
  "mode": "retrospective_descriptive",
  "backtest_safe": false
}
```

### Pathogen Normalization

RSV variants are normalized so product-level comparisons do not accidentally
split the same wave family:

```text
canonical_pathogen = RSV
pathogen_variant   = RSV A / RSV B / null
```

Influenza A, Influenza B and SARS-CoV-2 remain canonical product scopes.

### Backtest Tables

v1.3 persists reports into:

```text
virus_wave_backtest_runs
virus_wave_backtest_results
virus_wave_backtest_events
```

`virus_wave_backtest_runs` stores version, mode, scope, model lists, parameters
and the full summary JSON.

`virus_wave_backtest_results` stores one row per model:

```text
model_name
onset_detection_gain_days
peak_detection_gain_days
phase_accuracy
false_early_warning_rate
missed_wave_rate
false_post_peak_rate
lead_lag_stability
mean_alignment_score
mean_divergence_score
confidence_brier_score
```

`virus_wave_backtest_events` stores event-level diagnostics such as onset and
peak detection dates.

Manual trigger:

```python
from app.services.media.cockpit.virus_wave_backtest import run_all_virus_wave_backtests

with get_db_context() as db:
    run_all_virus_wave_backtests(db, mode="historical_cutoff", scope_mode="canonical")
```

Celery trigger:

```text
run_virus_wave_backtest_task
```

## Backtest Hardening v1.6

v1.6 keeps the same diagnostic-only goal, but fixes the main method issues found
in the review drilldown:

```text
seasonal_windows=true by default
peak_after_onset_enforced=true
method_flags are stored in run.parameters_json
clinical anchor warnings are exposed in reports
partial boundary seasons are ignored unless each source has enough points and
an adequate date span
```

Season windows use July-June epidemiological seasons, for example:

```text
2025_2026 = 2025-07-01 through 2026-06-30
```

This prevents one 156-week backtest from mixing unrelated waves, such as a
2023 AMELAG peak with a 2025 SurvStat peak.

Peak detection is constrained so the selected peak must be on or after the
detected onset in the same window. This prevents invalid event chronologies like
`peak_date < onset_date`.

Method flags can include:

```text
subtype_specific_amelag_vs_combined_clinical_anchor
rsv_variant_scope_requires_review
peak_before_onset_detected
```

Legacy Influenza A/B subtype scopes remain review-sensitive when SurvStat only
provides the combined clinical anchor `Influenza, saisonal`. Legacy RSV variant
scopes remain review-sensitive unless validated at canonical `RSV` / `RSV A+B`
level.

Manual trigger with default season windows:

```python
from app.services.media.cockpit.virus_wave_backtest import run_all_virus_wave_backtests

with get_db_context() as db:
    run_all_virus_wave_backtests(
        db,
        mode="historical_cutoff",
        seasonal_windows=True,
        scope_mode="canonical",
    )
```

## Evaluation Report v1.7

v1.7 reads the persisted backtest tables and creates a compact operator
report. The report is deliberately not a new budget engine. It answers:

```text
Which pathogen scopes are candidates for later Forecast Quality or Viral
Pressure simulation, and which need review or no-go?
```

The report compares:

```text
survstat_only
vs.
evidence_v1_1_quality_weighted
```

The output uses three recommendation states:

```text
go_for_simulation = useful timing gain without material quality penalty
review            = ambiguous or mapping-sensitive result
no_go             = worse timing, high false warning risk, missed wave risk,
                    or poorer phase accuracy
```

Important: `go_for_simulation` does not mean budget activation. It only means
the scope can be considered for a later offline simulation behind a separate
feature flag.

Budget impact remains:

```json
{
  "mode": "diagnostic_only",
  "can_change_budget": false,
  "reason": "evaluation_report_research_only"
}
```

Canonical `scope_mode=canonical` reports filter out old legacy subtype runs so
the current product-facing report only contains:

```text
Influenza A+B
RSV
SARS-CoV-2
```

Legacy reports can still expose subtype review warnings:

```text
subtype_specific_amelag_vs_combined_clinical_anchor
rsv_variant_scope_requires_review
```

Manual trigger:

```python
from app.services.media.cockpit.virus_wave_backtest_report import (
    build_virus_wave_backtest_evaluation_report,
    write_virus_wave_backtest_evaluation_report,
)

with get_db_context() as db:
    report = build_virus_wave_backtest_evaluation_report(db, scope_mode="canonical")
    write_virus_wave_backtest_evaluation_report(db, scope_mode="canonical")
```

Default report path:

```text
/app/data/processed/virus_wave_backtest_evaluation_report.md
```

Celery trigger:

```text
generate_virus_wave_backtest_report_task
```
