# Media Allocation Engine V1

## Scope

This document describes the first production-near heuristic media allocation layer implemented in:

- `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_media_allocation_engine.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_media_allocation_contracts.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_forecast.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/api/forecast.py`

The engine converts regional decision output into explainable budget and prioritization recommendations for PEIX / GELO.

This is not MMM, attribution or ROI modeling. It is an explicit heuristic layer.

Canonical upstream remains:

- `RegionalForecastService.predict_all_regions()`

The existing regional decision hook is not moved or recomputed inside allocation.

## Current Inputs

The engine consumes the already integrated regional decision output per Bundesland.

Primary inputs per region:

- `decision.stage`
- `decision_score` / `priority_score`
- `event_probability_calibrated`
- `decision.forecast_confidence`
- `decision.source_freshness_score`
- `decision.usable_source_share`
- `decision.source_coverage_score`
- `decision.source_revision_risk`
- `reason_trace.uncertainty`
- optional `state_population_millions`

The service wrapper also preserves existing operational gates from the media activation path:

- `quality_gate`
- `activation_policy`
- existing `business_gate`

Important: the allocation engine itself is decision-driven and does not integrate the new optional truth-layer from the separate GELO outcome work.

## Output

Per region, the allocation layer returns at least:

- `recommended_activation_level`
- `spend_readiness`
- `priority_rank`
- `suggested_budget_share`
- `suggested_budget_eur`
- `suggested_budget_amount`
- `allocation_score`
- `confidence`
- `reason_trace`
- `allocation_reason_trace`

Compatibility rule in V1 hardening:

- `suggested_budget_amount` is an additive alias for `suggested_budget_eur`
- `allocation_reason_trace` is an additive alias for `reason_trace`
- existing field names remain valid and unchanged

The service wrapper currently adds dashboard-ready convenience fields:

- `action`
- `intensity`
- `channels`
- `products`
- `timeline`
- `product_clusters`
- `keyword_clusters`

The API exposes the payload via:

- `GET /api/v1/forecast/regional/media-activation`
- `GET /api/v1/forecast/regional/media-allocation`

## Heuristic Design

### 1. Base activation comes from the regional decision engine

The allocation layer does not invent a new epidemiological stage.

It starts from:

- `Activate`
- `Prepare`
- `Watch`

`recommended_activation_level` is derived directly from `decision.stage`.

### 2. Allocation score

The engine computes an `allocation_score` as:

```text
weighted_signal_score
* label_weight(stage, risk_appetite)
* confidence_penalty
* region_weight
```

Where `weighted_signal_score` is built from these components:

| Component | Weight |
| --- | ---: |
| `priority_score` | 0.34 |
| `event_probability` | 0.24 |
| `forecast_confidence` | 0.18 |
| `source_quality` | 0.14 |
| `source_freshness` | 0.05 |
| `population_weighting` | 0.05 |

`source_quality` is currently the mean of:

- `source_freshness_score`
- `usable_source_share`
- `source_coverage_score`
- `1 - source_revision_risk`

### 3. Label weights

Base stage weights:

| Stage | Base weight |
| --- | ---: |
| `Activate` | 1.00 |
| `Prepare` | 0.58 |
| `Watch` | 0.08 |

These are further adjusted by `risk_appetite`:

- `Activate`: stays strongest
- `Prepare`: becomes more or less aggressive depending on appetite
- `Watch`: remains weak and observation-first

In V1, `risk_appetite = 0.60`.

### 4. Confidence and penalties

The engine computes a separate `confidence` score from:

- forecast confidence
- source quality
- number of uncertainty flags

Current thresholds:

| Confidence band | Threshold | Penalty multiplier |
| --- | ---: | ---: |
| low | `< 0.45` | 0.55 |
| medium | `< 0.60` | 0.82 |
| strong | `>= 0.60` | 1.00 |

Additional penalties apply when:

- `source_freshness_score < 0.50`
- `source_revision_risk > 0.55`

This is how low-confidence or stale-data regions are explicitly downweighted.

### 5. Optional region weighting

V1 hardening adds optional `region_weights`.

