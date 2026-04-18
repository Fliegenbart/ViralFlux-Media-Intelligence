# RSV A / h7 Ranking Experiments

## Goal

This document tracks the RSV-specific h7 pilot path that focuses on
ranking and score separation rather than calibration cleanup.

The implementation keeps the existing gate contract intact:

- no global model rewrite
- no gate softening
- no forced `GO`
- honest `WATCH` is preferred over fake promotion

## What Changed

The RSV path now runs through a dedicated preset:

- `backend/scripts/run_h7_pilot_only_training.py --preset rsv_ranking`

The RSV trainer can now apply:

- a feature subset centered on RSV and other signal-near families
- stronger recency weighting
- signal-agreement weighting over trend and momentum features
- tighter tree regularization for score separation

The comparison rows also expose explicit honesty fields:

- `calibration_mode`
- `gate_outcome`
- `retained`
- `retention_reason`
- `feature_selection`

## Execution Note

I could not rerun a fresh numeric RSV summary in this workspace because
the local PostgreSQL instance on `localhost:5432` does not contain the
viralflux forecast schema. It exposes other projects instead, so the
model code can be validated but not backtested on the required RSV data
here.

That means the table below is an implementation log plus the currently
known live baseline, not a fabricated performance report.

## Known Live Baseline

The existing h7 baseline reference for RSV A remains:

| Variant | precision_at_top3 | activation_false_positive_rate | ece | calibration mode | gate outcome | Retain? |
| --- | ---: | ---: | ---: | --- | --- | --- |
| `live_baseline` | 0.577778 | 0.005006 | 0.025965 | `raw_passthrough` | `WATCH` (`precision_at_top3_passed`) | baseline |

## RSV Experiment Matrix

These variants are implemented and ready to run against the correct
forecast database.

| Variant | Feature focus | Weighting / tuning | precision_at_top3 | activation_false_positive_rate | ece | calibration mode | gate outcome | Retain? | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `baseline_guard` | Full current h7 guard path | raw plus guarded isotonic only | not run here | not run here | not run here | `raw_passthrough` | `WATCH` | baseline reference | implemented |
| `rsv_signal_core` | RSV signal families only, with weather, pollen, and cross-virus noise removed | no extra weighting | not run here | not run here | not run here | n/a | n/a | pending run | implemented |
| `rsv_signal_core_weighted` | Same signal core as above | recency half-life 180d plus signal-agreement weight 0.35 | not run here | not run here | not run here | n/a | n/a | pending run | implemented |
| `rsv_signal_context_regularized` | Signal core plus state-context dummies | recency half-life 120d plus signal-agreement weight 0.45 plus stronger tree regularization | not run here | not run here | not run here | n/a | n/a | pending run | implemented |

## Honest Retention Rule

A variant is only considered retained if it improves `precision_at_top3`
while also keeping calibration and activation under control:

- `precision_at_top3` must increase
- `activation_false_positive_rate` must not increase
- `ece` must not increase
- `brier_score` must not increase

If nothing satisfies that rule, the path stays `WATCH`.

## Reproduce

Run the RSV path in a database-backed environment:

```bash
python backend/scripts/run_h7_pilot_only_training.py \
  --preset rsv_ranking \
  --virus "RSV A" \
  --output-root backend/app/ml_models/regional_panel_h7_pilot_only
```

The summary will be written to:

```text
backend/app/ml_models/regional_panel_h7_pilot_only/rsv_ranking_summary.json
```

For the server-side live evaluation with archived JSON and Markdown
outputs, use:

- [rsv_h7_live_evaluation_runbook.md](./rsv_h7_live_evaluation_runbook.md)
- [rsv_h7_persistent_evaluation.md](./rsv_h7_persistent_evaluation.md)

## Bottom Line

The RSV-specific optimization path is now in place, but this workspace
could not produce a fresh numeric comparison because the needed forecast
database is not present locally. The code is ready for a real RSV run in
the correct environment, and the retention logic will keep only honest
precision gains.
