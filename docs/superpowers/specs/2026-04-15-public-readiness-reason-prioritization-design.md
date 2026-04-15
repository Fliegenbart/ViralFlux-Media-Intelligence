# Public Readiness Reason Prioritization Design

**Date:** 2026-04-15

**Goal:** Make the public `/health/ready` explanation honest and easier to understand by showing system-wide readiness reasons before repetitive per-virus forecast warnings.

## Problem

The current public readiness payload can lead with multiple forecast-monitoring warnings like:

- `Influenza A: forecast readiness WATCH.`
- `Influenza B: forecast readiness WATCH.`
- `SARS-CoV-2: forecast readiness WATCH.`

That is misleading when the actual top-level degraded state is primarily caused by a system-wide component such as `schema_bootstrap` being `unknown`.

In simple words:
- the system is yellow for one main reason
- but the public API can show three louder secondary reasons first
- this makes the public explanation look less honest than the real internal snapshot

## Scope

This change only affects the **public explanation layer** in `backend/app/main.py`.

It does **not** change:

- the internal readiness snapshot in `backend/app/services/ops/production_readiness_service.py`
- the health status calculation (`healthy`, `degraded`, `unhealthy`)
- the forecast monitoring model logic
- the forecast promotion gate rules

## Recommended Approach

Use a public-reason prioritization pass in `backend/app/main.py` so that:

1. system-wide warning components are listed before forecast-monitoring items
2. forecast-monitoring reasons remain visible, but only after broader platform causes
3. the returned `status_reasons` stay short and stable

This is the safest option because it improves honesty and readability without weakening the actual readiness gate.

## Alternatives Considered

### Option A: Reorder only public reasons

Change the ordering in `_public_warning_reasons()` so that generic component messages such as `schema_bootstrap` come before per-virus forecast warnings.

Pros:
- very small change
- low risk
- keeps all existing signals

Cons:
- still may produce several repetitive forecast lines after the main reason

### Option B: Reorder and compact forecast-monitoring reasons

Do Option A, and also compress repetitive forecast-monitoring warnings into fewer public lines when they are not the primary cause.

Pros:
- clearest user-facing output
- prevents three near-identical forecast lines from pushing out more important reasons

Cons:
- slightly more opinionated presentation logic

### Option C: Change actual readiness gating

Make forecast monitoring less important in the real readiness status.

Pros:
- could reduce degraded states

Cons:
- not honest for this task
- changes product policy, not just explanation
- too risky for this narrow follow-up

## Decision

Implement **Option B**.

Reason:
- it keeps the real readiness status untouched
- it fixes the misleading public presentation
- it reduces noise from repetitive per-virus warnings

## Design

### 1. Public warning ordering

Update `_public_warning_reasons()` in `backend/app/main.py` so that warning reasons are collected in this order:

1. explicit snapshot warnings
2. non-forecast warning components with meaningful messages
3. regional/core scope warnings
4. forecast-monitoring warnings

This ensures system-wide problems appear first.

### 2. Forecast-monitoring compaction

When `forecast_monitoring` has several warning items with the same public pattern (`forecast readiness WATCH` and fresh monitoring fields), collapse them into a smaller set of reasons instead of returning one line per virus first.

The compaction rule should stay conservative:

- do not hide freshness failures
- do not hide critical monitoring failures
- do not change the meaning of the warning
- only compact repetitive, same-shape forecast readiness warnings

In simple words:
- if three warnings all say nearly the same thing, summarize them
- if one warning says something truly different, keep it separate

### 3. Status preservation

The `status`, `warning_count`, `blocker_count`, and the internal snapshot structure must stay unchanged.

Only the presentation of `status_reasons` should change.

## Data Flow

1. `ProductionReadinessService.build_snapshot()` produces the internal snapshot.
2. `_public_readiness_payload()` calls `_public_warning_reasons()`.
3. `_public_warning_reasons()` returns a better-prioritized and less repetitive reason list.
4. `/health/ready` returns the same status as before, but with clearer top reasons.

## Error Handling

If the new compaction logic cannot derive a grouped reason safely, it must fall back to the current per-item reason generation.

That means:
- no warnings are silently dropped because of malformed data
- the worst case is the old verbose behavior, not missing reasons

## Testing

Add or update tests in `backend/app/tests/test_main_security_surface.py` to prove:

1. a system-wide warning reason appears before forecast-monitoring reasons
2. repetitive forecast-monitoring reasons are compacted when they are same-shape warnings
3. distinct freshness-related forecast warnings are still preserved
4. the public payload still hides internal details

## Success Criteria

This design is successful if:

- `/health/ready` stays operationally truthful
- the top public reasons point to the real top-level degraded cause first
- repetitive per-virus forecast warnings no longer crowd out more important causes
- no internal health decision becomes looser

## Out of Scope

- fixing `schema_bootstrap = unknown`
- changing forecast-gate thresholds
- changing drift thresholds
- changing backtest architecture
- retraining or recalibrating any model
