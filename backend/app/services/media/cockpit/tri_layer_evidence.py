"""Experimental Tri-Layer Evidence Fusion snapshot.

This module is read-only and research-only. It may expose diagnostic evidence
for operators, but it must not change readiness, allocation, recommendations or
budget permission.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.services.media.cockpit.constants import BUNDESLAND_NAMES
from app.services.media.cockpit.freshness import build_data_freshness, build_source_status
from app.services.media.cockpit.phase_lead_authority import (
    phase_lead_decision_label,
    phase_lead_driver_labels,
    phase_lead_rank_by_code,
    phase_lead_regions_by_code,
    load_phase_lead_authority_snapshot,
)
from app.services.research.tri_layer.clinical_evidence import build_clinical_evidence_by_region
from app.services.research.tri_layer.observation_panel import build_tri_layer_observation_panel
from app.services.research.tri_layer.sales_adapter import load_sales_panel
from app.services.research.tri_layer.schema import SourceEvidence, TriLayerRegionEvidence
from app.services.research.tri_layer.service import build_region_snapshot as build_tri_layer_region_snapshot
from app.services.research.tri_layer.source_evidence_builder import build_source_evidence_from_panel


TriLayerMode = Literal["research", "shadow"]
EvidenceMode = Literal[
    "raw_tri_layer",
    "raw_plus_forecast_proxy",
    "forecast_proxy_only",
    "insufficient_data",
]
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
RAW_SOURCE_KEYS = ("wastewater", "survstat", "notaufnahme", "are", "grippeweb")
ALL_SOURCE_COUNT_KEYS = (*RAW_SOURCE_KEYS, "forecast_proxy")
FORECAST_PROXY_NOTE = (
    "Clinical evidence uses existing FluxEngine regional forecast proxy because raw clinical regional evidence is incomplete."
)


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
    evidence_mode: EvidenceMode = "insufficient_data"
    early_warning_score: float | None = None
    commercial_relevance_score: float | None = None
    budget_permission_state: BudgetPermissionState = "blocked"
    wave_phase: WavePhase = "unknown"
    posterior: TriLayerPosterior = Field(default_factory=TriLayerPosterior)
    evidence_weights: TriLayerEvidenceWeights = Field(default_factory=TriLayerEvidenceWeights)
    lead_lag: TriLayerLeadLag = Field(default_factory=TriLayerLeadLag)
    gates: TriLayerGates = Field(default_factory=TriLayerGates)
    source_counts: dict[str, int] = Field(default_factory=dict)
    point_in_time_notes: list[str] = Field(default_factory=list)
    phase_lead_rank: int | None = None
    phase_lead_score: float | None = None
    phase_lead_p_up_h7: float | None = None
    phase_lead_p_surge_h7: float | None = None
    phase_lead_growth: float | None = None
    phase_lead_drivers: list[str] = Field(default_factory=list)
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
    evidence_mode: EvidenceMode = "insufficient_data"
    summary: TriLayerSummary
    regions: list[TriLayerRegion]
    source_status: TriLayerSourceStatus
    source_counts: dict[str, int] = Field(default_factory=dict)
    point_in_time_notes: list[str] = Field(default_factory=list)
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


def _prediction_region_code(prediction: dict[str, Any]) -> str:
    return str(prediction.get("bundesland") or prediction.get("region_code") or "").upper()


def _source_counts(panel: Any | None, *, forecast_proxy_count: int = 0) -> dict[str, int]:
    counts = {key: 0 for key in ALL_SOURCE_COUNT_KEYS}
    if panel is not None and not getattr(panel, "empty", True):
        for source, count in panel["source"].value_counts().to_dict().items():
            key = str(source)
            if key in counts:
                counts[key] = int(count)
    counts["forecast_proxy"] = int(forecast_proxy_count)
    return counts


def _region_source_counts(panel: Any | None, *, region_code: str, forecast_proxy_used: bool) -> dict[str, int]:
    counts = {key: 0 for key in ALL_SOURCE_COUNT_KEYS}
    if panel is not None and not getattr(panel, "empty", True):
        region = str(region_code or "").upper()
        eligible = panel.loc[
            panel["region_code"].astype(str).str.upper().isin({region, "DE"})
        ]
        for source, count in eligible["source"].value_counts().to_dict().items():
            key = str(source)
            if key in counts:
                counts[key] = int(count)
    counts["forecast_proxy"] = 1 if forecast_proxy_used else 0
    return counts


def _point_in_time_notes(panel: Any | None) -> list[str]:
    if panel is None or getattr(panel, "empty", True) or "point_in_time_note" not in panel.columns:
        return []
    notes: list[str] = []
    for value in panel["point_in_time_note"].dropna().tolist():
        note = str(value).strip()
        if note and note not in notes:
            notes.append(note)
    return notes


def _region_point_in_time_notes(panel: Any | None, *, region_code: str, forecast_proxy_used: bool) -> list[str]:
    notes: list[str] = []
    if panel is not None and not getattr(panel, "empty", True) and "point_in_time_note" in panel.columns:
        region = str(region_code or "").upper()
        eligible = panel.loc[
            panel["region_code"].astype(str).str.upper().isin({region, "DE"})
        ]
        for value in eligible["point_in_time_note"].dropna().tolist():
            note = str(value).strip()
            if note and note not in notes:
                notes.append(note)
    if forecast_proxy_used and FORECAST_PROXY_NOTE not in notes:
        notes.append(FORECAST_PROXY_NOTE)
    return notes


def _raw_region_codes_from_panel(panel: Any | None) -> list[str]:
    if panel is None or getattr(panel, "empty", True):
        return []
    regional = panel.loc[
        panel["source"].isin({"survstat", "are", "grippeweb", "notaufnahme"})
        & (panel["region_code"].astype(str).str.upper() != "DE")
    ]
    return sorted(str(value).upper() for value in regional["region_code"].dropna().unique())


def _forecast_predictions_by_region(regional_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    predictions: dict[str, dict[str, Any]] = {}
    for prediction in list(regional_payload.get("predictions") or []):
        if not isinstance(prediction, dict):
            continue
        code = _prediction_region_code(prediction)
        if code:
            predictions[code] = prediction
    return predictions


def _region_evidence_mode(
    *,
    wastewater: SourceEvidence,
    raw_clinical: SourceEvidence | None,
    forecast_proxy_used: bool,
) -> EvidenceMode:
    has_raw_wastewater = wastewater.status != "not_connected" and any(
        value is not None for value in (wastewater.signal, wastewater.intensity, wastewater.growth)
    )
    has_raw_clinical = raw_clinical is not None and raw_clinical.status != "not_connected" and any(
        value is not None for value in (raw_clinical.signal, raw_clinical.intensity, raw_clinical.growth)
    )
    if has_raw_wastewater and has_raw_clinical:
        return "raw_tri_layer"
    if forecast_proxy_used and (has_raw_wastewater or has_raw_clinical):
        return "raw_plus_forecast_proxy"
    if forecast_proxy_used:
        return "forecast_proxy_only"
    return "insufficient_data"


def _aggregate_evidence_mode(regions: list[TriLayerRegion]) -> EvidenceMode:
    if not regions:
        return "insufficient_data"
    modes = {region.evidence_mode for region in regions}
    if "raw_plus_forecast_proxy" in modes or ("raw_tri_layer" in modes and "forecast_proxy_only" in modes):
        return "raw_plus_forecast_proxy"
    if modes == {"raw_tri_layer"} or "raw_tri_layer" in modes:
        return "raw_tri_layer"
    if modes == {"forecast_proxy_only"}:
        return "forecast_proxy_only"
    return "insufficient_data"


def _cap_budget_without_sales(
    state: BudgetPermissionState,
    *,
    sales_status: SourceConnectionState,
) -> BudgetPermissionState:
    if sales_status != "not_connected":
        return state
    order = {
        "blocked": 0,
        "calibration_window": 1,
        "shadow_only": 2,
        "limited": 3,
        "approved": 4,
    }
    return "shadow_only" if order.get(state, 0) > order["shadow_only"] else state


def _sales_source_status(db: Session, *, brand: str) -> TriLayerSourceStatusItem:
    try:
        panel = load_sales_panel(
            db,
            brand=brand,
            virus_typ="",
            cutoff=utc_now().date(),
        )
    except Exception:
        return TriLayerSourceStatusItem(status="not_connected", coverage=None, freshness_days=None)

    if panel.status.status != "connected":
        return TriLayerSourceStatusItem(status="not_connected", coverage=None, freshness_days=None)

    return TriLayerSourceStatusItem(
        status="connected" if panel.region_count >= len(BUNDESLAND_NAMES) else "partial",
        coverage=panel.status.coverage,
        freshness_days=panel.status.freshness_days,
    )


def _regions_from_forecast(
    regional_payload: dict[str, Any],
    *,
    source_status: TriLayerSourceStatus,
    observation_panel: Any | None = None,
    clinical_evidence_by_region: dict[str, SourceEvidence] | None = None,
    region_codes: list[str] | None = None,
    cutoff: datetime | None = None,
    virus_typ: str | None = None,
) -> list[TriLayerRegion]:
    predictions_by_region = _forecast_predictions_by_region(regional_payload)
    codes = list(region_codes or predictions_by_region.keys())
    cutoff_at = cutoff or utc_now().replace(tzinfo=None)
    panel_virus_typ = str(regional_payload.get("virus_typ") or virus_typ or "").strip()
    regions: list[TriLayerRegion] = []
    for code in codes:
        code = str(code or "").upper()
        if not code:
            continue
        prediction = predictions_by_region.get(code, {})
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
        forecast_proxy_clinical = SourceEvidence(
            status="partial" if forecast_proxy_available else "not_connected",
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
        raw_clinical = (clinical_evidence_by_region or {}).get(code)
        clinical_uses_proxy = (
            (raw_clinical is None or raw_clinical.status == "not_connected")
            and forecast_proxy_available
        )
        clinical = forecast_proxy_clinical if clinical_uses_proxy else (raw_clinical or SourceEvidence())
        if observation_panel is not None and panel_virus_typ:
            wastewater = build_source_evidence_from_panel(
                observation_panel,
                source="wastewater",
                region_code=code,
                virus_typ=panel_virus_typ,
                cutoff=cutoff_at,
                allow_national_fallback=True,
            )
        else:
            wastewater = SourceEvidence()
        evidence_mode = _region_evidence_mode(
            wastewater=wastewater,
            raw_clinical=raw_clinical,
            forecast_proxy_used=clinical_uses_proxy,
        )
        sales = SourceEvidence(status=source_status.sales.status)
        research_region = build_tri_layer_region_snapshot(
            TriLayerRegionEvidence(
                region=name,
                region_code=code,
                wastewater=wastewater,
                clinical=clinical,
                sales=sales,
            ),
            observation_panel=observation_panel,
            virus_typ=panel_virus_typ or virus_typ,
            cutoff=cutoff_at,
        )
        regional_budget_state = _cap_budget_without_sales(
            research_region.budget_permission_state,
            sales_status=source_status.sales.status,
        )
        regional_budget_can_change = (
            research_region.budget_can_change
            if source_status.sales.status != "not_connected"
            else False
        )
        if clinical_uses_proxy:
            explanation = (
                f"{FORECAST_PROXY_NOTE} Sales calibration is not connected, so this row cannot grant budget permission."
            )
        elif evidence_mode == "raw_tri_layer":
            explanation = (
                "Research-only regional diagnostic built from raw point-in-time wastewater and clinical observations. "
                "Sales calibration is not connected, so this row cannot grant budget permission."
            )
        else:
            explanation = (
                "Research-only regional diagnostic has insufficient raw Tri-Layer evidence for this region. "
                "Sales calibration is not connected, so this row cannot grant budget permission."
            )

        regions.append(
            TriLayerRegion(
                region=name,
                region_code=code,
                evidence_mode=evidence_mode,
                early_warning_score=research_region.early_warning_score,
                commercial_relevance_score=research_region.commercial_relevance_score,
                budget_permission_state=regional_budget_state,
                budget_can_change=regional_budget_can_change,
                wave_phase=research_region.wave_phase,
                posterior=TriLayerPosterior(
                    intensity_mean=research_region.posterior.intensity_mean,
                    intensity_p10=(
                        research_region.posterior.intensity_p10
                        if research_region.posterior.intensity_p10 is not None
                        else _optional_float(interval.get("lower"))
                    ),
                    intensity_p90=(
                        research_region.posterior.intensity_p90
                        if research_region.posterior.intensity_p90 is not None
                        else _optional_float(interval.get("upper"))
                    ),
                    growth_mean=research_region.posterior.growth_mean,
                    uncertainty=research_region.posterior.uncertainty,
                ),
                evidence_weights=TriLayerEvidenceWeights(**research_region.evidence_weights.model_dump()),
                lead_lag=TriLayerLeadLag(**research_region.lead_lag.model_dump()),
                gates=TriLayerGates(**research_region.gates.model_dump()),
                source_counts=_region_source_counts(
                    observation_panel,
                    region_code=code,
                    forecast_proxy_used=clinical_uses_proxy,
                ),
                point_in_time_notes=_region_point_in_time_notes(
                    observation_panel,
                    region_code=code,
                    forecast_proxy_used=clinical_uses_proxy,
                ),
                explanation=explanation,
            )
        )
    return regions


def _phase_gate_state(phase_region: dict[str, Any]) -> GateState:
    decision = phase_lead_decision_label(phase_region)
    return "pass" if decision == "Prepare" else "watch"


def _apply_phase_lead_authority_to_regions(
    regions: list[TriLayerRegion],
    phase_lead_snapshot: dict[str, Any] | None,
) -> list[TriLayerRegion]:
    by_code = phase_lead_regions_by_code(phase_lead_snapshot)
    ranks = phase_lead_rank_by_code(phase_lead_snapshot)
    if not by_code:
        return regions

    updated: list[TriLayerRegion] = []
    for region in regions:
        phase_region = by_code.get(region.region_code.upper())
        if not phase_region:
            updated.append(region)
            continue
        drivers = phase_lead_driver_labels(phase_lead_snapshot, region.region_code)
        score = _optional_float(phase_region.get("gegb"))
        p_up = _optional_float(phase_region.get("p_up_h7"))
        p_surge = _optional_float(phase_region.get("p_surge_h7"))
        growth = _optional_float(phase_region.get("current_growth"))
        gates = region.gates.model_copy(
            update={"epidemiological_signal": _phase_gate_state(phase_region)}
        )
        explanation = (
            f"Phase-Lead aggregate is the regional priority source. Haupttreiber: "
            f"{' + '.join(drivers) if drivers else 'Atemwegsdruck'}. "
            "Sales calibration is not connected, so this row cannot grant budget permission."
        )
        updated.append(
            region.model_copy(
                update={
                    "early_warning_score": round(score, 4) if score is not None else region.early_warning_score,
                    "posterior": region.posterior.model_copy(
                        update={
                            "growth_mean": growth if growth is not None else region.posterior.growth_mean,
                            "intensity_mean": p_up if p_up is not None else region.posterior.intensity_mean,
                        }
                    ),
                    "gates": gates,
                    "phase_lead_rank": ranks.get(region.region_code.upper()),
                    "phase_lead_score": round(score, 4) if score is not None else None,
                    "phase_lead_p_up_h7": round(p_up, 4) if p_up is not None else None,
                    "phase_lead_p_surge_h7": round(p_surge, 4) if p_surge is not None else None,
                    "phase_lead_growth": round(growth, 4) if growth is not None else None,
                    "phase_lead_drivers": drivers,
                    "explanation": explanation,
                }
            )
        )

    return sorted(
        updated,
        key=lambda region: (
            region.phase_lead_rank is None,
            region.phase_lead_rank or 999,
            region.region_code,
        ),
    )


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

    cutoff = utc_now().replace(tzinfo=None)
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
        "Clinical layer uses raw point-in-time observations where available; RegionalForecastService is forecast_proxy fallback only.",
    ]
    if sales_status.status == "not_connected":
        notes.append("Sales layer is not connected.")

    observation_panel = None
    try:
        observation_panel = build_tri_layer_observation_panel(
            db,
            virus_typ=virus_typ,
            cutoff=cutoff,
            region_codes=None,
        )
    except Exception:
        notes.append("Point-in-time observation panel unavailable for this research snapshot.")

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
    except Exception:
        regional_payload = {}
        notes.append("Regional forecast layer unavailable for this research snapshot.")

    prediction_region_codes = list(_forecast_predictions_by_region(regional_payload).keys())
    raw_region_codes = _raw_region_codes_from_panel(observation_panel)
    region_codes = sorted({*raw_region_codes, *prediction_region_codes})

    clinical_evidence_by_region: dict[str, SourceEvidence] = {}
    if region_codes:
        try:
            clinical_evidence_by_region = build_clinical_evidence_by_region(
                db,
                virus_typ=virus_typ,
                cutoff=cutoff,
                region_codes=region_codes,
            )
        except Exception:
            notes.append("Raw clinical observation layer unavailable; using forecast_proxy fallback where present.")

        regions = _regions_from_forecast(
            regional_payload,
            source_status=source_status,
            observation_panel=observation_panel,
            clinical_evidence_by_region=clinical_evidence_by_region,
            region_codes=region_codes,
            cutoff=cutoff,
            virus_typ=virus_typ,
        )

    try:
        phase_lead_authority = load_phase_lead_authority_snapshot()
    except Exception:
        phase_lead_authority = None
        notes.append("Phase-Lead aggregate unavailable for this Tri-Layer snapshot.")
    if phase_lead_authority:
        regions = _apply_phase_lead_authority_to_regions(regions, phase_lead_authority)
        notes.append("Phase-Lead aggregate is the regional priority source.")

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
    used_forecast_proxy_count = sum(
        int(region.source_counts.get("forecast_proxy", 0) > 0)
        for region in regions
    )
    point_in_time_notes = _point_in_time_notes(observation_panel)
    if used_forecast_proxy_count and FORECAST_PROXY_NOTE not in point_in_time_notes:
        point_in_time_notes.append(FORECAST_PROXY_NOTE)

    return TriLayerSnapshotResponse(
        mode=mode,
        as_of=utc_now().isoformat(),
        virus_typ=virus_typ,
        horizon_days=int(horizon_days),
        brand=str(brand or "").strip().lower() or "gelo",
        evidence_mode=_aggregate_evidence_mode(regions),
        summary=TriLayerSummary(
            early_warning_score=early_warning_score,
            commercial_relevance_score=None,
            budget_permission_state="blocked",
            budget_can_change=False,
            reason=reason,
        ),
        regions=regions,
        source_status=source_status,
        source_counts=_source_counts(
            observation_panel,
            forecast_proxy_count=used_forecast_proxy_count,
        ),
        point_in_time_notes=point_in_time_notes,
        model_notes=notes,
    )
