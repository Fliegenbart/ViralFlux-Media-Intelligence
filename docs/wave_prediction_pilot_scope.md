# Wave Prediction Pilot Scope

Stand: 2026-03-16

## Pilot Scope

The current pilot scope for wave-v1 is intentionally narrow.

Included pathogens:

- `Influenza A`
- `SARS-CoV-2`

Included start regions:

- `BY`
- `HH`

These choices are based on the current real-data matrix evaluation in
`data/processed/wave_matrix_eval/20260316T100806Z`.

Why this scope is selected:

- `SARS-CoV-2` is currently the strongest pathogen family in the matrix.
- `Influenza A` is good enough to pilot, even though it still produces more false alarms than desired.
- `HH` and `BY` are the best current start regions across the evaluated combinations.

## Not In Pilot Scope

The following are explicitly not part of the initial pilot:

- `RSV A`
- `NW`
- the broader all-pathogen / all-region rollout

## Error Analysis Track

The current error-analysis track is:

- `NW` for the pilot pathogens (`Influenza A`, `SARS-CoV-2`)
- `RSV A` across evaluated regions, with particular attention to `BW` and `NW`

Why these stay in analysis:

- `NW` is materially weaker than `BY` and `HH` in the current matrix.
- `RSV A` is the weakest pathogen family in the current matrix and is not ready for external rollout.

## Product Semantics

For the pilot, the external model output should remain:

- `wave_score`

The pilot should not claim calibrated event probabilities yet.
`wave_probability` remains out of scope until calibration behavior is stable enough across folds and regions.
