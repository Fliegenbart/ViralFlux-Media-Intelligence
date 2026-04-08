# Technical Audit: Current State

Audit date: 2026-03-16

## Scope

This document is a repository-grounded audit of the current implementation state in `ViralFlux-Media-Intelligence`.

Rules used for this audit:

- Only code that exists in this repository is considered.
- No claims are made about systems, models, jobs, or dashboards that are not present in code.
- `partial` means a capability is present, but only partly aligned with the target state.
- `legacy` means a capability is implemented and used, but is still aligned to an older framing or horizon.
- `experimental` means code exists, but it is not the primary delivery path visible in the current API/UI structure.
- This is a code audit, not a runtime validation. The repository snapshot was inspected; no claim is made that external services are currently reachable.

## Executive Summary

The current codebase already contains a substantial foundation for a 3-7 day regional virus-to-media system, but it is split across two generations of logic:

1. A legacy national forecasting line centered on 14-day daily forecasts.
2. A newer regional pooled-panel line explicitly designed for 3-7 day state-level wave prediction.

What already exists in code:

- Broad ingestion coverage for AMELAG, GrippeWeb, ARE consultations, IfSG influenza/RSV, emergency admissions, SurvStat, weather, humidity, pollen, school holidays, Google Trends, and BfArM shortage data.
- A strong regional feature builder for leakage-safe state-level inference.
- A regional training and inference stack with backtesting, calibration, quality gates, benchmark views, and media activation outputs.
- A media decision layer with cockpit, regions view, campaigns view, evidence view, outcome import, truth/business gates, and recommendation workflows.
- Monitoring and governance primitives including forecast accuracy logs, drift detection, market/customer backtests, `/health`, `/metrics`, and admin-triggered training.

What is not yet aligned to the target state:

- The repository still carries 14-day assumptions in core configuration and in the national forecast line.
- Regional predictions are generated from model artifacts on disk; there is no dedicated persistence layer for regional forecast outputs in the database schema.
- Forecast-to-media budget allocation is still heuristic and rules-based; there is no learned media budget optimizer tied to customer outcomes.
- Several media and playbook paths are still GELO-branded or GELO-hardcoded rather than PEIX-generic.
- Outcome integration is present, but currently centered on CSV import and observational scoring, not on a production outcome connector or a causal budget-response model.
- The repository snapshot does not contain committed model artifacts in `backend/app/ml_models/`; runtime depends on generated artifacts.

## Capability Audit

### 1. Data pipelines

Observed status:

- AMELAG wastewater ingest exists and writes both aggregated and site-level data.
- GrippeWeb, ARE consultations, influenza, RSV, and emergency admission ingestion exist.
- Weather, humidity, pollen, holidays, Trends, and BfArM ingest exist.
- SurvStat exists in three forms:
  - local weekly file importer,
  - transposed web-export importer,
  - SOAP/OLAP API importer for county-level data.
- Celery orchestration exists for a full ingestion pipeline.

Assessment:

- Data pipeline coverage is `yes` for the core epidemiological stack.
- Regional SurvStat truth is `yes`, because county-level storage and county-to-state aggregation code exist.
- Trends are `partial`, because current ingestion is national (`region='DE'`) and keyword-based.
- Weather is `partial`, because regionalization is approximated via 16 state capitals rather than a denser spatial coverage.
- Outcome data ingestion is `partial`, because customer truth is imported via CSV/record payloads, not via a dedicated production system connector.

### 2. Forecast models

Observed status:

- `ForecastService` implements a national stacking forecast using Holt-Winters, Ridge, Prophet, and XGBoost.
- `XGBoostTrainer` and Celery training tasks exist for national model promotion.
- `RegionalModelTrainer` implements pooled regional per-virus training with calibrated event probabilities, quantile regressors, walk-forward backtests, and quality gates.
- `RegionalForecastService` exposes 3-7 day ranked regional predictions and portfolio views.
- `WavePredictionService` exists as a separate stage-1 wave-prediction path.

Assessment:

- National forecasting exists, but is `legacy` relative to the stated target because it still uses 14-day defaults.
- Regional 3-7 day forecasting exists and is the strongest match to the target state.
- The separate `WavePredictionService` is `partial`/`experimental` because it still targets `target_wave14` and 14-day defaults.

### 3. Feature builders

Observed status:

