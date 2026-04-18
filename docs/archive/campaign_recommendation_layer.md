# Campaign Recommendation Layer

## Scope

This document describes the operational campaign recommendation layer built on top of the existing regional allocation path.

Relevant files:

- `backend/app/services/media/campaign_recommendation_service.py`
- `backend/app/services/media/campaign_recommendation_contracts.py`
- `backend/app/services/ml/regional_forecast.py`
- `backend/app/api/forecast.py`

Canonical upstream remains:

- `RegionalForecastService.predict_all_regions()`
- `RegionalForecastService.generate_media_allocation()`

This layer does not replace forecast, decision or allocation. It translates those outputs into discussion-ready campaign recommendations for a customer pilot.

## Business Purpose

Allocation says:

- which regions matter
- how strongly they should be prioritized
- how budget could be split

Campaign recommendation adds:

- which product cluster should lead
- which keyword cluster should frame the activation
- whether the budget is strong enough for a standalone push
- why the recommendation is discussable right now

This is not automated media buying. It is an explicit heuristic planning layer.

## Integration Point

The layer is deliberately attached after allocation.

Current path:

1. `predict_all_regions(...)`
2. regional decision hook
3. `generate_media_allocation(...)`
4. `generate_campaign_recommendations(...)`

This keeps the epidemiological core untouched.

## API

The new endpoint is:

- `GET /api/v1/forecast/regional/campaign-recommendations`

Inputs:

- `virus_typ`
- `weekly_budget_eur`
- `horizon_days`
- `top_n`

The endpoint consumes the existing allocation output and returns concrete campaign recommendations per region.

## Config Surface

The layer is configured through `CampaignRecommendationConfig`.

Current config groups:

### 1. Product clusters

Each product cluster defines:

- `cluster_key`
- `label`
- supported products
- supported viruses
- base fit
- activation-level fit

Current default clusters:

- `gelo_core_respiratory`
- `gelo_voice_recovery`
- `gelo_bronchial_support`

### 2. Keyword clusters

Each keyword cluster defines:

- `cluster_key`
- `label`
- parent `product_cluster_key`
- keyword list
- supported viruses
- base fit
- activation-level fit

Current defaults:

- `respiratory_relief_search`
- `voice_relief_search`
- `bronchial_recovery_search`

### 3. Region/product fit

`region_product_fit` is an explicit override map:

- keyed by Bundesland code
- values are per-cluster multipliers

Use case:

- Berlin, Hamburg and Bremen can boost the voice/throat cluster
- Bayern, Baden-Württemberg and Nordrhein-Westfalen can boost the respiratory core cluster
- selected eastern / northern regions can boost bronchial support

This is intentionally heuristic and openly configurable.

### 4. Spend guardrails

The layer uses a small explicit guardrail contract:

- `min_budget_share`
- `min_budget_amount_eur`
- `min_confidence_for_activate`
- `min_confidence_for_prepare`
- blocked spend statuses

The guardrails do not rewrite allocation. They mark whether a recommendation is ready for standalone discussion or should be bundled / held.

## Output Contract

Each recommendation exposes at least:

- `region`
- `region_name`
- `activation_level`
- `priority_rank`
- `suggested_budget_share`
- `suggested_budget_amount`
- `confidence`
- `evidence_class`
- `recommended_product_cluster`
- `recommended_keyword_cluster`
- `recommendation_rationale`
- `spend_guardrail_status`

Compatibility aliases are also included:

- `bundesland`
- `bundesland_name`

### Product cluster output

`recommended_product_cluster` contains:

- `cluster_key`
- `label`
- `fit_score`
- `products`
- `metadata`

### Keyword cluster output

`recommended_keyword_cluster` contains:

- `cluster_key`
- `label`
- `fit_score`
- `keywords`
- `metadata`

### Recommendation rationale

`recommendation_rationale` is structured, not free-form only:

- `why`
- `product_fit`
- `keyword_fit`
- `budget_notes`
- `evidence_notes`
- `guardrails`

This keeps recommendations immediately reviewable by PEIX teams.

## Heuristic Logic

### Product cluster selection

Product-cluster fit is currently built from:

- explicit cluster base fit
- overlap with products already present in allocation output
- activation-level fit
- allocation hint from upstream `product_clusters`
- regional fit multiplier
- confidence

The cluster with the strongest final fit wins.

### Keyword cluster selection

Keyword-cluster fit is built from:

- chosen product-cluster fit
- keyword-cluster base fit
- activation-level fit
- regional fit multiplier
- confidence

The winning keyword cluster becomes the recommendation anchor for immediate discussion.

### Guardrail status

Current statuses:

- `ready`
- `bundle_with_neighbor_region`
- `low_confidence_review`
- `blocked`
- `observe_only`

Interpretation:

- `ready`: campaign can be discussed as a standalone regional activation
- `bundle_with_neighbor_region`: signal is useful, but budget is too small for a clean standalone push
- `low_confidence_review`: the region is interesting, but PEIX should review before operationalizing
- `blocked`: upstream spend gate already blocks execution
- `observe_only`: no active budget recommendation exists

## Evidence Handling

The layer uses the existing truth/commercial overlay if present.

`evidence_class` is derived from:

- truth-backed evidence status from allocation, when available
- otherwise a fallback `epidemiological_only`

This means commercial evidence can harden the recommendation, but does not replace the epidemiological trigger.

## Empty-State Behavior

If allocation returns:

- `no_model`
- `no_data`
- or no recommendations

the campaign layer returns a stable response with:

- `status`
- `message`
- `headline`
- `summary`
- `config`
- `allocation_summary`
- `truth_layer`
- empty `recommendations`

## Current Limits

The current layer is intentionally simple:

- no automated bid management
- no MMM or ROI optimization
- no channel-specific performance learning
- region/product fit is configured heuristically, not learned from causal outcome models
- keyword selection is cluster-based, not generated from live search query mining

That is acceptable for V1 because the goal is operational clarity, not automation theatre.

## Test Coverage

Direct layer tests live in:

- `backend/app/tests/test_campaign_recommendation_service.py`

Integration coverage lives in:

- `backend/app/tests/test_regional_forecast_service.py`
- `backend/app/tests/test_forecast_api.py`

Covered behaviors:

- recommendation ranking
- region/product-fit influence
- explainability / rationale presence
- spend guardrail handling
- empty-state stability
- API passthrough
