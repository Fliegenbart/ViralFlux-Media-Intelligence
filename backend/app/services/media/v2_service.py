from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sqlalchemy.orm import Session

from app.models.database import (
    MediaOutcomeImportBatch,
    MediaOutcomeImportIssue,
    MediaOutcomeRecord,
)
from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine
from app.services.media.business_validation_service import BusinessValidationService
from app.services.media.cockpit_service import MediaCockpitService
from app.services.media.outcome_signal_service import OutcomeSignalService
from app.services.media.truth_gate_service import TruthGateService
from app.services.ml.forecast_decision_service import ForecastDecisionService
from app.services.media.v2.campaigns import build_campaigns_payload
from app.services.media.v2.decision import build_decision_payload
from app.services.media.v2.evidence import build_evidence_payload
from app.services.media.v2 import guidance
from app.services.media.v2 import lineage
from app.services.media.v2 import outcomes as outcomes_module
from app.services.media.v2 import cards as cards_module
from app.services.media.v2 import prioritization
from app.services.media.v2 import queue
from app.services.media.v2.regions import build_regions_payload


class MediaV2Service:
    """View-spezifische Contracts für Decision, Regionen, Kampagnen und Evidenz."""

    def __init__(self, db: Session):
        self.db = db
        self.cockpit_service = MediaCockpitService(db)
        self.engine = MarketingOpportunityEngine(db)
        self.truth_gate_service = TruthGateService()
        self.outcome_signal_service = OutcomeSignalService(db)
        self.business_validation_service = BusinessValidationService(db)

    def get_decision_payload(
        self,
        *,
        virus_typ: str = "Influenza A",
        target_source: str = "RKI_ARE",
        brand: str = "gelo",
    ) -> dict[str, Any]:
        return build_decision_payload(
            self,
            virus_typ=virus_typ,
            target_source=target_source,
            brand=brand,
        )

    def get_regions_payload(
        self,
        *,
        virus_typ: str = "Influenza A",
        target_source: str = "RKI_ARE",
        brand: str = "gelo",
    ) -> dict[str, Any]:
        return build_regions_payload(
            self,
            virus_typ=virus_typ,
            target_source=target_source,
            brand=brand,
        )

    def get_campaigns_payload(
        self,
        *,
        brand: str = "gelo",
        limit: int = 120,
    ) -> dict[str, Any]:
        return build_campaigns_payload(self, brand=brand, limit=limit)

    def get_evidence_payload(
        self,
        *,
        virus_typ: str = "Influenza A",
        target_source: str = "RKI_ARE",
        brand: str = "gelo",
    ) -> dict[str, Any]:
        return build_evidence_payload(
            self,
            virus_typ=virus_typ,
            target_source=target_source,
            brand=brand,
        )

    def get_forecast_monitoring(
        self,
        *,
        virus_typ: str = "Influenza A",
        target_source: str = "RKI_ARE",
    ) -> dict[str, Any]:
        return ForecastDecisionService(self.db).build_monitoring_snapshot(
            virus_typ=virus_typ,
            target_source=target_source,
        )

    def get_signal_stack(self, *, virus_typ: str = "Influenza A") -> dict[str, Any]:
        return lineage.build_signal_stack_payload(self, virus_typ=virus_typ)

    def get_model_lineage(self, *, virus_typ: str = "Influenza A") -> dict[str, Any]:
        return lineage.build_model_lineage_payload(self, virus_typ=virus_typ)

    def get_truth_coverage(
        self,
        *,
        brand: str = "gelo",
        virus_typ: str | None = None,
    ) -> dict[str, Any]:
        return outcomes_module.build_truth_coverage(
            self,
            brand=brand,
            virus_typ=virus_typ,
        )

    def get_truth_evidence(
        self,
        *,
        brand: str = "gelo",
        virus_typ: str | None = None,
    ) -> dict[str, Any]:
        return outcomes_module.build_truth_evidence(
            self,
            brand=brand,
            virus_typ=virus_typ,
        )

    def import_outcomes(
        self,
        *,
        source_label: str,
        records: list[dict[str, Any]] | None = None,
        csv_payload: str | None = None,
        brand: str = "gelo",
        replace_existing: bool = False,
        validate_only: bool = False,
        file_name: str | None = None,
    ) -> dict[str, Any]:
        return outcomes_module.import_outcomes(
            self,
            source_label=source_label,
            records=records,
            csv_payload=csv_payload,
            brand=brand,
            replace_existing=replace_existing,
            validate_only=validate_only,
            file_name=file_name,
        )

    def list_outcome_import_batches(
        self,
        *,
        brand: str = "gelo",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return outcomes_module.list_outcome_import_batches(
            self,
            brand=brand,
            limit=limit,
        )

    def get_outcome_import_batch_detail(self, *, batch_id: str) -> dict[str, Any] | None:
        return outcomes_module.get_outcome_import_batch_detail(
            self,
            batch_id=batch_id,
        )

    def outcome_template_csv(self) -> str:
        return outcomes_module.outcome_template_csv(self)

    def _campaign_cards(self, *, brand: str = "gelo", limit: int = 120) -> list[dict[str, Any]]:
        return cards_module._campaign_cards(self, brand=brand, limit=limit)

    def _attach_outcome_learning_to_card(
        self,
        *,
        card: dict[str, Any],
        learning_bundle: dict[str, Any],
        truth_gate: dict[str, Any],
    ) -> dict[str, Any]:
        return cards_module._attach_outcome_learning_to_card(
            self,
            card=card,
            learning_bundle=learning_bundle,
            truth_gate=truth_gate,
        )

    def _learned_priority_score(
        self,
        *,
        base_priority: float,
        outcome_signal_score: Any,
        truth_gate: dict[str, Any],
    ) -> float:
        return cards_module._learned_priority_score(
            self,
            base_priority=base_priority,
            outcome_signal_score=outcome_signal_score,
            truth_gate=truth_gate,
        )

    def _decision_freshness_state(self, source_status: dict[str, Any]) -> str:
        return guidance._decision_freshness_state(self, source_status)

    def _build_why_now(
        self,
        *,
        top_card: dict[str, Any] | None,
        top_regions: list[dict[str, Any]],
        cockpit: dict[str, Any],
        decision_state: str,
        signal_summary: dict[str, Any],
    ) -> list[str]:
        return guidance._build_why_now(
            self,
            top_card=top_card,
            top_regions=top_regions,
            cockpit=cockpit,
            decision_state=decision_state,
            signal_summary=signal_summary,
        )

    def _forecast_direction(self, region: dict[str, Any]) -> str:
        return prioritization._forecast_direction(self, region)

    def _priority_explanation(
        self,
        *,
        region: dict[str, Any],
        suggestion: dict[str, Any],
        forecast_direction: str,
        severity_score: int,
        momentum_score: int,
        actionability_score: int,
        decision_mode: str,
    ) -> str:
        return prioritization._priority_explanation(
            self,
            region=region,
            suggestion=suggestion,
            forecast_direction=forecast_direction,
            severity_score=severity_score,
            momentum_score=momentum_score,
            actionability_score=actionability_score,
            decision_mode=decision_mode,
        )

    def _campaign_state_counts(self, cards: list[dict[str, Any]]) -> dict[str, int]:
        return queue._campaign_state_counts(self, cards)

    def _campaign_sort_key(self, item: dict[str, Any]) -> tuple[Any, ...]:
        return queue._campaign_sort_key(self, item)

    def _build_campaign_queue(
        self,
        cards: list[dict[str, Any]],
        *,
        visible_limit: int = 8,
    ) -> dict[str, Any]:
        return queue._build_campaign_queue(self, cards, visible_limit=visible_limit)

    def _select_visible_queue_cards(
        self,
        cards: list[dict[str, Any]],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        return queue._select_visible_queue_cards(self, cards, limit=limit)

    def _decision_focus_card(self, cards: list[dict[str, Any]]) -> dict[str, Any] | None:
        return queue._decision_focus_card(self, cards)

    def _decision_top_products(
        self,
        cards: list[dict[str, Any]],
        top_card: dict[str, Any] | None,
    ) -> list[str]:
        return queue._decision_top_products(self, cards, top_card)

    def _recommended_action(
        self,
        *,
        decision_state: str,
        top_card: dict[str, Any] | None,
        top_regions: list[dict[str, Any]],
        decision_mode: str,
    ) -> str:
        return queue._recommended_action(
            self,
            decision_state=decision_state,
            top_card=top_card,
            top_regions=top_regions,
            decision_mode=decision_mode,
        )

    def _known_limits(
        self,
        cockpit: dict[str, Any],
        virus_typ: str,
        *,
        truth_coverage: dict[str, Any] | None = None,
        truth_validation_legacy: dict[str, Any] | None = None,
    ) -> list[str]:
        return guidance._known_limits(
            self,
            cockpit,
            virus_typ,
            truth_coverage=truth_coverage,
            truth_validation_legacy=truth_validation_legacy,
        )

    def _signal_group_summary(self, peix: dict[str, Any]) -> dict[str, Any]:
        return lineage._signal_group_summary(self, peix)

    def _decision_mode_from_contributions(
        self,
        *,
        epidemic_total: float,
        supply_total: float,
        context_total: float,
    ) -> dict[str, str]:
        return lineage._decision_mode_from_contributions(
            self,
            epidemic_total=epidemic_total,
            supply_total=supply_total,
            context_total=context_total,
        )

    def _severity_score(self, region: dict[str, Any]) -> int:
        return prioritization._severity_score(self, region)

    def _momentum_score(self, *, region: dict[str, Any], forecast_direction: str) -> int:
        return prioritization._momentum_score(
            self,
            region=region,
            forecast_direction=forecast_direction,
        )

    def _actionability_score(
        self,
        *,
        region: dict[str, Any],
        suggestion: dict[str, Any],
        severity_score: int,
        momentum_score: int,
    ) -> int:
        return prioritization._actionability_score(
            self,
            region=region,
            suggestion=suggestion,
            severity_score=severity_score,
            momentum_score=momentum_score,
        )

    def _region_decision_mode(self, peix_region: dict[str, Any]) -> dict[str, str]:
        return prioritization._region_decision_mode(self, peix_region)

    def _region_source_trace(self, peix_region: dict[str, Any]) -> list[str]:
        return prioritization._region_source_trace(self, peix_region)

    def _read_model_metadata(self, virus_typ: str) -> dict[str, Any]:
        return lineage._read_model_metadata(self, virus_typ)

    def _collect_outcome_rows(
        self,
        *,
        records: list[dict[str, Any]],
        csv_payload: str | None,
        brand: str,
        source_label: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return outcomes_module._collect_outcome_rows(
            self,
            records=records,
            csv_payload=csv_payload,
            brand=brand,
            source_label=source_label,
        )

    def _parse_csv_payload(
        self,
        csv_payload: str,
        *,
        brand: str,
        source_label: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return outcomes_module._parse_csv_payload(
            self,
            csv_payload,
            brand=brand,
            source_label=source_label,
        )

    def _coerce_week_start(self, value: Any) -> datetime | None:
        return outcomes_module._coerce_week_start(self, value)

    def _float_or_none(self, value: Any) -> float | None:
        return outcomes_module._float_or_none(self, value)

    def _truth_gate(self, truth_coverage: dict[str, Any]) -> dict[str, Any]:
        return outcomes_module._truth_gate(self, truth_coverage)

    def _latest_import_batch(self, *, brand: str) -> MediaOutcomeImportBatch | None:
        return outcomes_module._latest_import_batch(self, brand=brand)

    def _latest_epi_reference_week(self, *, virus_typ: str | None = None) -> datetime | None:
        return outcomes_module._latest_epi_reference_week(self, virus_typ=virus_typ)

    def _truth_freshness_state(
        self,
        *,
        latest_truth_week: datetime | None,
        reference_week: datetime | None,
    ) -> str:
        return outcomes_module._truth_freshness_state(
            self,
            latest_truth_week=latest_truth_week,
            reference_week=reference_week,
        )

    def _normalize_outcome_row(
        self,
        *,
        row: dict[str, Any],
        brand: str,
        source_label: str,
    ) -> dict[str, Any]:
        return outcomes_module._normalize_outcome_row(
            self,
            row=row,
            brand=brand,
            source_label=source_label,
        )

    def _normalize_outcome_product(
        self,
        *,
        brand: str,
        raw_product: Any,
    ) -> tuple[str | None, dict[str, str] | None]:
        return outcomes_module._normalize_outcome_product(
            self,
            brand=brand,
            raw_product=raw_product,
        )

    def _normalize_outcome_region(self, raw_region: Any) -> tuple[str | None, dict[str, str] | None]:
        return outcomes_module._normalize_outcome_region(self, raw_region)

    def _find_existing_outcome(
        self,
        *,
        brand: str,
        source_label: str,
        week_start: datetime,
        product: str,
        region_code: str,
    ) -> MediaOutcomeRecord | None:
        return outcomes_module._find_existing_outcome(
            self,
            brand=brand,
            source_label=source_label,
            week_start=week_start,
            product=product,
            region_code=region_code,
        )

    def _project_truth_coverage(
        self,
        *,
        brand: str,
        normalized_rows: list[dict[str, Any]],
        virus_typ: str | None,
        replace_existing: bool,
        validate_only: bool,
    ) -> dict[str, Any]:
        return outcomes_module._project_truth_coverage(
            self,
            brand=brand,
            normalized_rows=normalized_rows,
            virus_typ=virus_typ,
            replace_existing=replace_existing,
            validate_only=validate_only,
        )

    def _coverage_from_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        brand: str,
        virus_typ: str | None,
    ) -> dict[str, Any]:
        return outcomes_module._coverage_from_rows(
            self,
            rows,
            brand=brand,
            virus_typ=virus_typ,
        )

    def _issue_dict(
        self,
        *,
        batch_id: str,
        row_number: int | None,
        field_name: str | None,
        issue_code: str,
        message: str,
        raw_row: Any,
    ) -> dict[str, Any]:
        return outcomes_module._issue_dict(
            self,
            batch_id=batch_id,
            row_number=row_number,
            field_name=field_name,
            issue_code=issue_code,
            message=message,
            raw_row=raw_row,
        )

    def _issue_response(self, issue: dict[str, Any]) -> dict[str, Any]:
        return outcomes_module._issue_response(self, issue)

    def _issue_to_dict(self, issue: MediaOutcomeImportIssue) -> dict[str, Any]:
        return outcomes_module._issue_to_dict(self, issue)

    def _batch_to_dict(self, batch: MediaOutcomeImportBatch | SimpleNamespace) -> dict[str, Any]:
        return outcomes_module._batch_to_dict(self, batch)
