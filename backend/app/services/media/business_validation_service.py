from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import MediaOutcomeRecord
from app.services.media.outcome_signal_service import OutcomeSignalService
from app.services.media.semantic_contracts import (
    business_gate_contract,
    evidence_tier_contract,
    outcome_confidence_contract,
    outcome_signal_contract,
    truth_readiness_contract,
)
from app.services.media.truth_gate_service import TruthGateService

_MIN_COVERAGE_WEEKS = 26
_MIN_ACTIVATION_CYCLES = 2
_HOLDOUT_KEYS = ("holdout_group", "experiment_group", "test_group", "group", "experiment_arm")
_CHANNEL_KEYS = ("channel", "media_channel", "campaign_channel", "kanal")
_ACTIVATION_KEYS = ("activation_cycle", "campaign_id", "campaign_name", "wave_id", "flight_id")
_LIFT_KEYS = (
    "incremental_lift_pct",
    "holdout_lift_pct",
    "uplift_pct",
    "lift_pct",
    "incremental_revenue_lift_pct",
    "incremental_units_lift_pct",
    "validated_lift_pct",
)


@dataclass(slots=True)
class _OutcomeSummary:
    rows: int
    spend_rows: int
    coverage_weeks: int
    regions_with_spend: int
    products_with_spend: int
    activation_cycles: int
    channels_present: list[str]
    holdout_groups: list[str]
    holdout_labeled_rows: int
    lift_metrics_available: bool