- `RegionalFeatureBuilder` assembles leakage-safe state-level features from wastewater, SurvStat county truth, GrippeWeb, ARE, Notaufnahme, influenza, RSV, weather, humidity, pollen, holidays, and Trends.
- National forecast feature building exists in `ForecastService.prepare_training_data`.

Assessment:

- Regional feature building is `yes` for the target 3-7 day path.
- National feature building exists, but remains tied to the legacy national forecast path.
- Google Trends in the regional stack are `partial`, because the current regional feature builder uses national Trends and a narrow SARS-specific query.

### 4. Regional forecast logic

Observed status:

- `regional_panel_utils.py` defines `TARGET_WINDOW_DAYS = (3, 7)` and `EVENT_DEFINITION_VERSION = "regional_survstat_v2"`.
- API endpoints expose `/forecast/regional`, `/forecast/regional/predict`, `/forecast/regional/media-activation`, `/forecast/regional/benchmark`, `/forecast/regional/portfolio`, `/forecast/regional/validation`, and `/forecast/regional/backtest`.
- Frontend decision and region views consume regional benchmark and portfolio endpoints.

Assessment:

- Regional forecast logic for the next 3-7 days exists in code and is API-exposed.
- Forecast persistence is `no` for this path: there is no dedicated regional prediction table in the schema, and the runtime reads artifacts from disk.

### 5. Media and decision components

Observed status:

- Media cockpit payloads exist.
- Decision, regions, campaigns, and evidence payloads exist.
- Recommendation generation, region opening, AI regeneration, sync preparation, product catalog management, and weekly brief endpoints exist.
- Outcome truth coverage, truth gate, business gate, and outcome learning layers exist.
- Frontend pages and cockpit components exist for all main media workflows.

Assessment:

- Media decision support exists.
- Forecast-to-media recommendation exists, but is `partial` relative to the target:
  - the current system prioritizes and packages campaigns,
  - but budget movement is derived from heuristics and gates, not from a learned media optimization model.
- Outcome learning exists, but is `partial`:
  - it scores observed response by product/region,
  - it does not yet estimate concrete expected units/revenue lift from a trained causal or response model.

### 6. Quality, drift, and monitoring

Observed status:

- `ForecastAccuracyLog` persists rolling accuracy metrics and drift flags.
- `BacktestRun` and `BacktestPoint` persist market/customer backtest outputs.
- `BacktestService` computes decision metrics, interval coverage, event calibration, lead/lag, and quality gates.
- `ForecastDecisionService.build_monitoring_snapshot` is wired into `/health` and forecast monitoring endpoints.
- Prometheus metrics are exposed via `/metrics`.
- There are dedicated tests for regional forecast, forecast decisioning, media v2, business validation, and accuracy metrics.

Assessment:

- Monitoring and quality controls exist and are one of the stronger parts of the repository.
- The quality stack is mixed across old and new forecasting lines, so alignment to a single 3-7 day production path is still `partial`.

## File Inventory

Note: the tables below cover the files most relevant to the target system. Generic plumbing, styling, and unrelated pages are intentionally omitted.

### Core runtime and schema

| File | Purpose | Reifegrad | Technical debt | Gap vs target state |
| --- | --- | --- | --- | --- |
| `backend/app/main.py` | FastAPI entrypoint, router wiring, `/health`, `/metrics` | mature | App description still says `14-Tage-Frühsignal`; health combines mixed legacy/new signals | Core runtime is not yet framed around a single 3-7 day PEIX product path |
| `backend/app/core/config.py` | Global settings for forecast and wave services | legacy | `FORECAST_DAYS = 14` and `WAVE_PREDICTION_HORIZON_DAYS = 14` remain default | Core configuration is not yet centered on max 7-day horizons |
| `backend/app/models/database.py` | Persistence schema for ingest, forecast, backtest, media, and outcome tables | mature | Mixed schema generations; no dedicated regional prediction storage | No database-native persistence for regional 3-7 day forecast outputs |

### Data ingestion

