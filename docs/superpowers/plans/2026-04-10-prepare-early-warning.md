# Prepare Early Warning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `Prepare` into a real early-warning stage that stays visible without releasing paid budget, while `Activate` remains the only budget-ready stage.

**Architecture:** The change starts in the regional decision engine, because that is where `Watch`/`Prepare`/`Activate` are decided today. Then the plan propagates the new meaning through forecast output, media allocation, campaign recommendations, and the release smoke tests so the whole product speaks the same language.

**Tech Stack:** Python 3.11, FastAPI test client, unittest/pytest, existing ViralFlux ML service modules

---

### File Structure

**Core rule files**
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine_signals.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine_reasoning.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_contracts.py`

**Downstream product surfaces**
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_media_allocation_contracts.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_media_allocation_engine.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/media/campaign_recommendation_scoring.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/media/campaign_recommendation_rationale.py`

**Regression and contract tests**
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_decision_engine.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_forecast_api.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_media_allocation_engine.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_campaign_recommendation_service.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_smoke_test_release.py`

**Docs**
- Modify: `/Users/davidwegener/Desktop/viralflux/docs/operational_thresholds.md`

The decomposition goal is simple:
- decision engine decides whether a region is `watch`, `prepare_early`, `prepare`, or `activate`
- policy logic can downgrade `activate` to final `prepare`, but should not erase a useful early signal back to `watch`
- allocation and campaign layers must keep `Prepare` visible while forcing budget to `0`

### Task 1: Add A Real Early-Prepare Path In The Decision Engine

**Files:**
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_decision_engine.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine_signals.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine.py`

- [ ] **Step 1: Write the failing tests for `prepare_early` and gate downgrades**

```python
def test_signal_stage_returns_prepare_early_for_strong_early_warning_without_probability_threshold(self) -> None:
    config = self.engine.get_config("Influenza A")
    thresholds = self.engine._thresholds(config=config, action_threshold=0.9)

    stage = self.engine._signal_stage(
        decision_score=max(thresholds["prepare_score"] - 0.06, 0.0),
        event_probability=0.004,
        forecast_confidence=thresholds["prepare_forecast_confidence"],
        freshness_score=thresholds["prepare_freshness"],
        revision_risk=thresholds["prepare_revision_risk_max"] - 0.05,
        trend_score=thresholds["prepare_trend"],
        agreement_support_score=0.0,
        agreement_signal_count=1,
        agreement_direction="up",
        thresholds=thresholds,
        config=config,
    )

    self.assertEqual(stage, "prepare_early")


def test_quality_gate_downgrades_activate_to_prepare_not_watch(self) -> None:
    decision = self.engine.evaluate(
        virus_typ="Influenza A",
        prediction=self._prediction(quality_gate_passed=False),
        feature_row=self._feature_row(),
        metadata=self._metadata(),
    )

    self.assertEqual(decision.signal_stage, "activate")
    self.assertEqual(decision.stage, "prepare")
    self.assertIn("quality gate", " ".join(decision.reason_trace.policy_overrides).lower())


def test_watch_only_policy_keeps_early_prepare_visible(self) -> None:
    decision = self.engine.evaluate(
        virus_typ="Influenza A",
        prediction=self._prediction(
            event_probability=0.004,
            activation_policy="watch_only",
            action_threshold=0.9,
        ),
        feature_row=self._feature_row(
            trend_raw=0.12,
            secondary_trend_raw=0.06,
            signal_value=0.09,
        ),
        metadata=self._metadata(
            ece=0.08,
            brier_score=0.11,
            pr_auc=0.61,
        ),
    )

    self.assertEqual(decision.signal_stage, "prepare_early")
    self.assertEqual(decision.stage, "prepare")
```

- [ ] **Step 2: Run the decision-engine tests to verify they fail**

Run:

```bash
python3.11 -m pytest -q /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_decision_engine.py
```

Expected:
- FAIL because `_signal_stage()` does not accept `agreement_direction`
- FAIL because the engine still returns `watch` when `quality_gate` or `watch_only` blocks activation

- [ ] **Step 3: Implement the early-prepare stage and the new gate policy**

