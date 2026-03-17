# h7 Influenza Calibration Experiments

## Goal

Target only the two h7 pilot scopes that still fail on `ece_passed`:

- `Influenza A / h7`
- `Influenza B / h7`

The experiment contract is strict:

- improve `ece` honestly
- do not degrade `precision_at_top3`
- do not degrade `activation_false_positive_rate`
- do not weaken gates
- prefer `raw_passthrough` if no candidate wins honestly

## Baseline Before Local Experiments

Current live baseline after the guarded calibration rollout:

| Virus | precision_at_top3 | activation_fp_rate | pr_auc | brier | ece | calibration_version | selected_calibration_mode | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| Influenza A | 0.724359 | 0.052283 | 0.568928 | 0.102847 | 0.095076 | `raw_passthrough:h7:2026-03-17T15:54:41.258955` | `raw_passthrough` | `WATCH` (`ece_passed`) |
| Influenza B | 0.737179 | 0.049768 | 0.632008 | 0.098856 | 0.079591 | `raw_passthrough:h7:2026-03-17T16:02:46.339488` | `raw_passthrough` | `WATCH` (`ece_passed`) |

## Implemented Local Experiment Families

The h7-only pilot runner now supports these local calibration families
for Influenza A/B:

### `baseline_guard`

- Current live-compatible guarded path
- Candidates: raw plus guarded isotonic only

### `logit_temperature_grid`

- Monotone temperature-like logit remapping
- Ranking-neutral by construction
- Intended to reduce overconfidence while preserving order

### `shrinkage_blend_grid`

- Scope-specific shrinkage toward the fitted event prior
- Ranking-neutral by construction
- Intended to regularize probabilities without changing ranking order

### `quantile_smoothing_q8`

- Quantile-binned smoothed remapping with monotone enforcement
- Can improve calibration for sparse tails
- Guard rejects it immediately if ranking-side behavior slips

## Guard Rule Used For These Experiments

Additional candidates are only kept when they beat raw on the guard
segment under the same threshold basis:

- `brier_score` must not get worse
- `ece` must improve for real
- `precision_at_top3` must not get worse
- `activation_false_positive_rate` must not get worse

If no candidate passes that contract, the selected mode remains
`raw_passthrough`.

## How To Run

```bash
python backend/scripts/run_h7_pilot_only_training.py \
  --preset influenza_calibration \
  --virus "Influenza A" \
  --virus "Influenza B" \
  --output-root backend/app/ml_models/regional_panel_h7_pilot_only
```

The JSON comparison summary is written to:

```text
backend/app/ml_models/regional_panel_h7_pilot_only/influenza_calibration_summary.json
```

On the live worker, the same run was written to:

```text
/app/app/ml_models/regional_panel_h7_pilot_only/influenza_calibration_summary.json
```

Each comparison row now exposes these fields directly at row level and
also keeps the nested `metrics` object:

- `precision_at_top3`
- `activation_false_positive_rate`
- `pr_auc`
- `brier_score`
- `ece`
- `calibration_version`
- `selected_calibration_mode`
- `gate_summary`

## Observed Comparison Results

Comparison rule for retention in this document:

- `ece` must improve versus the live baseline
- `precision_at_top3` must not get worse
- `activation_false_positive_rate` must not get worse

### Influenza A / h7

