from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.services.media.business_validation_service import BusinessValidationService
from app.services.media.v2_service import MediaV2Service
from app.services.ml.regional_forecast import RegionalForecastService
from app.services.ops.regional_operational_snapshot_store import RegionalOperationalSnapshotStore


_LEGACY_RISK_ENGINE_CUTOFF_DATE = "2026-04-30"
_LIVE_EVALUATION_ARCHIVES = {
    ("RSV A", 7): "rsv_a_h7_rsv_ranking",
}
_DEFAULT_LIVE_EVALUATION_ROOT = (
    Path(__file__).resolve().parents[2] / "ml_models" / "regional_panel_h7_live_evaluation"
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class PilotReadoutService:
    """Single-source customer readout for the PEIX / GELO pilot surface."""

    def __init__(
        self,
        db: Session,
        *,
        live_evaluation_root: Path | None = None,
    ) -> None:
        self.db = db
        self.media_service = MediaV2Service(db)
        self.business_validation_service = BusinessValidationService(db)
        self.regional_service = RegionalForecastService(db)
        self.snapshot_store = RegionalOperationalSnapshotStore(db)
        self.live_evaluation_root = live_evaluation_root or _DEFAULT_LIVE_EVALUATION_ROOT

    def build_readout(
        self,
        *,
        brand: str = "gelo",
        virus_typ: str = "RSV A",
        horizon_days: int = 7,
        weekly_budget_eur: float = 120000.0,
        top_n: int = 12,
    ) -> dict[str, Any]:
        brand_value = str(brand or "gelo").strip().lower()
        forecast = self.regional_service.predict_all_regions(
            virus_typ=virus_typ,
            horizon_days=horizon_days,
        )
        allocation = self.regional_service.generate_media_allocation(
            virus_typ=virus_typ,
            weekly_budget_eur=weekly_budget_eur,
            horizon_days=horizon_days,
        )
        recommendations = self.regional_service.campaign_recommendation_service.recommend_from_allocation(
            allocation_payload=allocation,
            top_n=top_n,
        )
        recommendations.setdefault("horizon_days", horizon_days)
        recommendations.setdefault(
            "target_window_days",
            allocation.get("target_window_days") or [horizon_days, horizon_days],
        )

        truth_coverage = self.media_service.get_truth_coverage(
            brand=brand_value,
            virus_typ=virus_typ,
        )
        truth_gate = self.media_service.truth_gate_service.evaluate(truth_coverage)
        business_validation = self.business_validation_service.evaluate(
            brand=brand_value,
            virus_typ=virus_typ,
            truth_coverage=truth_coverage,
            truth_gate=truth_gate,
        )
        evaluation = self._latest_live_evaluation(
            virus_typ=virus_typ,
            horizon_days=horizon_days,
        )
        operational_snapshot = self.snapshot_store.latest_scope_snapshot(
            virus_typ=virus_typ,
            horizon_days=horizon_days,
        )
        recent_snapshots = self.snapshot_store.recent_scope_snapshots(
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            limit=3,
        )

        region_rows = self._region_rows(
            forecast=forecast,
            allocation=allocation,
            recommendations=recommendations,
        )
        forecast_readiness = self._forecast_first_scope_readiness(
            forecast=forecast,
            evaluation=evaluation,
        )
        commercial_validation_status = self._commercial_validation_status(
            truth_coverage=truth_coverage,
            business_validation=business_validation,
        )
        budget_mode = self._budget_mode(business_validation=business_validation)
        validation_disclaimer = self._validation_disclaimer(
            business_validation=business_validation,
            budget_mode=budget_mode,
        )
        scope_readiness_by_section = {
            "forecast": self._forecast_scope_readiness(forecast),
            "allocation": self._allocation_scope_readiness(allocation),
            "recommendation": self._recommendation_scope_readiness(recommendations),
            "evidence": self._evidence_scope_readiness(
                business_validation=business_validation,
                evaluation=evaluation,
            ),
        }
        overall_scope_readiness = forecast_readiness
        missing_requirements = self._missing_requirements(
            truth_coverage=truth_coverage,
            business_validation=business_validation,
        )
        gate_snapshot = self._gate_snapshot(
            forecast=forecast,
            truth_coverage=truth_coverage,
            business_validation=business_validation,
            evaluation=evaluation,
            forecast_readiness=forecast_readiness,
            commercial_validation_status=commercial_validation_status,
            overall_scope_readiness=overall_scope_readiness,
            missing_requirements=missing_requirements,
        )
        executive_summary = self._executive_summary(
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            weekly_budget_eur=weekly_budget_eur,
            forecast=forecast,
            allocation=allocation,
            recommendations=recommendations,
            region_rows=region_rows,
            forecast_readiness=forecast_readiness,
            commercial_validation_status=commercial_validation_status,
            budget_mode=budget_mode,
            validation_disclaimer=validation_disclaimer,
            overall_scope_readiness=overall_scope_readiness,
            gate_snapshot=gate_snapshot,
        )

        readout = {
            "brand": brand_value,
            "virus_typ": virus_typ,
            "horizon_days": int(horizon_days),
            "weekly_budget_eur": round(float(weekly_budget_eur), 2),
            "generated_at": _utc_now_iso(),
            "run_context": {
                "brand": brand_value,
                "virus_typ": virus_typ,
                "horizon_days": int(horizon_days),
                "generated_at": forecast.get("generated_at") or allocation.get("generated_at"),
                "as_of_date": forecast.get("as_of_date"),
                "target_week_start": forecast.get("predictions", [{}])[0].get("target_week_start")
                if forecast.get("predictions")
                else None,
                "model_version": forecast.get("model_version"),
                "calibration_version": forecast.get("calibration_version"),
                "artifact_transition_mode": forecast.get("artifact_transition_mode"),
                "rollout_mode": forecast.get("rollout_mode"),
                "activation_policy": forecast.get("activation_policy"),
                "forecast_readiness": forecast_readiness,
                "commercial_validation_status": commercial_validation_status,
                "pilot_mode": "forecast_first",
                "budget_mode": budget_mode,
                "validation_disclaimer": validation_disclaimer,
                "scope_readiness": overall_scope_readiness,
                "scope_readiness_by_section": scope_readiness_by_section,
                "promotion_status": self._promotion_status(
                    evaluation=evaluation,
                    forecast=forecast,
                ),
                "gate_snapshot": gate_snapshot,
            },
            "executive_summary": executive_summary,
            "operational_recommendations": {
                "scope_readiness": scope_readiness_by_section["recommendation"],
                "summary": {
                    "headline": recommendations.get("headline") or allocation.get("headline"),
                    "total_regions": len(region_rows),
                    "activate_regions": allocation.get("summary", {}).get("activate_regions"),
                    "prepare_regions": allocation.get("summary", {}).get("prepare_regions"),
                    "watch_regions": allocation.get("summary", {}).get("watch_regions"),
                    "ready_recommendations": recommendations.get("summary", {}).get("ready_recommendations"),
                    "guarded_recommendations": recommendations.get("summary", {}).get("guarded_recommendations"),
                    "observe_only_recommendations": recommendations.get("summary", {}).get("observe_only_recommendations"),
                },
                "regions": region_rows,
            },
            "pilot_evidence": {
                "scope_readiness": scope_readiness_by_section["evidence"],
                "evaluation": evaluation,
                "readiness": gate_snapshot,
                "truth_coverage": truth_coverage,
                "business_validation": business_validation,
                "operational_snapshot": operational_snapshot,
                "recent_operational_snapshots": recent_snapshots,
                "legacy_context": {
                    "status": "frozen",
                    "sunset_date": _LEGACY_RISK_ENGINE_CUTOFF_DATE,
                    "customer_surface_exposed": False,
                    "note": "Der alte Risk-Engine- und Supply-Shock-Pfad ist isoliert und bestimmt dieses Piloturteil nicht mehr.",
                },
            },
        }
        readout["empty_state"] = self._empty_state(
            forecast=forecast,
            overall_scope_readiness=overall_scope_readiness,
            gate_snapshot=gate_snapshot,
        )
        return readout

    def _region_rows(
        self,
        *,
        forecast: dict[str, Any],
        allocation: dict[str, Any],
        recommendations: dict[str, Any],
    ) -> list[dict[str, Any]]:
        forecast_rows = list(forecast.get("predictions") or [])
        allocation_rows = {
            str(item.get("bundesland") or item.get("region") or "").strip().upper(): item
            for item in (allocation.get("recommendations") or [])
        }
        recommendation_rows = {
            str(item.get("region") or "").strip().upper(): item
            for item in (recommendations.get("recommendations") or [])
        }
        rows: list[dict[str, Any]] = []
        for prediction in forecast_rows:
            region_code = str(prediction.get("bundesland") or "").strip().upper()
            allocation_item = allocation_rows.get(region_code) or {}
            recommendation_item = recommendation_rows.get(region_code) or {}
            decision_stage = (
                recommendation_item.get("activation_level")
                or allocation_item.get("recommended_activation_level")
                or prediction.get("decision_label")
                or "Beobachten"
            )
            decision_payload = allocation_item.get("decision") or prediction.get("decision") or {}
            reason_trace = self._unique_non_empty(
                [
                    *self._reason_trace_lines(prediction.get("reason_trace")),
                    *self._reason_trace_lines(allocation_item.get("reason_trace")),
                    *self._reason_trace_lines(
                        recommendation_item.get("recommendation_rationale"),
                    ),
                    str(decision_payload.get("explanation_summary") or "").strip(),
                    str(allocation_item.get("uncertainty_summary") or "").strip(),
                ]
            )
            reason_trace_details = self._unique_reason_details(
                [
                    *self._reason_trace_detail_items(prediction.get("reason_trace")),
                    *self._reason_trace_detail_items(allocation_item.get("reason_trace")),
                    *self._reason_trace_detail_items(
                        recommendation_item.get("recommendation_rationale"),
                    ),
                    decision_payload.get("explanation_summary_detail"),
                ]
            )
            rows.append(
                {
                    "region_code": region_code,
                    "region_name": prediction.get("bundesland_name") or recommendation_item.get("region_name"),
                    "decision_stage": decision_stage,
                    "forecast_scope_readiness": self._forecast_scope_readiness({"predictions": [prediction], "quality_gate": forecast.get("quality_gate"), "status": forecast.get("status")}),
                    "priority_rank": recommendation_item.get("priority_rank") or allocation_item.get("priority_rank") or prediction.get("decision_rank"),
                    "priority_score": prediction.get("priority_score"),
                    "event_probability": prediction.get("event_probability_calibrated"),
                    "allocation_score": allocation_item.get("allocation_score"),
                    "confidence": recommendation_item.get("confidence") or allocation_item.get("confidence"),
                    "budget_share": allocation_item.get("suggested_budget_share"),
                    "budget_amount_eur": allocation_item.get("suggested_budget_amount")
                    or allocation_item.get("budget_eur"),
                    "recommended_product": (
                        (recommendation_item.get("recommended_product_cluster") or {}).get("label")
                        or ((allocation_item.get("products") or [None])[0])
                    ),
                    "recommended_keywords": (
                        (recommendation_item.get("recommended_keyword_cluster") or {}).get("label")
                    ),
                    "campaign_recommendation": (
                        recommendation_item.get("timeline")
                        or recommendation_item.get("region_name")
                    ),
                    "channels": recommendation_item.get("channels") or allocation_item.get("channels") or [],
                    "uncertainty_summary": allocation_item.get("uncertainty_summary")
                    or prediction.get("uncertainty_summary"),
                    "uncertainty_summary_detail": decision_payload.get("uncertainty_summary_detail"),
                    "reason_trace": reason_trace[:4],
                    "reason_trace_details": reason_trace_details[:6],
                    "quality_gate": allocation_item.get("quality_gate") or forecast.get("quality_gate"),
                    "business_gate": allocation_item.get("business_gate") or forecast.get("business_gate"),
                    "spend_gate_status": allocation_item.get("spend_gate_status"),
                    "budget_release_recommendation": allocation_item.get("budget_release_recommendation"),
                }
            )
        rows.sort(
            key=lambda item: (
                int(item.get("priority_rank") or 10_000),
                -float(item.get("priority_score") or 0.0),
                -float(item.get("event_probability") or 0.0),
            )
        )
        return rows

    def _executive_summary(
        self,
        *,
        virus_typ: str,
        horizon_days: int,
        weekly_budget_eur: float,
        forecast: dict[str, Any],
        allocation: dict[str, Any],
        recommendations: dict[str, Any],
        region_rows: list[dict[str, Any]],
        forecast_readiness: str,
        commercial_validation_status: str,
        budget_mode: str,
        validation_disclaimer: str,
        overall_scope_readiness: str,
        gate_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        lead_region = region_rows[0] if region_rows else {}
        lead_stage = str(lead_region.get("decision_stage") or "Beobachten")
        reason_trace = list(lead_region.get("reason_trace") or [])[:3]
        reason_trace_details = list(lead_region.get("reason_trace_details") or [])[:3]
        blocked_reasons = list(allocation.get("summary", {}).get("spend_blockers") or [])
        if gate_snapshot["missing_requirements"]:
            blocked_reasons = self._unique_non_empty(
                blocked_reasons + gate_snapshot["missing_requirements"]
            )
        if overall_scope_readiness == "GO" and gate_snapshot.get("budget_release_status") == "GO":
            recommendation_text = (
                f"Fokussiere {lead_region.get('region_name')} jetzt und gib das Wochenbudget in der empfohlenen Verteilung frei."
            )
        elif overall_scope_readiness == "GO":
            recommendation_text = (
                f"Fokussiere {lead_region.get('region_name')} jetzt und nutze die Verteilung unten als forecast-basierten Szenario-Split, solange die kommerzielle Validierung noch aussteht."
            )
        elif lead_region:
            recommendation_text = (
                f"Behalte {lead_region.get('region_name')} ganz oben auf dem Plan, aber gib Budget erst frei, wenn die offenen Gate-Anforderungen geschlossen sind."
            )
        else:
            recommendation_text = "Für diesen Scope liegt aktuell noch keine belastbare Kundenempfehlung vor."
        return {
            "what_should_we_do_now": recommendation_text,
            "decision_stage": lead_stage,
            "forecast_readiness": forecast_readiness,
            "commercial_validation_status": commercial_validation_status,
            "pilot_mode": "forecast_first",
            "budget_mode": budget_mode,
            "validation_disclaimer": validation_disclaimer,
            "scope_readiness": overall_scope_readiness,
            "headline": recommendations.get("headline")
            or allocation.get("headline")
            or f"{virus_typ} / h{horizon_days}",
            "top_regions": region_rows[:3],
            "budget_recommendation": {
                "weekly_budget_eur": round(float(weekly_budget_eur), 2),
                "recommended_active_budget_eur": allocation.get("summary", {}).get("total_budget_allocated"),
                "scenario_budget_eur": allocation.get("summary", {}).get("total_budget_allocated"),
                "spend_enabled": bool(allocation.get("summary", {}).get("spend_enabled")),
                "budget_mode": budget_mode,
                "blocked_reasons": blocked_reasons,
            },
            "confidence_summary": {
                "lead_region_confidence": lead_region.get("confidence"),
                "lead_region_event_probability": lead_region.get("event_probability"),
                "evaluation_retained": (gate_snapshot.get("latest_evaluation") or {}).get("retained"),
                "evaluation_gate_outcome": (gate_snapshot.get("latest_evaluation") or {}).get("gate_outcome"),
            },
            "uncertainty_summary": lead_region.get("uncertainty_summary"),
            "uncertainty_summary_detail": lead_region.get("uncertainty_summary_detail"),
            "reason_trace": reason_trace,
            "reason_trace_details": reason_trace_details,
        }

    def _gate_snapshot(
        self,
        *,
        forecast: dict[str, Any],
        truth_coverage: dict[str, Any],
        business_validation: dict[str, Any],
        evaluation: dict[str, Any] | None,
        forecast_readiness: str,
        commercial_validation_status: str,
        overall_scope_readiness: str,
        missing_requirements: list[str],
    ) -> dict[str, Any]:
        quality_gate = forecast.get("quality_gate") or {}
        latest_evaluation = evaluation or {}
        budget_mode = self._budget_mode(business_validation=business_validation)
        return {
            "scope_readiness": overall_scope_readiness,
            "forecast_readiness": forecast_readiness,
            "epidemiology_status": self._epidemiology_status(forecast),
            "commercial_data_status": self._commercial_data_status(
                truth_coverage=truth_coverage,
                business_validation=business_validation,
            ),
            "commercial_validation_status": commercial_validation_status,
            "holdout_status": "GO" if business_validation.get("holdout_ready") else "WATCH",
            "budget_release_status": (
                "GO" if business_validation.get("validated_for_budget_activation") else "WATCH"
            ),
            "pilot_mode": "forecast_first",
            "budget_mode": budget_mode,
            "validation_disclaimer": self._validation_disclaimer(
                business_validation=business_validation,
                budget_mode=budget_mode,
            ),
            "missing_requirements": missing_requirements,
            "coverage_weeks": truth_coverage.get("coverage_weeks"),
            "truth_freshness_state": truth_coverage.get("truth_freshness_state"),
            "validation_status": business_validation.get("validation_status"),
            "quality_gate_failed_checks": list(quality_gate.get("failed_checks") or []),
            "forecast_gate_outcome": quality_gate.get("forecast_readiness"),
            "latest_evaluation": {
                "available": bool(evaluation),
                "run_id": latest_evaluation.get("run_id"),
                "generated_at": latest_evaluation.get("generated_at"),
                "selected_experiment_name": latest_evaluation.get("selected_experiment_name"),
                "calibration_mode": latest_evaluation.get("calibration_mode"),
                "gate_outcome": latest_evaluation.get("gate_outcome"),
                "retained": latest_evaluation.get("retained"),
                "archive_dir": latest_evaluation.get("archive_dir"),
            },
        }

    def _missing_requirements(
        self,
        *,
        truth_coverage: dict[str, Any],
        business_validation: dict[str, Any],
    ) -> list[str]:
        requirements: list[str] = []
        coverage_weeks = int(truth_coverage.get("coverage_weeks") or 0)
        if coverage_weeks <= 0:
            requirements.append("Es sind noch keine GELO-Outcome-Daten angeschlossen.")
        elif coverage_weeks < 26:
            requirements.append("Es fehlen noch mindestens 26 Wochen GELO-Outcome-Historie.")
        if not truth_coverage.get("required_fields_present"):
            requirements.append("Wöchentliche Media-Spend-Daten fehlen noch in der GELO-Outcome-Schicht.")
        if not truth_coverage.get("conversion_fields_present"):
            requirements.append("Sales-, Orders- oder Revenue-Metriken fehlen noch in der GELO-Outcome-Schicht.")
        if int(business_validation.get("activation_cycles") or 0) < 2:
            requirements.append("Es werden noch mindestens zwei klar markierte Aktivierungszyklen benötigt.")
        if not business_validation.get("holdout_ready"):
            requirements.append("Eine Test-/Kontrolllogik beziehungsweise ein Holdout-Design fehlt noch.")
        if not business_validation.get("lift_metrics_available"):
            requirements.append("Validierte inkrementelle Lift-Metriken fehlen noch.")
        return requirements

    def _forecast_scope_readiness(self, forecast: dict[str, Any]) -> str:
        status = str(forecast.get("status") or "").strip().lower()
        if status in {"no_model", "unsupported"}:
            return "NO_GO"
        if status == "no_data" or not (forecast.get("predictions") or []):
            return "NO_GO"
        if bool((forecast.get("quality_gate") or {}).get("overall_passed")):
            return "GO"
        return "WATCH"

    def _allocation_scope_readiness(self, allocation: dict[str, Any]) -> str:
        status = str(allocation.get("status") or "").strip().lower()
        if status in {"no_model", "unsupported", "no_data"} or not (allocation.get("recommendations") or []):
            return "NO_GO"
        if any(
            item.get("suggested_budget_share") is not None
            or item.get("suggested_budget_amount") is not None
            or item.get("budget_eur") is not None
            for item in (allocation.get("recommendations") or [])
        ):
            return "GO"
        return "WATCH"

    def _recommendation_scope_readiness(self, recommendations: dict[str, Any]) -> str:
        status = str(recommendations.get("status") or "").strip().lower()
        if status in {"no_model", "unsupported", "no_data"} or not (recommendations.get("recommendations") or []):
            return "NO_GO"
        if int(recommendations.get("summary", {}).get("ready_recommendations") or 0) > 0:
            return "GO"
        if int(recommendations.get("summary", {}).get("guarded_recommendations") or 0) > 0:
            return "GO"
        if int(recommendations.get("summary", {}).get("observe_only_recommendations") or 0) > 0:
            return "GO"
        return "WATCH"

    def _evidence_scope_readiness(
        self,
        *,
        business_validation: dict[str, Any],
        evaluation: dict[str, Any] | None,
    ) -> str:
        if evaluation and evaluation.get("gate_outcome") == "GO" and evaluation.get("retained") is True:
            return "GO"
        if evaluation or business_validation.get("coverage_weeks") or business_validation.get("validation_status"):
            return "WATCH"
        return "NO_GO"

    def _forecast_first_scope_readiness(
        self,
        *,
        forecast: dict[str, Any],
        evaluation: dict[str, Any] | None,
    ) -> str:
        forecast_readiness = self._forecast_scope_readiness(forecast)
        if forecast_readiness == "NO_GO":
            return "NO_GO"
        if (
            forecast_readiness == "GO"
            and evaluation
            and evaluation.get("gate_outcome") == "GO"
            and evaluation.get("retained") is True
        ):
            return "GO"
        return "WATCH"

    def _epidemiology_status(self, forecast: dict[str, Any]) -> str:
        if self._forecast_scope_readiness(forecast) == "GO":
            return "GO"
        if str(forecast.get("status") or "").strip().lower() in {"no_model", "no_data", "unsupported"}:
            return "NO_GO"
        return "WATCH"

    def _commercial_data_status(
        self,
        *,
        truth_coverage: dict[str, Any],
        business_validation: dict[str, Any],
    ) -> str:
        if int(truth_coverage.get("coverage_weeks") or 0) <= 0:
            return "NO_GO"
        if business_validation.get("validated_for_budget_activation"):
            return "GO"
        return "WATCH"

    def _commercial_validation_status(
        self,
        *,
        truth_coverage: dict[str, Any],
        business_validation: dict[str, Any],
    ) -> str:
        return self._commercial_data_status(
            truth_coverage=truth_coverage,
            business_validation=business_validation,
        )

    @staticmethod
    def _budget_mode(
        *,
        business_validation: dict[str, Any],
    ) -> str:
        if business_validation.get("validated_for_budget_activation"):
            return "validated_allocation"
        return "scenario_split"

    @staticmethod
    def _validation_disclaimer(
        *,
        business_validation: dict[str, Any],
        budget_mode: str,
    ) -> str:
        if budget_mode == "validated_allocation" and business_validation.get("validated_for_budget_activation"):
            return "Forecast und kommerzielle Validierung greifen für diesen Scope bereits sauber zusammen."
        return (
            "Diese Budgetsicht ist ein forecast-basierter Szenario-Split. "
            "Die kommerzielle Validierung für die Budgetfreigabe von GELO steht noch aus."
        )

    def _promotion_status(
        self,
        *,
        evaluation: dict[str, Any] | None,
        forecast: dict[str, Any],
    ) -> str:
        if evaluation and evaluation.get("gate_outcome") == "GO" and evaluation.get("retained") is True:
            return "promoted_or_ready"
        if self._forecast_scope_readiness(forecast) == "GO":
            return "operational_go_without_budget_release"
        return "not_promoted"

    def _empty_state(
        self,
        *,
        forecast: dict[str, Any],
        overall_scope_readiness: str,
        gate_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        status = str(forecast.get("status") or "").strip().lower()
        if status in {"no_model", "unsupported"}:
            return {
                "code": "no_model",
                "title": "Für diesen Scope ist aktuell kein kundenfähiges Modell verfügbar.",
                "body": "Wechsle Virus oder Horizont, bis der regionale Forecast-Pfad wieder verfügbar ist.",
            }
        if status == "no_data" or not (forecast.get("predictions") or []):
            return {
                "code": "no_data",
                "title": "Der Modellpfad existiert, aber aktuell reichen die Live-Daten noch nicht für eine Pilotentscheidung.",
                "body": "Die Oberfläche bleibt lesbar, aber es wird keine harte Empfehlung gezeigt.",
            }
        if overall_scope_readiness == "GO":
            return {
                "code": "ready",
                "title": "Dieser Scope ist für den Forecast-First-Pilot bereit.",
                "body": "Die aktuelle Empfehlungskette ist konsistent genug für ein kundenseitiges Forecast-Gespräch.",
            }
        if overall_scope_readiness == "NO_GO":
            return {
                "code": "no_go",
                "title": "Dieser Scope bleibt bewusst gesperrt.",
                "body": "Harte Gates schlagen noch fehl, deshalb bleibt die Budgetfreigabe geschlossen.",
            }
        if gate_snapshot.get("forecast_readiness") != "GO":
            return {
                "code": "watch_only",
                "title": "Der Pilot ist sichtbar, aber der Forecast-Pfad ist noch nicht stabil genug.",
                "body": "Belasse den Scope auf WATCH, bis Forecast-Evidenz und Promotion-Pfad stark genug für einen sauberen kundenseitigen Readout sind.",
            }
        return {
            "code": "watch_only",
            "title": "Der Forecast ist nutzbar, die kommerzielle Validierung steht aber noch aus.",
            "body": "Nutze die aktuelle Verteilung als Szenario-Split für die Planung und erkläre, dass GELO-Outcome-Daten später die kommerzielle Validierung freischalten.",
        }

    def _latest_live_evaluation(
        self,
        *,
        virus_typ: str,
        horizon_days: int,
    ) -> dict[str, Any] | None:
        archive_name = _LIVE_EVALUATION_ARCHIVES.get((virus_typ, int(horizon_days)))
        if not archive_name:
            return None
        archive_root = self.live_evaluation_root / archive_name
        if not archive_root.exists():
            return None
        candidates = sorted(
            [
                path
                for path in archive_root.iterdir()
                if path.is_dir() and (path / "report.json").exists()
            ],
            key=lambda path: path.name,
            reverse=True,
        )
        if not candidates:
            return None
        report_path = candidates[0] / "report.json"
        try:
            report = json.loads(report_path.read_text())
        except Exception:
            return None
        return {
            "archive_dir": str(candidates[0]),
            "report_path": str(report_path),
            "run_id": report.get("run_id"),
            "generated_at": report.get("generated_at"),
            "selected_experiment_name": report.get("selected_experiment_name"),
            "calibration_mode": report.get("calibration_mode"),
            "gate_outcome": report.get("gate_outcome"),
            "retained": report.get("retained"),
            "baseline": report.get("baseline"),
            "selected_experiment": report.get("selected_experiment"),
            "comparison_table": report.get("comparison_table") or [],
            "validation": report.get("validation") or {},
        }

    @staticmethod
    def _reason_trace_lines(trace: Any) -> list[str]:
        if not trace:
            return []
        if isinstance(trace, str):
            stripped = trace.strip()
            return [stripped] if stripped else []
        if isinstance(trace, list):
            lines: list[str] = []
            for item in trace:
                if PilotReadoutService._is_reason_detail_item(item):
                    message = str(item.get("message") or "").strip()
                    if message:
                        lines.append(message)
                    continue
                stripped = str(item).strip()
                if stripped:
                    lines.append(stripped)
            return lines
        if isinstance(trace, dict):
            lines: list[str] = []
            for key in (
                "why",
                "uncertainty",
                "guardrails",
                "budget_notes",
                "evidence_notes",
                "product_fit",
                "keyword_fit",
            ):
                value = trace.get(key)
                if isinstance(value, list):
                    lines.extend(str(item).strip() for item in value if str(item).strip())
            for key in (
                "why_details",
                "uncertainty_details",
                "policy_override_details",
                "budget_driver_details",
                "blocker_details",
                "guardrail_details",
                "budget_note_details",
                "evidence_note_details",
                "product_fit_details",
                "keyword_fit_details",
            ):
                value = trace.get(key)
                if isinstance(value, list):
                    for item in value:
                        if PilotReadoutService._is_reason_detail_item(item):
                            message = str(item.get("message") or "").strip()
                            if message:
                                lines.append(message)
            if trace.get("summary"):
                lines.append(str(trace.get("summary")).strip())
            return [item for item in lines if item]
        return [str(trace).strip()]

    @staticmethod
    def _is_reason_detail_item(value: Any) -> bool:
        return (
            isinstance(value, dict)
            and isinstance(value.get("code"), str)
            and isinstance(value.get("message"), str)
        )

    @classmethod
    def _reason_trace_detail_items(cls, trace: Any) -> list[dict[str, Any]]:
        if not trace:
            return []
        if cls._is_reason_detail_item(trace):
            return [dict(trace)]
        if isinstance(trace, list):
            return [dict(item) for item in trace if cls._is_reason_detail_item(item)]
        if isinstance(trace, dict):
            details: list[dict[str, Any]] = []
            for key in (
                "why_details",
                "uncertainty_details",
                "policy_override_details",
                "budget_driver_details",
                "blocker_details",
                "guardrail_details",
                "budget_note_details",
                "evidence_note_details",
                "product_fit_details",
                "keyword_fit_details",
            ):
                value = trace.get(key)
                if isinstance(value, list):
                    details.extend(dict(item) for item in value if cls._is_reason_detail_item(item))
            return details
        return []

    @staticmethod
    def _unique_reason_details(values: list[Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for value in values:
            if not PilotReadoutService._is_reason_detail_item(value):
                continue
            key = json.dumps(value, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            result.append(dict(value))
        return result

    @staticmethod
    def _unique_non_empty(values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            cleaned = str(value or "").strip()
            if cleaned and cleaned not in result:
                result.append(cleaned)
        return result