```python
def signal_stage(
    *,
    decision_score: float,
    event_probability: float,
    forecast_confidence: float,
    freshness_score: float,
    revision_risk: float,
    trend_score: float,
    agreement_support_score: float,
    agreement_signal_count: int,
    agreement_direction: str,
    thresholds: Mapping[str, float],
    config: Any,
) -> str:
    activate_agreement_ok = (
        agreement_signal_count < int(config.min_agreement_signal_count)
        or agreement_support_score >= float(thresholds["activate_agreement"])
    )
    prepare_agreement_ok = (
        agreement_signal_count < int(config.min_agreement_signal_count)
        or agreement_support_score >= float(thresholds["prepare_agreement"])
    )
    early_prepare_score_floor = max(0.0, float(thresholds["prepare_score"]) - 0.06)
    early_prepare_agreement_ok = (
        prepare_agreement_ok
        or (agreement_signal_count >= 1 and str(agreement_direction).lower() == "up")
    )

    if all(
        (
            decision_score >= float(thresholds["activate_score"]),
            event_probability >= float(thresholds["activate_probability"]),
            forecast_confidence >= float(thresholds["activate_forecast_confidence"]),
            freshness_score >= float(thresholds["activate_freshness"]),
            revision_risk <= float(thresholds["activate_revision_risk_max"]),
            trend_score >= float(thresholds["activate_trend"]),
            activate_agreement_ok,
        )
    ):
        return "activate"
    if all(
        (
            decision_score >= float(thresholds["prepare_score"]),
            event_probability >= float(thresholds["prepare_probability"]),
            forecast_confidence >= float(thresholds["prepare_forecast_confidence"]),
            freshness_score >= float(thresholds["prepare_freshness"]),
            revision_risk <= float(thresholds["prepare_revision_risk_max"]),
            trend_score >= float(thresholds["prepare_trend"]),
            prepare_agreement_ok,
        )
    ):
        return "prepare"
    if all(
        (
            decision_score >= early_prepare_score_floor,
            forecast_confidence >= float(thresholds["prepare_forecast_confidence"]),
            freshness_score >= float(thresholds["prepare_freshness"]),
            revision_risk <= float(thresholds["prepare_revision_risk_max"]),
            trend_score >= float(thresholds["prepare_trend"]),
            early_prepare_agreement_ok,
        )
    ):
        return "prepare_early"
    return "watch"


def policy_stage(
    *,
    signal_stage: str,
    prediction: Mapping[str, Any],
) -> tuple[str, list[str]]:
    overrides: list[str] = []
    activation_policy = str(prediction.get("activation_policy") or "quality_gate")
    quality_gate = dict(prediction.get("quality_gate") or {})

    if signal_stage == "watch":
        return "watch", overrides

    if activation_policy == "watch_only":
        overrides.append("Activation policy 'watch_only' keeps the region in Prepare until budget release is allowed.")
        return "prepare", overrides

    if not quality_gate.get("overall_passed"):
        overrides.append("Regional quality gate blocks Activate, but the region stays visible as Prepare.")
        return "prepare", overrides

    if signal_stage == "prepare_early":
        return "prepare", overrides
    return signal_stage, overrides
```

Also update the engine wrapper so `_signal_stage()` forwards `agreement_direction=agreement_bundle["direction"]`.

- [ ] **Step 4: Run the tests again to verify the new behavior passes**

Run:

```bash
python3.11 -m pytest -q /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_decision_engine.py
```

Expected:
- PASS
- Tests prove that `prepare_early` exists
- Tests prove that gate blocks now demote to final `prepare`, not final `watch`

- [ ] **Step 5: Commit**

```bash
git add \
  /Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine_signals.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_decision_engine.py
git commit -m "feat: add early prepare decision path"
```

### Task 2: Make Forecast Output Explain Early Prepare Clearly

