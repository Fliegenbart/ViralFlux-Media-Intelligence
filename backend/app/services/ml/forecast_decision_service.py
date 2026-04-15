from __future__ import annotations
from app.core.time import utc_now

from datetime import datetime, timedelta
import math
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.schema_contracts import ensure_ml_forecast_schema_aligned
from app.models.database import (
    BacktestRun,
    ForecastAccuracyLog,
    MediaOutcomeRecord,
    MLForecast,
    WastewaterAggregated,
)
from app.services.ml.forecast_contracts import (
    BACKTEST_RELIABILITY_PROXY_SOURCE,
    DEFAULT_DECISION_BASELINE_WINDOW_DAYS,
    DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
    DEFAULT_DECISION_HORIZON_DAYS,
    BurdenForecast,
    BurdenForecastPoint,
    EventForecast,
    ForecastMonitoringSnapshot,
    ForecastQuality,
    HEURISTIC_EVENT_SCORE_SOURCE,
    OpportunityAssessment,
    heuristic_event_score_from_forecast,
    normalize_event_forecast_payload,
    normalized_decision_priority_index,
    normalized_signal_index,
    resolve_decision_basis_score,
    resolve_decision_basis_type,
)
from app.services.ml.forecast_horizon_utils import DEFAULT_FORECAST_REGION, reliability_score_from_metrics


REQUIRED_OUTCOME_FIELD_NAMES = ("media_spend_eur",)
CONVERSION_OUTCOME_FIELD_NAMES = ("sales_units", "order_count", "revenue_eur")


