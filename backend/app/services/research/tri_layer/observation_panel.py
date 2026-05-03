"""Canonical point-in-time observation panel for Tri-Layer research.

The panel intentionally contains source observations, not model outputs. It is
used as a leakage-safe raw evidence layer that later Tri-Layer services can
consume without mixing epidemiological measurements with forecast proxies.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Literal

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import (
    AREKonsultation,
    GrippeWebData,
    NotaufnahmeSyndromData,
    SurvstatWeeklyData,
    WastewaterAggregated,
)
from app.services.ml.forecast_service import SURVSTAT_VIRUS_MAP
from app.services.ml.regional_panel_utils import (
    BUNDESLAND_NAMES,
    SOURCE_LAG_DAYS,
    normalize_state_code,
)


ObservationSource = Literal[
    "wastewater",
    "survstat",
    "notaufnahme",
    "are",
    "grippeweb",
    "forecast_proxy",
]

PANEL_COLUMNS = [
    "source",
    "source_detail",
    "virus_typ",
    "region_code",
    "region_name",
    "signal_date",
    "available_at",
    "value_raw",
    "value_normalized",
    "baseline",
    "intensity",
    "growth_7d",
    "acceleration_7d",
    "freshness_days",
    "coverage",
    "revision_risk",
    "usable_confidence",
    "is_point_in_time_safe",
    "point_in_time_note",
]

_NOTAUFNAHME_SYNDROME_FOR_VIRUS: dict[str, str] = {
    "Influenza A": "ILI",
    "Influenza B": "ILI",
    "RSV A": "ARI",
    "SARS-CoV-2": "COVID",
}

_STATE_NAME_TO_CODE_CASEFOLD = {
    str(name).casefold(): code for code, name in BUNDESLAND_NAMES.items()
}
_STATE_NAME_TO_CODE_CASEFOLD.update(
    {
        "baden-wuerttemberg": "BW",
        "baden-wurttemberg": "BW",
        "thueringen": "TH",
        "gesamt": "DE",
        "bundesweit": "DE",
        "deutschland": "DE",
        "de": "DE",
    }
)


def _empty_panel() -> pd.DataFrame:
    return pd.DataFrame(columns=PANEL_COLUMNS)


def _timestamp(value: date | datetime | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts


def _to_datetime(value: date | datetime | pd.Timestamp) -> datetime:
    return _timestamp(value).to_pydatetime()


def _normalise_region_code(value: str | None) -> str | None:
    if not value:
        return None
    direct = normalize_state_code(str(value))
    if direct:
        return direct
    return _STATE_NAME_TO_CODE_CASEFOLD.get(str(value).strip().casefold())


def _region_name(region_code: str | None) -> str | None:
    if region_code == "DE":
        return "Deutschland"
    if region_code:
        return BUNDESLAND_NAMES.get(region_code)
    return None


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clip01(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(1.0, float(value)))


def _sigmoid(value: float | None) -> float | None:
    if value is None:
        return None
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, float(value)))))


def _coverage_from_wastewater(*, anteil_bev: float | None, n_standorte: int | None) -> float | None:
    if anteil_bev is not None:
        return _clip01(float(anteil_bev))
    if n_standorte is None:
        return None
    # Aggregated AMELAG rows are national summaries. Site count is only a rough
    # coverage proxy, so keep it conservative.
    return _clip01(float(n_standorte) / 16.0)


def _available_at(
    *,
    signal_date: datetime,
    true_available_at: datetime | None,
    fallback_days: int,
    source_label: str,
) -> tuple[datetime, bool, str | None]:
    if true_available_at is not None and pd.notna(true_available_at):
        return _to_datetime(true_available_at), True, None
    inferred = _timestamp(signal_date) + pd.Timedelta(days=int(fallback_days))
    return (
        inferred.to_pydatetime(),
        False,
        f"available_at inferred as signal_date + {fallback_days} days for {source_label}",
    )


def _created_or_inferred_available_at(
    *,
    signal_date: datetime,
    created_at: datetime | None,
    fallback_days: int,
    source_label: str,
    max_created_delay_days: int = 14,
) -> tuple[datetime, bool, str | None]:
    if created_at is not None and pd.notna(created_at):
        base = _timestamp(signal_date) + pd.Timedelta(days=int(fallback_days))
        created_ts = _timestamp(created_at)
        if created_ts <= base + pd.Timedelta(days=int(max_created_delay_days)):
            return created_ts.to_pydatetime(), True, "created_at used as ingestion timestamp"
    return _available_at(
        signal_date=signal_date,
        true_available_at=None,
        fallback_days=fallback_days,
        source_label=source_label,
    )


def _region_allowed(region_code: str | None, allowed: set[str] | None) -> bool:
    if not region_code:
        return False
    if allowed is None:
        return True
    # National fallback evidence is useful context for regional scopes, but it
    # stays explicitly marked as DE and partial coverage.
    return region_code in allowed or region_code == "DE"


def _base_row(
    *,
    source: ObservationSource,
    source_detail: str,
    virus_typ: str,
    region_code: str,
    signal_date: datetime,
    available_at: datetime,
    value_raw: float | None,
    coverage: float | None,
    revision_risk: float | None,
    is_point_in_time_safe: bool,
    point_in_time_note: str | None,
    baseline: float | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "source_detail": source_detail,
        "virus_typ": virus_typ,
        "region_code": region_code,
        "region_name": _region_name(region_code),
        "signal_date": _to_datetime(signal_date),
        "available_at": _to_datetime(available_at),
        "value_raw": value_raw,
        "value_normalized": None,
        "baseline": baseline,
        "intensity": None,
        "growth_7d": None,
        "acceleration_7d": None,
        "freshness_days": None,
        "coverage": coverage,
        "revision_risk": revision_risk,
        "usable_confidence": None,
        "is_point_in_time_safe": bool(is_point_in_time_safe),
        "point_in_time_note": point_in_time_note,
    }


def _fallback_series_key(row: dict[str, Any]) -> tuple[str, str, datetime]:
    source = str(row.get("source") or "")
    detail = str(row.get("source_detail") or "")
    detail = detail.replace(":national_fallback", "").replace(":state", "")
    return (
        source,
        detail,
        _to_datetime(row["signal_date"]),
    )


def _drop_superseded_national_fallbacks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    regional_sources = {"survstat", "are", "grippeweb"}
    regional_keys = {
        _fallback_series_key(row)
        for row in rows
        if row.get("source") in regional_sources and row.get("region_code") != "DE"
    }
    if not regional_keys:
        return rows

    pruned: list[dict[str, Any]] = []
    for row in rows:
        is_national_fallback = (
            row.get("source") in regional_sources
            and row.get("region_code") == "DE"
            and "national_fallback" in str(row.get("source_detail") or "")
        )
        if is_national_fallback and _fallback_series_key(row) in regional_keys:
            continue
        pruned.append(row)
    return pruned


def _load_wastewater_rows(
    db: Session,
    *,
    virus_typ: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    allowed_regions: set[str] | None,
) -> list[dict[str, Any]]:
    rows = (
        db.query(WastewaterAggregated)
        .filter(
            WastewaterAggregated.virus_typ == virus_typ,
            WastewaterAggregated.datum >= start.to_pydatetime(),
            WastewaterAggregated.datum <= end.to_pydatetime(),
        )
        .order_by(WastewaterAggregated.datum.asc())
        .all()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        region_code = "DE"
        if not _region_allowed(region_code, allowed_regions):
            continue
        signal_date = _to_datetime(row.datum)
        available_at, safe, note = _available_at(
            signal_date=signal_date,
            true_available_at=row.available_time,
            fallback_days=7,
            source_label="WastewaterAggregated",
        )
        value = _safe_float(row.viruslast)
        if value is None:
            value = _safe_float(row.viruslast_normalisiert)
        out.append(
            _base_row(
                source="wastewater",
                source_detail="wastewater_aggregated:national_fallback",
                virus_typ=virus_typ,
                region_code=region_code,
                signal_date=signal_date,
                available_at=available_at,
                value_raw=value,
                coverage=_coverage_from_wastewater(
                    anteil_bev=_safe_float(row.anteil_bev),
                    n_standorte=int(row.n_standorte) if row.n_standorte is not None else None,
                ),
                revision_risk=0.05 if safe else 0.25,
                is_point_in_time_safe=safe,
                point_in_time_note=note,
            )
        )
    return out


def _load_survstat_rows(
    db: Session,
    *,
    virus_typ: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    allowed_regions: set[str] | None,
) -> list[dict[str, Any]]:
    diseases = tuple(SURVSTAT_VIRUS_MAP.get(virus_typ, []))
    if not diseases:
        return []
    rows = (
        db.query(
            SurvstatWeeklyData.week_start,
            func.max(SurvstatWeeklyData.available_time).label("available_time"),
            SurvstatWeeklyData.bundesland,
            func.sum(SurvstatWeeklyData.incidence).label("incidence"),
        )
        .filter(
            func.lower(SurvstatWeeklyData.disease).in_(diseases),
            SurvstatWeeklyData.week_start >= start.to_pydatetime(),
            SurvstatWeeklyData.week_start <= end.to_pydatetime(),
            SurvstatWeeklyData.age_group.in_(["00+", "Gesamt", None]),
        )
        .group_by(SurvstatWeeklyData.week_start, SurvstatWeeklyData.bundesland)
        .order_by(SurvstatWeeklyData.week_start.asc())
        .all()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        region_code = _normalise_region_code(row.bundesland)
        if not _region_allowed(region_code, allowed_regions):
            continue
        signal_date = _to_datetime(row.week_start)
        available_at, safe, note = _available_at(
            signal_date=signal_date,
            true_available_at=row.available_time,
            fallback_days=14,
            source_label="SurvstatWeeklyData",
        )
        source_detail = (
            "survstat_weekly:national_fallback"
            if region_code == "DE"
            else "survstat_weekly:state"
        )
        out.append(
            _base_row(
                source="survstat",
                source_detail=source_detail,
                virus_typ=virus_typ,
                region_code=str(region_code),
                signal_date=signal_date,
                available_at=available_at,
                value_raw=_safe_float(row.incidence),
                coverage=0.35 if region_code == "DE" else 1.0,
                revision_risk=0.10 if safe else 0.30,
                is_point_in_time_safe=safe,
                point_in_time_note=note,
            )
        )
    return out


def _load_are_rows(
    db: Session,
    *,
    virus_typ: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    allowed_regions: set[str] | None,
) -> list[dict[str, Any]]:
    rows = (
        db.query(
            AREKonsultation.bundesland,
            AREKonsultation.datum,
            func.max(AREKonsultation.available_time).label("available_time"),
            func.avg(AREKonsultation.konsultationsinzidenz).label("incidence"),
        )
        .filter(
            AREKonsultation.altersgruppe == "00+",
            AREKonsultation.datum >= start.to_pydatetime(),
            AREKonsultation.datum <= end.to_pydatetime(),
        )
        .group_by(AREKonsultation.bundesland, AREKonsultation.datum)
        .order_by(AREKonsultation.datum.asc())
        .all()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        region_code = _normalise_region_code(row.bundesland)
        if not _region_allowed(region_code, allowed_regions):
            continue
        signal_date = _to_datetime(row.datum)
        available_at, safe, note = _available_at(
            signal_date=signal_date,
            true_available_at=row.available_time,
            fallback_days=SOURCE_LAG_DAYS["are_konsultation"],
            source_label="AREKonsultation",
        )
        out.append(
            _base_row(
                source="are",
                source_detail="are_konsultation:00+",
                virus_typ=virus_typ,
                region_code=str(region_code),
                signal_date=signal_date,
                available_at=available_at,
                value_raw=_safe_float(row.incidence),
                coverage=0.35 if region_code == "DE" else 1.0,
                revision_risk=0.10 if safe else 0.25,
                is_point_in_time_safe=safe,
                point_in_time_note=note,
            )
        )
    return out


def _load_grippeweb_rows(
    db: Session,
    *,
    virus_typ: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    allowed_regions: set[str] | None,
) -> list[dict[str, Any]]:
    rows = (
        db.query(
            GrippeWebData.bundesland,
            GrippeWebData.datum,
            GrippeWebData.erkrankung_typ,
            func.max(GrippeWebData.created_at).label("created_at"),
            func.avg(GrippeWebData.inzidenz).label("incidence"),
        )
        .filter(
            GrippeWebData.datum >= start.to_pydatetime(),
            GrippeWebData.datum <= end.to_pydatetime(),
            GrippeWebData.erkrankung_typ.in_(["ARE", "ILI"]),
            GrippeWebData.altersgruppe.in_(["00+", "Gesamt", None]),
        )
        .group_by(GrippeWebData.bundesland, GrippeWebData.datum, GrippeWebData.erkrankung_typ)
        .order_by(GrippeWebData.datum.asc())
        .all()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        region_code = _normalise_region_code(row.bundesland) or "DE"
        if not _region_allowed(region_code, allowed_regions):
            continue
        signal_date = _to_datetime(row.datum)
        available_at, safe, note = _created_or_inferred_available_at(
            signal_date=signal_date,
            created_at=row.created_at,
            fallback_days=SOURCE_LAG_DAYS["grippeweb"],
            source_label="GrippeWebData",
        )
        signal_type = str(row.erkrankung_typ or "").strip().upper() or "UNKNOWN"
        out.append(
            _base_row(
                source="grippeweb",
                source_detail=f"grippeweb:{signal_type}"
                + (":national_fallback" if region_code == "DE" else ":state"),
                virus_typ=virus_typ,
                region_code=region_code,
                signal_date=signal_date,
                available_at=available_at,
                value_raw=_safe_float(row.incidence),
                coverage=0.35 if region_code == "DE" else 1.0,
                revision_risk=0.10 if safe else 0.25,
                is_point_in_time_safe=safe,
                point_in_time_note=note,
            )
        )
    return out


def _load_notaufnahme_rows(
    db: Session,
    *,
    virus_typ: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    allowed_regions: set[str] | None,
) -> list[dict[str, Any]]:
    syndrome = _NOTAUFNAHME_SYNDROME_FOR_VIRUS.get(virus_typ)
    if not syndrome:
        return []
    if not _region_allowed("DE", allowed_regions):
        return []
    rows = (
        db.query(NotaufnahmeSyndromData)
        .filter(
            NotaufnahmeSyndromData.syndrome == syndrome,
            NotaufnahmeSyndromData.ed_type == "all",
            NotaufnahmeSyndromData.age_group == "00+",
            NotaufnahmeSyndromData.datum >= start.to_pydatetime(),
            NotaufnahmeSyndromData.datum <= end.to_pydatetime(),
        )
        .order_by(NotaufnahmeSyndromData.datum.asc())
        .all()
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        signal_date = _to_datetime(row.datum)
        available_at, safe, note = _created_or_inferred_available_at(
            signal_date=signal_date,
            created_at=row.created_at,
            fallback_days=SOURCE_LAG_DAYS["notaufnahme"],
            source_label="NotaufnahmeSyndromData",
        )
        value = _safe_float(row.relative_cases_7day_ma)
        if value is None:
            value = _safe_float(row.relative_cases)
        out.append(
            _base_row(
                source="notaufnahme",
                source_detail=f"notaufnahme_syndrome:{syndrome}:national_fallback",
                virus_typ=virus_typ,
                region_code="DE",
                signal_date=signal_date,
                available_at=available_at,
                value_raw=value,
                baseline=_safe_float(row.expected_value),
                coverage=0.35,
                revision_risk=0.10 if safe else 0.25,
                is_point_in_time_safe=safe,
                point_in_time_note=note,
            )
        )
    return out


def _enrich_metrics(panel: pd.DataFrame, *, cutoff: pd.Timestamp) -> pd.DataFrame:
    if panel.empty:
        return _empty_panel()

    enriched = panel.copy()
    enriched["signal_date"] = pd.to_datetime(enriched["signal_date"], errors="coerce")
    enriched["available_at"] = pd.to_datetime(enriched["available_at"], errors="coerce")
    enriched = enriched.loc[enriched["available_at"] <= cutoff].copy()
    if enriched.empty:
        return _empty_panel()

    for column in ("value_raw", "baseline", "coverage", "revision_risk"):
        enriched[column] = pd.to_numeric(enriched[column], errors="coerce")

    enriched = enriched.sort_values(["source", "region_code", "source_detail", "signal_date"]).reset_index(drop=True)
    for _, group in enriched.groupby(["source", "region_code", "source_detail"], sort=False):
        previous_growth: float | None = None
        group_indices = list(group.index)
        for index in group_indices:
            row = enriched.loc[index]
            current_date = pd.Timestamp(row["signal_date"])
            current_value = _safe_float(row["value_raw"])
            prior = enriched.loc[
                group_indices,
                ["signal_date", "value_raw"],
            ].copy()
            prior = prior.loc[pd.to_datetime(prior["signal_date"]) < current_date]
            prior_values = pd.to_numeric(prior["value_raw"], errors="coerce").dropna()

            baseline = _safe_float(row.get("baseline"))
            if not prior_values.empty:
                baseline = float(prior_values.tail(52).median())
            if baseline is not None:
                enriched.at[index, "baseline"] = baseline

            value_normalized: float | None = None
            if current_value is not None and baseline is not None:
                value_normalized = math.log1p(max(current_value, 0.0)) - math.log1p(max(baseline, 0.0))
                enriched.at[index, "value_normalized"] = value_normalized
                enriched.at[index, "intensity"] = _sigmoid(value_normalized)

            growth: float | None = None
            prior_7d = prior.loc[
                pd.to_datetime(prior["signal_date"]) <= current_date - pd.Timedelta(days=7)
            ]
            prior_7d_values = pd.to_numeric(prior_7d["value_raw"], errors="coerce").dropna()
            if current_value is not None and not prior_7d_values.empty:
                previous_value = float(prior_7d_values.iloc[-1])
                growth = (current_value - previous_value) / max(abs(previous_value), 1.0)
                enriched.at[index, "growth_7d"] = growth

            if growth is not None and previous_growth is not None:
                enriched.at[index, "acceleration_7d"] = growth - previous_growth
            if growth is not None:
                previous_growth = growth

    freshness_days = (cutoff - enriched["available_at"]).dt.total_seconds() / 86400.0
    enriched["freshness_days"] = freshness_days.clip(lower=0.0)
    enriched["revision_risk"] = enriched["revision_risk"].fillna(
        enriched["is_point_in_time_safe"].map({True: 0.10, False: 0.25})
    )
    freshness_score = enriched["freshness_days"].map(lambda value: math.exp(-float(value) / 28.0))
    coverage = pd.to_numeric(enriched["coverage"], errors="coerce")
    revision = pd.to_numeric(enriched["revision_risk"], errors="coerce").clip(lower=0.0, upper=1.0)
    enriched["usable_confidence"] = (coverage * freshness_score * (1.0 - revision)).clip(lower=0.0, upper=1.0)

    enriched = enriched[PANEL_COLUMNS].copy()
    enriched["is_point_in_time_safe"] = enriched["is_point_in_time_safe"].astype(object)
    return enriched.reset_index(drop=True)


def build_tri_layer_observation_panel(
    db: Session,
    *,
    virus_typ: str,
    cutoff: date | datetime,
    start_date: date | datetime | None = None,
    end_date: date | datetime | None = None,
    region_codes: list[str] | None = None,
    include_forecast_proxy: bool = False,
) -> pd.DataFrame:
    """Build leakage-safe source observations visible at ``cutoff``.

    ``include_forecast_proxy`` is accepted for the future API, but defaults to
    false because this canonical panel is meant to separate raw observations
    from model outputs.
    """
    del include_forecast_proxy
    cutoff_ts = _timestamp(cutoff)
    end = _timestamp(end_date) if end_date is not None else cutoff_ts
    start = _timestamp(start_date) if start_date is not None else end - pd.Timedelta(days=365)
    allowed_regions = (
        {code for value in region_codes or [] if (code := _normalise_region_code(value))}
        if region_codes is not None
        else None
    )

    rows: list[dict[str, Any]] = []
    rows.extend(
        _load_wastewater_rows(
            db,
            virus_typ=virus_typ,
            start=start,
            end=end,
            allowed_regions=allowed_regions,
        )
    )
    rows.extend(
        _load_survstat_rows(
            db,
            virus_typ=virus_typ,
            start=start,
            end=end,
            allowed_regions=allowed_regions,
        )
    )
    rows.extend(
        _load_notaufnahme_rows(
            db,
            virus_typ=virus_typ,
            start=start,
            end=end,
            allowed_regions=allowed_regions,
        )
    )
    rows.extend(
        _load_are_rows(
            db,
            virus_typ=virus_typ,
            start=start,
            end=end,
            allowed_regions=allowed_regions,
        )
    )
    rows.extend(
        _load_grippeweb_rows(
            db,
            virus_typ=virus_typ,
            start=start,
            end=end,
            allowed_regions=allowed_regions,
        )
    )

    if not rows:
        return _empty_panel()
    rows = _drop_superseded_national_fallbacks(rows)
    return _enrich_metrics(pd.DataFrame(rows), cutoff=cutoff_ts)
