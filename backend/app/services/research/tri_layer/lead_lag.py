"""Dynamic lead-lag estimates for TLEF-BICG v0."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import pandas as pd

from app.services.research.tri_layer.schema import LeadLagEstimate, SourceEvidence


LagStatus = Literal["estimated", "insufficient_data", "flat_correlation", "not_available"]
CLINICAL_SOURCES = ("survstat", "notaufnahme", "are", "grippeweb")


@dataclass(frozen=True)
class LagDistribution:
    mean_days: float | None
    mode_days: int | None
    p10_days: float | None
    p90_days: float | None
    uncertainty: float | None
    method: str
    n_pairs: int
    status: LagStatus


def _empty_distribution(status: LagStatus, *, method: str, n_pairs: int = 0, uncertainty: float | None = None) -> LagDistribution:
    return LagDistribution(
        mean_days=None,
        mode_days=None,
        p10_days=None,
        p90_days=None,
        uncertainty=uncertainty,
        method=method,
        n_pairs=int(n_pairs),
        status=status,
    )


def _timestamp(value: date | datetime | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts


def _source_names(source: str) -> set[str]:
    if source == "clinical":
        return set(CLINICAL_SOURCES)
    return {source}


def _visible_source_rows(
    panel: pd.DataFrame,
    *,
    source: str,
    region_code: str,
    virus_typ: str,
    cutoff: date | datetime,
) -> pd.DataFrame:
    if panel is None or panel.empty:
        return pd.DataFrame()

    required = {"source", "virus_typ", "region_code", "signal_date", "available_at"}
    if not required.issubset(set(panel.columns)):
        return pd.DataFrame()

    cutoff_ts = _timestamp(cutoff)
    frame = panel.copy()
    frame["signal_date"] = pd.to_datetime(frame["signal_date"], errors="coerce")
    frame["available_at"] = pd.to_datetime(frame["available_at"], errors="coerce")
    frame = frame.loc[
        frame["source"].isin(_source_names(source))
        & (frame["virus_typ"] == virus_typ)
        & (frame["available_at"] <= cutoff_ts)
        & (frame["signal_date"] <= cutoff_ts)
    ].copy()
    if frame.empty:
        return frame

    region = str(region_code or "").upper()
    exact = frame.loc[frame["region_code"].astype(str).str.upper() == region].copy()
    if not exact.empty:
        return exact

    fallback = frame.loc[frame["region_code"].astype(str).str.upper() == "DE"].copy()
    return fallback


def _series_from_rows(rows: pd.DataFrame) -> pd.Series:
    if rows.empty:
        return pd.Series(dtype=float)

    frame = rows.copy()
    for column in ("value_normalized", "growth_7d", "value_raw"):
        if column not in frame.columns:
            frame[column] = None

    value = pd.to_numeric(frame["value_normalized"], errors="coerce")
    value = value.where(value.notna(), pd.to_numeric(frame["growth_7d"], errors="coerce"))
    value = value.where(value.notna(), pd.to_numeric(frame["value_raw"], errors="coerce"))
    frame["__value"] = value
    frame = frame.dropna(subset=["signal_date", "__value"])
    if frame.empty:
        return pd.Series(dtype=float)

    series = frame.groupby("signal_date")["__value"].mean().sort_index()
    if len(series) < 2:
        return pd.Series(dtype=float)

    full_index = pd.date_range(series.index.min(), series.index.max(), freq="D")
    series = series.reindex(full_index).interpolate(method="time").ffill().bfill()
    deltas = series.diff().dropna()
    return deltas.astype(float)


def _corr_for_lag(source_a_delta: pd.Series, source_b_delta: pd.Series, lag_days: int) -> tuple[float | None, int]:
    shifted_a = source_a_delta.shift(int(lag_days), freq="D")
    aligned = pd.concat([shifted_a.rename("a"), source_b_delta.rename("b")], axis=1, sort=False).dropna()
    n_pairs = int(len(aligned))
    if n_pairs < 2:
        return None, n_pairs
    if float(aligned["a"].std(ddof=0)) <= 1e-12 or float(aligned["b"].std(ddof=0)) <= 1e-12:
        return None, n_pairs
    corr = float(aligned["a"].corr(aligned["b"]))
    return (corr if math.isfinite(corr) else None), n_pairs


def _softmax(values: list[float], *, temperature: float) -> list[float]:
    if not values:
        return []
    scaled = [temperature * max(float(value), 0.0) for value in values]
    max_scaled = max(scaled)
    exp_values = [math.exp(value - max_scaled) for value in scaled]
    denom = sum(exp_values)
    if denom <= 0:
        return [1.0 / len(values)] * len(values)
    return [value / denom for value in exp_values]


def _weighted_quantile(values: list[int], weights: list[float], quantile: float) -> float | None:
    if not values or not weights or len(values) != len(weights):
        return None
    target = max(0.0, min(1.0, float(quantile)))
    cumulative = 0.0
    for value, weight in sorted(zip(values, weights), key=lambda pair: pair[0]):
        cumulative += float(weight)
        if cumulative >= target:
            return float(value)
    return float(values[-1])


def _normalized_entropy(weights: list[float]) -> float | None:
    if not weights:
        return None
    if len(weights) == 1:
        return 0.0
    entropy = -sum(float(weight) * math.log(max(float(weight), 1e-12)) for weight in weights)
    return max(0.0, min(1.0, entropy / math.log(len(weights))))


def estimate_source_pair_lag_distribution(
    panel: pd.DataFrame,
    *,
    source_a: str,
    source_b: str,
    region_code: str,
    virus_typ: str,
    cutoff: date | datetime,
    max_lag_days: int = 21,
    min_pairs: int = 8,
) -> LagDistribution:
    """Estimate the lag where source A changes lead source B changes."""
    method = "daily_delta_cross_correlation_softmax_v1"
    if panel is None or panel.empty:
        return _empty_distribution("not_available", method=method)

    source_a_rows = _visible_source_rows(
        panel,
        source=source_a,
        region_code=region_code,
        virus_typ=virus_typ,
        cutoff=cutoff,
    )
    source_b_rows = _visible_source_rows(
        panel,
        source=source_b,
        region_code=region_code,
        virus_typ=virus_typ,
        cutoff=cutoff,
    )
    if source_a_rows.empty or source_b_rows.empty:
        return _empty_distribution("not_available", method=method)

    source_a_delta = _series_from_rows(source_a_rows)
    source_b_delta = _series_from_rows(source_b_rows)
    if source_a_delta.empty or source_b_delta.empty:
        return _empty_distribution("insufficient_data", method=method)
    rough_pairs = min(int(len(source_a_delta)), int(len(source_b_delta)))
    if rough_pairs < int(min_pairs):
        return _empty_distribution("insufficient_data", method=method, n_pairs=rough_pairs)
    if float(source_a_delta.std(ddof=0)) <= 1e-12 or float(source_b_delta.std(ddof=0)) <= 1e-12:
        return _empty_distribution("flat_correlation", method=method, n_pairs=rough_pairs, uncertainty=1.0)

    lags = list(range(0, max(0, int(max_lag_days)) + 1))
    correlations: list[float] = []
    usable_lags: list[int] = []
    pair_counts: list[int] = []
    for lag in lags:
        corr, n_pairs = _corr_for_lag(source_a_delta, source_b_delta, lag)
        pair_counts.append(n_pairs)
        if corr is None or n_pairs < int(min_pairs):
            continue
        usable_lags.append(lag)
        correlations.append(corr)

    n_pairs = max(pair_counts) if pair_counts else 0
    if not usable_lags:
        return _empty_distribution("insufficient_data", method=method, n_pairs=n_pairs)

    positive_scores = [max(corr, 0.0) for corr in correlations]
    max_score = max(positive_scores)
    if max_score <= 0.05 or (max(positive_scores) - min(positive_scores)) <= 0.03:
        uncertainty = _normalized_entropy([1.0 / len(usable_lags)] * len(usable_lags))
        return _empty_distribution("flat_correlation", method=method, n_pairs=n_pairs, uncertainty=uncertainty)

    weights = _softmax(positive_scores, temperature=8.0)
    mean_days = sum(float(lag) * weight for lag, weight in zip(usable_lags, weights))
    mode_days = usable_lags[weights.index(max(weights))]
    uncertainty = _normalized_entropy(weights)

    return LagDistribution(
        mean_days=round(mean_days, 4),
        mode_days=int(mode_days),
        p10_days=_weighted_quantile(usable_lags, weights, 0.10),
        p90_days=_weighted_quantile(usable_lags, weights, 0.90),
        uncertainty=round(float(uncertainty), 4) if uncertainty is not None else None,
        method=method,
        n_pairs=int(n_pairs),
        status="estimated",
    )


def estimate_lead_lag(
    *,
    wastewater: SourceEvidence,
    clinical: SourceEvidence,
    sales: SourceEvidence,
    panel: pd.DataFrame | None = None,
    virus_typ: str | None = None,
    region_code: str | None = None,
    cutoff: date | datetime | None = None,
) -> LeadLagEstimate:
    """Estimate lead-lag values from visible historical panel rows."""
    wastewater_to_clinical = None
    uncertainties: list[float] = []

    if (
        wastewater.status != "not_connected"
        and clinical.status != "not_connected"
        and panel is not None
        and virus_typ
        and region_code
        and cutoff is not None
    ):
        distribution = estimate_source_pair_lag_distribution(
            panel,
            source_a="wastewater",
            source_b="clinical",
            region_code=region_code,
            virus_typ=virus_typ,
            cutoff=cutoff,
        )
        if distribution.status == "estimated":
            wastewater_to_clinical = distribution.mean_days
        if distribution.uncertainty is not None:
            uncertainties.append(distribution.uncertainty)

    lag_uncertainty = round(sum(uncertainties) / len(uncertainties), 4) if uncertainties else None
    return LeadLagEstimate(
        wastewater_to_clinical_days_mean=wastewater_to_clinical,
        clinical_to_sales_days_mean=None,
        lag_uncertainty=lag_uncertainty,
    )
