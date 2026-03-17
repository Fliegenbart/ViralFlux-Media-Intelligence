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
  --output-root backend/ml_models/regional_panel_h7_pilot_only
```

The JSON comparison summary is written to:

```text
backend/ml_models/regional_panel_h7_pilot_only/influenza_calibration_summary.json
```

## Comparison Table Template

Each output row contains:

- `precision_at_top3`
- `activation_false_positive_rate`
- `pr_auc`
- `brier_score`
- `ece`
- `calibration_version`
- `selected_calibration_mode`
- `gate_summary`

## Current Finding

At the current live baseline, `raw_passthrough` remains the honest
winner for both Influenza A/h7 and Influenza B/h7. The new h7-only
experiment path is in place specifically so that additional local
calibration candidates can be tested without triggering a full
multi-horizon retrain or weakening the gate contract.
