# Tri-Layer Evidence Fusion

## 1. Purpose

Tri-Layer Evidence Fusion (TLEF-BICG v0) is an experimental research module for comparing epidemiological signals, clinical confirmation and future commercial calibration in one diagnostic view.

The module exists to help researchers and operators inspect whether a regional virus signal is early, corroborated, commercially measurable and safe to isolate from media effects. It is not part of the production allocation engine.

Mandatory operating principle:

```text
Early Warning is not Budget Approval.
```

## 2. Research-only status

This module is research-only. It is protected as a cockpit sub-route, but it is not the live cockpit decision surface.

```text
This module does not alter live allocation or campaign recommendation outputs.
```

It does not change:

- existing `/cockpit` snapshot semantics
- production readiness status
- regional forecast outputs
- media allocation outputs
- campaign recommendation outputs
- budget permission in existing production services

## 3. Mathematical model summary

TLEF-BICG v0 is a deterministic, testable MVP. It is not yet a validated Bayesian particle filter.

The current service estimates a latent regional wave state from available proxy evidence:

- `intensity_mean`
- `growth_mean`
- `uncertainty`
- `wave_phase`

Evidence quality is summarized per source using freshness, reliability, baseline stability, signal-to-noise, consistency, drift and coverage where those values are available. Connected sources are normalized into evidence weights with a softmax-style weighting step. Missing sources are excluded instead of being filled with fake values.

Early Warning Score is computed as a conservative proxy:

```text
EWS = 100 * P_wave_proxy * epi_quality
```

Commercial Relevance Score is only computed when a real sales calibration source is connected and usable.

```text
Sales Relevance is not inferred from epidemiology alone.
```

## 4. API endpoints

### Snapshot

```http
GET /api/v1/media/cockpit/tri-layer/snapshot
```

Query parameters:

- `virus_typ`, default `Influenza A`
- `horizon_days`, default `7`, allowed `3`, `7`, `14`
- `brand`, default `gelo`
- `client`, default `GELO`
- `mode`, default `research`, allowed `research`, `shadow`

The endpoint is protected by the same cockpit auth mechanism as:

```http
GET /api/v1/media/cockpit/snapshot
```

### Backtest start

```http
POST /api/v1/media/cockpit/tri-layer/backtest
```

The POST endpoint enqueues a Celery research job. It must not run heavy historical computation inside the request process.

### Backtest status

```http
GET /api/v1/media/cockpit/tri-layer/backtest/{run_id}
```

Returns the Celery status and a final report when complete.

### Latest completed backtest

```http
GET /api/v1/media/cockpit/tri-layer/backtest/latest?virus_typ=Influenza%20A&horizon_days=7
```

Reads the latest completed report metadata from the accepted backtest artifact location. It does not start computation. If no report exists, it returns `report: null`.

## 5. Frontend route

The experimental frontend page is:

```text
/cockpit/tri-layer
```

It is a protected cockpit sub-route and uses the same access pattern as `/cockpit`. The customer-facing cockpit remains stable. The route is labelled as a research layer and includes visible safety copy that it does not activate or change media budget.

## 6. Source assumptions

TLEF v0 uses the best available internal service outputs without calling public HTTP APIs from inside the backend.

Current assumptions:

- Regional forecast output may provide event probability, expected delta, confidence and artifact diagnostics.
- Wastewater evidence may be connected, partial or unavailable depending on existing source coverage.
- Clinical evidence may be connected, partial or unavailable depending on existing source coverage.
- Sales evidence is unavailable unless a real brand-level sell-out source exists and passes schema checks.

Missing data is represented honestly:

- score fields use `null`
- source status uses `not_connected` or `partial`
- coverage and freshness use `null` when unknown
- no fake sales values are generated

## 7. Gate semantics

Each regional result includes conservative gates:

- `epidemiological_signal`
- `clinical_confirmation`
- `sales_calibration`
- `coverage`
- `drift`
- `budget_isolation`

Gate values:

- `pass`: usable for the current research decision layer
- `watch`: signal exists, but uncertainty or incompleteness remains
- `fail`: blocking condition
- `not_available`: required evidence is not connected or cannot be assessed

Clinical confirmation can improve confidence in an epidemiological signal, but it does not create commercial validation.

## 8. Budget isolation rule

Budget permission is deliberately more conservative than early warning.

```text
Budget Permission remains blocked/shadow-only unless Sales Calibration and Budget Isolation pass.
```

Budget states:

- `blocked`: no usable signal or a hard gate failed
- `calibration_window`: epidemiological signal exists, but clinical confirmation is still missing
- `shadow_only`: epidemiological and clinical signal exist, but sales calibration is missing
- `limited`: sales and core gates pass, but budget isolation is only watch-level
- `approved`: all gates pass

In v0, `budget_can_change` remains `false` for live behavior. Even when tests inject fully valid evidence to exercise the state machine, this module does not modify production budget services.

## 9. Backtest design

The backtest runner is research-only and uses point-in-time semantics:

- each cutoff only uses evidence available at that cutoff
- no future observations are allowed in feature or gate evaluation
- unavailable historical sources are marked unavailable for that cutoff
- generated reports are written under the processed data/artifact area and should not be committed

Tracked metrics include:

- `onset_detection_gain`
- `peak_lead_time`
- `false_early_warning_rate`
- `phase_accuracy`
- `sales_lift_predictiveness`
- `budget_regret_reduction`
- `calibration_error`
- `number_of_cutoffs`
- `number_of_regions`
- `gate_transition_counts`

Baselines include:

- `persistence`
- `clinical_only`
- `wastewater_plus_clinical`
- `tri_layer_without_budget_isolation`
- `tri_layer_with_budget_isolation`

The comparison between `tri_layer_without_budget_isolation` and `tri_layer_with_budget_isolation` is required because it tests whether the budget isolation gate reduces false budget triggers.

## 10. GPU execution notes

CPU is the default. Local development and CI must not require a GPU.

Tri-Layer research code reuses the regional XGBoost runtime configuration. Experimental workers may opt in with:

```bash
REGIONAL_XGBOOST_DEVICE=cuda
```

or a specific device:

```bash
REGIONAL_XGBOOST_DEVICE=cuda:0
```

GPU execution is intended for Celery research jobs and future challenger models, not synchronous production request handling.

## 11. What is explicitly NOT guaranteed

This module does not guarantee:

- scientific validation
- forecast superiority over existing models
- causal sales lift
- customer ROI
- budget approval
- media incrementality
- readiness approval
- production allocation changes

The method is experimental and should be read as diagnostic evidence, not as a final decision authority.

## 12. How to interpret the scores

### Early Warning Score

Early Warning Score estimates whether available epidemiological evidence suggests a regional wave signal. A high value can justify attention, review or shadow monitoring.

It does not approve budget.

```text
Early Warning is not Budget Approval.
```

### Commercial Relevance Score

Commercial Relevance Score is `null` unless real, usable sales calibration is connected.

It must not be inferred from epidemiology alone. If Sales is `not_connected`, the page must show that honestly.

```text
Sales Relevance is not inferred from epidemiology alone.
```

### Budget Permission State

Budget Permission State describes the research gate result for the Tri-Layer module. It is intentionally conservative.

```text
Budget Permission remains blocked/shadow-only unless Sales Calibration and Budget Isolation pass.
```

This state does not change live allocation, campaign recommendation outputs or existing production budget permission.