| File | Purpose | Reifegrad | Technical debt | Gap vs target state |
| --- | --- | --- | --- | --- |
| `backend/app/services/data_ingest/amelag_service.py` | AMELAG wastewater import, site mapping, aggregated writes | mature | Static coordinate mapping for plants | Strong fit; no major target gap in current scope |
| `backend/app/services/data_ingest/grippeweb_service.py` | GrippeWeb TSV ingest | mature | Seasonal lookback is hardcoded to recent seasons | No structural blocker for target state |
| `backend/app/services/data_ingest/are_konsultation_service.py` | ARE consultation ingest | mature | Seasonal lookback is hardcoded | No structural blocker for target state |
| `backend/app/services/data_ingest/er_admissions_service.py` | Emergency admission and site metadata ingest | mature | Separate source path from regional forecast artifacts | No structural blocker for target state |
| `backend/app/services/data_ingest/influenza_service.py` | IfSG influenza ingest | mature | Standard weekly ingest only | No structural blocker for target state |
| `backend/app/services/data_ingest/rsv_service.py` | IfSG RSV ingest | mature | Standard weekly ingest only | No structural blocker for target state |
| `backend/app/services/data_ingest/survstat_service.py` | Local weekly SurvStat file import into `SurvstatWeeklyData` | partial | Upsert map key ignores `age_group`; local-file workflow only | Useful for weekly truth, but not a clean production regional truth path on its own |
| `backend/app/services/data_ingest/survstat_export_importer.py` | Import transposed SurvStat web exports | partial | `nach_bundesland` and `nach_landkreis` write yearly aggregate `week=0` records | Does not provide weekly regional truth suitable for 3-7 day forecasting |
| `backend/app/services/data_ingest/survstat_api_service.py` | County-level SurvStat SOAP/OLAP ingest plus population sync | mature | Operational complexity and external SOAP dependency | Strong fit for regional truth generation |
| `backend/app/services/data_ingest/weather_service.py` | BrightSky/DWD ingest for observations and next-day forecast horizon | partial | Regional coverage is proxied by 16 capitals | Weather and humidity exist, but not at a finer regional granularity |
| `backend/app/services/data_ingest/holidays_service.py` | School holiday import and helpers | mature | API-based yearly refresh only | Good fit; no major blocker |
| `backend/app/services/data_ingest/trends_service.py` | Google Trends ingest for fixed keywords in `DE` | partial | National-only, fixed keyword set, rate-limit-sensitive | Trends are present but not regionalized |
| `backend/app/services/data_ingest/pollen_service.py` | DWD pollen ingest by region code | mature | Mapping simplifications between DWD regions and states | Pollen context exists; target state does not require more at this phase |
| `backend/app/services/data_ingest/bfarm_service.py` | BfArM shortage ingest and cache helpers | mature | Supply signal is separate from epi truth | Context signal only, not core forecast truth |
| `backend/app/services/data_ingest/tasks.py` | Celery orchestration for full data ingestion | mature | Single broad task mixes core and context sources | No target blocker, but not yet separated into target-state domain jobs |

### Forecasting and ML

| File | Purpose | Reifegrad | Technical debt | Gap vs target state |
| --- | --- | --- | --- | --- |
| `backend/app/services/ml/forecast_service.py` | National daily stacking forecast using wastewater target and auxiliary features | legacy | Still centered on 14-day national forecasts; mixed feature conventions | Not the target 3-7 day regional delivery path |
| `backend/app/services/ml/model_trainer.py` | Offline XGBoost training/promotion for national forecasts | mature | Promotes the legacy national line, not the regional line | Useful for legacy stack, not sufficient for target path |
| `backend/app/services/ml/forecast_decision_service.py` | Converts forecasts/backtests/truth readiness into decision contracts | partial | `expected_units_lift` and `expected_revenue_lift` stay `None`; mixes legacy and new gates | Strong bridge layer, but not yet a full forecast-to-media economics model |
| `backend/app/services/ml/regional_panel_utils.py` | Shared constants, event definitions, rollout policies, regional metrics | mature | Separate utility layer from national config | Strong fit for 3-7 day target path |
| `backend/app/services/ml/regional_features.py` | Leakage-safe state-level feature builder using county truth and context features | mature | National Trends reused in regional path; weather proxy comes from capitals | Strong fit; Trends/weather granularity remains partial |
| `backend/app/services/ml/regional_trainer.py` | Regional pooled-panel training, calibration, artifact persistence, quality gates | mature | Artifact-based deployment; no DB-native model registry | Strong fit for regional 3-7 day forecasting |
| `backend/app/services/ml/regional_forecast.py` | Loads regional artifacts, produces ranked state predictions, media activation, benchmark, portfolio | partial | Hardcoded `GELO_PRODUCTS`, channel mixes, and artifact-only runtime dependency | Regional inference exists, but PEIX-generic activation and persistence are not finished |
| `backend/app/services/ml/regional_backtest.py` | Regional backtest access layer | mature | Depends on artifact availability | Strong fit for target QA needs |
| `backend/app/services/ml/backtester.py` | Market/customer backtesting, calibration, quality gate, persistence | mature | Large mixed-scope service with legacy and new concerns combined | Strong fit for validation; needs alignment to one target path |
| `backend/app/services/ml/tasks.py` | Celery ML tasks for national training, accuracy logging, regional training | mature | Forecast accuracy task is still based on legacy national forecast tables | Monitoring exists, but target path alignment is partial |
| `backend/app/services/ml/wave_prediction_service.py` | Separate wave prediction pipeline with classifier/regressor/backtest | experimental | Uses `target_wave14` and 14-day defaults; separate from main regional API path | Not aligned with the requested max 7-day target state |