Design:

- keyed by Bundesland code with tolerant fallback to state name
- default weight is `1.0`
- applied only inside allocation, never inside the decision engine
- useful for explicit PEIX steering without duplicating forecast or decision logic

### 6. Optional population weighting

If `state_population_millions` is available, the engine adds a small logarithmic population term.

Current defaults:

- enabled: `true`
- population reference: `8.0` million

Population weighting is intentionally small and does not override the decision stage.

## Budget Distribution Rules

### Budget config

Current V1 config:

| Parameter | Value |
| --- | ---: |
| baseline total budget | 50,000 EUR |
| min budget per active region | 3,000 EUR |
| max budget share per region | 0.55 |
| spend-enabled labels | `Prepare`, `Activate` |
| watch budget share cap | 0.0 |
| region weights | `{}` |

### Distribution logic

If spend is enabled:

1. only `Prepare` and `Activate` regions are eligible for positive share
2. each eligible region receives a minimum floor based on `min_budget_per_active_region_eur`
3. the remaining share is distributed proportional to `allocation_score`
4. each region is capped by `max_budget_share_per_region`
5. the final shares are normalized so the total equals `1.0`

If spend is not enabled:

- all regions keep rank and explanation
- all `suggested_budget_share` values are `0.0`
- all `suggested_budget_eur` values are `0.0`
- all `suggested_budget_amount` values are `0.0`

## Spend Gates In The Service Wrapper

The engine itself is generic. The current `RegionalForecastService.generate_media_allocation(...)` wrapper decides whether spend is globally enabled.

Spend is blocked when at least one of these applies:

- `activation_policy == "watch_only"`
- `business_gate.validated_for_budget_activation == false`
- `quality_gate.overall_passed == false`

When blocked:

- `recommended_activation_level` still reflects the decision engine
- compatibility field `action` is downgraded to `watch`
- budget stays at zero
- blockers are included in `reason_trace.blockers`

This preserves the current operational behavior of the existing media activation path while still exposing the new allocation logic.

## Empty-State Behavior

If the upstream forecast layer returns:

- `no_model`
- `no_data`
- or an empty region list

the media allocation wrapper still returns a stable allocation payload with:

- `status`
- `message`
- `headline`
- `summary`
- `allocation_config`
- `generated_at`
- empty `recommendations`

This keeps the API dashboard-safe even when no regional allocation can be produced yet.

## Reason Trace

Every allocation recommendation contains:

- `why`
- `budget_drivers`
- `uncertainty`
- `blockers`

Examples of explanation content:

- why the region ranked highly
- whether `Activate` or `Prepare` boosted the score
- whether low confidence reduced spend
- whether budget was blocked by rollout or quality policy

## Product Clusters

V1 already exposes `product_clusters`, but only as a simple heuristic default cluster based on the virus line and `GELO_PRODUCTS`.

Current state:

- product clusters: simple default cluster present
- keyword clusters: empty in V1

This keeps the API extensible without pretending that keyword or CPC optimization already exists.

## API Shape

`/regional/media-allocation` and `/regional/media-activation` currently return:

- top-level `headline`
- top-level `summary`
- top-level `allocation_config`
- `recommendations[]`

Each recommendation includes both new allocation fields and compatibility fields from the older activation payload.

For empty states, the payload additionally includes:

- `status`
- `message`

## Tests

The current implementation is covered by:

- `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_media_allocation_engine.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_forecast_service.py`
- `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_forecast_api.py`

Covered cases include:

- ranking `Activate > Prepare > Watch`
- budget shares sum to `1.0`
- low-confidence regions receive less allocation
- configured `region_weights` can shift ranking inside the allocation layer
- blocked spend produces zero budget
- alias fields stay consistent with the legacy field names
- empty predictions keep a stable response shape
- API response includes allocation fields

## Current Limits

V1 deliberately does not do the following:

- no truth-layer coupling
- no MMM
- no ROI optimization
- no CPC / auction / competition integration
- no keyword selection model
- no outcome-based budget feedback loop

This is a transparent first operational layer on top of epidemiological regional decisions.
