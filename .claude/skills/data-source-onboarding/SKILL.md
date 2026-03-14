# Data Source Onboarding

## Use When

- adding a new epidemiological, clinical, or business-side signal
- changing availability semantics of an existing source

## Workflow

1. Identify the source table and owner module in `backend/app/services/data_ingest/`.
2. Define `available_time` or an explicit lag before adding any feature usage.
3. Decide whether the source belongs in:
   - epidemiology layer
   - activation/business layer
   - dashboard only
4. Add leakage-safe tests for the new source.
5. Update manifests or docs if the source changes model coverage or decision behavior.

## Rule

If a new source is business truth or response data, keep it out of the epidemiological target definition.