**Files:**
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine_reasoning.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_forecast_api.py`

- [ ] **Step 1: Write the failing API and reasoning tests**

```python
def test_regional_predict_response_exposes_prepare_early_signal_but_prepare_stage(self) -> None:
    payload = {
        "virus_typ": "Influenza A",
        "horizon_days": 7,
        "decision_summary": {
            "watch_regions": 0,
            "prepare_regions": 1,
            "activate_regions": 0,
            "avg_priority_score": 0.58,
            "top_region": "BY",
            "top_region_decision": "Prepare",
        },
        "predictions": [
            {
                "bundesland": "BY",
                "bundesland_name": "Bayern",
                "horizon_days": 7,
                "event_probability_calibrated": 0.004,
                "decision_label": "Prepare",
                "priority_score": 0.58,
                "uncertainty_summary": "Residual uncertainty is currently limited.",
                "decision": {
                    "stage": "prepare",
                    "signal_stage": "prepare_early",
                    "decision_score": 0.58,
                    "metadata": {"prepare_mode": "early_warning"},
                },
            }
        ],
        "top_5": [],
        "top_decisions": [],
        "generated_at": "2026-04-10T12:00:00",
    }

    with patch(
        "app.services.ml.regional_forecast.RegionalForecastService.predict_all_regions",
        return_value=payload,
    ):
        response = self.client.get(
            "/api/v1/forecast/regional/predict?virus_typ=Influenza%20A&horizon_days=7",
            headers=self.admin_headers,
        )

    self.assertEqual(response.status_code, 200)
    body = response.json()
    first_prediction = body["predictions"][0]
    self.assertEqual(first_prediction["decision"]["stage"], "prepare")
    self.assertEqual(first_prediction["decision"]["signal_stage"], "prepare_early")
    self.assertEqual(first_prediction["decision"]["metadata"]["prepare_mode"], "early_warning")
```

Add one reasoning assertion in `test_regional_decision_engine.py`:

```python
self.assertEqual(decision.reason_trace.why_details[0]["code"], "prepare_early_signal")
self.assertIn("early warning", decision.explanation_summary.lower())
```

- [ ] **Step 2: Run the forecast contract test to verify it fails**

Run:

```bash
python3.11 -m pytest -q /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_forecast_api.py
```

Expected:
- FAIL because reasoning and metadata do not yet describe `prepare_early`

- [ ] **Step 3: Implement the output and explanation changes**

```python
if signal_stage == "prepare_early":
    message = (
        f"Early warning: trend, freshness and confidence support preparation, even though event probability {event_probability:.2f} is still below the hard Prepare threshold."
    )
    why.append(message)
    why_details.append(
        reason_detail(
            "prepare_early_signal",
            message,
            event_probability=round(event_probability, 4),
            prepare_probability_threshold=round(float(thresholds["prepare_probability"]), 4),
        )
    )
elif signal_stage == "prepare":
    ...
```

And add the metadata marker inside `RegionalDecision(...)`:

```python
"prepare_mode": (
    "early_warning"
    if signal_stage == "prepare_early"
    else "standard_prepare" if signal_stage == "prepare" else None
),
```

Update summary text:

```python
if stage == "prepare" and signal_stage == "prepare_early":
    return (
        f"{bundesland_name} shows an early warning pattern. Prepare assets and monitoring, "
        "but do not release paid budget yet."
    )
```

- [ ] **Step 4: Run the forecast and reasoning tests again**

Run:

```bash
python3.11 -m pytest -q \
  /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_decision_engine.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_forecast_api.py
```

Expected:
- PASS
- API payload still exposes final `prepare`
- decision internals expose `signal_stage = prepare_early`
- explanation text clearly says early warning / no budget yet

- [ ] **Step 5: Commit**

```bash
git add \
  /Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine_reasoning.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_forecast_api.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_decision_engine.py
git commit -m "feat: explain early prepare in forecast output"
```

### Task 3: Keep Prepare Visible But Remove Budget Release

**Files:**
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_media_allocation_contracts.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_media_allocation_engine.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_media_allocation_engine.py`

- [ ] **Step 1: Write the failing allocation tests**

```python
def test_prepare_regions_stay_ranked_but_receive_zero_budget(self) -> None:
    payload = self.engine.allocate(
        virus_typ="Influenza A",
        total_budget_eur=20_000,
        predictions=[
            _prediction(
                bundesland="BY",
                bundesland_name="Bayern",
                stage="prepare",
                priority_score=0.61,
                event_probability=0.004,
                forecast_confidence=0.66,
                source_freshness_score=0.78,
                usable_source_share=0.82,
                source_coverage_score=0.80,
                source_revision_risk=0.18,
            ),
            _prediction(
                bundesland="BB",
                bundesland_name="Brandenburg",
                stage="watch",
                priority_score=0.38,
                event_probability=0.002,
                forecast_confidence=0.51,
                source_freshness_score=0.64,
                usable_source_share=0.70,
                source_coverage_score=0.71,
                source_revision_risk=0.22,
            ),
        ],
        spend_enabled=True,
    )

    prepare_item = next(item for item in payload["recommendations"] if item["bundesland"] == "BY")
    self.assertEqual(prepare_item["recommended_activation_level"], "Prepare")
    self.assertEqual(prepare_item["suggested_budget_share"], 0.0)
    self.assertEqual(prepare_item["suggested_budget_eur"], 0.0)
    self.assertEqual(prepare_item["spend_readiness"], "prepare_only")
```