### Media, decisioning, and playbooks

| File | Purpose | Reifegrad | Technical debt | Gap vs target state |
| --- | --- | --- | --- | --- |
| `backend/app/services/media/peix_score_service.py` | Unified epidemiological score for regions and drivers | partial | Heuristic weighting layer mixing forecast, shortage, weather, search, and baseline | Useful prioritization layer, but not a standalone 3-7 day probability model |
| `backend/app/services/media/cockpit_service.py` | Aggregates map, bento, backtest summary, freshness, and recommendation refs | mature | Mixes wastewater map views with PEIX score fallback | Strong product read-model; no major blocker |
| `backend/app/services/media/v2_service.py` | Decision, regions, campaigns, evidence, outcome import, truth coverage, model lineage contracts | mature | Large service with many responsibilities | Strong delivery layer; still relies on heuristic learning and CSV truth onboarding |
| `backend/app/services/media/business_validation_service.py` | Converts truth coverage and holdout evidence into commercial readiness | mature | Business gate depends on imported outcome semantics in `extra_data` | Good gating layer; not a response model |
| `backend/app/services/media/outcome_signal_service.py` | Builds observational response signals by product/region | partial | Aggregates historical response; no causal lift estimation | Outcome scoring exists, but budget optimization does not |
| `backend/app/services/media/truth_gate_service.py` | Normalizes truth coverage into readiness states | mature | Threshold logic is rule-based | Good operational gate; no blocker |
| `backend/app/services/media/product_catalog_service.py` | Brand catalog refresh, product-condition mappings, approval workflow | mature | Brand and rule sets remain GELO-oriented by default | Product mapping exists, but PEIX-general multi-brand abstraction is partial |
| `backend/app/services/marketing_engine/opportunity_engine.py` | Opportunity orchestration, persistence, playbook and AI package generation | partial | Budget shift and readiness are heuristic; workflow mixes legacy and new status models | Useful campaign factory, but not yet a learned media decision engine |
| `backend/app/services/media/playbook_engine.py` | Rule-based playbook candidate selection from PEIX and context signals | partial | Fixed playbooks, fixed channel mixes, GELO condition framing | Good tactical layer; not PEIX-generic and not outcome-optimized |
| `backend/app/services/media/ai_campaign_planner.py` | Local vLLM-based campaign copy/planning with fallback template | partial | Generates structured plans, not budget or allocation optimization | Helpful execution assistant, not part of core prediction science |

### APIs

| File | Purpose | Reifegrad | Technical debt | Gap vs target state |
| --- | --- | --- | --- | --- |
| `backend/app/api/forecast.py` | National forecast, monitoring, accuracy, and regional forecast/media endpoints | mature | Mixes legacy national and target regional paths in one router | API surface already exposes target path, but legacy defaults remain present |
| `backend/app/api/media.py` | Cockpit, decision, regions, campaigns, evidence, outcomes, recommendations, products, weekly brief | mature | Broad router with mixed read/write responsibilities | Strong product API; PEIX genericity remains partial |
| `backend/app/api/backtest.py` | Market and customer backtests, business pitch, wave radar, top regions | mature | Large mixed analytical surface with legacy naming and targets | Strong validation API; not yet simplified around the target operating model |
| `backend/app/api/admin_ml.py` | Admin training endpoints for national and regional models | mature | Regional and national training remain separate operational paths | Good ops surface; target path still split across multiple model families |

### Frontend media product

