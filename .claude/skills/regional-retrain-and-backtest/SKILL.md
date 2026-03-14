# Regional Retrain And Backtest

## Use When

- a regional virus model was changed and needs a fresh train/backtest cycle
- model artifacts, quality gates, or rollout metadata must be regenerated

## Workflow

1. Verify feature and label changes locally before training.
2. Run targeted backend tests.
3. Retrain only the affected virus line unless the change is cross-virus.
4. Read the generated `metadata.json`, `backtest.json`, `threshold_manifest.json`, and `point_in_time_snapshot.json`.
5. Compare the new candidate to the current baseline before any deploy.

## Guardrails

- Do not treat a retrain as an improvement without checking `precision_at_top3`, `pr_auc`, `ece`, and false activations together.
- Do not silently move a `watch_only` line into activation mode.

