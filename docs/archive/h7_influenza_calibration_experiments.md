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

## Historical Live Baseline Reference

The last documented live baseline after the earlier guarded calibration
rollout was:

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

## Verified Local Reruns In This Workspace

Freshly re-run on `2026-04-14` with:

```bash
python backend/scripts/run_h7_pilot_only_training.py \
  --preset influenza_calibration \
  --virus "Influenza A" \
  --output-root backend/app/ml_models/regional_panel_h7_pilot_only
```

and:

```bash
python backend/scripts/run_h7_pilot_only_training.py \
  --preset influenza_calibration \
  --virus "Influenza B" \
  --output-root backend/app/ml_models/regional_panel_h7_pilot_only
```

Important local caveat:

- the canonical live baseline artifact under
  `backend/app/ml_models/regional_panel/influenza_a/horizon_7`
  is currently missing in this workspace
- the canonical live baseline artifact under
  `backend/app/ml_models/regional_panel/influenza_b/horizon_7`
  is also currently missing in this workspace
- the generated summary therefore reports `live_baseline.status = missing`
  for both reruns
- for this rerun, the truthful local reference row is `baseline_guard`

### Influenza A / h7

| Run | precision_at_top3 | activation_fp_rate | pr_auc | brier | ece | calibration_version | selected_calibration_mode | Retain? | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| `logit_temperature_grid` | 0.687943 | 0.013928 | 0.457293 | 0.160031 | 0.155023 | `logit_temp_guarded_t2:h7:2026-04-14T13:49:15.747379` | `logit_temp_guarded_t2` | yes | `WATCH` (`pr_auc_passed`, `ece_passed`) |
| `shrinkage_blend_grid` | 0.687943 | 0.016713 | 0.342838 | 0.168499 | 0.161409 | `shrinkage_guarded_a0p3:h7:2026-04-14T13:54:14.153612` | `shrinkage_guarded_a0p3` | yes | `WATCH` (`pr_auc_passed`, `ece_passed`) |
| `baseline_guard` | 0.687943 | 0.013928 | 0.335851 | 0.172629 | 0.171710 | `raw_passthrough:h7:2026-04-14T13:44:14.557767` | `raw_passthrough` | yes | `WATCH` (`pr_auc_passed`, `brier_passed`, `ece_passed`) |
| `quantile_smoothing_q8` | 0.687943 | 0.013928 | 0.335851 | 0.172629 | 0.171710 | `raw_passthrough:h7:2026-04-14T13:59:22.084250` | `raw_passthrough` | yes | `WATCH` (`pr_auc_passed`, `brier_passed`, `ece_passed`) |

Verdict for the verified local Influenza A rerun:

- `baseline_guard` now truthfully stays on `raw_passthrough`
- `logit_temperature_grid` remains the strongest candidate in the rerun
- `shrinkage_blend_grid` improves over `baseline_guard`, but not as much as `logit_temperature_grid`
- `quantile_smoothing_q8` collapses back to the same effective result as `baseline_guard`
- the scope remains `WATCH`

### Influenza B / h7

| Run | precision_at_top3 | activation_fp_rate | pr_auc | brier | ece | calibration_version | selected_calibration_mode | Retain? | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| `logit_temperature_grid` | 0.771605 | 0.009036 | 0.394168 | 0.221548 | 0.226309 | `logit_temp_guarded_t1p1:h7:2026-04-14T16:16:42.909833` | `logit_temp_guarded_t1p1` | yes | `WATCH` (`pr_auc_passed`, `ece_passed`) |
| `shrinkage_blend_grid` | 0.771605 | 0.019578 | 0.300215 | 0.232895 | 0.224214 | `shrinkage_guarded_a0p3:h7:2026-04-14T16:21:59.681194` | `shrinkage_guarded_a0p3` | yes | `WATCH` (`pr_auc_passed`, `brier_passed`, `ece_passed`) |
| `baseline_guard` | 0.771605 | 0.009036 | 0.278340 | 0.234560 | 0.235023 | `raw_passthrough:h7:2026-04-14T16:10:41.525201` | `raw_passthrough` | yes | `WATCH` (`pr_auc_passed`, `brier_passed`, `ece_passed`) |
| `quantile_smoothing_q8` | 0.771605 | 0.000000 | 0.278340 | 0.234560 | 0.235023 | `raw_passthrough:h7:2026-04-14T16:27:17.014374` | `raw_passthrough` | yes | `WATCH` (`pr_auc_passed`, `brier_passed`, `ece_passed`) |

Verdict for the verified local Influenza B rerun:

- `baseline_guard` now truthfully stays on `raw_passthrough`
- `logit_temperature_grid` is the strongest candidate in the rerun
- `shrinkage_blend_grid` improves over `baseline_guard`, but it raises `activation_false_positive_rate`
- `quantile_smoothing_q8` collapses back to `raw_passthrough` again
- the scope remains `WATCH`

## Current Takeaway

After the verified `2026-04-14` local reruns:

- Influenza A/h7 points to `logit_temp_guarded_t2` as the leading candidate
- Influenza B/h7 points to `logit_temp_guarded_t1p1` as the leading candidate
- the `baseline_guard` path is now verified to stay on `raw_passthrough` in both local reruns
- `quantile_smoothing_q8` still does not beat the truthful fallback in either virus
- the local workspace still lacks the canonical live Influenza-A and Influenza-B baseline artifacts, so these reruns are best read as internal candidate ranking, not as final promotion proof against the live bundle
