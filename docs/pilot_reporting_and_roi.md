# Pilot Reporting and ROI

## Scope

This document describes the pilot reporting and audit layer for PEIX / GELO readouts.

Important:

- the customer-facing product can now run in **Forecast-First** mode without GELO outcome data
- this reporting and ROI layer is therefore the **second layer**, not the first product claim
- before GELO data exists, `/pilot` may already show forecast, prioritization, and scenario splits
- only after GELO data flows does this reporting layer become the commercial validation surface

Relevant files:

- `/Users/davidwegener/Desktop/viralflux/backend/app/services/media/pilot_reporting_service.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/api/media.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/models/database.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/services/media/truth_layer_service.py`

The goal is not media mix modeling. The goal is a reproducible audit layer that answers:

- what was recommended
- what was activated
- what happened afterwards
- what evidence exists for or against the recommendation

## Integration Point

The reporting layer sits after the operational recommendation flow and after the Forecast-First pilot surface.

Current path:

1. Forecast
2. Decision
3. Allocation
4. Campaign recommendation
5. Customer-facing `pilot-readout`
6. Pilot reporting / ROI audit

The reporting layer does not rewrite epidemiological or allocation logic. It reads persisted recommendation and outcome records and turns them into an audit-ready readout.

## Forecast-First vs Commercial Validation

### Forecast-First

This is the first product layer for PEIX / GELO.

It is already valid when:

- the active scope is forecast-ready
- regions can be prioritized
- scenario-based budget splits can be shown
- commercial evidence is still pending

### Commercial Validation

This reporting layer becomes commercially relevant when:

- GELO spend and outcome data are ingested
- activations and holdouts are visible
- before/after and lift evidence can be attached to the same recommendation chain

Until then, ROI language stays out of the primary customer claim.

## Data Sources

The current implementation is intentionally pragmatic and deterministic.

### Recommendation history

Primary source:

- `MarketingOpportunity`

Used fields include:

- `opportunity_id`
- `status`
- `brand`
- `product`
- `activation_start`
- `activation_end`
- `recommendation_reason`
- `campaign_payload`
- `created_at`
- `updated_at`

Recommendation cards are normalized through the existing internal helper in `MarketingOpportunityEngine._model_to_dict(...)` so that reporting uses the same persisted opportunity shape as the operational media UI.

### Activation history

Primary source:

- `AuditLog`

Used to reconstruct workflow transitions such as:

- `READY -> APPROVED`
- `APPROVED -> ACTIVATED`

Current limitation:

- the system does not yet have a separate event-sourcing table for activations
- activation history is therefore derived from workflow state plus audit trail

### Outcome evidence

Source preference:

1. `OutcomeObservation`
2. `MediaOutcomeRecord` fallback

This matches the existing truth-layer preference so that reporting does not invent a second outcome-normalization path.

## API

Endpoint:

- `GET /api/v1/media/pilot-reporting`

Wichtig:

- `pilot-reporting` ist jetzt ein Legacy-/Backoffice-Readout für historische ROI-Analysen.
- Die kundennahe Pilot-Oberflaeche nutzt stattdessen `GET /api/v1/media/pilot-readout`.
- `pilot-readout` ist damit die Forecast-First-Leseschicht.
- `pilot-reporting` ist die spätere Commercial- und Audit-Schicht.

Supported query parameters:

- `brand`
- `lookback_weeks`
- `window_start`
- `window_end`
- `region_code`
- `product`
- `include_draft`

Validation behavior:

- `lookback_weeks` is constrained at the API layer
- `window_end < window_start` returns `422`
- empty result sets still return a stable reporting payload

## Output Sections

The reporting payload contains these top-level blocks.

### 1. `recommendation_history`

One item per persisted recommendation.

Includes at least:

- `opportunity_id`
- `created_at`
- `updated_at`
- `current_status`
- `status_history`
- `brand`
- `product`
- `region_codes`
- `priority_score`
- `signal_score`
- `signal_confidence_pct`
- `event_probability_pct`
- `activation_window`
- `lead_time_days`
- `recommendation_summary`

### 2. `activation_history`

One item per recommendation that has activation-relevant workflow evidence.

Includes at least:

- `opportunity_id`
- `current_status`
- `approved_at`
- `activated_at`
- `activation_window`
- `lead_time_days`
- `product`
- `region_codes`
- `weekly_budget_eur`
- `total_flight_budget_eur`

### 3. `before_after_comparison`

One item per region scope.

Includes at least:

- `region_code`
- `product`
- `before_window`
- `after_window`
- `before`
- `after`
- `primary_metric`
- `before_value`
- `after_value`
- `delta_absolute`
- `delta_pct`
- `outcome_support_status`
- `truth_assessment`

`before` and `after` contain aggregated metric summaries over the matched windows.

### 4. `region_evidence_view`

Region-level rollup for pilot readouts.

Includes at least:

- `region_code`
- `region_name`
- `recommendations`
- `activations`
- `avg_priority_score`
- `avg_lead_time_days`
- `avg_after_delta_pct`
- `hit_rate`
- `agreement_with_outcome_signals`
- `dominant_evidence_status`
- `top_products`

### 5. `pilot_kpi_summary`

Compact KPI block for PEIX / GELO review rounds.

Current KPI set:

- `hit_rate`
- `early_warning_lead_time_days`
- `share_of_correct_regional_prioritizations`
- `agreement_with_outcome_signals`

## KPI Definitions

### Hit rate

Definition:

- share of activated scopes with a positive primary KPI delta
- and at least moderate signal/outcome agreement

This is intentionally strict. A positive delta alone is not counted as a clean hit.

### Early warning lead time

Definition:

- days between recommendation creation and activation window start

The report exposes average and median lead time.

### Share of correct regional prioritizations

Definition:

- looks at scopes with outcome evidence and a priority score
- computes the median priority score
- evaluates above-median scopes
- counts supportive and directional-positive results as correct prioritizations

This gives a simple pilot-grade answer to whether the system placed attention in mostly sensible regions.

### Agreement with outcome signals

Definition:

- share of assessed scopes with `moderate` or `strong` signal/outcome agreement

This metric comes from the existing truth-layer agreement logic and remains optional.

## Before/After Methodology

The current implementation uses the recommendation activation window as the anchor.

For each scope:

1. derive the active/after window from the persisted activation range
2. derive a matched pre-window with the same duration immediately before activation
3. aggregate only observations that fall fully inside the respective window
4. choose the primary KPI from a fixed metric precedence
5. compute absolute and relative delta
6. combine the delta with truth-layer agreement status

Primary KPI precedence is currently:

1. `revenue`
2. `orders`
3. `sales`
4. `search_demand`
5. `qualified_visits`
6. `campaign_response`
7. `clicks`
8. `impressions`

## Reproducibility

The reporting layer is designed for repeatable pilot readouts.

Reproducibility comes from:

- persisted `MarketingOpportunity` rows
- persisted `AuditLog` transitions
- persisted `OutcomeObservation` or `MediaOutcomeRecord` rows
- explicit reporting windows

Practical guidance:

- use explicit `window_start` and `window_end` for PEIX / GELO readout snapshots
- avoid relying only on the rolling `lookback_weeks` window when exporting a final pilot deck

## Empty-State Behavior

If no recommendations are found for the selected scope:

- `recommendation_history` is `[]`
- `activation_history` is `[]`
- `region_evidence_view` is `[]`
- `before_after_comparison` is `[]`
- KPI values stay `null` where no evidence exists

This is intentional. The endpoint stays stable and explainable instead of returning inconsistent shapes.

## Current Limits

The current layer is useful for pilot readouts, but it is not a full causal measurement system.

Known limits:

- no full MMM or incrementality model
- activation history is reconstructed from workflow state and audit logs
- before/after comparison is heuristic and can be influenced by concurrent market effects
- region scopes are as good as the persisted campaign targeting information
- outcome evidence remains optional; missing evidence does not break the payload

## Recommended PEIX / GELO Readout Flow

For a pilot review:

1. call `/api/v1/media/pilot-reporting` with explicit reporting dates for historical ROI analysis
2. review `pilot_kpi_summary`
3. inspect `region_evidence_view` for directional wins and misses
4. inspect `before_after_comparison` for the strongest and weakest scopes
5. cross-check `recommendation_history` and `activation_history` to explain what was recommended versus what actually went live

This gives a pragmatic evidence layer for commercial discussion without replacing the existing forecast and decision stack.
