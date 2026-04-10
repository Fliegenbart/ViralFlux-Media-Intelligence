from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.services.media.business_validation_service import BusinessValidationService
from app.services.media import pilot_readout_readiness
from app.services.media import pilot_readout_sections
from app.services.media import pilot_readout_trace
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
        if operational_snapshot:
            operational_snapshot = RegionalOperationalSnapshotStore._normalized_metadata(
                dict(operational_snapshot)
            )
        recent_snapshots = self.snapshot_store.recent_scope_snapshots(
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            limit=3,
        )
        recent_snapshots = [
            RegionalOperationalSnapshotStore._normalized_metadata(dict(item))
            for item in recent_snapshots
            if item
        ]

        region_rows = self._region_rows(
            forecast=forecast,
            allocation=allocation,
            recommendations=recommendations,
        )
        forecast_readiness = self._forecast_first_scope_readiness(
            forecast=forecast,
            evaluation=evaluation,
            operational_snapshot=operational_snapshot,
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
            "forecast": self._forecast_scope_readiness(
                forecast,
                operational_snapshot=operational_snapshot,
            ),
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
            operational_snapshot=operational_snapshot,
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
                    operational_snapshot=operational_snapshot,
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
                    "note": "Der alte Legacy-Risk-Pfad ist entfernt und bestimmt dieses Piloturteil nicht mehr.",
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
        return pilot_readout_sections.build_region_rows(
            self,
            forecast=forecast,
            allocation=allocation,
            recommendations=recommendations,
        )

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
        return pilot_readout_sections.build_executive_summary(
            self,
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

    def _gate_snapshot(
        self,
        *,
        forecast: dict[str, Any],
        truth_coverage: dict[str, Any],
        business_validation: dict[str, Any],
        evaluation: dict[str, Any] | None,
        operational_snapshot: dict[str, Any] | None,
        forecast_readiness: str,
        commercial_validation_status: str,
        overall_scope_readiness: str,
        missing_requirements: list[str],
    ) -> dict[str, Any]:
        return pilot_readout_readiness._gate_snapshot(
            self,
            forecast=forecast,
            truth_coverage=truth_coverage,
            business_validation=business_validation,
            evaluation=evaluation,
            operational_snapshot=operational_snapshot,
            forecast_readiness=forecast_readiness,
            commercial_validation_status=commercial_validation_status,
            overall_scope_readiness=overall_scope_readiness,
            missing_requirements=missing_requirements,
        )

    def _missing_requirements(
        self,
        *,
        truth_coverage: dict[str, Any],
        business_validation: dict[str, Any],
    ) -> list[str]:
        return pilot_readout_readiness._missing_requirements(
            self,
            truth_coverage=truth_coverage,
            business_validation=business_validation,
        )

    def _forecast_scope_readiness(
        self,
        forecast: dict[str, Any],
        *,
        operational_snapshot: dict[str, Any] | None = None,
    ) -> str:
        return pilot_readout_readiness._forecast_scope_readiness(
            self,
            forecast,
            operational_snapshot=operational_snapshot,
        )

    def _allocation_scope_readiness(self, allocation: dict[str, Any]) -> str:
        return pilot_readout_readiness._allocation_scope_readiness(self, allocation)

    def _recommendation_scope_readiness(self, recommendations: dict[str, Any]) -> str:
        return pilot_readout_readiness._recommendation_scope_readiness(self, recommendations)

    def _evidence_scope_readiness(
        self,
        *,
        business_validation: dict[str, Any],
        evaluation: dict[str, Any] | None,
    ) -> str:
        return pilot_readout_readiness._evidence_scope_readiness(
            self,
            business_validation=business_validation,
            evaluation=evaluation,
        )

    def _forecast_first_scope_readiness(
        self,
        *,
        forecast: dict[str, Any],
        evaluation: dict[str, Any] | None,
        operational_snapshot: dict[str, Any] | None = None,
    ) -> str:
        return pilot_readout_readiness._forecast_first_scope_readiness(
            self,
            forecast=forecast,
            evaluation=evaluation,
            operational_snapshot=operational_snapshot,
        )

    def _epidemiology_status(
        self,
        forecast: dict[str, Any],
        *,
        operational_snapshot: dict[str, Any] | None = None,
    ) -> str:
        return pilot_readout_readiness._epidemiology_status(
            self,
            forecast,
            operational_snapshot=operational_snapshot,
        )

    @staticmethod
    def _status_to_readiness(value: Any) -> str:
        return pilot_readout_readiness._status_to_readiness(None, value)

    def _operational_scope_status(self, operational_snapshot: dict[str, Any] | None) -> str:
        return pilot_readout_readiness._operational_scope_status(self, operational_snapshot)

    def _operational_readiness_snapshot(
        self,
        operational_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return pilot_readout_readiness._operational_readiness_snapshot(self, operational_snapshot)

    def _commercial_data_status(
        self,
        *,
        truth_coverage: dict[str, Any],
        business_validation: dict[str, Any],
    ) -> str:
        return pilot_readout_readiness._commercial_data_status(
            self,
            truth_coverage=truth_coverage,
            business_validation=business_validation,
        )

    def _commercial_validation_status(
        self,
        *,
        truth_coverage: dict[str, Any],
        business_validation: dict[str, Any],
    ) -> str:
        return pilot_readout_readiness._commercial_validation_status(
            self,
            truth_coverage=truth_coverage,
            business_validation=business_validation,
        )

    @staticmethod
    def _budget_mode(
        *,
        business_validation: dict[str, Any],
    ) -> str:
        return pilot_readout_readiness._budget_mode(
            None,
            business_validation=business_validation,
        )

    @staticmethod
    def _validation_disclaimer(
        *,
        business_validation: dict[str, Any],
        budget_mode: str,
    ) -> str:
        return pilot_readout_readiness._validation_disclaimer(
            None,
            business_validation=business_validation,
            budget_mode=budget_mode,
        )

    def _promotion_status(
        self,
        *,
        evaluation: dict[str, Any] | None,
        forecast: dict[str, Any],
        operational_snapshot: dict[str, Any] | None = None,
    ) -> str:
        return pilot_readout_readiness._promotion_status(
            self,
            evaluation=evaluation,
            forecast=forecast,
            operational_snapshot=operational_snapshot,
        )

    def _empty_state(
        self,
        *,
        forecast: dict[str, Any],
        overall_scope_readiness: str,
        gate_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        return pilot_readout_readiness._empty_state(
            self,
            forecast=forecast,
            overall_scope_readiness=overall_scope_readiness,
            gate_snapshot=gate_snapshot,
        )

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
        return pilot_readout_trace.reason_trace_lines(trace)

    @staticmethod
    def _is_reason_detail_item(value: Any) -> bool:
        return pilot_readout_trace.is_reason_detail_item(value)

    @classmethod
    def _reason_trace_detail_items(cls, trace: Any) -> list[dict[str, Any]]:
        return pilot_readout_trace.reason_trace_detail_items(trace)

    @staticmethod
    def _unique_reason_details(values: list[Any]) -> list[dict[str, Any]]:
        return pilot_readout_trace.unique_reason_details(values)

    @staticmethod
    def _unique_non_empty(values: list[str]) -> list[str]:
        return pilot_readout_trace.unique_non_empty(values)