- [ ] **Step 2: Run the allocation tests to verify they fail**

Run:

```bash
python3.11 -m pytest -q /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_media_allocation_engine.py
```

Expected:
- FAIL because `prepare` is still inside `spend_enabled_labels`
- FAIL because the engine still allocates real budget to `Prepare`

- [ ] **Step 3: Implement the no-budget prepare semantics**

```python
DEFAULT_MEDIA_ALLOCATION_CONFIG = RegionalMediaAllocationConfig(
    ...
    spend_enabled_labels=("activate",),
    ...
)
```

Update scoring/readiness:

```python
eligible_for_budget = bool(
    spend_enabled
    and stage in set(self.config.spend_enabled_labels)
    and not spend_blockers
)

if stage == "prepare":
    spend_readiness = "prepare_only"
elif eligible_for_budget:
    spend_readiness = "ready"
else:
    spend_readiness = "watch_only"
```

Add reason-trace wording:

```python
if stage == "prepare":
    blockers.append("Prepare is an early-warning stage. Keep the region visible, but do not release paid budget yet.")
```

- [ ] **Step 4: Run the allocation tests again**

Run:

```bash
python3.11 -m pytest -q /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_media_allocation_engine.py
```

Expected:
- PASS
- `Prepare` still ranks above `Watch`
- budget totals now come only from `Activate`

- [ ] **Step 5: Commit**

```bash
git add \
  /Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_media_allocation_contracts.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_media_allocation_engine.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_media_allocation_engine.py
git commit -m "feat: keep prepare visible without budget allocation"
```

### Task 4: Align Campaign Recommendations With The New Prepare Meaning

**Files:**
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/media/campaign_recommendation_scoring.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/services/media/campaign_recommendation_rationale.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_campaign_recommendation_service.py`

- [ ] **Step 1: Write the failing campaign test**

```python
def test_prepare_recommendation_without_budget_stays_discussion_only(self) -> None:
    payload = self.service.recommend_from_allocation(
        allocation_payload={
            "virus_typ": "Influenza A",
            "recommendations": [
                _allocation_item(
                    bundesland="BE",
                    bundesland_name="Berlin",
                    activation_level="Prepare",
                    budget_share=0.0,
                    budget_amount=0.0,
                    confidence=0.69,
                    products=["GeloRevoice"],
                    spend_gate_status="guarded_release",
                    budget_release_recommendation="hold",
                ),
            ],
        }
    )

    first = payload["recommendations"][0]
    self.assertEqual(first["spend_guardrail_status"], "observe_only")
    self.assertIn(
        "no paid activation budget is released yet",
        " ".join(first["recommendation_rationale"]["guardrails"]).lower(),
    )
```

- [ ] **Step 2: Run the campaign tests to verify they fail**

Run:

```bash
python3.11 -m pytest -q /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_campaign_recommendation_service.py
```

Expected:
- FAIL because rationale still says `Prepare` carries a real budget share and active wave plan

- [ ] **Step 3: Implement the campaign-layer wording and guardrails**

```python
def guardrail_status(...):
    if stage == "watch" or budget_amount <= 0.0:
        return "observe_only"
```

```python
if stage.lower() == "prepare" and budget_amount <= 0.0:
    why = [
        f"{region_name} is an early-warning Prepare region. Operative preparation is justified, but no paid activation budget is released yet.",
        f"Allocation confidence {confidence:.2f} is good enough for preparation work, not for live spend release.",
    ]
    budget_notes = [
        "Suggested campaign budget is 0.00 EUR until Activate is reached and spend gates open.",
    ]