| File | Purpose | Reifegrad | Technical debt | Gap vs target state |
| --- | --- | --- | --- | --- |
| `frontend/src/features/media/api.ts` | Frontend API client for decision, regions, campaigns, evidence, outcomes, regional benchmark/portfolio | mature | Frontend is coupled to current endpoint layout | Strong fit for existing product path |
| `frontend/src/features/media/useMediaData.ts` | Page-level data loading for decision, regions, campaigns, evidence | mature | Request composition mirrors current mixed backend contracts | Strong fit for current UI |
| `frontend/src/pages/media/DecisionPage.tsx` | Loads weekly decision, evidence, wave outlook, regional benchmark, regional portfolio | mature | Depends on multiple backend paths at once | Strong fit for current decision workflow |
| `frontend/src/pages/media/RegionsPage.tsx` | Regional prioritization flow and open-or-create region campaign action | mature | Still creates GELO-branded region campaigns by default | Strong fit for current workflow; PEIX-genericity is partial |
| `frontend/src/pages/media/CampaignsPage.tsx` | Campaign generation and campaign board entry page | mature | Generation uses GELO defaults and fixed channel pool | Good current product surface, not yet PEIX-generic |
| `frontend/src/pages/media/EvidencePage.tsx` | Evidence and truth import page | mature | Outcome onboarding is still file-centric | Strong fit for governance and validation |
| `frontend/src/components/cockpit/DecisionView.tsx` | Main decision UI with GO/WATCH state, regional focus, and evidence summary | mature | UI copy still says `ViralFlux for GELO` | Product framing is not yet PEIX-neutral |
| `frontend/src/components/cockpit/RegionWorkbench.tsx` | Region inspector, Germany map, top-region panel, generate/open recommendation actions | mature | Budget guidance remains heuristic and explanation-based | Strong operational UI for region prioritization |
| `frontend/src/components/cockpit/CampaignStudio.tsx` | Campaign workflow board with generation and lane-based review | mature | UI is downstream of heuristic prioritization | Good operational surface; not a budget optimizer |
| `frontend/src/components/cockpit/EvidencePanel.tsx` | Forecast/truth/source/import evidence tabs | mature | Mirrors current mixed evidence contracts | Strong governance UI |

### Tests and automated safeguards

| File | Purpose | Reifegrad | Technical debt | Gap vs target state |
| --- | --- | --- | --- | --- |
| `backend/app/tests/test_regional_forecast_service.py` | Validates regional prediction payloads, business gate behavior, and media activation policies | mature | Uses stubbed artifacts rather than real persisted artifacts | Good coverage of target regional path |
| `backend/app/tests/test_forecast_decision_service.py` | Validates forecast bundle, monitoring snapshot, and truth readiness behavior | mature | Focuses more on contract behavior than end-to-end runtime | Good decision-layer coverage |
| `backend/app/tests/test_media_v2_service.py` | Validates outcome import, truth coverage, duplicates, and stale truth handling | mature | Service-level tests only | Good truth/media service coverage |
| `backend/app/tests/test_media_v2_api.py` | Validates media API endpoints for outcomes and recommendation list fields | mature | API tests depend on patched services for some flows | Good contract-level API coverage |
| `backend/app/tests/test_ml_tasks_accuracy.py` | Validates like-for-like forecast accuracy metric logic | mature | Covers a narrow task path only | Good targeted guard for drift logic |
| `backend/app/tests/test_wave_prediction_service.py` | Covers separate wave prediction path | partial | Protects an experimental path that is not the main target delivery path | Experimental path remains outside the main production target |

## Confirmed Gaps Against the Target State

These gaps are grounded in existing code and schema only.

1. Horizon alignment gap

- The target state requires max 7 days.
- The repository still defaults to 14 days in `backend/app/core/config.py`, `backend/app/services/ml/forecast_service.py`, `backend/app/services/ml/wave_prediction_service.py`, and the app description in `backend/app/main.py`.

2. Single-path architecture gap

- The repository contains at least three forecast lines:
  - national stacking forecast,
  - regional pooled-panel forecast,
  - separate wave prediction service.
- The target state needs a single production path for 3-7 day regional forecasting.

3. Regional prediction persistence gap

- `RegionalForecastService` loads artifacts from disk.
- The schema has no dedicated table for regional forecast outputs.
- The repository snapshot contains no committed model artifacts beyond `.gitkeep` in `backend/app/ml_models/`.

4. Outcome-to-budget modeling gap

