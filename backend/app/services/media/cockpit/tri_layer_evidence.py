"""Experimental Tri-Layer Evidence Fusion snapshot.

This module is read-only and research-only. It may expose diagnostic evidence
for operators, but it must not change readiness, allocation, recommendations or
budget permission.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.database import MediaOutcomeRecord
from app.services.media.cockpit.constants import BUNDESLAND_NAMES
from app.services.media.cockpit.freshness import build_data_freshness, build_source_status
from app.services.research.tri_layer.schema import SourceEvidence, TriLayerRegionEvidence
from app.services.research.tri_layer.service import build_region_snapshot as build_tri_layer_region_snapshot


TriLayerMode = Literal["research", "shadow"]
BudgetPermissionState = Literal[
    "blocked",
    "calibration_window",
    "shadow_only",
    "limited",
    "approved",
]
WavePhase = Literal["baseline", "early_growth", "acceleration", "peak", "decline", "unknown"]
GateState = Literal["pass", "watch", "fail", "not_available"]
SourceConnectionState = Literal["connected", "partial", "not_connected"]


class TriLayerSummary(BaseModel):
    early_warning_score: float | None = None
    commercial_relevance_score: float | None = None
    budget_permission_state: BudgetPermissionState = "blocked"
    budget_can_change: bool = False
    reason: str


class TriLayerPosterior(BaseModel):
    intensity_mean: float | None = None
    intensity_p10: float | None = None
    intensity_p90: float | None = None
    growth_mean: float | None = None
    uncertainty: float | None = None


class TriLayerEvidenceWeights(BaseModel):
    wastewater: float | None = None
    clinical: float | None = None
    sales: float | None = None


class TriLayerLeadLag(BaseModel):
    wastewater_to_clinical_days_mean: float | None = None
    clinical_to_sales_days_mean: float | None = None
    lag_uncertainty: float | None = None


class TriLayerGates(BaseModel):
    epidemiological_signal: GateState = "not_available"
    clinical_confirmation: GateState = "not_available"
    sales_calibration: GateState = "not_available"
    coverage: GateState = "not_available"
    drift: GateState = "not_available"
    budget_isolation: GateState = "pass"


class TriLayerRegion(BaseModel):
    region: str
    region_code: str
    early_warning_score: float | None = None
    commercial_relevance_score: float | None = None
    budget_permission_state: BudgetPermissionState = "blocked"
    wave_phase: WavePhase = "unknown"
    posterior: TriLayerPosterior = Field(default_factory=TriLayerPosterior)
    evidence_weights: TriLayerEvidenceWeights = Field(default_factory=TriLayerEvidenceWeights)
    lead_lag: TriLayerLeadLag = Field(default_factory=TriLayerLeadLag)
    gates: TriLayerGates = Field(default_factory=TriLayerGates)
    explanation: str


class TriLayerSourceStatusItem(BaseModel):
    status: SourceConnectionState
    coverage: float | None = None
    freshness_days: float | None = None


class TriLayerSourceStatus(BaseModel):
    wastewater: TriLayerSourceStatusItem
    clinical: TriLayerSourceStatusItem
    sales: TriLayerSourceStatusItem


class TriLayerSnapshotResponse(BaseModel):
    module: Literal["tri_layer_evidence_fusion"] = "tri_layer_evidence_fusion"
    version: Literal["tlef_bicg_v0"] = "tlef_bicg_v0"
    mode: TriLayerMode
    as_of: str
    virus_typ: str
    horizon_days: int
    brand: str
    summary: TriLayerSummary
    regions: list[TriLayerRegion]
    source_status: TriLayerSourceStatus
    model_notes: list[str]


def _normalise_freshness_timestamp(
    value: datetime | None,
    *,
    now: datetime | None = None,
) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _source_item_from_freshness(items: list[dict[str, Any]], source_keys: set[str]) -> TriLayerSourceStatusItem:
    selected = [item for item in items if str(item.get("source_key")) in source_keys]
    if not selected:
        return TriLayerSourceStatusItem(status="not_connected")

    connected = [item for item in selected if item.get("freshness_state") != "no_data"]
    live = [item for item in selected if item.get("freshness_state") == "live"]
    if not connected:
        status: SourceConnectionState = "not_connected"
    elif len(live) == len(selected):
        status = "connected"
    else:
        status = "partial"

    ages = [
        float(item["age_days"])
        for item in connected
        if isinstance(item.get("age_days"), (int, float))
    ]
    return TriLayerSourceStatusItem(
        status=status,
        coverage=round(len(connected) / len(selected), 4) if selected else None,
        freshness_days=round(min(ages), 2) if ages else None,
    )


def _optional_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _clamp01(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(1.0, value))


def _status_for_research(
    source_status: TriLayerSourceStatusItem,
    *,
    allow_forecast_proxy: bool = False,
) -> SourceConnectionState:
    if source_status.status != "not_connected":
        return source_status.status
    return "partial" if allow_forecast_proxy else "not_connected"


def _sales_source_status(db: Session, *, brand: str) -> TriLayerSourceStatusItem:
    row = (
        db.query(
            func.count(MediaOutcomeRecord.id).label("rows"),
            func.count(func.distinct(MediaOutcomeRecord.region_code)).label("regions"),
            func.max(MediaOutcomeRecord.updated_at).label("latest"),
        )
        .filter(func.lower(MediaOutcomeRecord.brand) == str(brand or "").strip().lower())
        .one()
    )
    rows = int(row.rows or 0)
    if rows <= 0:
        return TriLayerSourceStatusItem(status="not_connected", coverage=None, freshness_days=None)

    region_count = int(row.regions or 0)
    latest = row.latest
    freshness_days = None
    if latest is not None:
        freshness_days = round(max(0.0, (utc_now().replace(tzinfo=None) - latest.replace(tzinfo=None)).total_seconds() / 86400.0), 2)
    return TriLayerSourceStatusItem(
        status="connected" if region_count >= len(BUNDESLAND_NAMES) else "partial",
        coverage=round(region_count / len(BUNDESLAND_NAMES), 4),
        freshness_days=freshness_days,
    )


def _regions_from_forecast(
    regional_payload: dict[str, Any],
    *,
    source_status: TriLayerSourceStatus,
) -> list[TriLayerRegion]:
    predictions = list(regional_payload.get("predictions") or [])
    regions: list[TriLayerRegion] = []
    for prediction in predictions:
        code = str(prediction.get("bundesland") or prediction.get("region_code") or "").upper()
        if not code:
            continue
        name = str(prediction.get("bundesland_name") or BUNDESLAND_NAMES.get(code, code))
        event_probability = _clamp01(_optional_float(prediction.get("event_probability")))
        change_pct = _optional_float(prediction.get("change_pct"))
        growth = round(change_pct / 100.0, 4) if change_pct is not None else None
        decision = prediction.get("decision") if isinstance(prediction.get("decision"), dict) else {}
        confidence = _clamp01(_optional_float(
            decision.get("signal_support_score")
            or decision.get("forecast_confidence")
            or prediction.get("event_probability")
        ))
        freshness_score = _clamp01(_optional_float(decision.get("source_freshness_score")))
        coverage_score = _clamp01(_optional_float(decision.get("source_coverage_score")))
        revision_risk = _clamp01(_optional_float(decision.get("source_revision_risk")))
        interval = prediction.get("prediction_interval") if isinstance(prediction.get("prediction_interval"), dict) else {}

        forecast_proxy_available = event_probability is not None
        clinical_status = _status_for_research(
            source_status.clinical,
            allow_forecast_proxy=forecast_proxy_available,
        )
        wastewater_status = _status_for_research(source_status.wastewater)
        clinical = SourceEvidence(
            status=clinical_status,
            freshness=freshness_score,
            reliability=confidence,
            baseline_stability=confidence,
            snr=confidence,
            consistency=confidence,
            drift=revision_risk,
            coverage=coverage_score,
            signal=event_probability,
            intensity=event_probability,
            growth=growth,
        )
        wastewater = SourceEvidence(
            status=wastewater_status,
            freshness=(
                _clamp01(1.0 - (source_status.wastewater.freshness_days / 14.0))
                if source_status.wastewater.freshness_days is not None
                else None
            ),
            reliability=None,
            baseline_stability=None,
            snr=None,
            consistency=None,
            drift=None,
            coverage=source_status.wastewater.coverage,
            signal=None,
            intensity=None,
            growth=None,
        )
        sales = SourceEvidence(status=source_status.sales.status)
        research_region = build_tri_layer_region_snapshot(
            TriLayerRegionEvidence(
                region=name,
                region_code=code,
                wastewater=wastewater,
                clinical=clinical,
                sales=sales,
            )
        )

        regions.append(
            TriLayerRegion(
                region=name,
                region_code=code,
                early_warning_score=research_region.early_warning_score,
                commercial_relevance_score=research_region.commercial_relevance_score,
                budget_permission_state=research_region.budget_permission_state,
                wave_phase=research_region.wave_phase,
                posterior=TriLayerPosterior(
                    intensity_mean=research_region.posterior.intensity_mean,
                    intensity_p10=_optional_float(interval.get("lower")),
                    intensity_p90=_optional_float(interval.get("upper")),
                    growth_mean=research_region.posterior.growth_mean,
                    uncertainty=research_region.posterior.uncertainty,
                ),
                evidence_weights=TriLayerEvidenceWeights(**research_region.evidence_weights.model_dump()),
                lead_lag=TriLayerLeadLag(**research_region.lead_lag.model_dump()),
                gates=TriLayerGates(**research_region.gates.model_dump()),
                explanation=(
                    "Research-only regional diagnostic built from existing FluxEngine regional "
                    "forecast outputs. Sales calibration is not connected, so this row cannot "
                    "grant budget permission."
                ),
            )
        )
    return regions


def build_tri_layer_snapshot(
    db: Session,
    *,
    virus_typ: str = "Influenza A",
    horizon_days: int = 7,
    brand: str = "gelo",
    client: str = "GELO",
    mode: TriLayerMode = "research",
) -> TriLayerSnapshotResponse:
    """Build the experimental Tri-Layer Evidence Fusion payload."""

    data_freshness = build_data_freshness(db, normalize_freshness_timestamp=_normalise_freshness_timestamp)
    freshness_items = list((build_source_status(data_freshness).get("items") or []))
    sales_status = _sales_source_status(db, brand=brand)
    source_status = TriLayerSourceStatus(
        wastewater=_source_item_from_freshness(freshness_items, {"wastewater"}),
        clinical=_source_item_from_freshness(freshness_items, {"notaufnahme", "survstat", "are_konsultation"}),
        sales=sales_status,
    )

    regional_payload: dict[str, Any] = {}
    regions: list[TriLayerRegion] = []
    notes = [
        "Research-only. Does not change media budget.",
    ]
    if sales_status.status == "not_connected":
        notes.append("Sales layer is not connected.")

    try:
        from app.services.ml.regional_forecast import RegionalForecastService

        regional_payload = RegionalForecastService(db).predict_all_regions(
            virus_typ=virus_typ,
            brand=brand or client or "gelo",
            horizon_days=int(horizon_days),
        )
        artifact_diagnostic = regional_payload.get("artifact_diagnostic")
        if isinstance(artifact_diagnostic, dict):
            operator_message = str(artifact_diagnostic.get("operator_message") or "").strip()
            if operator_message:
                notes.append(f"Regional forecast artifact diagnostic: {operator_message}")
        status = str(regional_payload.get("status") or "").strip()
        message = str(regional_payload.get("message") or "").strip()
        if status in {"no_model", "unsupported", "no_data"} and message:
            notes.append(f"Regional forecast status {status}: {message}")
        regions = _regions_from_forecast(
            regional_payload,
            source_status=source_status,
        )
    except Exception:
        regional_payload = {}
        notes.append("Regional forecast layer unavailable for this research snapshot.")

    early_scores = [
        float(region.early_warning_score)
        for region in regions
        if region.early_warning_score is not None
    ]
    early_warning_score = round(sum(early_scores) / len(early_scores), 4) if early_scores else None
    reason = (
        "Research-only diagnostic snapshot. Budget permission remains blocked because "
        "the Sales calibration layer is not connected."
        if sales_status.status == "not_connected"
        else "Research-only diagnostic snapshot. Budget changes are isolated in this module."
    )

    return TriLayerSnapshotResponse(
        mode=mode,
        as_of=utc_now().isoformat(),
        virus_typ=virus_typ,
        horizon_days=int(horizon_days),
        brand=str(brand or "").strip().lower() or "gelo",
        summary=TriLayerSummary(
            early_warning_score=early_warning_score,
            commercial_relevance_score=None,
            budget_permission_state="blocked",
            budget_can_change=False,
            reason=reason,
        ),
        regions=regions,
        source_status=source_status,
        model_notes=notes,
    )
