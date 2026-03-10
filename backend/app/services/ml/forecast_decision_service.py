from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import (
    BacktestRun,
    ForecastAccuracyLog,
    MediaOutcomeRecord,
    MLForecast,
    WastewaterAggregated,
)
from app.services.ml.forecast_contracts import (
    DEFAULT_DECISION_BASELINE_WINDOW_DAYS,
    DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
    DEFAULT_DECISION_HORIZON_DAYS,
    BurdenForecast,
    BurdenForecastPoint,
    EventForecast,
    ForecastMonitoringSnapshot,
    ForecastQuality,
    OpportunityAssessment,
    confidence_label,
    event_probability_from_forecast,
    normalized_expected_value_index,
)


REQUIRED_OUTCOME_FIELD_NAMES = ("media_spend_eur",)
CONVERSION_OUTCOME_FIELD_NAMES = ("sales_units", "order_count", "revenue_eur")


class ForecastDecisionService:
    """Forecast-first runtime adapter for decision, risk and opportunity layers."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _latest_forecasts(self, virus_typ: str) -> list[MLForecast]:
        latest = (
            self.db.query(MLForecast)
            .filter(MLForecast.virus_typ == virus_typ)
            .order_by(MLForecast.created_at.desc())
            .first()
        )
        if not latest or not latest.created_at:
            return []
        return (
            self.db.query(MLForecast)
            .filter(
                MLForecast.virus_typ == virus_typ,
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
        age_days = (datetime.utcnow() - latest_created_at).total_seconds() / 86400.0
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
        age_days = (datetime.utcnow() - latest_created_at).total_seconds() / 86400.0
        if age_days <= fresh_days:
            return "fresh"
        if age_days <= stale_days:
            return "stale"
        return "expired"

    def _baseline_value(self, *, virus_typ: str) -> float:
        cutoff = datetime.utcnow() - timedelta(days=DEFAULT_DECISION_BASELINE_WINDOW_DAYS)
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
        raw_event_probability = None
        if horizon_forecast is not None and baseline_value > 0:
            raw_event_probability = event_probability_from_forecast(
                prediction=float(horizon_forecast.predicted_value or 0.0),
                baseline=baseline_value,
                lower_bound=horizon_forecast.lower_bound,
                upper_bound=horizon_forecast.upper_bound,
                threshold_pct=DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
            )

        market_metrics = latest_market.metrics if latest_market and latest_market.metrics else {}
        quality_gate = market_metrics.get("quality_gate") or {}
        event_calibration = market_metrics.get("event_calibration") or {}
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
        forecast_ready = bool(
            quality_gate.get("overall_passed")
            and drift_status != "warning"
            and freshness_status == "fresh"
        )

        confidence_parts: list[float] = []
        if quality_gate:
            confidence_parts.append(0.85 if quality_gate.get("overall_passed") else 0.45)
        if event_calibration.get("brier_score") is not None:
            confidence_parts.append(
                max(0.0, min(1.0, 1.0 - (float(event_calibration["brier_score"]) / 0.25)))
            )
        if event_calibration.get("ece") is not None:
            confidence_parts.append(
                max(0.0, min(1.0, 1.0 - (float(event_calibration["ece"]) / 0.20)))
            )
        confidence_value = (
            round(sum(confidence_parts) / len(confidence_parts), 3)
            if confidence_parts
            else None
        )

        event_forecast = EventForecast(
            event_key=f"{virus_typ.lower().replace(' ', '_')}_growth_7d",
            horizon_days=DEFAULT_DECISION_HORIZON_DAYS,
            event_probability=raw_event_probability,
            threshold_pct=DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
            baseline_value=round(float(baseline_value), 3) if baseline_value > 0 else None,
            threshold_value=(
                round(float(baseline_value) * 1.25, 3)
                if baseline_value > 0
                else None
            ),
            calibration_method=str(
                event_calibration.get("calibration_method")
                or "growth_sigmoid_with_oos_gate"
            ),
            brier_score=(
                round(float(event_calibration["brier_score"]), 4)
                if event_calibration.get("brier_score") is not None
                else None
            ),
            ece=(
                round(float(event_calibration["ece"]), 4)
                if event_calibration.get("ece") is not None
                else None
            ),
            calibration_passed=(
                bool(event_calibration.get("calibration_passed"))
                if event_calibration
                else None
            ),
            confidence=confidence_value,
            confidence_label=confidence_label(confidence_value),
        )

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

        compatibility_score = normalized_expected_value_index(
            event_probability=raw_event_probability,
            modifier=1.0 if forecast_ready else 0.75,
        )
        component_scores = {
            "wastewater": round(min(1.0, max(0.0, (raw_event_probability or 0.0) * 1.05)), 4),
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
                min(1.0, max(0.0, compatibility_score / 100.0)),
                4,
            ),
        }

        return {
            "virus_typ": virus_typ,
            "target_source": target_source,
            "burden_forecast": burden_forecast.to_dict(),
            "event_forecast": event_forecast.to_dict(),
            "forecast_quality": forecast_quality.to_dict(),
            "compatibility": {
                "final_risk_score": compatibility_score,
                "confidence_level": event_forecast.confidence_label,
                "component_scores": component_scores,
            },
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
            alerts.append("Kein Markt-Backtest fuer das Promotion-Gate vorhanden.")
        elif backtest_freshness_status != "fresh":
            alerts.append("Letzter Markt-Backtest ist nicht frisch.")

        promotion_gate = forecast_quality.get("promotion_gate") or {}
        interval_coverage = forecast_quality.get("interval_coverage") or {}
        if promotion_gate and not bool(promotion_gate.get("overall_passed")):
            alerts.append("Forecast-Promotion-Gate steht aktuell auf WATCH.")
        if interval_coverage and interval_coverage.get("interval_passed") is False:
            alerts.append("Intervallabdeckung liegt ausserhalb des Zielbands.")
        if event_forecast and event_forecast.get("calibration_passed") is False:
            alerts.append("Event-Probability ist nicht ausreichend kalibriert.")

        lead_lag = latest_backtest_payload.get("lead_lag") or {}
        effective_lead_days = lead_lag.get("effective_lead_days")
        if effective_lead_days is not None and float(effective_lead_days) <= 0:
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
                "confidence": event_forecast.get("confidence"),
                "confidence_label": event_forecast.get("confidence_label"),
                "calibration_passed": event_forecast.get("calibration_passed"),
            },
            latest_accuracy=latest_accuracy_payload,
            latest_backtest=latest_backtest_payload,
            alerts=alerts,
        )
        return snapshot.to_dict()

    def get_truth_readiness(
        self,
        *,
        brand: str = "gelo",
    ) -> dict[str, Any]:
        brand_value = str(brand or "gelo").strip().lower()
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
        brand: str = "gelo",
        secondary_modifier: float = 1.0,
    ) -> dict[str, Any]:
        bundle = self.build_forecast_bundle(virus_typ=virus_typ, target_source=target_source)
        quality = bundle.get("forecast_quality") or {}
        event_forecast = bundle.get("event_forecast") or {}
        truth = self.get_truth_readiness(brand=brand)
        event_probability = event_forecast.get("event_probability")
        expected_value_index = normalized_expected_value_index(
            event_probability=event_probability,
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
            expected_value_index=expected_value_index,
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
        compatibility = bundle.get("compatibility") or {}
        return {
            "virus_typ": virus_typ,
            "final_risk_score": compatibility.get("final_risk_score", 0.0),
            "confidence_level": compatibility.get("confidence_level", "Mittel"),
            "component_scores": compatibility.get("component_scores", {}),
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
            (float(item.get("final_risk_score") or 0.0) for item in per_virus.values()),
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
        cutoff = datetime.utcnow() - timedelta(days=max(1, int(days)))
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
            probability = event_probability_from_forecast(
                prediction=float(row.predicted_value or 0.0),
                baseline=baseline,
                lower_bound=row.lower_bound,
                upper_bound=row.upper_bound,
                threshold_pct=DEFAULT_DECISION_EVENT_THRESHOLD_PCT,
            ) if baseline > 0 else None
            history.append(
                {
                    "date": row.forecast_date.isoformat() if row.forecast_date else None,
                    "score": normalized_expected_value_index(event_probability=probability),
                    "event_probability": probability,
                    "model_version": row.model_version,
                }
            )
        return {
            "virus_typ": virus_typ,
            "history": history,
        }