class BusinessValidationService:
    """Separates commercial validation from epidemiological readiness."""

    def __init__(self, db: Session):
        self.db = db
        self.truth_gate_service = TruthGateService()
        self.outcome_signal_service = OutcomeSignalService(db)

    @staticmethod
    def _normalize_brand(brand: str) -> str:
        if brand is None:
            raise ValueError("brand must be provided")
        brand_value = str(brand).strip().lower()
        if not brand_value:
            raise ValueError("brand must be a non-empty string")
        return brand_value

    def evaluate(
        self,
        *,
        brand: str,
        virus_typ: str | None = None,
        truth_coverage: dict[str, Any] | None = None,
        truth_gate: dict[str, Any] | None = None,
        outcome_learning_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        brand_value = self._normalize_brand(brand)
        coverage = self._normalize_truth_coverage(truth_coverage) if truth_coverage else self._fallback_truth_coverage(brand=brand_value)
        gate = truth_gate or self.truth_gate_service.evaluate(coverage)
        learning_summary = outcome_learning_summary or self.outcome_signal_service.build_learning_bundle(
            brand=brand_value,
            truth_coverage=coverage,
            truth_gate=gate,
        )["summary"]
        rows = self._rows_for_brand(brand=brand_value)
        summary = self._summarize_rows(rows)

        truth_ready = bool(gate.get("passed"))
        holdout_ready = (
            int(coverage.get("coverage_weeks") or 0) >= _MIN_COVERAGE_WEEKS
            and summary.activation_cycles >= _MIN_ACTIVATION_CYCLES
            and len(summary.holdout_groups) >= 2
        )
        validated_for_budget_activation = bool(
            truth_ready
            and holdout_ready
            and summary.lift_metrics_available
        )

        if validated_for_budget_activation:
            validation_status = "passed_holdout_validation"
            decision_scope = "validated_budget_activation"
            evidence_tier = "commercially_validated"
            action_class = "customer_lift_ready"
            message = "Die Kundendaten zeigen belastbare Aktivierungszyklen und eine belastbare Validierung mit Vergleichsgruppe."
            guidance = "Budgetempfehlungen dürfen jetzt epidemiologisches Signal und belastbare Geschäftsdaten gemeinsam nutzen."
        elif int(coverage.get("coverage_weeks") or 0) <= 0:
            validation_status = "pending_truth_connection"
            decision_scope = "decision_support_only"
            evidence_tier = "no_truth"
            action_class = "watch_only"
            message = "Es fehlen noch echte Kundendaten für eine kommerzielle Validierung."
            guidance = "Zuerst Mediabudget sowie Verkaufs- oder Bestelldaten importieren, bevor Budgetfreigaben bewertet werden."
        elif int(coverage.get("coverage_weeks") or 0) < _MIN_COVERAGE_WEEKS:
            validation_status = "building_truth_layer"
            decision_scope = "decision_support_only"
            evidence_tier = "observational"
            action_class = "market_watch"
            message = "Die Kundendatenhistorie ist angeschlossen, für kommerzielle Freigaben aber noch zu kurz."
            guidance = "Mindestens 26 Wochen Kundendaten aufbauen, bevor die Validierung mit Vergleichsgruppe bewertet wird."
        elif summary.activation_cycles < _MIN_ACTIVATION_CYCLES:
            validation_status = "pending_activation_history"
            decision_scope = "decision_support_only"
            evidence_tier = "truth_backed"
            action_class = "market_watch"
            message = "Die Kundendatenhistorie ist vorhanden, aber es gibt noch zu wenige echte Aktivierungszyklen."
            guidance = "Mindestens zwei klar erkennbare Aktivierungszyklen dokumentieren, bevor Budgetfreigaben validiert werden."
        elif not holdout_ready:
            validation_status = "pending_holdout_design"
            decision_scope = "decision_support_only"
            evidence_tier = "truth_backed"
            action_class = "market_watch"
            message = "Kundendaten sind vorhanden, aber es fehlt noch ein klares Design mit Vergleichsgruppe."
            guidance = "Zukünftige Aktivierungen mit Test- und Vergleichsgruppen markieren, damit die zusätzliche Wirkung sauber geprüft werden kann."
        else:
            validation_status = "pending_holdout_validation"
            decision_scope = "decision_support_only"
            evidence_tier = "holdout_ready"
            action_class = "market_watch"
            message = "Das Design mit Vergleichsgruppe ist erkennbar, aber es fehlen noch belastbare Werte zur zusätzlichen Wirkung."
            guidance = "Die Kundendaten-Importe um Auswertungen zur Mehrwirkung oder Vergleichsgruppen ergänzen."

        return {
            "brand": brand_value,
            "virus_typ": virus_typ,
            "operator_context": {
                "operator": "platform",
                "product_mode": "portfolio_media_tool",
                "truth_partner": brand_value,
            },
            "truth_readiness": str(
                coverage.get("trust_readiness")
                or coverage.get("truth_readiness")
                or gate.get("learning_state")
                or "noch_nicht_angeschlossen"
            ),
            "truth_ready": truth_ready,
            "coverage_weeks": int(coverage.get("coverage_weeks") or 0),
            "regions_with_spend": summary.regions_with_spend,
            "products_with_spend": summary.products_with_spend,
            "activation_cycles": summary.activation_cycles,
            "holdout_ready": holdout_ready,
            "holdout_groups": summary.holdout_groups,
            "holdout_labeled_rows": summary.holdout_labeled_rows,
            "channels_present": summary.channels_present,
            "lift_metrics_available": summary.lift_metrics_available,
            "outcome_signal_score": learning_summary.get("outcome_signal_score"),
            "outcome_confidence_pct": learning_summary.get("outcome_confidence_pct"),
            "expected_units_lift_enabled": validated_for_budget_activation,
            "expected_revenue_lift_enabled": validated_for_budget_activation,
            "action_class": action_class,
            "validation_status": validation_status,
            "decision_scope": decision_scope,
            "validated_for_budget_activation": validated_for_budget_activation,
            "evidence_tier": evidence_tier,
            "message": message,
            "guidance": guidance,
            "validation_requirements": {
                "min_coverage_weeks": _MIN_COVERAGE_WEEKS,
                "min_activation_cycles": _MIN_ACTIVATION_CYCLES,
                "requires_explicit_holdout_design": True,
                "requires_validated_lift_metrics": True,
            },
            "field_contracts": {
                "truth_readiness": truth_readiness_contract(),
                "business_gate": business_gate_contract(),
                "evidence_tier": evidence_tier_contract(),
                "outcome_signal_score": outcome_signal_contract(),
                "outcome_confidence_pct": outcome_confidence_contract(),
            },
        }

    def _rows_for_brand(self, *, brand: str) -> list[MediaOutcomeRecord]:
        return (
            self.db.query(MediaOutcomeRecord)
            .filter(func.lower(MediaOutcomeRecord.brand) == brand)
            .order_by(MediaOutcomeRecord.week_start.asc(), MediaOutcomeRecord.id.asc())
            .all()
        )

    def _fallback_truth_coverage(self, *, brand: str) -> dict[str, Any]:
        rows = self._rows_for_brand(brand=brand)
        week_values = sorted({row.week_start.date().isoformat() for row in rows if row.week_start})
        return {
            "coverage_weeks": len(week_values),
            "trust_readiness": "belastbar" if len(week_values) >= 52 else "im_aufbau" if len(week_values) >= 26 else "erste_signale" if week_values else "noch_nicht_angeschlossen",
            "truth_freshness_state": "unknown",
            "required_fields_present": ["Mediabudget"] if any(row.media_spend_eur is not None for row in rows) else [],
            "conversion_fields_present": [
                label
                for field_name, label in (
                    ("sales_units", "Verkäufe"),
                    ("order_count", "Bestellungen"),
                    ("revenue_eur", "Umsatz"),
                )
                if any(getattr(row, field_name) is not None for row in rows)
            ],
        }

    @staticmethod
    def _normalize_truth_coverage(truth_coverage: dict[str, Any]) -> dict[str, Any]:
        coverage = dict(truth_coverage or {})
        required = coverage.get("required_fields_present")
        if isinstance(required, bool):
            coverage["required_fields_present"] = ["Mediabudget"] if required else []
        conversion = coverage.get("conversion_fields_present")
        if isinstance(conversion, bool):
            coverage["conversion_fields_present"] = ["Wirkungsdaten"] if conversion else []
        if "trust_readiness" not in coverage and "truth_readiness" in coverage:
            coverage["trust_readiness"] = coverage.get("truth_readiness")
        if "truth_freshness_state" not in coverage:
            coverage["truth_freshness_state"] = coverage.get("freshness_state") or "unknown"
        return coverage

    def _summarize_rows(self, rows: list[MediaOutcomeRecord]) -> _OutcomeSummary:
        spend_rows = [row for row in rows if float(row.media_spend_eur or 0.0) > 0.0]
        spend_regions = {str(row.region_code or "").strip().upper() for row in spend_rows if str(row.region_code or "").strip()}
        spend_products = {str(row.product or "").strip() for row in spend_rows if str(row.product or "").strip()}
        channels_present = sorted({
            channel
            for row in spend_rows
            if (channel := self._extract_channel(row.extra_data))
        })
        holdout_groups = sorted({
            group
            for row in rows
            if (group := self._extract_holdout_group(row.extra_data))
        })
        holdout_labeled_rows = sum(1 for row in rows if self._extract_holdout_group(row.extra_data))
        activation_cycles = self._activation_cycles(spend_rows)
        lift_metrics_available = any(self._has_lift_metrics(row.extra_data) for row in rows)
        coverage_weeks = len({row.week_start.date().isoformat() for row in rows if row.week_start})

        return _OutcomeSummary(
            rows=len(rows),
            spend_rows=len(spend_rows),
            coverage_weeks=coverage_weeks,
            regions_with_spend=len(spend_regions),
            products_with_spend=len(spend_products),
            activation_cycles=activation_cycles,
            channels_present=channels_present,
            holdout_groups=holdout_groups,
            holdout_labeled_rows=holdout_labeled_rows,
            lift_metrics_available=lift_metrics_available,
        )

    def _activation_cycles(self, rows: list[MediaOutcomeRecord]) -> int:
        explicit_cycles = sorted({
            key
            for row in rows
            if (key := self._extract_activation_key(row.extra_data))
        })
        if explicit_cycles:
            return len(explicit_cycles)

        week_values = sorted({row.week_start.date().isoformat() for row in rows if row.week_start})
        if not week_values:
            return 0

        cycles = 1
        previous = datetime.fromisoformat(week_values[0])
        for current_text in week_values[1:]:
            current = datetime.fromisoformat(current_text)
            if (current - previous).days > 21:
                cycles += 1
            previous = current
        return cycles

    @staticmethod
    def _extract_channel(extra_data: Any) -> str | None:
        if not isinstance(extra_data, dict):
            return None
        for key in _CHANNEL_KEYS:
            raw_value = extra_data.get(key)
            if raw_value is None:
                continue
            value = str(raw_value).strip().lower()
            if value:
                return value
        return None

    @staticmethod
    def _extract_activation_key(extra_data: Any) -> str | None:
        if not isinstance(extra_data, dict):
            return None
        for key in _ACTIVATION_KEYS:
            raw_value = extra_data.get(key)
            if raw_value is None:
                continue
            value = str(raw_value).strip().lower()
            if value:
                return value
        campaign_start = extra_data.get("campaign_start")
        if campaign_start is not None:
            value = str(campaign_start).strip().lower()
            if value:
                return value
        return None

    @staticmethod
    def _extract_holdout_group(extra_data: Any) -> str | None:
        if not isinstance(extra_data, dict):
            return None
        for key in _HOLDOUT_KEYS:
            raw_value = extra_data.get(key)
            if raw_value is None:
                continue
            if isinstance(raw_value, bool):
                return "control" if raw_value else "treated"
            value = str(raw_value).strip().lower()
            if value:
                return value
        holdout_flag = extra_data.get("holdout")
        if isinstance(holdout_flag, bool):
            return "control" if holdout_flag else "treated"
        return None

    @staticmethod
    def _has_lift_metrics(extra_data: Any) -> bool:
        if not isinstance(extra_data, dict):
            return False
        for key in _LIFT_KEYS:
            raw_value = extra_data.get(key)
            if raw_value is None:
                continue
            try:
                float(raw_value)
            except (TypeError, ValueError):
                if isinstance(raw_value, bool):
                    return raw_value
                continue
            return True
        validated_flag = extra_data.get("lift_validated")
        return bool(validated_flag) if isinstance(validated_flag, bool) else False