| Run | precision_at_top3 | activation_fp_rate | pr_auc | brier | ece | calibration_version | selected_calibration_mode | Retain? | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| `live_baseline` | 0.724359 | 0.052283 | 0.568928 | 0.102847 | 0.095076 | `raw_passthrough:h7:2026-03-17T15:54:41.258955` | `raw_passthrough` | baseline | `WATCH` (`ece_passed`) |
| `baseline_guard` | 0.724359 | 0.052283 | 0.568928 | 0.102847 | 0.095076 | `raw_passthrough:h7:2026-03-17T17:40:30.506556` | `raw_passthrough` | no | `WATCH` (`ece_passed`) |
| `logit_temperature_grid` | 0.724359 | 0.052283 | 0.599340 | 0.096200 | 0.080051 | `logit_temp_guarded_t2:h7:2026-03-17T17:43:35.563395` | `logit_temp_guarded_t2` | yes | `WATCH` (`ece_passed`) |
| `shrinkage_blend_grid` | 0.747917 | 0.048634 | 0.585018 | 0.104295 | 0.096889 | `shrinkage_guarded_a0p3:h7:2026-03-17T17:46:40.755849` | `shrinkage_guarded_a0p3` | no | `WATCH` (`ece_passed`) |
| `quantile_smoothing_q8` | 0.724359 | 0.052283 | 0.567420 | 0.102847 | 0.095076 | `raw_passthrough:h7:2026-03-17T17:49:43.474191` | `raw_passthrough` | no | `WATCH` (`ece_passed`) |

Verdict for Influenza A:

- `logit_temperature_grid` is the only honest improvement versus the live baseline.
- It lowers `ece` by `0.015025` and `brier` by `0.006647` while leaving `precision_at_top3` and `activation_false_positive_rate` unchanged.
- The scope still does not clear `ece_passed`, so this is an honest improvement, not a promotion to `GO`.

### Influenza B / h7

| Run | precision_at_top3 | activation_fp_rate | pr_auc | brier | ece | calibration_version | selected_calibration_mode | Retain? | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| `live_baseline` | 0.737179 | 0.049768 | 0.632008 | 0.098856 | 0.079591 | `raw_passthrough:h7:2026-03-17T16:02:46.339488` | `raw_passthrough` | baseline | `WATCH` (`ece_passed`) |
| `baseline_guard` | 0.737179 | 0.049768 | 0.632008 | 0.098856 | 0.079591 | `raw_passthrough:h7:2026-03-17T17:52:45.294072` | `raw_passthrough` | no | `WATCH` (`ece_passed`) |
| `logit_temperature_grid` | 0.741453 | 0.049768 | 0.656558 | 0.094915 | 0.074984 | `logit_temp_guarded_t2:h7:2026-03-17T17:55:48.413897` | `logit_temp_guarded_t2` | yes | `WATCH` (`ece_passed`) |
| `shrinkage_blend_grid` | 0.743750 | 0.044147 | 0.643951 | 0.098757 | 0.078599 | `shrinkage_guarded_a0p3:h7:2026-03-17T17:58:52.027940` | `shrinkage_guarded_a0p3` | yes | `WATCH` (`ece_passed`) |
| `quantile_smoothing_q8` | 0.737179 | 0.049768 | 0.632008 | 0.098856 | 0.079591 | `raw_passthrough:h7:2026-03-17T18:01:53.403389` | `raw_passthrough` | no | `WATCH` (`ece_passed`) |

Verdict for Influenza B:

- `logit_temperature_grid` is the strongest honest improvement.
- It lowers `ece` by `0.004607` and `brier` by `0.003941`, keeps `activation_false_positive_rate` flat, and slightly improves `precision_at_top3`.
- `shrinkage_blend_grid` also qualifies as an honest improvement, but the `ece` gain is smaller at `0.000992`.
- The scope remains `WATCH` because `ece_passed` is still not green.

## Final Finding

The h7-only pilot path now proves two useful points without weakening any
gate:

- Influenza A/h7 has one honest calibration winner: `logit_temp_guarded_t2`.
- Influenza B/h7 has two honest winners, with `logit_temp_guarded_t2` clearly stronger than `shrinkage_guarded_a0p3`.
- `quantile_smoothing_q8` did not beat `raw_passthrough` for either virus.
- None of the honest improvements is yet large enough to move either
  scope from `WATCH` to `GO`.

That means the correct operational interpretation is:

- keep the gates unchanged
- treat `logit_temperature_grid` as the leading next-step candidate for
  any isolated h7 promotion test
- keep `raw_passthrough` as the truthful fallback wherever the local
  experiment does not produce a real gain
