"""Independent clinical SourceEvidence for Tri-Layer research snapshots."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.services.ml.regional_panel_utils import normalize_state_code
from app.services.research.tri_layer.observation_panel import build_tri_layer_observation_panel
from app.services.research.tri_layer.schema import SourceEvidence


CLINICAL_SOURCES = ("survstat", "notaufnahme", "are", "grippeweb")
_SOURCE_WEIGHTS = {
    "survstat": 1.0,
    "are": 0.85,
    "grippeweb": 0.75,
    "notaufnahme": 0.65,
}


def _timestamp(value: date | datetime | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clip(value: float | None, lower: float = 0.0, upper: float = 1.0) -> float | None:
    if value is None:
        return None
    return max(lower, min(upper, float(value)))


def _sigmoid(value: float | None) -> float | None:
    if value is None:
        return None
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, float(value)))))


def _normalise_region_code(value: str | None) -> str | None:
    if not value:
        return None
    return normalize_state_code(str(value)) or str(value).strip().upper()


def _weighted_mean(values: list[tuple[float | None, float]]) -> float | None:
    total = 0.0
    weight_total = 0.0
    for value, weight in values:
        if value is None or weight <= 0:
            continue
        total += float(value) * float(weight)
        weight_total += float(weight)
    if weight_total <= 0:
        return None
    return total / weight_total


def _freshness_score(row: pd.Series) -> float | None:
    freshness_days = _safe_float(row.get("freshness_days"))
    if freshness_days is None:
        return None
    return _clip(math.exp(-max(freshness_days, 0.0) / 14.0))


def _signal(row: pd.Series) -> float | None:
    normalized = _safe_float(row.get("value_normalized"))
    if normalized is not None:
        return _clip(_sigmoid(normalized))
    raw = _safe_float(row.get("value_raw"))
    baseline = _safe_float(row.get("baseline"))
    if raw is None or baseline is None:
        return None
    return _clip(_sigmoid(math.log1p(max(raw, 0.0)) - math.log1p(max(baseline, 0.0))))


def _intensity(row: pd.Series, signal: float | None) -> float | None:
    explicit = _safe_float(row.get("intensity"))
    if explicit is not None:
        return _clip(explicit)
    return signal


def _momentum(rows: pd.DataFrame, row: pd.Series) -> float | None:
    current_value = _safe_float(row.get("value_raw"))
    if current_value is None:
        return _clip(_safe_float(row.get("growth_7d")), lower=-1.0, upper=1.0)

    source = str(row.get("source") or "")
    lookback_days = 14 if source == "survstat" else 7
    current_date = pd.Timestamp(row.get("signal_date"))
    if pd.isna(current_date):
        return _clip(_safe_float(row.get("growth_7d")), lower=-1.0, upper=1.0)

    frame = rows.copy()
    frame["signal_date"] = pd.to_datetime(frame["signal_date"], errors="coerce")
    prior = frame.loc[frame["signal_date"] <= current_date - pd.Timedelta(days=lookback_days)]
    prior_values = pd.to_numeric(prior.sort_values("signal_date").get("value_raw"), errors="coerce").dropna()
    if prior_values.empty:
        return _clip(_safe_float(row.get("growth_7d")), lower=-1.0, upper=1.0)

    previous_value = float(prior_values.iloc[-1])
    return _clip((float(current_value) - previous_value) / max(abs(previous_value), 1.0), lower=-1.0, upper=1.0)


def _baseline_stability(rows: pd.DataFrame) -> float | None:
    baselines = pd.to_numeric(rows.get("baseline"), errors="coerce").dropna()
    if baselines.empty:
        return None
    mean = abs(float(baselines.mean()))
    if mean <= 0:
        return 0.5
    cv = float(baselines.std(ddof=0)) / max(mean, 1e-6)
    return _clip(1.0 / (1.0 + max(cv, 0.0)))


def _snr(rows: pd.DataFrame, latest_signal: float | None) -> float | None:
    normalized = pd.to_numeric(rows.get("value_normalized"), errors="coerce").dropna()
    if latest_signal is None or normalized.empty:
        return None
    noise = float(normalized.diff().dropna().std(ddof=0)) if len(normalized) >= 3 else float(normalized.std(ddof=0))
    return _clip(abs(float(latest_signal) - 0.5) / max(abs(noise), 0.05))


def _clinical_consistency(signals: list[float], growths: list[float], *, regional_source_count: int) -> float | None:
    if len(signals) >= 2:
        signal_agreement = 1.0 - min(1.0, float(pd.Series(signals).std(ddof=0)) * 2.0)
        if len(growths) >= 2:
            positives = sum(1 for value in growths if value > 0.03)
            negatives = sum(1 for value in growths if value < -0.03)
            momentum_agreement = max(positives, negatives, len(growths) - positives - negatives) / len(growths)
            return _clip(0.7 * signal_agreement + 0.3 * momentum_agreement)
        return _clip(signal_agreement)
    if signals:
        return 0.65 if regional_source_count > 0 else 0.45
    return None


def _source_groups_for_region(panel: pd.DataFrame, region_code: str) -> list[tuple[str, pd.DataFrame, bool]]:
    groups: list[tuple[str, pd.DataFrame, bool]] = []
    region = str(region_code or "").upper()
    for source in CLINICAL_SOURCES:
        source_rows = panel.loc[panel["source"] == source].copy()
        if source_rows.empty:
            continue
        exact = source_rows.loc[source_rows["region_code"].astype(str).str.upper() == region].copy()
        if not exact.empty:
            groups.append((source, exact.sort_values(["available_at", "signal_date"]), False))
            continue
        national = source_rows.loc[source_rows["region_code"].astype(str).str.upper() == "DE"].copy()
        if not national.empty:
            groups.append((source, national.sort_values(["available_at", "signal_date"]), True))
    return groups


def _evidence_from_panel_for_region(panel: pd.DataFrame, *, region_code: str, cutoff: date | datetime) -> SourceEvidence:
    if panel.empty:
        return SourceEvidence(status="not_connected")

    cutoff_ts = _timestamp(cutoff)
    frame = panel.copy()
    frame["available_at"] = pd.to_datetime(frame["available_at"], errors="coerce")
    frame["signal_date"] = pd.to_datetime(frame["signal_date"], errors="coerce")
    frame = frame.loc[
        frame["source"].isin(CLINICAL_SOURCES)
        & (frame["available_at"] <= cutoff_ts)
        & (frame["signal_date"] <= cutoff_ts)
    ].copy()
    if frame.empty:
        return SourceEvidence(status="not_connected")

    source_evidence: list[dict[str, float | bool | str | None]] = []
    for source, rows, national_fallback in _source_groups_for_region(frame, region_code):
        latest = rows.iloc[-1]
        coverage = _clip(_safe_float(latest.get("coverage")))
        if national_fallback and region_code != "DE" and coverage is not None:
            coverage = min(float(coverage), 0.35)
        freshness = _freshness_score(latest)
        signal = _signal(latest)
        intensity = _intensity(latest, signal)
        growth = _momentum(rows, latest)
        revision_risk = _clip(_safe_float(latest.get("revision_risk")))
        if bool(latest.get("is_point_in_time_safe")) is False:
            revision_risk = max(float(revision_risk or 0.0), 0.25)
        weight = _SOURCE_WEIGHTS.get(source, 0.5) * (0.45 if national_fallback and region_code != "DE" else 1.0)
        if coverage is not None:
            weight *= max(0.25, float(coverage))
        source_evidence.append(
            {
                "source": source,
                "national_fallback": national_fallback and region_code != "DE",
                "weight": weight,
                "signal": signal,
                "intensity": intensity,
                "growth": growth,
                "freshness": freshness,
                "coverage": coverage,
                "revision_risk": revision_risk,
                "baseline_stability": _baseline_stability(rows),
                "snr": _snr(rows, signal),
            }
        )

    if not source_evidence:
        return SourceEvidence(status="not_connected")

    regional_count = sum(1 for item in source_evidence if not bool(item["national_fallback"]))
    national_count = len(source_evidence) - regional_count
    weighted = [(item.get("signal"), float(item["weight"] or 0.0)) for item in source_evidence]
    signal = _weighted_mean(weighted)
    intensity = _weighted_mean([(item.get("intensity"), float(item["weight"] or 0.0)) for item in source_evidence])
    growth = _weighted_mean([(item.get("growth"), float(item["weight"] or 0.0)) for item in source_evidence])
    freshness = _weighted_mean([(item.get("freshness"), float(item["weight"] or 0.0)) for item in source_evidence])
    coverage = _weighted_mean([(item.get("coverage"), float(item["weight"] or 0.0)) for item in source_evidence])
    revision_risk = _weighted_mean([(item.get("revision_risk"), float(item["weight"] or 0.0)) for item in source_evidence])
    baseline_stability = _weighted_mean([(item.get("baseline_stability"), float(item["weight"] or 0.0)) for item in source_evidence])
    snr = _weighted_mean([(item.get("snr"), float(item["weight"] or 0.0)) for item in source_evidence])

    signals = [float(item["signal"]) for item in source_evidence if item.get("signal") is not None]
    growths = [float(item["growth"]) for item in source_evidence if item.get("growth") is not None]
    consistency = _clinical_consistency(signals, growths, regional_source_count=regional_count)
    disagreement_drift = (1.0 - consistency) * 0.5 if consistency is not None else 0.25
    drift = _clip(max(float(revision_risk or 0.0), disagreement_drift))

    source_count_score = _clip(0.90 * regional_count + 0.35 * national_count)
    reliability = None
    if coverage is not None and freshness is not None and source_count_score is not None:
        reliability = _clip(float(coverage) * float(freshness) * float(source_count_score) * (1.0 - float(drift or 0.0)))

    return SourceEvidence(
        status="connected" if regional_count > 0 else "partial",
        freshness=_clip(freshness),
        reliability=reliability,
        baseline_stability=_clip(baseline_stability),
        snr=_clip(snr),
        consistency=_clip(consistency),
        drift=drift,
        coverage=_clip(coverage),
        signal=_clip(signal),
        intensity=_clip(intensity),
        growth=_clip(growth, lower=-1.0, upper=1.0),
    )


def build_clinical_evidence_by_region(
    db: Session,
    *,
    virus_typ: str,
    cutoff: date | datetime,
    region_codes: list[str] | None = None,
) -> dict[str, SourceEvidence]:
    """Build independent clinical SourceEvidence per requested region."""
    panel = build_tri_layer_observation_panel(
        db,
        virus_typ=virus_typ,
        cutoff=cutoff,
        region_codes=region_codes,
    )
    if panel.empty:
        return {
            str(code).upper(): SourceEvidence(status="not_connected")
            for code in (region_codes or [])
            if str(code).strip()
        }

    if region_codes is not None:
        regions = [
            code
            for value in region_codes
            if (code := _normalise_region_code(value))
        ]
    else:
        visible = panel.loc[panel["source"].isin(CLINICAL_SOURCES)]
        regions = sorted(str(value).upper() for value in visible["region_code"].dropna().unique())

    return {
        region: _evidence_from_panel_for_region(panel, region_code=region, cutoff=cutoff)
        for region in regions
    }
