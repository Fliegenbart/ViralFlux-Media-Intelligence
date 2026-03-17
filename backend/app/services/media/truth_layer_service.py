"""Optional truth/outcome validation layer for GELO business release logic."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import MediaOutcomeRecord, OutcomeObservation
from app.services.media.truth_layer_contracts import (
    HoldoutEligibility,
    OutcomeObservationInput,
    OutcomeReadinessAssessment,
    SignalOutcomeAgreement,
    TruthLayerAssessment,
)


SUPPORTED_OUTCOME_METRICS = {
    "media_spend",
    "impressions",
    "clicks",
    "qualified_visits",
    "search_demand",
    "sales",
    "orders",
    "revenue",
    "campaign_response",
}
RESPONSE_METRICS = {"sales", "orders", "revenue", "search_demand", "qualified_visits", "campaign_response"}
HIGH_VALUE_RESPONSE_METRICS = {"sales", "orders", "revenue"}
_HOLDOUT_KEYS = ("holdout_group", "experiment_group", "test_group", "group", "experiment_arm")
_CAMPAIGN_KEYS = ("campaign_id", "activation_cycle", "flight_id", "campaign_name", "wave_id")
_CHANNEL_KEYS = ("channel", "media_channel", "campaign_channel", "kanal")
_LIFT_KEYS = (
    "incremental_lift_pct",
    "holdout_lift_pct",
    "uplift_pct",
    "lift_pct",
    "incremental_revenue_lift_pct",
    "incremental_units_lift_pct",
    "validated_lift_pct",
)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


class TruthLayerService:
    """Keep outcome validation optional and separated from forecast truth."""

    def __init__(self, db: Session):
        self.db = db

    def upsert_observations(
        self,
        observations: list[OutcomeObservationInput],
    ) -> dict[str, Any]:
        inserted = 0
        updated = 0
        for observation in observations:
            normalized = self._normalize_input(observation)
            existing = (
                self.db.query(OutcomeObservation)
                .filter(
                    OutcomeObservation.window_start == normalized.window_start,
                    OutcomeObservation.window_end == normalized.window_end,
                    func.lower(OutcomeObservation.brand) == normalized.brand.lower(),
                    OutcomeObservation.product == normalized.product,
                    OutcomeObservation.region_code == normalized.region_code,
                    OutcomeObservation.metric_name == normalized.metric_name,
                    OutcomeObservation.source_label == normalized.source_label,
                )
                .one_or_none()
            )
            payload = {
                "brand": normalized.brand,
                "product": normalized.product,
                "region_code": normalized.region_code,
                "window_start": normalized.window_start,
                "window_end": normalized.window_end,
                "metric_name": normalized.metric_name,
                "metric_value": normalized.metric_value,
                "metric_unit": normalized.metric_unit,
                "source_label": normalized.source_label,
                "channel": normalized.channel,
                "campaign_id": normalized.campaign_id,
                "holdout_group": normalized.holdout_group,
                "confidence_hint": normalized.confidence_hint,
                "metadata_json": normalized.metadata,
            }
            if existing is None:
                self.db.add(OutcomeObservation(**payload))
                inserted += 1
            else:
                for key, value in payload.items():
                    setattr(existing, key, value)
                updated += 1

        self.db.commit()
        return {
            "inserted": inserted,
            "updated": updated,
            "total": inserted + updated,
        }

    def assess(
        self,
        *,
        brand: str = "gelo",
        region_code: str | None = None,
        product: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        signal_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        observations, source_mode = self._load_scope_observations(
            brand=brand,
            region_code=region_code,
            product=product,
            window_start=window_start,
            window_end=window_end,
        )
        readiness = self._readiness(observations)
        holdout = self._holdout_eligibility(observations=observations, readiness=readiness)
        agreement = self._signal_outcome_agreement(
            observations=observations,
            readiness=readiness,
            holdout=holdout,
            signal_context=signal_context,
        )
        evidence_status, evidence_confidence = self._evidence_status(
            readiness=readiness,
            holdout=holdout,
            agreement=agreement,
            observations=observations,
        )
        assessment = TruthLayerAssessment(
            scope={
                "brand": str(brand or "gelo").strip().lower(),
                "region_code": str(region_code).upper() if region_code else None,
                "product": str(product).strip() if product else None,
                "window_start": window_start.isoformat() if window_start else None,
                "window_end": window_end.isoformat() if window_end else None,
            },
            outcome_readiness=readiness,
            signal_outcome_agreement=agreement,
            holdout_eligibility=holdout,
            evidence_status=evidence_status,
            evidence_confidence=evidence_confidence,
            commercial_gate={
                "budget_decision_allowed": bool(evidence_status == "commercially_validated"),
                "decision_scope": (
                    "validated_budget_activation"
                    if evidence_status == "commercially_validated"
                    else "decision_support_only"
                ),
                "message": self._commercial_message(
                    evidence_status=evidence_status,
                    agreement=agreement,
                    readiness=readiness,
                    holdout=holdout,
                ),
            },
            metadata={
                "source_mode": source_mode,
                "observations": len(observations),
                "metrics_present": readiness.metrics_present,
            },
        )
        return assessment.to_dict()

    def _normalize_input(self, observation: OutcomeObservationInput) -> OutcomeObservationInput:
        metric_name = self._normalize_metric_name(observation.metric_name)
        if metric_name not in SUPPORTED_OUTCOME_METRICS:
            raise ValueError(f"Unsupported outcome metric_name: {observation.metric_name}")
        if observation.window_end < observation.window_start:
            raise ValueError("window_end must be on or after window_start")
        return OutcomeObservationInput(
            brand=str(observation.brand or "gelo").strip().lower(),
            product=str(observation.product or "").strip(),
            region_code=str(observation.region_code or "").strip().upper(),
            metric_name=metric_name,
            metric_value=float(observation.metric_value),
            window_start=observation.window_start,
            window_end=observation.window_end,
            source_label=str(observation.source_label or "manual").strip().lower(),
            metric_unit=str(observation.metric_unit).strip() if observation.metric_unit else None,
            channel=str(observation.channel).strip().lower() if observation.channel else None,
            campaign_id=str(observation.campaign_id).strip() if observation.campaign_id else None,
            holdout_group=str(observation.holdout_group).strip().lower() if observation.holdout_group else None,
            confidence_hint=float(observation.confidence_hint) if observation.confidence_hint is not None else None,
            metadata=dict(observation.metadata or {}),
        )

    @staticmethod
    def _normalize_metric_name(raw_value: str) -> str:
        value = str(raw_value or "").strip().lower()
        aliases = {
            "media_spend_eur": "media_spend",
            "search_lift_index": "search_demand",
            "sales_units": "sales",
            "order_count": "orders",
            "revenue_eur": "revenue",
        }
        return aliases.get(value, value)

    def _load_scope_observations(
        self,
        *,
        brand: str,
        region_code: str | None,
        product: str | None,
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> tuple[list[dict[str, Any]], str]:
        normalized_brand = str(brand or "gelo").strip().lower()
        query = self.db.query(OutcomeObservation).filter(
            func.lower(OutcomeObservation.brand) == normalized_brand
        )
        if region_code:
            query = query.filter(OutcomeObservation.region_code == str(region_code).strip().upper())
        if product:
            query = query.filter(OutcomeObservation.product == str(product).strip())
        if window_start:
            query = query.filter(OutcomeObservation.window_end >= window_start)
        if window_end:
            query = query.filter(OutcomeObservation.window_start <= window_end)

        rows = query.order_by(OutcomeObservation.window_start.asc(), OutcomeObservation.id.asc()).all()
        if rows:
            return [self._observation_to_dict(row) for row in rows], "outcome_observations"

        fallback_query = self.db.query(MediaOutcomeRecord).filter(
            func.lower(MediaOutcomeRecord.brand) == normalized_brand
        )
        if region_code:
            fallback_query = fallback_query.filter(MediaOutcomeRecord.region_code == str(region_code).strip().upper())
        if product:
            fallback_query = fallback_query.filter(MediaOutcomeRecord.product == str(product).strip())
        if window_start:
            fallback_query = fallback_query.filter(MediaOutcomeRecord.week_start >= window_start - timedelta(days=6))
        if window_end:
            fallback_query = fallback_query.filter(MediaOutcomeRecord.week_start <= window_end)
        fallback_rows = fallback_query.order_by(MediaOutcomeRecord.week_start.asc(), MediaOutcomeRecord.id.asc()).all()
        if not fallback_rows:
            return [], "empty"
        return self._normalize_media_outcome_records(fallback_rows), "media_outcome_records_fallback"

    @staticmethod
    def _observation_to_dict(row: OutcomeObservation) -> dict[str, Any]:
        return {
            "brand": str(row.brand or "gelo").strip().lower(),
            "product": str(row.product or "").strip(),
            "region_code": str(row.region_code or "").strip().upper(),
            "window_start": row.window_start,
            "window_end": row.window_end,
            "metric_name": str(row.metric_name or "").strip().lower(),
            "metric_value": float(row.metric_value or 0.0),
            "source_label": str(row.source_label or "manual").strip().lower(),
            "channel": str(row.channel or "").strip().lower() if row.channel else None,
            "campaign_id": str(row.campaign_id or "").strip() if row.campaign_id else None,
            "holdout_group": str(row.holdout_group or "").strip().lower() if row.holdout_group else None,
            "confidence_hint": float(row.confidence_hint) if row.confidence_hint is not None else None,
            "metadata": dict(row.metadata_json or {}),
        }

    def _normalize_media_outcome_records(self, rows: list[MediaOutcomeRecord]) -> list[dict[str, Any]]:
        metric_map = {
            "media_spend": "media_spend_eur",
            "impressions": "impressions",
            "clicks": "clicks",
            "qualified_visits": "qualified_visits",
            "search_demand": "search_lift_index",
            "sales": "sales_units",
            "orders": "order_count",
            "revenue": "revenue_eur",
        }
        observations: list[dict[str, Any]] = []
        for row in rows:
            extra_data = dict(row.extra_data or {})
            base = {
                "brand": str(row.brand or "gelo").strip().lower(),
                "product": str(row.product or "").strip(),
                "region_code": str(row.region_code or "").strip().upper(),
                "window_start": row.week_start,
                "window_end": (row.week_start + timedelta(days=6)) if row.week_start else row.week_start,
                "source_label": str(row.source_label or "manual").strip().lower(),
                "channel": self._extract_text(extra_data, _CHANNEL_KEYS),
                "campaign_id": self._extract_text(extra_data, _CAMPAIGN_KEYS),
                "holdout_group": self._extract_holdout_group(extra_data),
                "confidence_hint": None,
                "metadata": extra_data,
            }
            for metric_name, field_name in metric_map.items():
                value = getattr(row, field_name)
                if value is None:
                    continue
                observations.append(
                    {
                        **base,
                        "metric_name": metric_name,
                        "metric_value": float(value or 0.0),
                    }
                )
        return observations

    def _readiness(self, observations: list[dict[str, Any]]) -> OutcomeReadinessAssessment:
        if not observations:
            return OutcomeReadinessAssessment(
                status="missing",
                score=0.0,
                coverage_weeks=0,
                notes=["No outcome observations available for the requested scope."],
            )

        windows = {
            obs["window_start"].date().isoformat()
            for obs in observations
            if obs.get("window_start") is not None
        }
        metrics_present = sorted({str(obs["metric_name"]) for obs in observations if obs.get("metric_name")})
        regions_present = len({str(obs["region_code"]) for obs in observations if obs.get("region_code")})
        products_present = len({str(obs["product"]) for obs in observations if obs.get("product")})
        spend_windows = len({
            obs["window_start"].date().isoformat()
            for obs in observations
            if obs.get("metric_name") == "media_spend" and float(obs.get("metric_value") or 0.0) > 0.0
        })
        response_windows = len({
            obs["window_start"].date().isoformat()
            for obs in observations
            if obs.get("metric_name") in RESPONSE_METRICS and float(obs.get("metric_value") or 0.0) > 0.0
        })
        coverage_weeks = len(windows)

        coverage_score = _clamp(coverage_weeks / 26.0)
        spend_score = _clamp(spend_windows / 8.0)
        response_score = _clamp(response_windows / 8.0)
        metric_diversity_score = _clamp(len(set(metrics_present) & (RESPONSE_METRICS | {"media_spend"})) / 5.0)
        readiness_score = round(
            0.35 * coverage_score
            + 0.25 * spend_score
            + 0.25 * response_score
            + 0.15 * metric_diversity_score,
            4,
        )

        if coverage_weeks >= 26 and spend_windows >= 8 and response_windows >= 4:
            status = "ready"
        elif coverage_weeks >= 12 and spend_windows >= 4 and response_windows >= 2:
            status = "partial"
        else:
            status = "sparse"

        notes: list[str] = []
        if coverage_weeks < 12:
            notes.append("Coverage window is still short for commercial validation.")
        if "media_spend" not in metrics_present:
            notes.append("Media spend is missing, so causal-style validation remains incomplete.")
        if not (set(metrics_present) & RESPONSE_METRICS):
            notes.append("No commercial response metric is available yet.")

        return OutcomeReadinessAssessment(
            status=status,
            score=readiness_score,
            coverage_weeks=coverage_weeks,
            metrics_present=metrics_present,
            regions_present=regions_present,
            products_present=products_present,
            spend_windows=spend_windows,
            response_windows=response_windows,
            notes=notes,
        )

    def _holdout_eligibility(
        self,
        *,
        observations: list[dict[str, Any]],
        readiness: OutcomeReadinessAssessment,
    ) -> HoldoutEligibility:
        holdout_groups = sorted({
            str(obs.get("holdout_group"))
            for obs in observations
            if obs.get("holdout_group")
        })
        ready = len(holdout_groups) >= 2
        eligible = bool(
            readiness.coverage_weeks >= 12
            and readiness.spend_windows >= 4
            and readiness.response_windows >= 2
            and (readiness.regions_present >= 2 or readiness.products_present >= 2 or ready)
        )
        if ready:
            reason = "Explicit holdout groups are present in the scoped outcome data."
        elif eligible:
            reason = "Scope has enough coverage and variation to add holdout/control tags in future activations."
        else:
            reason = "Scope still lacks enough coverage or variation for a reliable holdout design."
        return HoldoutEligibility(
            eligible=eligible,
            ready=ready,
            holdout_groups=holdout_groups,
            reason=reason,
        )

    def _signal_outcome_agreement(
        self,
        *,
        observations: list[dict[str, Any]],
        readiness: OutcomeReadinessAssessment,
        holdout: HoldoutEligibility,
        signal_context: dict[str, Any] | None,
    ) -> SignalOutcomeAgreement:
        signal_present = self._signal_present(signal_context)
        signal_confidence = self._signal_confidence(signal_context)
        outcome_support, outcome_confidence, historical_response, notes = self._historical_response_signal(
            observations=observations,
            readiness=readiness,
            holdout=holdout,
        )

        if not signal_present:
            return SignalOutcomeAgreement(
                status="no_signal",
                signal_present=False,
                historical_response_observed=historical_response,
                score=None,
                signal_confidence=signal_confidence,
                outcome_support_score=outcome_support,
                outcome_confidence=outcome_confidence,
                notes=["No epidemiological signal context was supplied for agreement evaluation.", *notes],
            )

        if not historical_response:
            return SignalOutcomeAgreement(
                status="no_outcome_support",
                signal_present=True,
                historical_response_observed=False,
                score=round(0.2 * float(signal_confidence or 0.0), 4),
                signal_confidence=signal_confidence,
                outcome_support_score=outcome_support,
                outcome_confidence=outcome_confidence,
                notes=["Epidemiological signal is present, but historical commercial response is not yet established.", *notes],
            )

        agreement_score = round(
            0.50 * float(outcome_support or 0.0)
            + 0.30 * float(outcome_confidence or 0.0)
            + 0.20 * float(signal_confidence or 0.0),
            4,
        )
        if agreement_score >= 0.70:
            status = "strong"
        elif agreement_score >= 0.50:
            status = "moderate"
        else:
            status = "weak"
        return SignalOutcomeAgreement(
            status=status,
            signal_present=True,
            historical_response_observed=True,
            score=agreement_score,
            signal_confidence=signal_confidence,
            outcome_support_score=outcome_support,
            outcome_confidence=outcome_confidence,
            notes=notes,
        )

    def _historical_response_signal(
        self,
        *,
        observations: list[dict[str, Any]],
        readiness: OutcomeReadinessAssessment,
        holdout: HoldoutEligibility,
    ) -> tuple[float, float, bool, list[str]]:
        if not observations:
            return 0.0, 0.0, False, ["No observations available for historical response scoring."]

        per_window: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        lift_metrics_available = False
        for obs in observations:
            key = obs["window_start"].date().isoformat()
            per_window[key][str(obs["metric_name"])] += float(obs.get("metric_value") or 0.0)
            if self._has_lift_metrics(obs.get("metadata")):
                lift_metrics_available = True

        spend_windows = 0
        responding_windows = 0
        strong_windows = 0
        for metrics in per_window.values():
            spend_value = float(metrics.get("media_spend") or 0.0)
            if spend_value <= 0.0:
                continue
            spend_windows += 1
            response_strength = 0.0
            if any(float(metrics.get(metric) or 0.0) > 0.0 for metric in HIGH_VALUE_RESPONSE_METRICS):
                response_strength += 1.0
            if any(float(metrics.get(metric) or 0.0) > 0.0 for metric in {"search_demand", "qualified_visits", "campaign_response"}):
                response_strength += 0.6
            if float(metrics.get("clicks") or 0.0) > 0.0 or float(metrics.get("impressions") or 0.0) > 0.0:
                response_strength += 0.25
            if response_strength > 0.0:
                responding_windows += 1
            if response_strength >= 1.0:
                strong_windows += 1

        historical_response = spend_windows > 0 and responding_windows > 0
        support_score = _clamp((0.6 * strong_windows + 0.4 * responding_windows) / max(spend_windows, 1))
        confidence = _clamp(
            0.45 * readiness.score
            + 0.30 * _clamp(responding_windows / 8.0)
            + 0.15 * (1.0 if holdout.eligible else 0.0)
            + 0.10 * (1.0 if lift_metrics_available else 0.0)
        )
        notes: list[str] = []
        if not historical_response:
            notes.append("No spend window with observable response was found in the requested scope.")
        if not lift_metrics_available:
            notes.append("No explicit lift metric is attached yet; agreement remains observational.")
        return round(support_score, 4), round(confidence, 4), historical_response, notes

    @staticmethod
    def _signal_present(signal_context: dict[str, Any] | None) -> bool:
        if not signal_context:
            return False
        if signal_context.get("signal_present") is not None:
            return bool(signal_context.get("signal_present"))
        stage = str(signal_context.get("decision_stage") or signal_context.get("stage") or "").lower()
        if stage in {"prepare", "activate"}:
            return True
        probability = signal_context.get("event_probability")
        try:
            return float(probability or 0.0) >= 0.5
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _signal_confidence(signal_context: dict[str, Any] | None) -> float | None:
        if not signal_context:
            return None
        for key in ("confidence", "forecast_confidence", "event_probability"):
            raw_value = signal_context.get(key)
            if raw_value is None:
                continue
            try:
                return _clamp(float(raw_value))
            except (TypeError, ValueError):
                continue
        return None

    def _evidence_status(
        self,
        *,
        readiness: OutcomeReadinessAssessment,
        holdout: HoldoutEligibility,
        agreement: SignalOutcomeAgreement,
        observations: list[dict[str, Any]],
    ) -> tuple[str, float]:
        lift_metrics_available = any(self._has_lift_metrics(obs.get("metadata")) for obs in observations)
        if readiness.status == "missing":
            return "no_truth", 0.0
        if holdout.ready and lift_metrics_available:
            return "commercially_validated", 0.95
        if holdout.ready:
            return "holdout_ready", 0.82
        if agreement.status in {"strong", "moderate"} and readiness.status in {"partial", "ready"}:
            return "truth_backed", round(
                _clamp(
                    0.55 * float(agreement.score or 0.0)
                    + 0.45 * float(readiness.score or 0.0)
                ),
                4,
            )
        if readiness.status in {"partial", "ready"}:
            return "observational", round(_clamp(0.65 * float(readiness.score or 0.0)), 4)
        return "explorative", round(_clamp(0.45 * float(readiness.score or 0.0)), 4)

    @staticmethod
    def _commercial_message(
        *,
        evidence_status: str,
        agreement: SignalOutcomeAgreement,
        readiness: OutcomeReadinessAssessment,
        holdout: HoldoutEligibility,
    ) -> str:
        if evidence_status == "commercially_validated":
            return "Outcome data can now harden budget decisions for this scope."
        if evidence_status == "holdout_ready":
            return "Outcome data is structurally ready, but validated lift still needs to be documented."
        if evidence_status == "truth_backed":
            return "Outcome history supports the epidemiological signal, but the layer remains observational."
        if holdout.eligible:
            return "Scope is ready for a future holdout design, but current decisions should still treat outcomes as supportive evidence."
        if readiness.status == "missing":
            return "No GELO outcome data is connected for this scope yet."
        return "Outcome data can inform prioritization, but not yet release budget decisions."

    @staticmethod
    def _extract_text(extra_data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            raw_value = extra_data.get(key)
            if raw_value is None:
                continue
            value = str(raw_value).strip()
            if value:
                return value
        return None

    @staticmethod
    def _extract_holdout_group(extra_data: dict[str, Any]) -> str | None:
        for key in _HOLDOUT_KEYS:
            raw_value = extra_data.get(key)
            if raw_value is None:
                continue
            if isinstance(raw_value, bool):
                return "control" if raw_value else "treated"
            value = str(raw_value).strip().lower()
            if value:
                return value
        return None

    @staticmethod
    def _has_lift_metrics(extra_data: Any) -> bool:
        if not isinstance(extra_data, dict):
            return False
        return any(extra_data.get(key) is not None for key in _LIFT_KEYS)
