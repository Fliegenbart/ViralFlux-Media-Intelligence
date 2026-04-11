# Regional Artifact Bootstrap Design

## Goal

Make the regional forecast path understandable and operationally honest when model artifacts are missing.

Today a fresh clone can start the backend, but the regional forecast path often degrades into `no_model` because the required artifact bundle under `backend/app/ml_models/regional_panel/...` is not present. The system technically survives, but a new developer or buyer does not get a clear explanation of what is missing or how to fix it.

## Desired Outcome

When regional artifacts are missing, the product should fail clearly and explain:

- which scopes are missing
- which files or bundles are expected
- which bootstrap command to run next

This should be visible in both the forecast-facing runtime responses and the operational readiness view.

## Non-Goals

- no automatic training during app startup
- no fake or demo forecast payloads pretending to be real model output
- no new model registry service
- no redesign of the existing training pipeline

## Current Problem

The regional forecast path in `RegionalForecastService` loads horizon-scoped artifacts from disk. If the bundle is absent or incomplete, the prediction path returns `status="no_model"`. This is technically explicit, but operationally weak because it does not reliably tell a beginner what to do next.

At the same time, the repository snapshot contains registry metadata and experimental artifact outputs, but not the actual production-ready regional panel bundles. That means a fresh clone looks more complete than it really is.

## Proposed Approach

We will keep the existing `no_model` semantics, but enrich them with a first-class bootstrap explanation.

The fix has three parts:

1. Centralize missing-artifact diagnostics for the regional forecast path.
2. Expose a human-readable bootstrap message and command in the forecast response.
3. Surface the same information in operational readiness checks and the release-facing docs.

## Design

### 1. Central Regional Artifact Diagnostics

Add a small helper in the regional forecast artifact path that can answer:

- does the requested artifact scope exist
- is the bundle incomplete
- is the bundle present but structurally invalid
- what command should the operator run next

The helper should work on the same scope dimensions already used today:

- `virus_typ`
- `horizon_days`

It should return a normalized diagnostic payload rather than a plain string.

Suggested fields:

- `status`
- `artifact_scope`
- `artifact_dir`
- `missing_files`
- `bootstrap_required`
- `operator_message`
- `bootstrap_command`
- `artifact_transition_mode`

### 2. Forecast Response Contract

Keep the public response status as `no_model`, but add structured operational guidance when the root cause is missing artifacts.

Suggested additional response fields:

- `missing_artifacts: true`
- `missing_scopes: [...]`
- `operator_message: "..."`
- `bootstrap_command: "cd backend && python scripts/backfill_regional_model_artifacts.py --horizon 3 --horizon 5 --horizon 7"`

This preserves backward compatibility for consumers already checking `status`, while making the payload much more understandable for humans and future UI improvements.

### 3. Readiness Integration

Operational readiness should expose the same condition in a simple, explicit way.

Suggested readiness fields:

- `regional_artifacts_ready`
- `regional_artifact_blockers`
- `regional_artifact_bootstrap_command`

This allows a release or buyer demo checklist to say:

- backend is running
- but the regional model layer is not prepared yet

That is much better than a silent runtime degradation discovered only after clicking through forecast views.

### 4. Documentation

Update the production/readiness documentation so there is one short operational path:

1. run artifact bootstrap
2. recompute operational views
3. run smoke test

The docs should mirror the exact bootstrap command emitted by the runtime response so the system and docs never disagree.

## File-Level Plan

Primary files:

- `backend/app/services/ml/regional_forecast_artifacts.py`
- `backend/app/services/ml/regional_forecast_prediction.py`
- `backend/app/services/ops/production_readiness_service.py`
- `docs/production_readiness_checklist.md`

Likely supporting tests:

- `backend/app/tests/test_regional_forecast_service.py`
- `backend/app/tests/test_production_readiness_service.py`

## Error Handling

There are three distinct cases and they should stay distinct:

1. **Missing bundle**
   - response stays `no_model`
   - add bootstrap guidance

2. **Incomplete bundle**
   - response stays `no_model`
   - list missing files

3. **Invalid bundle**
   - response stays `no_model`
   - explain why the bundle is unusable, for example missing `horizon_days` in metadata or training-only features leaking into inference

We should not collapse these cases into one generic message.

## Testing Strategy

Add or update tests for:

- missing artifact directory returns `no_model` plus bootstrap guidance
- incomplete artifact bundle lists the missing files
- readiness exposes missing regional artifacts as an explicit blocker
- existing valid artifact flows behave unchanged

Keep the tests narrow and contract-focused. We do not need to retrain models to verify this fix.

## Rollout

This is a low-risk runtime contract improvement.

- no model behavior changes when artifacts are present
- no startup training side effects
- no new external dependencies

The main behavior change is that operators and future UI surfaces get a clearer explanation when artifacts are absent.

## Recommendation

Implement this as a small fail-fast and bootstrap-guidance improvement first.

If we later want a smoother onboarding story, we can add an optional developer bootstrap wrapper script, but that should come after the runtime is already honest and understandable.