class ForecastDecisionService:
    """Forecast-first runtime adapter for decision, risk and opportunity layers."""

    GENERIC_MARKET_PROXY_SOURCES = {"RKI_ARE", "ATEMWEGSINDEX"}

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _normalize_brand(brand: str) -> str:
        if brand is None:
            raise ValueError("brand must be provided")
        brand_value = str(brand).strip().lower()
        if not brand_value:
            raise ValueError("brand must be a non-empty string")
        return brand_value

    def _latest_forecasts(self, virus_typ: str) -> list[MLForecast]:
        ensure_ml_forecast_schema_aligned(self.db)
        latest = (
            self.db.query(MLForecast)
            .filter(
                MLForecast.virus_typ == virus_typ,
                MLForecast.region == DEFAULT_FORECAST_REGION,
                MLForecast.horizon_days == DEFAULT_DECISION_HORIZON_DAYS,
            )
            .order_by(MLForecast.created_at.desc())
            .first()
        )
        if not latest or not latest.created_at:
            return []
        return (
            self.db.query(MLForecast)
            .filter(
                MLForecast.virus_typ == virus_typ,
                MLForecast.region == DEFAULT_FORECAST_REGION,
                MLForecast.horizon_days == DEFAULT_DECISION_HORIZON_DAYS,
                MLForecast.created_at >= latest.created_at - timedelta(seconds=10),
            )
            .order_by(MLForecast.forecast_date.asc())
            .all()
        )

    def _latest_market_backtest(
        self,
        *,
        virus_typ: str,
        target_source: str = "RKI_ARE",
    ) -> BacktestRun | None:
        query = self.db.query(BacktestRun).filter(
            BacktestRun.mode == "MARKET_CHECK",
            BacktestRun.virus_typ == virus_typ,
        )
        if target_source:
            query = query.filter(
                func.upper(BacktestRun.target_source) == str(target_source).strip().upper()
            )
        return query.order_by(BacktestRun.created_at.desc()).first()

    @classmethod
    def _market_gate_is_advisory_proxy(
        cls,
        *,
        latest_market: BacktestRun | None,
        target_source: str | None = None,
    ) -> bool:
        source = (
            latest_market.target_source
            if latest_market and latest_market.target_source
            else target_source
        )
        return str(source or "").strip().upper() in cls.GENERIC_MARKET_PROXY_SOURCES

    def _latest_customer_backtest(self, *, virus_typ: str) -> BacktestRun | None:
        return (
            self.db.query(BacktestRun)
            .filter(
                BacktestRun.mode == "CUSTOMER_CHECK",
                BacktestRun.virus_typ == virus_typ,
            )
            .order_by(BacktestRun.created_at.desc())
            .first()
        )

    def _latest_accuracy(self, *, virus_typ: str) -> ForecastAccuracyLog | None:
        return (
            self.db.query(ForecastAccuracyLog)
            .filter(ForecastAccuracyLog.virus_typ == virus_typ)
            .order_by(ForecastAccuracyLog.computed_at.desc())
            .first()
        )

    def _freshness_state(self, latest_created_at: datetime | None) -> str:
        if latest_created_at is None:
            return "missing"
        age_days = (utc_now() - latest_created_at).total_seconds() / 86400.0
        if age_days <= 10:
            return "fresh"
        if age_days <= 21:
            return "stale"
        return "expired"

    def _monitoring_freshness_state(
        self,
        latest_created_at: datetime | None,
        *,
        fresh_days: float,
        stale_days: float,
    ) -> str:
        if latest_created_at is None:
            return "missing"
        age_days = (utc_now() - latest_created_at).total_seconds() / 86400.0
        if age_days <= fresh_days:
            return "fresh"
        if age_days <= stale_days:
            return "stale"
        return "expired"

    def _sanitize_json_value(self, value: Any) -> Any:
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, dict):
            return {str(key): self._sanitize_json_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize_json_value(item) for item in value]
        if isinstance(value, tuple):
            return [self._sanitize_json_value(item) for item in value]
        return value

    def _baseline_value(self, *, virus_typ: str) -> float:
        cutoff = utc_now() - timedelta(days=DEFAULT_DECISION_BASELINE_WINDOW_DAYS)
        rows = (
            self.db.query(WastewaterAggregated.viruslast)
            .filter(
                WastewaterAggregated.virus_typ == virus_typ,
                WastewaterAggregated.datum >= cutoff,
                WastewaterAggregated.viruslast.isnot(None),
            )
            .order_by(WastewaterAggregated.datum.asc())
            .all()
        )
        values = [float(row[0]) for row in rows if row[0] is not None]
        if not values:
            latest = (
                self.db.query(WastewaterAggregated.viruslast)
                .filter(
                    WastewaterAggregated.virus_typ == virus_typ,
                    WastewaterAggregated.viruslast.isnot(None),
                )
                .order_by(WastewaterAggregated.datum.desc())
                .first()
            )
            return float(latest[0]) if latest and latest[0] is not None else 0.0
        values.sort()
        mid = len(values) // 2
        if len(values) % 2 == 1:
            return float(values[mid])
        return float((values[mid - 1] + values[mid]) / 2.0)

    @staticmethod
    def _stored_event_forecast(forecast: MLForecast | None) -> dict[str, Any]:
        if forecast is None:
            return {}
        payload = (forecast.features_used or {}).get("event_forecast") or {}
        if not isinstance(payload, dict):
            return {}
        return normalize_event_forecast_payload(payload)

    @staticmethod
    def _resolved_reliability_score(
        *,
        stored_event_forecast: dict[str, Any],
        event_calibration: dict[str, Any],
        horizon_forecast: MLForecast | None,
    ) -> float | None:
        if stored_event_forecast.get("reliability_score") is not None:
            return float(stored_event_forecast["reliability_score"])
        if event_calibration.get("reliability_score") is not None:
            return float(event_calibration["reliability_score"])
        derived_reliability = reliability_score_from_metrics(event_calibration or {})
        if derived_reliability is not None:
            return float(derived_reliability)
        if horizon_forecast is not None and horizon_forecast.confidence is not None:
            # Legacy compatibility only: older rows may only have top-level confidence.
            return float(horizon_forecast.confidence)
        return None

    @staticmethod
    def _resolved_backtest_quality_score(
        *,
        stored_event_forecast: dict[str, Any],
        market_metrics: dict[str, Any],
    ) -> float | None:
        if stored_event_forecast.get("backtest_quality_score") is not None:
            return float(stored_event_forecast["backtest_quality_score"])
        if market_metrics.get("backtest_quality_score") is not None:
            return float(market_metrics["backtest_quality_score"])
        mape = market_metrics.get("mape")
        if mape is None:
            return None
        return round(max(0.0, min(1.0, 1.0 - (float(mape) / 100.0))), 4)

    @staticmethod
    def _resolve_event_calibration(
        *,
        probability_is_learned: bool,
        stored_event_forecast: dict[str, Any],
        event_calibration: dict[str, Any],
        probability_source: str,
    ) -> dict[str, Any]:
        if not probability_is_learned:
            return {
                "calibration_method": str(
                    stored_event_forecast.get("calibration_method") or probability_source
                ),
                "brier_score": None,
                "ece": None,
                "calibration_passed": None,
            }

        has_backtest_calibration = any(
            event_calibration.get(key) is not None
            for key in ("calibration_passed", "brier_score", "ece")
        )
        calibration_method = (
            event_calibration.get("calibration_method")
            if has_backtest_calibration and event_calibration.get("calibration_method")
            else stored_event_forecast.get("calibration_method")
        )
        calibration_passed = (
            event_calibration.get("calibration_passed")
            if has_backtest_calibration
            else stored_event_forecast.get("calibration_passed")
        )
        brier_score = (
            event_calibration.get("brier_score")
            if has_backtest_calibration and event_calibration.get("brier_score") is not None
            else stored_event_forecast.get("brier_score")
        )
        ece = (
            event_calibration.get("ece")
            if has_backtest_calibration and event_calibration.get("ece") is not None
            else stored_event_forecast.get("ece")
        )
        return {
            "calibration_method": str(calibration_method or probability_source),
            "brier_score": (round(float(brier_score), 4) if brier_score is not None else None),
            "ece": (round(float(ece), 4) if ece is not None else None),
            "calibration_passed": (
                bool(calibration_passed)
                if calibration_passed is not None
                else None
            ),
        }

    @staticmethod
    def _clean_decision_event_forecast(payload: dict[str, Any]) -> dict[str, Any]:
        return normalize_event_forecast_payload(payload)

    def _resolve_live_event_probability(
        self,
        *,
        horizon_forecast: MLForecast | None,
        baseline_value: float,
    ) -> dict[str, Any]:
        stored = self._stored_event_forecast(horizon_forecast)
        stored_probability = stored.get("event_probability")
        if stored_probability is not None:
            return {
                "event_probability": float(stored_probability),
                "heuristic_event_score": (
                    float(stored["heuristic_event_score"])
                    if stored.get("heuristic_event_score") is not None
                    else None
                ),
                "probability_source": str(
                    stored.get("probability_source") or stored.get("calibration_method") or "learned"
                ),
                "reliability_score": stored.get("reliability_score"),
                "backtest_quality_score": stored.get("backtest_quality_score"),
                "calibration_mode": stored.get("calibration_mode"),
                "uncertainty_source": stored.get("uncertainty_source"),
                "fallback_reason": stored.get("fallback_reason"),
                "learned_model_version": stored.get("learned_model_version"),
                "fallback_used": bool(stored.get("fallback_used")),
            }

        stored_heuristic = stored.get("heuristic_event_score")
        if stored_heuristic is not None:
            return {
                "event_probability": None,
                "heuristic_event_score": float(stored_heuristic),
                "probability_source": str(stored.get("probability_source") or HEURISTIC_EVENT_SCORE_SOURCE),
                "reliability_score": stored.get("reliability_score"),
                "backtest_quality_score": stored.get("backtest_quality_score"),
                "calibration_mode": stored.get("calibration_mode"),
                "uncertainty_source": stored.get("uncertainty_source"),
                "fallback_reason": stored.get("fallback_reason"),
                "learned_model_version": stored.get("learned_model_version"),
                "fallback_used": True,
            }

        if horizon_forecast is not None and baseline_value > 0:
            return {
                "event_probability": None,
                "heuristic_event_score": heuristic_event_score_from_forecast(
                    prediction=float(horizon_forecast.predicted_value or 0.0),
                    baseline=baseline_value,
                    lower_bound=horizon_forecast.lower_bound,
                    upper_bound=horizon_forecast.upper_bound,
                    threshold_pct=DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
                ),
                "probability_source": HEURISTIC_EVENT_SCORE_SOURCE,
                "reliability_score": None,
                "backtest_quality_score": None,
                "calibration_mode": None,
                "uncertainty_source": BACKTEST_RELIABILITY_PROXY_SOURCE,
                "fallback_reason": "stored_event_probability_missing",
                "learned_model_version": None,
                "fallback_used": True,
            }
        return {
            "event_probability": None,
            "heuristic_event_score": None,
            "probability_source": HEURISTIC_EVENT_SCORE_SOURCE,
            "reliability_score": None,
            "backtest_quality_score": None,
            "calibration_mode": None,
            "uncertainty_source": BACKTEST_RELIABILITY_PROXY_SOURCE,
            "fallback_reason": "stored_event_probability_missing",
            "learned_model_version": None,
            "fallback_used": True,
        }

    def build_forecast_bundle(
        self,
        *,
        virus_typ: str,
        target_source: str = "RKI_ARE",
    ) -> dict[str, Any]:
        forecasts = self._latest_forecasts(virus_typ)
        latest_market = self._latest_market_backtest(virus_typ=virus_typ, target_source=target_source)
        latest_accuracy = self._latest_accuracy(virus_typ=virus_typ)

        issue_date = (
            forecasts[0].created_at.isoformat()
            if forecasts and forecasts[0].created_at
            else None
        )
        burden_points = [
            BurdenForecastPoint(
                target_date=forecast.forecast_date.isoformat() if forecast.forecast_date else "",
                median=float(forecast.predicted_value or 0.0),
                lower=(
                    float(forecast.lower_bound)
                    if forecast.lower_bound is not None
                    else None
                ),
                upper=(
                    float(forecast.upper_bound)
                    if forecast.upper_bound is not None
                    else None
                ),
            )
            for forecast in forecasts
            if forecast.forecast_date is not None
        ]
        burden_forecast = BurdenForecast(
            target=virus_typ,
            region="DE",
            issue_date=issue_date,
            horizon_days=len(burden_points),
            model_version=forecasts[0].model_version if forecasts else None,
            points=burden_points,
        )

        baseline_value = self._baseline_value(virus_typ=virus_typ)
        horizon_index = min(
            max(DEFAULT_DECISION_HORIZON_DAYS - 1, 0),
            max(len(forecasts) - 1, 0),
        )
        horizon_forecast = forecasts[horizon_index] if forecasts else None
        resolved_event_signal = self._resolve_live_event_probability(
            horizon_forecast=horizon_forecast,
            baseline_value=baseline_value,
        )
        stored_event_forecast = self._stored_event_forecast(horizon_forecast)
        event_probability = resolved_event_signal.get("event_probability")
        heuristic_event_score = resolved_event_signal.get("heuristic_event_score")
        probability_source = str(resolved_event_signal.get("probability_source") or HEURISTIC_EVENT_SCORE_SOURCE)
        uncertainty_source = (
            resolved_event_signal.get("uncertainty_source")
            or BACKTEST_RELIABILITY_PROXY_SOURCE
        )
        fallback_reason = resolved_event_signal.get("fallback_reason")
        learned_model_version = resolved_event_signal.get("learned_model_version")
        fallback_used = bool(resolved_event_signal.get("fallback_used"))
        decision_basis_score = resolve_decision_basis_score(
            event_probability=(
                float(event_probability)
                if event_probability is not None
                else None
            ),
            heuristic_event_score=(
                float(heuristic_event_score)
                if heuristic_event_score is not None
                else None
            ),
        )
        decision_basis_type = resolve_decision_basis_type(
            event_probability=(
                float(event_probability)
                if event_probability is not None
                else None
            ),
            heuristic_event_score=(
                float(heuristic_event_score)
                if heuristic_event_score is not None
                else None
            ),
        )
        probability_is_learned = event_probability is not None

        market_metrics = latest_market.metrics if latest_market and latest_market.metrics else {}
        quality_gate = market_metrics.get("quality_gate") or {}
        event_calibration = market_metrics.get("event_calibration") or {}
        calibration_mode = resolved_event_signal.get("calibration_mode") or event_calibration.get("calibration_mode")
        interval_coverage = market_metrics.get("interval_coverage") or {}
        timing_metrics = market_metrics.get("timing_metrics") or {}
        improvement = latest_market.improvement_vs_baselines if latest_market and latest_market.improvement_vs_baselines else {}

        drift_status = (
            "warning"
            if latest_accuracy and bool(latest_accuracy.drift_detected)
            else ("ok" if latest_accuracy else "unknown")
        )
        freshness_status = self._freshness_state(
            forecasts[0].created_at if forecasts and forecasts[0].created_at else None
        )
        market_gate_is_advisory_proxy = self._market_gate_is_advisory_proxy(
            latest_market=latest_market,
            target_source=target_source,
        )
        forecast_ready = bool(
            latest_market is not None
            and (
                market_gate_is_advisory_proxy
                or quality_gate.get("overall_passed")
            )
            and drift_status != "warning"
            and freshness_status == "fresh"
        )
        reliability_score = self._resolved_reliability_score(
            stored_event_forecast=stored_event_forecast,
            event_calibration=event_calibration,
            horizon_forecast=horizon_forecast,
        )
        backtest_quality_score = self._resolved_backtest_quality_score(
            stored_event_forecast=stored_event_forecast,
            market_metrics=market_metrics,
        )
        resolved_calibration = self._resolve_event_calibration(
            probability_is_learned=probability_is_learned,
            stored_event_forecast=stored_event_forecast,
            event_calibration=event_calibration,
            probability_source=probability_source,
        )

        event_forecast = EventForecast(
            event_key=f"{virus_typ.lower().replace(' ', '_')}_growth_7d",
            horizon_days=DEFAULT_DECISION_HORIZON_DAYS,
            event_probability=(float(event_probability) if event_probability is not None else None),
            heuristic_event_score=(
                float(heuristic_event_score)
                if heuristic_event_score is not None
                else None
            ),
            threshold_pct=DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
            baseline_value=round(float(baseline_value), 3) if baseline_value > 0 else None,
            threshold_value=(
                round(float(baseline_value) * 1.25, 3)
                if baseline_value > 0
                else None
            ),
            calibration_method=resolved_calibration["calibration_method"],
            brier_score=resolved_calibration["brier_score"],
            ece=resolved_calibration["ece"],
            calibration_passed=resolved_calibration["calibration_passed"],
            reliability_score=reliability_score,
            backtest_quality_score=backtest_quality_score,
            probability_source=probability_source,
            calibration_mode=(str(calibration_mode) if calibration_mode is not None else None),
            uncertainty_source=str(uncertainty_source),
            fallback_reason=(str(fallback_reason) if fallback_reason is not None else None),
            learned_model_version=learned_model_version,
            fallback_used=fallback_used,
        ).to_dict()
        event_forecast = self._clean_decision_event_forecast(event_forecast)

        forecast_quality = ForecastQuality(
            forecast_readiness="GO" if forecast_ready else "WATCH",
            drift_status=drift_status,
            freshness_status=freshness_status,
            baseline_deltas={
                "mae_vs_persistence_pct": improvement.get("mae_vs_persistence_pct"),
                "mae_vs_seasonal_pct": improvement.get("mae_vs_seasonal_pct"),
            },
            timing_metrics=timing_metrics,
            interval_coverage=interval_coverage,
            promotion_gate=quality_gate,
        )

        signal_index = normalized_signal_index(
            signal_basis_score=decision_basis_score,
        )
        decision_priority_index = normalized_decision_priority_index(
            decision_basis_score=decision_basis_score,
            modifier=1.0 if forecast_ready else 0.75,
        )
        component_scores = {
            "wastewater": round(min(1.0, max(0.0, (decision_basis_score or 0.0) * 1.05)), 4),
            "notaufnahme": round(
                min(1.0, max(0.0, float(timing_metrics.get("corr_at_best_lag", 0.0) or 0.0))),
                4,
            ),
            "search_trends": round(
                min(1.0, max(0.0, float(horizon_forecast.trend_momentum_7d or 0.0)))
                if horizon_forecast and horizon_forecast.trend_momentum_7d is not None
                else 0.0,
                4,
            ),
            "environment": round(
                min(1.0, max(0.0, float(interval_coverage.get("coverage_80_gap_score", 0.0) or 0.0))),
                4,
            ),
            "drug_shortage": 0.0,
            "order_velocity": round(
                min(1.0, max(0.0, decision_priority_index / 100.0)),
                4,
            ),
        }

        decision_summary = {
            "signal_index": signal_index,
            "signal_basis_score": decision_basis_score,
            "signal_basis_type": decision_basis_type,
            "decision_priority_index": decision_priority_index,
            "decision_basis_score": decision_basis_score,
            "decision_basis_type": decision_basis_type,
            "reliability_label": event_forecast.get("reliability_label"),
            "component_scores": component_scores,
            "signal_source": event_forecast.get("signal_source"),
        }

        return {
            "virus_typ": virus_typ,
            "target_source": target_source,
            "burden_forecast": burden_forecast.to_dict(),
            "event_forecast": event_forecast,
            "forecast_quality": forecast_quality.to_dict(),
            "decision_summary": decision_summary,
        }

    def build_monitoring_snapshot(
        self,
        *,
        virus_typ: str,
        target_source: str = "RKI_ARE",
    ) -> dict[str, Any]:
        bundle = self.build_forecast_bundle(virus_typ=virus_typ, target_source=target_source)
        burden_forecast = bundle.get("burden_forecast") or {}
        event_forecast = bundle.get("event_forecast") or {}
        forecast_quality = bundle.get("forecast_quality") or {}
        latest_accuracy = self._latest_accuracy(virus_typ=virus_typ)
        latest_market = self._latest_market_backtest(virus_typ=virus_typ, target_source=target_source)

        accuracy_freshness_status = self._monitoring_freshness_state(
            latest_accuracy.computed_at if latest_accuracy else None,
            fresh_days=2,
            stale_days=5,
        )
        backtest_freshness_status = self._monitoring_freshness_state(
            latest_market.created_at if latest_market else None,
            fresh_days=14,
            stale_days=35,
        )

        latest_accuracy_payload = {
            "computed_at": latest_accuracy.computed_at.isoformat() if latest_accuracy and latest_accuracy.computed_at else None,
            "window_days": latest_accuracy.window_days if latest_accuracy else None,
            "samples": latest_accuracy.samples if latest_accuracy else None,
            "mae": latest_accuracy.mae if latest_accuracy else None,
            "rmse": latest_accuracy.rmse if latest_accuracy else None,
            "mape": latest_accuracy.mape if latest_accuracy else None,
            "correlation": latest_accuracy.correlation if latest_accuracy else None,
            "drift_detected": bool(latest_accuracy.drift_detected) if latest_accuracy else None,
            "freshness_status": accuracy_freshness_status,
        }
        latest_backtest_payload = {
            "run_id": latest_market.run_id if latest_market else None,
            "created_at": latest_market.created_at.isoformat() if latest_market and latest_market.created_at else None,
            "target_source": latest_market.target_source if latest_market else target_source,
            "freshness_status": backtest_freshness_status,
            "quality_gate": (latest_market.metrics or {}).get("quality_gate") if latest_market and latest_market.metrics else None,
            "interval_coverage": (latest_market.metrics or {}).get("interval_coverage") if latest_market and latest_market.metrics else None,
            "event_calibration": (latest_market.metrics or {}).get("event_calibration") if latest_market and latest_market.metrics else None,
            "timing_metrics": (latest_market.metrics or {}).get("timing_metrics") if latest_market and latest_market.metrics else None,
            "lead_lag": latest_market.lead_lag if latest_market else None,
            "improvement_vs_baselines": latest_market.improvement_vs_baselines if latest_market else None,
        }
        market_gate_is_advisory_proxy = self._market_gate_is_advisory_proxy(
            latest_market=latest_market,
            target_source=target_source,
        )

        alerts: list[str] = []
        if not (burden_forecast.get("points") or []):
            alerts.append("Kein aktueller Live-Forecast vorhanden.")
        if str(forecast_quality.get("freshness_status") or "missing") != "fresh":
            alerts.append("Live-Forecast ist nicht frisch genug.")
        if latest_accuracy is None:
            alerts.append("Kein Accuracy-Monitoring vorhanden.")
        elif accuracy_freshness_status != "fresh":
            alerts.append("Accuracy-Monitoring ist nicht frisch.")
        if latest_accuracy and (latest_accuracy.samples or 0) < 7:
            alerts.append("Accuracy-Monitoring basiert auf sehr wenigen Paaren.")
        if str(forecast_quality.get("drift_status") or "unknown") == "warning":
            alerts.append("MAPE-Drift ist im Accuracy-Monitoring aktiv.")
        if latest_market is None:
            alerts.append("Kein Markt-Backtest für das Promotion-Gate vorhanden.")
        elif backtest_freshness_status != "fresh":
            alerts.append("Letzter Markt-Backtest ist nicht frisch.")

        promotion_gate = forecast_quality.get("promotion_gate") or {}
        interval_coverage = forecast_quality.get("interval_coverage") or {}
        if (
            promotion_gate
            and not market_gate_is_advisory_proxy
            and not bool(promotion_gate.get("overall_passed"))
        ):
            alerts.append("Forecast-Promotion-Gate steht aktuell auf WATCH.")
        if interval_coverage and interval_coverage.get("interval_passed") is False:
            alerts.append("Intervallabdeckung liegt ausserhalb des Zielbands.")
        if event_forecast and event_forecast.get("calibration_passed") is False:
            alerts.append("Gelernte Event-Wahrscheinlichkeit ist nicht ausreichend kalibriert.")

        lead_lag = latest_backtest_payload.get("lead_lag") or {}
        effective_lead_days = lead_lag.get("effective_lead_days")
        if (
            not market_gate_is_advisory_proxy
            and effective_lead_days is not None
            and float(effective_lead_days) <= 0
        ):
            alerts.append("Effektive Vorlaufzeit ist nicht positiv.")

        critical = any(
            condition
            for condition in (
                not (burden_forecast.get("points") or []),
                str(forecast_quality.get("freshness_status") or "missing") in {"missing", "expired"},
                latest_market is None,
                backtest_freshness_status == "expired",
            )
        )
        warning = any(
            condition
            for condition in (
                bool(alerts),
                str(forecast_quality.get("forecast_readiness") or "WATCH") != "GO",
                accuracy_freshness_status in {"stale", "expired", "missing"},
                str(forecast_quality.get("drift_status") or "unknown") == "warning",
            )
        )
        monitoring_status = "critical" if critical else ("warning" if warning else "healthy")

        snapshot = ForecastMonitoringSnapshot(
            virus_typ=virus_typ,
            target_source=target_source,
            monitoring_status=monitoring_status,
            forecast_readiness=str(forecast_quality.get("forecast_readiness") or "WATCH"),
            drift_status=str(forecast_quality.get("drift_status") or "unknown"),
            freshness_status=str(forecast_quality.get("freshness_status") or "missing"),
            accuracy_freshness_status=accuracy_freshness_status,
            backtest_freshness_status=backtest_freshness_status,
            issue_date=burden_forecast.get("issue_date"),
            model_version=burden_forecast.get("model_version"),
            event_forecast={
                "event_probability": event_forecast.get("event_probability"),
                "heuristic_event_score": event_forecast.get("heuristic_event_score"),
                "decision_basis_score": resolve_decision_basis_score(
                    event_probability=event_forecast.get("event_probability"),
                    heuristic_event_score=event_forecast.get("heuristic_event_score"),
                ),
                "decision_basis_type": resolve_decision_basis_type(
                    event_probability=event_forecast.get("event_probability"),
                    heuristic_event_score=event_forecast.get("heuristic_event_score"),
                ),
                "reliability_score": event_forecast.get("reliability_score"),
                "reliability_label": event_forecast.get("reliability_label"),
                "backtest_quality_score": event_forecast.get("backtest_quality_score"),
                "calibration_passed": event_forecast.get("calibration_passed"),
                "probability_source": event_forecast.get("probability_source"),
                "signal_source": event_forecast.get("signal_source"),
                "calibration_mode": event_forecast.get("calibration_mode"),
                "uncertainty_source": event_forecast.get("uncertainty_source"),
                "fallback_reason": event_forecast.get("fallback_reason"),
                "fallback_used": event_forecast.get("fallback_used"),
            },
            latest_accuracy=latest_accuracy_payload,
            latest_backtest=latest_backtest_payload,
            alerts=alerts,
        )
        return self._sanitize_json_value(snapshot.to_dict())

    def get_truth_readiness(
        self,
        *,
        brand: str,
    ) -> dict[str, Any]:
        brand_value = self._normalize_brand(brand)
        rows = (
            self.db.query(MediaOutcomeRecord)
            .filter(func.lower(MediaOutcomeRecord.brand) == brand_value)
            .order_by(MediaOutcomeRecord.week_start.asc())
            .all()
        )
        if not rows:
            return {
                "coverage_weeks": 0,
                "truth_readiness": "noch_nicht_angeschlossen",
                "truth_ready": False,
                "expected_units_lift_enabled": False,
                "expected_revenue_lift_enabled": False,
            }

        week_values = sorted({row.week_start.date().isoformat() for row in rows if row.week_start})
        coverage_weeks = len(week_values)
        required_present = all(
            any(getattr(row, field_name) is not None for row in rows)
            for field_name in REQUIRED_OUTCOME_FIELD_NAMES
        )
        conversion_present = any(
            any(getattr(row, field_name) is not None for row in rows)
            for field_name in CONVERSION_OUTCOME_FIELD_NAMES
        )
        if coverage_weeks >= 52:
            readiness = "belastbar"
        elif coverage_weeks >= 26:
            readiness = "im_aufbau"
        elif coverage_weeks > 0:
            readiness = "erste_signale"
        else:
            readiness = "noch_nicht_angeschlossen"

        truth_ready = coverage_weeks >= 26 and required_present and conversion_present
        return {
            "coverage_weeks": coverage_weeks,
            "truth_readiness": readiness,
            "truth_ready": truth_ready,
            "required_fields_present": required_present,
            "conversion_fields_present": conversion_present,
            "expected_units_lift_enabled": truth_ready,
            "expected_revenue_lift_enabled": truth_ready,
        }

    def build_opportunity_assessment(
        self,
        *,
        virus_typ: str,
        target_source: str = "RKI_ARE",
        brand: str,
        secondary_modifier: float = 1.0,
    ) -> dict[str, Any]:
        brand_value = self._normalize_brand(brand)
        bundle = self.build_forecast_bundle(virus_typ=virus_typ, target_source=target_source)
        quality = bundle.get("forecast_quality") or {}
        event_forecast = bundle.get("event_forecast") or {}
        truth = self.get_truth_readiness(brand=brand_value)
        decision_basis_score = resolve_decision_basis_score(
            event_probability=event_forecast.get("event_probability"),
            heuristic_event_score=event_forecast.get("heuristic_event_score"),
        )
        decision_basis_type = resolve_decision_basis_type(
            event_probability=event_forecast.get("event_probability"),
            heuristic_event_score=event_forecast.get("heuristic_event_score"),
        )
        decision_priority_index = normalized_decision_priority_index(
            decision_basis_score=decision_basis_score,
            modifier=secondary_modifier,
        )

        if quality.get("forecast_readiness") != "GO":
            action_class = "watch_only"
        elif truth.get("truth_ready"):
            action_class = "customer_lift_ready"
        else:
            action_class = "market_watch"

        assessment = OpportunityAssessment(
            action_class=action_class,
            truth_readiness=str(truth.get("truth_readiness") or "noch_nicht_angeschlossen"),
            forecast_readiness=str(quality.get("forecast_readiness") or "WATCH"),
            decision_priority_index=decision_priority_index,
            decision_basis_score=decision_basis_score,
            decision_basis_type=decision_basis_type,
            expected_units_lift=None,
            expected_revenue_lift=None,
            lift_interval=None,
            secondary_modifier=round(float(secondary_modifier), 3),
            explanation=(
                "Belastbare Umsatz- oder Revenue-Lift-Werte werden erst bei ausreichender Customer-Truth freigeschaltet."
                if not truth.get("truth_ready")
                else "Outcome-Layer ist freigeschaltet, konkrete Lift-Modellierung folgt auf den Forecast-Outputs."
            ),
        )
        return assessment.to_dict()

    def build_legacy_outbreak_score(
        self,
        *,
        virus_typ: str,
        target_source: str = "RKI_ARE",
    ) -> dict[str, Any]:
        bundle = self.build_forecast_bundle(virus_typ=virus_typ, target_source=target_source)
        decision_summary = bundle.get("decision_summary") or {}
        return {
            "virus_typ": virus_typ,
            "signal_index": decision_summary.get("signal_index", 0.0),
            "signal_basis_score": decision_summary.get("signal_basis_score"),
            "signal_basis_type": decision_summary.get("signal_basis_type"),
            "decision_priority_index": decision_summary.get("decision_priority_index", 0.0),
            "decision_basis_score": decision_summary.get("decision_basis_score"),
            "decision_basis_type": decision_summary.get("decision_basis_type"),
            "reliability_label": decision_summary.get("reliability_label", "Mittel"),
            "signal_source": (bundle.get("event_forecast") or {}).get("signal_source"),
            "component_scores": decision_summary.get("component_scores", {}),
            "event_forecast": bundle.get("event_forecast"),
            "forecast_quality": bundle.get("forecast_quality"),
            "burden_forecast": bundle.get("burden_forecast"),
        }

    def build_all_legacy_outbreak_scores(
        self,
        *,
        virus_types: list[str],
        target_source: str = "RKI_ARE",
    ) -> dict[str, Any]:
        per_virus = {
            virus_typ: self.build_legacy_outbreak_score(
                virus_typ=virus_typ,
                target_source=target_source,
            )
            for virus_typ in virus_types
        }
        overall = max(
            (float(item.get("decision_priority_index") or 0.0) for item in per_virus.values()),
            default=0.0,
        )
        return {
            "overall_score": round(overall, 1),
            "per_virus": per_virus,
        }

    def get_legacy_score_history(
        self,
        *,
        virus_typ: str,
        days: int = 90,
    ) -> dict[str, Any]:
        baseline = self._baseline_value(virus_typ=virus_typ)
        cutoff = utc_now() - timedelta(days=max(1, int(days)))
        rows = (
            self.db.query(MLForecast)
            .filter(
                MLForecast.virus_typ == virus_typ,
                MLForecast.forecast_date >= cutoff,
            )
            .order_by(MLForecast.forecast_date.asc())
            .all()
        )
        history: list[dict[str, Any]] = []
        for row in rows:
            stored = self._stored_event_forecast(row)
            stored_probability = stored.get("event_probability")
            if stored_probability is not None:
                probability = float(stored_probability)
                heuristic_score = (
                    float(stored["heuristic_event_score"])
                    if stored.get("heuristic_event_score") is not None
                    else None
                )
                probability_source = str(
                    stored.get("probability_source") or stored.get("calibration_method") or "learned"
                )
            else:
                probability = None
                heuristic_score = (
                    heuristic_event_score_from_forecast(
                        prediction=float(row.predicted_value or 0.0),
                        baseline=baseline,
                        lower_bound=row.lower_bound,
                        upper_bound=row.upper_bound,
                        threshold_pct=DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
                    )
                    if baseline > 0
                    else None
                )
                probability_source = HEURISTIC_EVENT_SCORE_SOURCE
            decision_basis_score = resolve_decision_basis_score(
                event_probability=probability,
                heuristic_event_score=heuristic_score,
            )
            decision_basis_type = resolve_decision_basis_type(
                event_probability=probability,
                heuristic_event_score=heuristic_score,
            )
            history.append(
                {
                    "date": row.forecast_date.isoformat() if row.forecast_date else None,
                    "signal_index": normalized_signal_index(
                        signal_basis_score=decision_basis_score
                    ),
                    "signal_basis_score": decision_basis_score,
                    "signal_basis_type": decision_basis_type,
                    "decision_priority_index": normalized_decision_priority_index(
                        decision_basis_score=decision_basis_score
                    ),
                    "decision_basis_score": decision_basis_score,
                    "decision_basis_type": decision_basis_type,
                    "event_probability": probability,
                    "heuristic_event_score": heuristic_score,
                    "signal_source": probability_source,
                    "probability_source": (probability_source if probability is not None else None),
                    "model_version": row.model_version,
                }
            )
        return {
            "virus_typ": virus_typ,
            "history": history,
        }
