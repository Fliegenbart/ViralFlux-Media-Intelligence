"""Pilot reporting and audit layer for regional recommendation outcomes."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import median
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import AuditLog, MarketingOpportunity
from app.services.marketing_engine.opportunity_engine import (
    BUNDESLAND_NAMES,
    MarketingOpportunityEngine,
)
from app.services.media.truth_layer_service import TruthLayerService


_PRIMARY_METRIC_ORDER = (
    "revenue",
    "orders",
    "sales",
    "search_demand",
    "qualified_visits",
    "campaign_response",
    "clicks",
    "impressions",
)
_ACTIVATION_STATUSES = {"APPROVED", "ACTIVATED", "EXPIRED"}
_EXCLUDED_DEFAULT_STATUSES = {"DISMISSED"}
_EXCLUDED_NON_RECOMMENDED_STATUSES = {"DISMISSED", "DRAFT"}


def _normalize_brand(value: str) -> str:
    return str(value or "gelo").strip().lower()


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def _round_or_none(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


class PilotReportingService:
    """Deterministic pilot reporting on top of recommendations, activations and truth."""

    def __init__(self, db: Session):
        self.db = db
        self.truth_layer_service = TruthLayerService(db)
        self.opportunity_engine = MarketingOpportunityEngine(db)

    def build_pilot_report(
        self,
        *,
        brand: str = "gelo",
        lookback_weeks: int = 26,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        region_code: str | None = None,
        product: str | None = None,
        include_draft: bool = False,
    ) -> dict[str, Any]:
        effective_end = _parse_datetime(window_end) or datetime.utcnow()
        effective_start = _parse_datetime(window_start) or (effective_end - timedelta(weeks=max(int(lookback_weeks), 1)))
        if effective_end < effective_start:
            raise ValueError("window_end must be on or after window_start")

        normalized_brand = _normalize_brand(brand)
        normalized_region = str(region_code or "").strip().upper() or None
        normalized_product = str(product or "").strip() or None

        rows = self._recommendation_rows(
            brand=normalized_brand,
            window_start=effective_start,
            window_end=effective_end,
        )
        opportunities = []
        for row in rows:
            card = self.opportunity_engine._model_to_dict(row, normalize_status=True)
            if normalized_region:
                scoped_regions = self._scope_regions(card)
                if normalized_region not in {scope["region_code"] for scope in scoped_regions}:
                    continue
            if normalized_product and str(card.get("recommended_product") or card.get("product") or "").strip() != normalized_product:
                continue
            if str(card.get("status") or "").upper() in _EXCLUDED_DEFAULT_STATUSES:
                continue
            if not include_draft and str(card.get("status") or "").upper() in _EXCLUDED_NON_RECOMMENDED_STATUSES:
                continue
            opportunities.append((row, card))

        audit_events = self._audit_events_for_rows(rows)
        recommendation_history: list[dict[str, Any]] = []
        activation_history: list[dict[str, Any]] = []
        before_after_comparison: list[dict[str, Any]] = []
        region_buckets: dict[str, dict[str, Any]] = defaultdict(self._region_bucket)

        for row, card in opportunities:
            status_history = self._status_history(row=row, card=card, audit_events=audit_events.get(row.id, []))
            activation_window = self._activation_window(card)
            signal_context = self._signal_context(card)
            scopes = self._scope_regions(card)
            current_status = str(card.get("status") or "").upper()
            lead_time_days = self._lead_time_days(card=card, activation_window=activation_window)
            history_item = self._recommendation_history_item(
                card=card,
                status_history=status_history,
                scopes=scopes,
                activation_window=activation_window,
                lead_time_days=lead_time_days,
            )
            recommendation_history.append(history_item)

            status_markers = self._status_markers(status_history=status_history, current_status=current_status, updated_at=row.updated_at)
            if current_status in _ACTIVATION_STATUSES or status_markers.get("approved_at") or status_markers.get("activated_at"):
                activation_history.append(
                    self._activation_history_item(
                        card=card,
                        scopes=scopes,
                        activation_window=activation_window,
                        lead_time_days=lead_time_days,
                        status_markers=status_markers,
                    )
                )

            for scope in scopes:
                comparison = self._build_scope_comparison(
                    brand=normalized_brand,
                    card=card,
                    scope=scope,
                    activation_window=activation_window,
                    signal_context=signal_context,
                    lead_time_days=lead_time_days,
                    current_status=current_status,
                )
                before_after_comparison.append(comparison)
                self._accumulate_region_bucket(region_buckets[scope["region_code"]], card=card, comparison=comparison, scope=scope)

        region_evidence_view = self._region_evidence_view(region_buckets)
        pilot_kpi_summary = self._pilot_kpi_summary(before_after_comparison)

        return {
            "brand": normalized_brand,
            "generated_at": datetime.utcnow().isoformat(),
            "reporting_window": {
                "start": effective_start.isoformat(),
                "end": effective_end.isoformat(),
                "lookback_weeks": max(int(lookback_weeks), 1),
                "region_code": normalized_region,
                "product": normalized_product,
                "include_draft": include_draft,
            },
            "summary": {
                "total_recommendations": len(recommendation_history),
                "activated_recommendations": len(activation_history),
                "region_scopes": len(before_after_comparison),
                "regions_covered": len(region_evidence_view),
                "products_covered": len({
                    str(item.get("product") or "").strip()
                    for item in recommendation_history
                    if str(item.get("product") or "").strip()
                }),
                "comparisons_with_evidence": sum(
                    1 for item in before_after_comparison if item["outcome_support_status"] != "insufficient_evidence"
                ),
                "supportive_comparisons": sum(
                    1 for item in before_after_comparison if item["outcome_support_status"] == "supportive"
                ),
            },
            "pilot_kpi_summary": pilot_kpi_summary,
            "recommendation_history": sorted(recommendation_history, key=lambda item: item["created_at"] or ""),
            "activation_history": sorted(
                activation_history,
                key=lambda item: item.get("activated_at") or item.get("approved_at") or item.get("activation_window", {}).get("start") or "",
            ),
            "region_evidence_view": region_evidence_view,
            "before_after_comparison": before_after_comparison,
            "methodology": {
                "version": "pilot_reporting_v1",
                "recommendation_history_source": "MarketingOpportunity + AuditLog",
                "outcome_source_preference": "OutcomeObservation with MediaOutcomeRecord fallback",
                "before_after_definition": "Matched pre-window vs active/after window using the configured activation range.",
                "strict_hit_definition": "A hit requires a positive primary KPI delta and at least moderate signal/outcome agreement.",
            },
        }

    def _recommendation_rows(
        self,
        *,
        brand: str,
        window_start: datetime,
        window_end: datetime,
    ) -> list[MarketingOpportunity]:
        query = (
            self.db.query(MarketingOpportunity)
            .filter(func.lower(MarketingOpportunity.brand) == brand)
            .filter(MarketingOpportunity.created_at >= window_start)
            .filter(MarketingOpportunity.created_at <= window_end)
            .order_by(MarketingOpportunity.created_at.asc(), MarketingOpportunity.id.asc())
        )
        return query.all()

    def _audit_events_for_rows(self, rows: list[MarketingOpportunity]) -> dict[int, list[AuditLog]]:
        row_ids = [row.id for row in rows if row.id is not None]
        if not row_ids:
            return {}
        query = (
            self.db.query(AuditLog)
            .filter(AuditLog.entity_type == "MarketingOpportunity")
            .filter(AuditLog.action == "STATUS_CHANGE")
            .filter(AuditLog.entity_id.in_(row_ids))
            .order_by(AuditLog.timestamp.asc(), AuditLog.id.asc())
        )
        grouped: dict[int, list[AuditLog]] = defaultdict(list)
        for event in query.all():
            if event.entity_id is not None:
                grouped[int(event.entity_id)].append(event)
        return grouped

    def _status_history(
        self,
        *,
        row: MarketingOpportunity,
        card: dict[str, Any],
        audit_events: list[AuditLog],
    ) -> list[dict[str, Any]]:
        current_status = str(card.get("status") or "").upper()
        if audit_events:
            initial_status = str(audit_events[0].old_value or current_status).upper()
        else:
            initial_status = current_status
        history = [
            {
                "timestamp": row.created_at.isoformat() if row.created_at else None,
                "from_status": None,
                "to_status": initial_status,
                "source": "recommendation_created",
            }
        ]
        for event in audit_events:
            history.append(
                {
                    "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                    "from_status": str(event.old_value or "").upper() or None,
                    "to_status": str(event.new_value or "").upper() or None,
                    "source": "audit_log",
                    "audit_action": event.action,
                    "audit_reason": event.reason,
                }
            )
        if history[-1].get("to_status") != current_status:
            history.append(
                {
                    "timestamp": row.updated_at.isoformat() if row.updated_at else None,
                    "from_status": history[-1].get("to_status"),
                    "to_status": current_status,
                    "source": "current_row_state",
                }
            )
        return history

    @staticmethod
    def _status_markers(
        *,
        status_history: list[dict[str, Any]],
        current_status: str,
        updated_at: datetime | None,
    ) -> dict[str, str | None]:
        approved_at = next((item.get("timestamp") for item in status_history if item.get("to_status") == "APPROVED"), None)
        activated_at = next((item.get("timestamp") for item in status_history if item.get("to_status") == "ACTIVATED"), None)
        if current_status == "APPROVED" and not approved_at:
            approved_at = updated_at.isoformat() if updated_at else None
        if current_status == "ACTIVATED" and not activated_at:
            activated_at = updated_at.isoformat() if updated_at else None
        return {
            "approved_at": approved_at,
            "activated_at": activated_at,
        }

    def _scope_regions(self, card: dict[str, Any]) -> list[dict[str, str]]:
        region_codes = [str(code).strip().upper() for code in (card.get("region_codes") or []) if str(code).strip()]
        if not region_codes:
            return [{"region_code": "DE", "region_name": "Deutschland"}]
        return [
            {
                "region_code": code,
                "region_name": BUNDESLAND_NAMES.get(code, code),
            }
            for code in region_codes
        ]

    @staticmethod
    def _activation_window(card: dict[str, Any]) -> dict[str, str | None]:
        preview = card.get("campaign_preview") or {}
        preview_window = preview.get("activation_window") or {}
        return {
            "start": (
                card.get("activation_start")
                or preview_window.get("start")
            ),
            "end": (
                card.get("activation_end")
                or preview_window.get("end")
            ),
        }

    @staticmethod
    def _signal_context(card: dict[str, Any]) -> dict[str, Any]:
        decision_brief = card.get("decision_brief") or {}
        expectation = decision_brief.get("expectation") or {}
        status = str(card.get("status") or "").upper()
        if status in {"APPROVED", "ACTIVATED", "EXPIRED"}:
            stage = "activate"
        elif status == "READY":
            stage = "prepare"
        else:
            stage = "watch"

        confidence = card.get("confidence")
        if confidence is None:
            raw_conf = expectation.get("signal_confidence_pct") or expectation.get("confidence_pct")
            try:
                confidence = float(raw_conf) / 100.0 if raw_conf is not None else None
            except (TypeError, ValueError):
                confidence = None

        event_probability = expectation.get("event_probability_pct")
        try:
            normalized_probability = float(event_probability) / 100.0 if event_probability is not None else None
        except (TypeError, ValueError):
            normalized_probability = None

        return {
            "decision_stage": stage,
            "stage": stage,
            "confidence": confidence,
            "event_probability": normalized_probability,
            "signal_present": stage in {"prepare", "activate"},
        }

    @staticmethod
    def _lead_time_days(
        *,
        card: dict[str, Any],
        activation_window: dict[str, str | None],
    ) -> int | None:
        created_at = _parse_datetime(card.get("created_at"))
        activation_start = _parse_datetime(activation_window.get("start"))
        if not created_at or not activation_start:
            return None
        return max((activation_start.date() - created_at.date()).days, 0)

    def _recommendation_history_item(
        self,
        *,
        card: dict[str, Any],
        status_history: list[dict[str, Any]],
        scopes: list[dict[str, str]],
        activation_window: dict[str, str | None],
        lead_time_days: int | None,
    ) -> dict[str, Any]:
        decision_brief = card.get("decision_brief") or {}
        expectation = decision_brief.get("expectation") or {}
        return {
            "opportunity_id": card.get("id"),
            "created_at": card.get("created_at"),
            "updated_at": card.get("updated_at"),
            "current_status": card.get("status"),
            "status_history": status_history,
            "brand": card.get("brand"),
            "product": card.get("recommended_product") or card.get("product"),
            "region_codes": [scope["region_code"] for scope in scopes],
            "region_names": [scope["region_name"] for scope in scopes],
            "priority_score": _round_or_none(card.get("priority_score"), 2),
            "signal_score": _round_or_none(card.get("signal_score"), 2),
            "signal_confidence_pct": _round_or_none(card.get("signal_confidence_pct"), 1),
            "event_probability_pct": _round_or_none(expectation.get("event_probability_pct"), 1),
            "activation_window": activation_window,
            "lead_time_days": lead_time_days,
            "playbook_key": card.get("playbook_key"),
            "playbook_title": card.get("playbook_title"),
            "trigger_event": ((card.get("trigger_context") or {}).get("event")),
            "recommendation_summary": decision_brief.get("summary_sentence") or card.get("reason") or card.get("recommendation_reason"),
            "mapping_status": card.get("mapping_status"),
            "guardrail_notes": card.get("guardrail_notes") or [],
        }

    def _activation_history_item(
        self,
        *,
        card: dict[str, Any],
        scopes: list[dict[str, str]],
        activation_window: dict[str, str | None],
        lead_time_days: int | None,
        status_markers: dict[str, str | None],
    ) -> dict[str, Any]:
        preview = card.get("campaign_preview") or {}
        budget = preview.get("budget") or {}
        return {
            "opportunity_id": card.get("id"),
            "current_status": card.get("status"),
            "approved_at": status_markers.get("approved_at"),
            "activated_at": status_markers.get("activated_at"),
            "activation_window": activation_window,
            "lead_time_days": lead_time_days,
            "product": card.get("recommended_product") or card.get("product"),
            "region_codes": [scope["region_code"] for scope in scopes],
            "region_names": [scope["region_name"] for scope in scopes],
            "weekly_budget_eur": budget.get("weekly_budget_eur"),
            "total_flight_budget_eur": budget.get("total_flight_budget_eur"),
            "primary_kpi": card.get("primary_kpi"),
            "campaign_name": card.get("campaign_name"),
        }

    def _build_scope_comparison(
        self,
        *,
        brand: str,
        card: dict[str, Any],
        scope: dict[str, str],
        activation_window: dict[str, str | None],
        signal_context: dict[str, Any],
        lead_time_days: int | None,
        current_status: str,
    ) -> dict[str, Any]:
        after_start = _parse_datetime(activation_window.get("start"))
        after_end = _parse_datetime(activation_window.get("end"))
        before_window: dict[str, str | None] = {"start": None, "end": None}
        before_summary = self._empty_metric_summary()
        after_summary = self._empty_metric_summary()

        if after_start and after_end and after_end >= after_start:
            duration_days = max((after_end.date() - after_start.date()).days + 1, 1)
            before_end_dt = after_start - timedelta(days=1)
            before_start_dt = before_end_dt - timedelta(days=duration_days - 1)
            before_window = {
                "start": before_start_dt.isoformat(),
                "end": before_end_dt.isoformat(),
            }
            before_summary = self._metric_summary(
                brand=brand,
                product=str(card.get("recommended_product") or card.get("product") or "").strip(),
                region_code=scope["region_code"],
                window_start=before_start_dt,
                window_end=before_end_dt,
            )
            after_summary = self._metric_summary(
                brand=brand,
                product=str(card.get("recommended_product") or card.get("product") or "").strip(),
                region_code=scope["region_code"],
                window_start=after_start,
                window_end=after_end,
            )

        primary_metric = self._primary_metric(before_summary["metrics"], after_summary["metrics"])
        before_value = float(before_summary["metrics"].get(primary_metric) or 0.0) if primary_metric else None
        after_value = float(after_summary["metrics"].get(primary_metric) or 0.0) if primary_metric else None
        delta_absolute = None
        delta_pct = None
        if primary_metric is not None and before_value is not None and after_value is not None:
            delta_absolute = after_value - before_value
            if before_value > 0:
                delta_pct = ((after_value - before_value) / before_value) * 100.0
            elif after_value > 0:
                delta_pct = 100.0
            else:
                delta_pct = 0.0

        truth_assessment = self.truth_layer_service.assess(
            brand=brand,
            region_code=None if scope["region_code"] == "DE" else scope["region_code"],
            product=str(card.get("recommended_product") or card.get("product") or "").strip(),
            window_start=after_start,
            window_end=after_end,
            signal_context=signal_context,
        )
        agreement = truth_assessment.get("signal_outcome_agreement") or {}
        evidence_status = str(truth_assessment.get("evidence_status") or "no_truth")
        outcome_support_status = self._outcome_support_status(
            delta_pct=delta_pct,
            agreement_status=str(agreement.get("status") or ""),
            evidence_status=evidence_status,
            primary_metric=primary_metric,
        )

        return {
            "comparison_id": f"{card.get('id')}:{scope['region_code']}",
            "opportunity_id": card.get("id"),
            "region_code": scope["region_code"],
            "region_name": scope["region_name"],
            "product": card.get("recommended_product") or card.get("product"),
            "current_status": current_status,
            "is_activated": current_status in _ACTIVATION_STATUSES,
            "priority_score": _round_or_none(card.get("priority_score"), 2),
            "lead_time_days": lead_time_days,
            "before_window": before_window,
            "after_window": activation_window,
            "before": before_summary,
            "after": after_summary,
            "primary_metric": primary_metric,
            "before_value": _round_or_none(before_value, 2),
            "after_value": _round_or_none(after_value, 2),
            "delta_absolute": _round_or_none(delta_absolute, 2),
            "delta_pct": _round_or_none(delta_pct, 2),
            "outcome_support_status": outcome_support_status,
            "truth_assessment": {
                "evidence_status": evidence_status,
                "evidence_confidence": truth_assessment.get("evidence_confidence"),
                "outcome_readiness": truth_assessment.get("outcome_readiness") or {},
                "signal_outcome_agreement": agreement,
                "commercial_gate": truth_assessment.get("commercial_gate") or {},
            },
        }

    def _metric_summary(
        self,
        *,
        brand: str,
        product: str,
        region_code: str,
        window_start: datetime,
        window_end: datetime,
    ) -> dict[str, Any]:
        observations, source_mode = self.truth_layer_service._load_scope_observations(
            brand=brand,
            region_code=None if region_code == "DE" else region_code,
            product=product,
            window_start=window_start,
            window_end=window_end,
        )
        observations = [
            observation
            for observation in observations
            if self._observation_within_window(
                observation=observation,
                window_start=window_start,
                window_end=window_end,
            )
        ]
        if not observations:
            source_mode = "empty"
        metrics: Counter[str] = Counter()
        weeks: set[str] = set()
        for observation in observations:
            metrics[str(observation.get("metric_name") or "")] += float(observation.get("metric_value") or 0.0)
            if observation.get("window_start"):
                weeks.add(observation["window_start"].date().isoformat())
        return {
            "source_mode": source_mode,
            "observation_count": len(observations),
            "coverage_weeks": len(weeks),
            "metrics": {
                key: round(float(value), 2)
                for key, value in sorted(metrics.items())
            },
        }

    @staticmethod
    def _observation_within_window(
        *,
        observation: dict[str, Any],
        window_start: datetime,
        window_end: datetime,
    ) -> bool:
        observation_start = _parse_datetime(observation.get("window_start"))
        observation_end = _parse_datetime(observation.get("window_end"))
        if observation_start is None:
            return False
        if observation_end is None:
            observation_end = observation_start
        return observation_start >= window_start and observation_end <= window_end

    @staticmethod
    def _empty_metric_summary() -> dict[str, Any]:
        return {
            "source_mode": "empty",
            "observation_count": 0,
            "coverage_weeks": 0,
            "metrics": {},
        }

    @staticmethod
    def _primary_metric(before_metrics: dict[str, Any], after_metrics: dict[str, Any]) -> str | None:
        combined = {**before_metrics, **after_metrics}
        for metric_name in _PRIMARY_METRIC_ORDER:
            if float(combined.get(metric_name) or 0.0) > 0.0:
                return metric_name
        return None

    @staticmethod
    def _outcome_support_status(
        *,
        delta_pct: float | None,
        agreement_status: str,
        evidence_status: str,
        primary_metric: str | None,
    ) -> str:
        normalized_agreement = str(agreement_status or "").strip().lower()
        if primary_metric is None and evidence_status == "no_truth":
            return "insufficient_evidence"
        if primary_metric is None:
            return "mixed"
        if delta_pct is None:
            return "insufficient_evidence"
        if delta_pct > 0 and normalized_agreement in {"moderate", "strong"}:
            return "supportive"
        if delta_pct > 0:
            return "mixed"
        return "not_supportive"

    @staticmethod
    def _region_bucket() -> dict[str, Any]:
        return {
            "region_name": None,
            "recommendations": 0,
            "activations": 0,
            "priority_scores": [],
            "lead_times": [],
            "products": Counter(),
            "supportive": 0,
            "assessed": 0,
            "agreements": 0,
            "agreement_assessed": 0,
            "delta_pcts": [],
            "evidence_status_counts": Counter(),
        }

    def _accumulate_region_bucket(
        self,
        bucket: dict[str, Any],
        *,
        card: dict[str, Any],
        comparison: dict[str, Any],
        scope: dict[str, str],
    ) -> None:
        bucket["region_name"] = scope["region_name"]
        bucket["recommendations"] += 1
        if comparison["is_activated"]:
            bucket["activations"] += 1
        priority_score = comparison.get("priority_score")
        if priority_score is not None:
            bucket["priority_scores"].append(float(priority_score))
        if comparison.get("lead_time_days") is not None:
            bucket["lead_times"].append(int(comparison["lead_time_days"]))
        product = str(card.get("recommended_product") or card.get("product") or "").strip()
        if product:
            bucket["products"][product] += 1
        evidence_status = str((comparison.get("truth_assessment") or {}).get("evidence_status") or "")
        if evidence_status:
            bucket["evidence_status_counts"][evidence_status] += 1
        agreement_status = str((((comparison.get("truth_assessment") or {}).get("signal_outcome_agreement") or {}).get("status")) or "")
        if agreement_status:
            bucket["agreement_assessed"] += 1
            if agreement_status in {"moderate", "strong"}:
                bucket["agreements"] += 1
        if comparison["outcome_support_status"] != "insufficient_evidence":
            bucket["assessed"] += 1
            if comparison["outcome_support_status"] == "supportive":
                bucket["supportive"] += 1
        if comparison.get("delta_pct") is not None:
            bucket["delta_pcts"].append(float(comparison["delta_pct"]))

    def _region_evidence_view(self, buckets: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        items = []
        for region_code, bucket in buckets.items():
            avg_priority = (
                round(sum(bucket["priority_scores"]) / len(bucket["priority_scores"]), 2)
                if bucket["priority_scores"] else None
            )
            avg_lead = (
                round(sum(bucket["lead_times"]) / len(bucket["lead_times"]), 1)
                if bucket["lead_times"] else None
            )
            avg_delta = (
                round(sum(bucket["delta_pcts"]) / len(bucket["delta_pcts"]), 2)
                if bucket["delta_pcts"] else None
            )
            hit_rate = (
                round(bucket["supportive"] / bucket["assessed"], 4)
                if bucket["assessed"] else None
            )
            agreement_rate = (
                round(bucket["agreements"] / bucket["agreement_assessed"], 4)
                if bucket["agreement_assessed"] else None
            )
            dominant_evidence_status = None
            if bucket["evidence_status_counts"]:
                dominant_evidence_status = bucket["evidence_status_counts"].most_common(1)[0][0]
            items.append(
                {
                    "region_code": region_code,
                    "region_name": bucket["region_name"] or BUNDESLAND_NAMES.get(region_code, region_code),
                    "recommendations": bucket["recommendations"],
                    "activations": bucket["activations"],
                    "avg_priority_score": avg_priority,
                    "avg_lead_time_days": avg_lead,
                    "avg_after_delta_pct": avg_delta,
                    "hit_rate": hit_rate,
                    "agreement_with_outcome_signals": agreement_rate,
                    "dominant_evidence_status": dominant_evidence_status,
                    "top_products": [name for name, _count in bucket["products"].most_common(3)],
                    "evidence_status_counts": dict(bucket["evidence_status_counts"]),
                }
            )
        items.sort(
            key=lambda item: (
                float(item.get("hit_rate") or 0.0),
                float(item.get("avg_priority_score") or 0.0),
                item.get("recommendations") or 0,
            ),
            reverse=True,
        )
        return items

    def _pilot_kpi_summary(self, comparisons: list[dict[str, Any]]) -> dict[str, Any]:
        activated = [item for item in comparisons if item["is_activated"]]
        assessed_activated = [item for item in activated if item["outcome_support_status"] != "insufficient_evidence"]
        supportive_activated = [item for item in assessed_activated if item["outcome_support_status"] == "supportive"]
        lead_times = [item["lead_time_days"] for item in activated if item.get("lead_time_days") is not None]

        assessed_with_priority = [
            item for item in comparisons
            if item["outcome_support_status"] != "insufficient_evidence" and item.get("priority_score") is not None
        ]
        threshold_priority = (
            median([float(item["priority_score"]) for item in assessed_with_priority])
            if assessed_with_priority else None
        )
        high_priority_items = [
            item for item in assessed_with_priority
            if threshold_priority is not None and float(item["priority_score"]) >= float(threshold_priority)
        ]
        correct_high_priority = [
            item for item in high_priority_items
            if item["outcome_support_status"] in {"supportive", "mixed"}
        ]

        agreement_assessed = [
            item for item in comparisons
            if str((((item.get("truth_assessment") or {}).get("signal_outcome_agreement") or {}).get("status")) or "")
            not in {"", "no_signal"}
        ]
        agreement_positive = [
            item for item in agreement_assessed
            if str((((item.get("truth_assessment") or {}).get("signal_outcome_agreement") or {}).get("status")) or "") in {"moderate", "strong"}
        ]

        return {
            "hit_rate": {
                "value": _round_or_none(len(supportive_activated) / len(assessed_activated), 4) if assessed_activated else None,
                "supportive": len(supportive_activated),
                "assessed": len(assessed_activated),
                "definition": "Share of activated scopes with positive primary KPI delta and at least moderate outcome agreement.",
            },
            "early_warning_lead_time_days": {
                "average": _round_or_none(sum(lead_times) / len(lead_times), 2) if lead_times else None,
                "median": _round_or_none(float(median(lead_times)), 2) if lead_times else None,
                "assessed": len(lead_times),
                "definition": "Days between recommendation creation and activation window start.",
            },
            "share_of_correct_regional_prioritizations": {
                "value": _round_or_none(len(correct_high_priority) / len(high_priority_items), 4) if high_priority_items else None,
                "supportive_or_directional": len(correct_high_priority),
                "assessed_high_priority": len(high_priority_items),
                "priority_threshold": _round_or_none(float(threshold_priority), 2) if threshold_priority is not None else None,
                "definition": "Share of above-median priority scopes with supportive or directional positive after-window evidence.",
            },
            "agreement_with_outcome_signals": {
                "value": _round_or_none(len(agreement_positive) / len(agreement_assessed), 4) if agreement_assessed else None,
                "agreeing_scopes": len(agreement_positive),
                "assessed": len(agreement_assessed),
                "definition": "Share of assessed scopes with moderate or strong signal/outcome agreement.",
            },
        }
