"""Build Tri-Layer SourceEvidence from canonical PIT observation panels."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import pandas as pd

from app.services.research.tri_layer.schema import SourceEvidence


TRI_LAYER_SOURCES = (
    "wastewater",
    "survstat",
    "notaufnahme",
    "are",
    "grippeweb",
    "forecast_proxy",
)


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


def _visible_source_rows(
    panel: pd.DataFrame,
    *,
    source: str,
    region_code: str,
    virus_typ: str,
    cutoff: date | datetime,
    allow_national_fallback: bool,
) -> tuple[pd.DataFrame, bool]:
    if panel is None or panel.empty:
        return pd.DataFrame(), False

    cutoff_ts = _timestamp(cutoff)
    frame = panel.copy()
    frame = frame.loc[
        (frame.get("source") == source)
        & (frame.get("virus_typ") == virus_typ)
    ].copy()
    if frame.empty:
        return frame, False

    frame["available_at"] = pd.to_datetime(frame["available_at"], errors="coerce")
    frame["signal_date"] = pd.to_datetime(frame["signal_date"], errors="coerce")
    frame = frame.loc[
        (frame["available_at"] <= cutoff_ts)
        & (frame["signal_date"] <= cutoff_ts)
    ].copy()
    if frame.empty:
        return frame, False

    region = str(region_code or "").upper()
    exact = frame.loc[frame["region_code"].astype(str).str.upper() == region].copy()
    if not exact.empty:
        return exact.sort_values(["available_at", "signal_date"]).reset_index(drop=True), False

    if not allow_national_fallback:
        return pd.DataFrame(), False

    fallback = frame.loc[frame["region_code"].astype(str).str.upper() == "DE"].copy()
    return fallback.sort_values(["available_at", "signal_date"]).reset_index(drop=True), not fallback.empty


def _latest_row(rows: pd.DataFrame) -> pd.Series | None:
    if rows.empty:
        return None
    return rows.sort_values(["available_at", "signal_date"]).iloc[-1]


def _row_count_coverage(rows: pd.DataFrame) -> float | None:
    if rows.empty:
        return None
    return _clip(float(len(rows)) / 4.0)


def _freshness(row: pd.Series) -> float | None:
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


def _growth(row: pd.Series) -> float | None:
    return _clip(_safe_float(row.get("growth_7d")), lower=-1.0, upper=1.0)


def _prior_window(rows: pd.DataFrame, row: pd.Series, *, max_rows: int = 8) -> pd.DataFrame:
    current_signal_date = pd.Timestamp(row.get("signal_date"))
    if pd.isna(current_signal_date):
        return rows.iloc[0:0].copy()
    frame = rows.copy()
    frame["signal_date"] = pd.to_datetime(frame["signal_date"], errors="coerce")
    prior = frame.loc[frame["signal_date"] < current_signal_date].sort_values("signal_date")
    return prior.tail(max_rows).copy()


def _snr(rows: pd.DataFrame, row: pd.Series) -> float | None:
    normalized = _safe_float(row.get("value_normalized"))
    if normalized is None:
        return None
    values = pd.to_numeric(_prior_window(rows, row).get("value_normalized"), errors="coerce").dropna()
    if len(values) >= 2:
        deltas = values.diff().dropna()
        noise = float(deltas.std(ddof=0)) if len(deltas) >= 2 else float(values.std(ddof=0))
    elif len(values) == 1:
        noise = abs(float(normalized) - float(values.iloc[-1]))
    else:
        noise = abs(float(normalized))
    return _clip(abs(float(normalized)) / max(noise, 0.05))


def _baseline_stability(rows: pd.DataFrame, row: pd.Series) -> float | None:
    baselines = pd.to_numeric(_prior_window(rows, row).get("baseline"), errors="coerce").dropna()
    if baselines.empty:
        return None
    mean = abs(float(baselines.mean()))
    if mean <= 0:
        return 0.5
    cv = float(baselines.std(ddof=0)) / max(mean, 1e-6)
    return _clip(1.0 / (1.0 + max(cv, 0.0)))


def _consistency(rows: pd.DataFrame, row: pd.Series) -> float | None:
    visible = pd.concat([_prior_window(rows, row), row.to_frame().T], ignore_index=True)
    growth = pd.to_numeric(visible.get("growth_7d"), errors="coerce").dropna()
    if len(growth) >= 2:
        return _clip(1.0 / (1.0 + abs(float(growth.std(ddof=0)))))
    normalized = pd.to_numeric(visible.get("value_normalized"), errors="coerce").dropna()
    if len(normalized) >= 2:
        return _clip(1.0 / (1.0 + abs(float(normalized.diff().dropna().std(ddof=0)))))
    return None


def _reliability(row: pd.Series, *, coverage: float | None, freshness: float | None, drift: float | None) -> float | None:
    explicit = _safe_float(row.get("usable_confidence"))
    if explicit is not None:
        return _clip(explicit)
    if coverage is None or freshness is None:
        return None
    return _clip(float(coverage) * float(freshness) * (1.0 - float(drift or 0.0)))


def build_source_evidence_from_panel(
    panel: pd.DataFrame,
    source: str,
    region_code: str,
    virus_typ: str,
    cutoff: date | datetime,
    *,
    allow_national_fallback: bool = False,
) -> SourceEvidence:
    """Convert the latest visible panel row into Tri-Layer SourceEvidence."""
    rows, used_fallback = _visible_source_rows(
        panel,
        source=source,
        region_code=region_code,
        virus_typ=virus_typ,
        cutoff=cutoff,
        allow_national_fallback=allow_national_fallback,
    )
    row = _latest_row(rows)
    if row is None:
        return SourceEvidence(status="not_connected")

    coverage = _safe_float(row.get("coverage"))
    if coverage is None:
        coverage = _row_count_coverage(rows)
    if used_fallback and coverage is not None:
        coverage = min(float(coverage), 0.75)

    freshness = _freshness(row)
    drift = _clip(_safe_float(row.get("revision_risk")))
    signal = _signal(row)
    reliability = _reliability(row, coverage=coverage, freshness=freshness, drift=drift)

    return SourceEvidence(
        status="partial" if used_fallback else "connected",
        freshness=freshness,
        reliability=reliability,
        baseline_stability=_baseline_stability(rows, row),
        snr=_snr(rows, row),
        consistency=_consistency(rows, row),
        drift=drift,
        coverage=_clip(coverage),
        signal=signal,
        intensity=_intensity(row, signal),
        growth=_growth(row),
    )


def aggregate_source_evidence_by_region(
    panel: pd.DataFrame,
    virus_typ: str,
    cutoff: date | datetime,
    *,
    allow_national_fallback: bool = False,
) -> dict[str, dict[str, SourceEvidence]]:
    """Build SourceEvidence for every region represented in the panel."""
    if panel is None or panel.empty:
        return {}

    visible = panel.copy()
    visible["available_at"] = pd.to_datetime(visible["available_at"], errors="coerce")
    visible["signal_date"] = pd.to_datetime(visible["signal_date"], errors="coerce")
    cutoff_ts = _timestamp(cutoff)
    visible = visible.loc[
        (visible["virus_typ"] == virus_typ)
        & (visible["available_at"] <= cutoff_ts)
        & (visible["signal_date"] <= cutoff_ts)
    ].copy()
    if visible.empty:
        return {}

    regions = sorted(str(value).upper() for value in visible["region_code"].dropna().unique())
    sources = sorted(source for source in visible["source"].dropna().unique() if source in TRI_LAYER_SOURCES)
    return {
        region: {
            source: build_source_evidence_from_panel(
                visible,
                source=source,
                region_code=region,
                virus_typ=virus_typ,
                cutoff=cutoff,
                allow_national_fallback=allow_national_fallback,
            )
            for source in sources
        }
        for region in regions
    }
