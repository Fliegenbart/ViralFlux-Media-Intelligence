# h7 Pilot-Only Training Path

## Purpose

This path exists for the three day-one pilot scopes only:

- `Influenza A / h7`
- `Influenza B / h7`
- `RSV A / h7`

It is intentionally narrower than the full regional backfill path:

- pilot-only
- h7-only
- virus-selectable
- separate artifacts
- directly comparable against the current live baseline

It does not relax gates and it does not overwrite the canonical live
artifact root by default.

## Code Path

The targeted path is implemented in:

- `backend/app/services/ml/h7_pilot_training.py`
- `backend/scripts/run_h7_pilot_only_training.py`

The existing regional trainer remains the training backbone:

- `backend/app/services/ml/regional_trainer.py`

The new pilot path adds:

- per-virus h7-only experiment runs
- separate artifact roots for pilot runs
- baseline-vs-experiment comparison rows
- optional scope-specific calibration experiment families

## Artifact Isolation

Default pilot-only artifacts are written under:

```text
backend/app/ml_models/regional_panel_h7_pilot_only/
```

Each experiment run stays isolated below its own experiment name and
virus slug. The canonical live baseline stays under:

```text
backend/app/ml_models/regional_panel/
```

This keeps comparison honest:

- live baseline remains readable without retraining
- pilot-only runs do not silently replace live h7 bundles
- each experiment can be inspected or promoted independently later

## Supported Presets

### `pilot_baseline`

Runs the current guarded calibration path for the selected h7 pilot
viruses without adding extra calibration candidates.

### `influenza_calibration`

Runs local h7-only calibration experiments for:

- `Influenza A`
- `Influenza B`

If `RSV A` is explicitly included, it stays on the baseline guard path.

### `rsv_ranking`

Runs the RSV-specific h7 ranking path for:

- `RSV A`

This path keeps calibration guardrails intact and focuses on feature
subset tuning, trend/momentum/agreement weighting, and score separation
improvements. `Influenza A` and `Influenza B` stay on the baseline guard
path if they are explicitly included.

## Commands

Run the h7 pilot-only baseline for all three pilot scopes:

```bash
python backend/scripts/run_h7_pilot_only_training.py \
  --preset pilot_baseline \
  --output-root backend/app/ml_models/regional_panel_h7_pilot_only
```

Run only one pilot virus:

```bash
python backend/scripts/run_h7_pilot_only_training.py \
  --preset pilot_baseline \
  --virus "Influenza A"
```

Run the focused Influenza A/B calibration experiments:

```bash
python backend/scripts/run_h7_pilot_only_training.py \
  --preset influenza_calibration \
  --virus "Influenza A" \
  --virus "Influenza B" \
  --output-root backend/app/ml_models/regional_panel_h7_pilot_only
```

Run the RSV A ranking experiments:

```bash
python backend/scripts/run_h7_pilot_only_training.py \
  --preset rsv_ranking \
  --virus "RSV A" \
  --output-root backend/app/ml_models/regional_panel_h7_pilot_only
```

Override lookback consistently across all selected specs:

```bash
python backend/scripts/run_h7_pilot_only_training.py \
  --preset influenza_calibration \
  --lookback-days 720
```

## Comparison Output

The runner emits one comparison row per baseline or experiment. Each row
contains at least:

- `precision_at_top3`
- `activation_false_positive_rate`
- `pr_auc`
- `brier_score`
- `ece`
- `calibration_version`
- `selected_calibration_mode`
- `calibration_mode`
- `gate_outcome`
- `retained`
- `retention_reason`
- `feature_selection`
- `recency_weight_half_life_days`
- `signal_agreement_weight`
- `gate_summary`

These metrics are exposed twice on purpose:

- directly on each comparison row for fast diffing
- inside the nested `metrics` object for machine-friendly grouping

The JSON summary is written to:

```text
<output-root>/<preset>_summary.json
```

Per virus, the summary contains:

- `baseline`
- `runs`
- `comparison_table`
- `best_experiment`
- `best_retained_experiment`

## Current Live Baseline Reference

Observed live h7 baseline after guarded calibration fell back to
`raw_passthrough`:

| Virus | precision_at_top3 | activation_fp_rate | pr_auc | brier | ece | selected_calibration_mode | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Influenza A | 0.724359 | 0.052283 | 0.568928 | 0.102847 | 0.095076 | `raw_passthrough` | `WATCH` (`ece_passed`) |
| Influenza B | 0.737179 | 0.049768 | 0.632008 | 0.098856 | 0.079591 | `raw_passthrough` | `WATCH` (`ece_passed`) |
| RSV A | 0.577778 | 0.005006 | 0.572278 | 0.028113 | 0.025965 | `raw_passthrough` | `WATCH` (`precision_at_top3_passed`) |

## Non-Goals

This path does not:

- retrain h3 or h5
- retrain non-pilot viruses by default
- weaken any quality gate threshold
- overwrite live artifacts unless promoted explicitly later