- Forecast-to-decision contracts exist.
- Outcome truth import exists.
- Business validation exists.
- Observational outcome scoring exists.
- Concrete expected units/revenue lift is still explicitly left unset in `ForecastDecisionService.build_opportunity_assessment`.
- There is no learned media budget optimizer or response model in the inspected code.

5. PEIX productization gap

- Multiple backend and frontend paths are still GELO-specific:
  - hardcoded products in `regional_forecast.py`,
  - GELO-focused playbooks and product mappings,
  - `ViralFlux for GELO` UI copy in `DecisionView.tsx`,
  - default brand values across media APIs and pages.

6. Regional context granularity gap

- Weather is state-capital based, not broader regional weather coverage.
- Trends are ingested only for `DE`, not state/county level.

7. Outcome operations gap

- Customer truth is onboarded via CSV or JSON payload import.
- `MediaV2Service.get_truth_evidence()` explicitly notes that the current customer-data area is based on validated CSV import, not a direct customer-system API.

8. SurvStat ingestion consistency gap

- The local weekly SurvStat importer parses age groups, but its `existing_map` upsert key is only `(week_label, bundesland, disease)`.
- The schema stores `age_group`, so age-group-specific imports can collide in the current implementation.

## Staged Development Roadmap

This roadmap only derives from the observed codebase and the gaps above.

### Stage 1: Freeze the target path around the regional 3-7 day stack

Goal:

- Make the regional pooled-panel path the primary production line for 3-7 day forecasting.

Concrete next steps:

- Make the 3-7 day regional path the primary documented product path in code and docs.
- Move core config defaults from 14 days to max 7 days where still set globally.
- Deprecate or clearly isolate the legacy national 14-day path and the separate `WavePredictionService` path.

### Stage 2: Persist regional predictions and model lineage

Goal:

- Turn regional inference from artifact-only runtime output into a traceable production record.

Concrete next steps:

- Add a database table for regional forecast runs and per-region predictions.
- Persist generated regional predictions, thresholds, artifact version, and business gate state.
- Keep forecast-to-media decisions reproducible from stored prediction snapshots.

### Stage 3: Harden the regional truth layer

Goal:

- Make SurvStat-based regional truth cleaner and operationally safer.

Concrete next steps:

- Fix the age-group collision risk in the local SurvStat weekly importer.
- Standardize on the county-level SurvStat API path plus explicit weekly aggregation rules.
- Keep export-based imports as fallback or historical import tools, not as the primary truth path.

### Stage 4: Upgrade context features for regional decision quality

Goal:

- Improve regional explanatory power without expanding beyond the current target horizon.

Concrete next steps:

- Regionalize Trends or define a clear replacement if regional Trends are not available.
- Replace state-capital weather proxies with a denser or population-weighted regional weather representation.
- Keep humidity, holidays, and pollen in the feature set, but standardize their freshness and source coverage contracts.

### Stage 5: Move from heuristic activation to learned media decisioning

Goal:

- Convert the current decision-support/media layer into a measurable budget decision layer.

Concrete next steps:

- Keep existing truth gate and business gate as release controls.
- Introduce a learned response model for spend-to-outcome behavior by region/product/channel.
- Replace heuristic `budget_shift_pct` and channel defaults with model-backed recommendations where truth coverage is sufficient.

### Stage 6: Generalize from GELO-branded implementation to PEIX operator product

Goal:

- Remove brand-specific assumptions from the core product layer.

Concrete next steps:

- Move GELO defaults into brand configuration rather than core services.
- Generalize playbooks, product mappings, UI copy, and activation outputs for PEIX as operator.
- Keep brand-specific catalogs and mappings as tenant or partner data, not as hardcoded runtime defaults.

### Stage 7: Production readiness and operating model

Goal:

- Make the target-state system operationally auditable and supportable.

Concrete next steps:

- Standardize one forecast path, one training path, one persistence path, and one monitoring path.
- Expand runbooks around artifact generation and deployment, because the repo snapshot currently contains no committed model artifacts.
- Use the existing backtest, drift, truth, and evidence contracts as the release checklist for model promotion.

## Bottom Line

The repository already contains the essential building blocks for a regional 3-7 day virus-to-media system:

- ingestion,
- regional features,
- regional model training,
- ranked regional inference,
- decision surfaces,
- evidence gates,
- and monitoring.

The main work is not inventing these pieces from zero. The main work is consolidating them into one production path, removing 14-day legacy assumptions, persisting regional outputs, and replacing heuristic media activation with outcome-backed decisioning.