```

Also change the fallback guardrail copy:

```python
message = "Recommendation stays preparation-only for now."
```

- [ ] **Step 4: Run the campaign tests again**

Run:

```bash
python3.11 -m pytest -q /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_campaign_recommendation_service.py
```

Expected:
- PASS
- `Prepare` recommendations remain visible
- they no longer read like ready-to-spend campaign activations

- [ ] **Step 5: Commit**

```bash
git add \
  /Users/davidwegener/Desktop/viralflux/backend/app/services/media/campaign_recommendation_scoring.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/services/media/campaign_recommendation_rationale.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_campaign_recommendation_service.py
git commit -m "feat: align campaign rationale with early prepare"
```

### Task 5: Update Smoke Expectations, Docs, And Run Final Verification

**Files:**
- Modify: `/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_smoke_test_release.py`
- Modify: `/Users/davidwegener/Desktop/viralflux/docs/operational_thresholds.md`

- [ ] **Step 1: Write the failing smoke-test fixture updates**

Replace the old `Prepare` budget fixtures with explicit zero-budget preparation fixtures:

```python
{
    "bundesland": "BY",
    "recommended_activation_level": "Prepare",
    "suggested_budget_share": 0.0,
    "suggested_budget_amount": 0.0,
    "allocation_reason_trace": {"drivers": ["early_prepare_signal"]},
    "confidence": 0.66,
}
```

And in the campaign fixture:

```python
{
    "region": "BY",
    "recommended_product_cluster": {"label": "Respiratory Core Demand"},
    "recommended_keyword_cluster": {"label": "Respiratory Relief Search"},
    "activation_level": "Prepare",
    "suggested_budget_amount": 0.0,
    "confidence": 0.66,
    "evidence_class": "moderate",
    "recommendation_rationale": {
        "summary": ["Early warning supports preparation, but no paid activation budget is released yet."]
    },
}
```

Update the doc summary in `operational_thresholds.md`:

```markdown
- `Prepare`: early-warning stage for operational preparation only; no paid budget release
- `Activate`: strong signal that can release budget if business and quality gates are open
```

- [ ] **Step 2: Run the smoke and doc-adjacent tests to verify they fail**

Run:

```bash
python3.11 -m pytest -q /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_smoke_test_release.py
```

Expected:
- FAIL because the fixture still encodes the old `Prepare with budget` product meaning

- [ ] **Step 3: Apply the smoke/doc updates and run the full verification pass**

Run:

```bash
python3.11 -m pytest -q \
  /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_decision_engine.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_forecast_api.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_regional_media_allocation_engine.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_campaign_recommendation_service.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_smoke_test_release.py
python3.11 -m py_compile \
  /Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine_signals.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_decision_engine_reasoning.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/services/ml/regional_media_allocation_engine.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/services/media/campaign_recommendation_scoring.py \
  /Users/davidwegener/Desktop/viralflux/backend/app/services/media/campaign_recommendation_rationale.py
```

Expected:
- PASS on all listed tests
- `py_compile` returns no output

- [ ] **Step 4: Commit**

```bash
git add \
  /Users/davidwegener/Desktop/viralflux/backend/app/tests/test_smoke_test_release.py \
  /Users/davidwegener/Desktop/viralflux/docs/operational_thresholds.md
git commit -m "test: update smoke expectations for early prepare"
```

- [ ] **Step 5: Optional post-merge live validation**

Run after merge/deploy:

```bash
python3.11 /Users/davidwegener/Desktop/viralflux/backend/scripts/smoke_test_release.py \
  --base-url https://fluxengine.labpulse.ai \
  --virus "Influenza A" \
  --horizon 7 \
  --budget-eur 50000 \
  --top-n 3
```

Expected:
- release smoke still returns success
- `Prepare` may now appear live without any non-zero budget
- `Activate` stays rare and continues to require open gates

## Self-Review

### Spec coverage
- Early-warning `Prepare` rule: covered by Task 1
- No-budget `Prepare`: covered by Task 3 and Task 4
- Clear output semantics: covered by Task 2
- Safety constraints around `Activate`: covered by Task 1 and Task 3
- Tests and verification: covered by all tasks, with final pass in Task 5

### Placeholder scan
- No placeholder markers or deferred implementation notes remain
- Each task names exact files, exact commands, and concrete code snippets

### Type consistency
- `signal_stage` becomes `prepare_early` internally
- final public `stage` remains `prepare`
- `metadata["prepare_mode"]` carries the semantic distinction
- allocation still consumes final `stage`, not the internal signal stage
