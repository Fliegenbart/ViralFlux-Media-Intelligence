"""Live-source helpers for production readiness snapshots."""

from __future__ import annotations

from datetime import datetime
from math import ceil
from typing import Any

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import (
    AREKonsultation,
    GoogleTrendsData,
    GrippeWebData,
    InfluenzaData,
    NotaufnahmeSyndromData,
    RSVData,
    WastewaterData,
)
from app.services.ml.regional_panel_utils import SOURCE_LAG_DAYS, effective_available_time

_LIVE_SOURCE_CONTRACTS_BY_VIRUS: dict[str, tuple[dict[str, Any], ...]] = {
    "Influenza A": (
        {"source_id": "wastewater", "criticality": "critical", "cadence_days": 1, "coverage_window_days": 2, "minimum_points": 1, "label": "Wastewater"},
        {"source_id": "grippeweb_are", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ARE"},
        {"source_id": "grippeweb_ili", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ILI"},
        {"source_id": "ifsg_influenza", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "IfSG Influenza"},
    ),
    "Influenza B": (
        {"source_id": "wastewater", "criticality": "critical", "cadence_days": 1, "coverage_window_days": 2, "minimum_points": 1, "label": "Wastewater"},
        {"source_id": "grippeweb_are", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ARE"},
        {"source_id": "grippeweb_ili", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ILI"},
        {"source_id": "ifsg_influenza", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "IfSG Influenza"},
    ),
    "RSV A": (
        {"source_id": "wastewater", "criticality": "critical", "cadence_days": 1, "coverage_window_days": 2, "minimum_points": 1, "label": "Wastewater"},
        {"source_id": "grippeweb_are", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ARE"},
        {"source_id": "grippeweb_ili", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ILI"},
        {"source_id": "ifsg_rsv", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "IfSG RSV"},
    ),
    "SARS-CoV-2": (
        {"source_id": "wastewater", "criticality": "critical", "cadence_days": 1, "coverage_window_days": 2, "minimum_points": 1, "label": "Wastewater"},
        {"source_id": "grippeweb_are", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ARE"},
        {"source_id": "grippeweb_ili", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "GrippeWeb ILI"},
        {"source_id": "sars_are", "criticality": "critical", "cadence_days": 7, "coverage_window_days": 28, "label": "ARE Konsultation"},
        {"source_id": "sars_notaufnahme", "criticality": "critical", "cadence_days": 1, "coverage_window_days": 2, "minimum_points": 1, "label": "Notaufnahme COVID"},
        {"source_id": "sars_trends", "criticality": "advisory", "cadence_days": 1, "coverage_window_days": 2, "minimum_points": 1, "label": "Google Trends Corona Test"},
    ),
}


def latest_source_state(
    service,
    db: Session,
    *,
    virus_typ: str,
    observed_at: datetime,
) -> dict[str, Any]:
    source_frames = service._load_live_source_frames(
        db,
        virus_typ=virus_typ,
        observed_at=observed_at,
    )
    source_states = {
        spec["source_id"]: service._live_source_state_entry(
            frame=source_frames.get(spec["source_id"]),
            observed_at=observed_at,
            source_id=str(spec["source_id"]),
            label=str(spec["label"]),
            criticality=str(spec["criticality"]),
            cadence_days=int(spec["cadence_days"]),
            coverage_window_days=int(spec["coverage_window_days"]),
            minimum_points=int(spec.get("minimum_points") or 0),
        )
        for spec in service._live_source_specs(virus_typ)
    }
    return service._aggregate_live_source_state(source_states=source_states)


def load_live_source_frames(
    service,
    db: Session,
    *,
    virus_typ: str,
    observed_at: datetime,
) -> dict[str, pd.DataFrame]:
    observed_ts = pd.Timestamp(observed_at).normalize()
    specs = service._live_source_specs(virus_typ)
    max_window_days = max((int(spec.get("coverage_window_days") or 0) for spec in specs), default=28)
    start_date = observed_ts - pd.Timedelta(days=max(max_window_days, 28))
    frames: dict[str, pd.DataFrame] = {
        "wastewater": service._load_live_wastewater_frame(
            db,
            virus_typ=virus_typ,
            start_date=start_date,
            end_date=observed_ts,
        ),
        "grippeweb_are": service._load_live_grippeweb_frame(
            db,
            signal_type="ARE",
            start_date=start_date,
            end_date=observed_ts,
        ),
        "grippeweb_ili": service._load_live_grippeweb_frame(
            db,
            signal_type="ILI",
            start_date=start_date,
            end_date=observed_ts,
        ),
    }
    if virus_typ in {"Influenza A", "Influenza B"}:
        frames["ifsg_influenza"] = service._load_live_ifsg_frame(
            db,
            model=InfluenzaData,
            lag_days=SOURCE_LAG_DAYS["influenza_ifsg"],
            start_date=start_date,
            end_date=observed_ts,
        )
    elif virus_typ == "RSV A":
        frames["ifsg_rsv"] = service._load_live_ifsg_frame(
            db,
            model=RSVData,
            lag_days=SOURCE_LAG_DAYS["rsv_ifsg"],
            start_date=start_date,
            end_date=observed_ts,
        )
    elif virus_typ == "SARS-CoV-2":
        frames["sars_are"] = service._load_live_are_frame(
            db,
            start_date=start_date,
            end_date=observed_ts,
        )
        frames["sars_notaufnahme"] = service._load_live_notaufnahme_frame(
            db,
            start_date=start_date,
            end_date=observed_ts,
        )
        frames["sars_trends"] = service._load_live_trends_frame(
            db,
            start_date=start_date,
            end_date=observed_ts,
        )
    return frames


def load_live_wastewater_frame(
    service,
    db: Session,
    *,
    virus_typ: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    rows = (
        db.query(
            WastewaterData.datum,
            func.max(WastewaterData.available_time).label("available_time"),
        )
        .filter(
            WastewaterData.virus_typ == virus_typ,
            WastewaterData.datum >= start_date.to_pydatetime(),
            WastewaterData.datum <= end_date.to_pydatetime(),
        )
        .group_by(WastewaterData.datum)
        .order_by(WastewaterData.datum.asc())
        .all()
    )
    return service._live_frame_from_available_rows(rows=rows, lag_days=0)


def load_live_grippeweb_frame(
    service,
    db: Session,
    *,
    signal_type: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    rows = (
        db.query(
            GrippeWebData.datum,
            func.max(GrippeWebData.created_at).label("created_at"),
        )
        .filter(
            GrippeWebData.datum >= start_date.to_pydatetime(),
            GrippeWebData.datum <= end_date.to_pydatetime(),
            GrippeWebData.erkrankung_typ == signal_type,
            GrippeWebData.altersgruppe.in_(["00+", "Gesamt"]),
        )
        .group_by(GrippeWebData.datum)
        .order_by(GrippeWebData.datum.asc())
        .all()
    )
    return service._live_frame_from_created_rows(
        rows=rows,
        lag_days=SOURCE_LAG_DAYS["grippeweb"],
    )


def load_live_ifsg_frame(
    service,
    db: Session,
    *,
    model: Any,
    lag_days: int,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    rows = (
        db.query(
            model.datum,
            func.max(model.available_time).label("available_time"),
        )
        .filter(
            model.datum >= start_date.to_pydatetime(),
            model.datum <= end_date.to_pydatetime(),
            model.altersgruppe.in_(["00+", "Gesamt"]),
        )
        .group_by(model.datum)
        .order_by(model.datum.asc())
        .all()
    )
    return service._live_frame_from_available_rows(rows=rows, lag_days=lag_days)


def load_live_are_frame(
    service,
    db: Session,
    *,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    rows = (
        db.query(
            AREKonsultation.datum,
            func.max(AREKonsultation.available_time).label("available_time"),
        )
        .filter(
            AREKonsultation.datum >= start_date.to_pydatetime(),
            AREKonsultation.datum <= end_date.to_pydatetime(),
            AREKonsultation.altersgruppe == "00+",
        )
        .group_by(AREKonsultation.datum)
        .order_by(AREKonsultation.datum.asc())
        .all()
    )
    return service._live_frame_from_available_rows(
        rows=rows,
        lag_days=SOURCE_LAG_DAYS["are_konsultation"],
    )


def load_live_notaufnahme_frame(
    service,
    db: Session,
    *,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    rows = (
        db.query(
            NotaufnahmeSyndromData.datum,
            func.max(NotaufnahmeSyndromData.created_at).label("created_at"),
        )
        .filter(
            NotaufnahmeSyndromData.datum >= start_date.to_pydatetime(),
            NotaufnahmeSyndromData.datum <= end_date.to_pydatetime(),
            NotaufnahmeSyndromData.syndrome == "COVID",
            NotaufnahmeSyndromData.ed_type == "all",
            NotaufnahmeSyndromData.age_group == "00+",
        )
        .group_by(NotaufnahmeSyndromData.datum)
        .order_by(NotaufnahmeSyndromData.datum.asc())
        .all()
    )
    return service._live_frame_from_created_rows(
        rows=rows,
        lag_days=SOURCE_LAG_DAYS["notaufnahme"],
    )


def load_live_trends_frame(
    service,
    db: Session,
    *,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    rows = (
        db.query(
            GoogleTrendsData.datum,
            func.max(GoogleTrendsData.available_time).label("available_time"),
        )
        .filter(
            GoogleTrendsData.datum >= start_date.to_pydatetime(),
            GoogleTrendsData.datum <= end_date.to_pydatetime(),
            func.lower(GoogleTrendsData.keyword) == "corona test",
            GoogleTrendsData.region == "DE",
        )
        .group_by(GoogleTrendsData.datum)
        .order_by(GoogleTrendsData.datum.asc())
        .all()
    )
    return service._live_frame_from_available_rows(
        rows=rows,
        lag_days=SOURCE_LAG_DAYS["google_trends"],
    )


def live_frame_from_available_rows(*, rows: Any, lag_days: int) -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "datum": pd.Timestamp(row.datum).normalize(),
                "available_time": effective_available_time(row.datum, row.available_time, lag_days),
            }
            for row in rows
        ]
    )
    if frame.empty:
        return frame
    return frame.sort_values("datum").reset_index(drop=True)


def live_frame_from_created_rows(service, *, rows: Any, lag_days: int) -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "datum": pd.Timestamp(row.datum).normalize(),
                "available_time": service._proxy_available_time_from_created(
                    datum=row.datum,
                    created_at=row.created_at,
                    lag_days=lag_days,
                ),
            }
            for row in rows
        ]
    )
    if frame.empty:
        return frame
    return frame.sort_values("datum").reset_index(drop=True)


def proxy_available_time_from_created(
    *,
    datum: datetime | pd.Timestamp,
    created_at: datetime | pd.Timestamp | None,
    lag_days: int,
    max_created_delay_days: int = 14,
) -> pd.Timestamp:
    base_available_time = effective_available_time(datum, None, lag_days)
    if created_at is None or pd.isna(created_at):
        return base_available_time
    created_ts = pd.Timestamp(created_at)
    if created_ts <= base_available_time + pd.Timedelta(days=max_created_delay_days):
        return created_ts
    return base_available_time


def live_source_specs(virus_typ: str) -> tuple[dict[str, Any], ...]:
    return _LIVE_SOURCE_CONTRACTS_BY_VIRUS.get(str(virus_typ or "").strip(), tuple())


def live_source_state_entry(
    service,
    *,
    frame: Any,
    observed_at: datetime,
    source_id: str,
    label: str,
    criticality: str,
    cadence_days: int,
    coverage_window_days: int,
    minimum_points: int = 0,
) -> dict[str, Any]:
    observed_ts = _parse_timestamp(observed_at) or observed_at
    observed_date = observed_ts.date()
    latest_available_as_of = None
    visible = frame.copy() if frame is not None and hasattr(frame, "copy") else None

    if visible is not None and not visible.empty and "datum" in visible.columns:
        visible = visible.copy()
        visible["datum"] = pd.to_datetime(visible["datum"], errors="coerce").dt.normalize()
        visible = visible.loc[visible["datum"].notna() & (visible["datum"] <= pd.Timestamp(observed_date))].copy()
        if "available_time" in visible.columns:
            visible["available_time"] = pd.to_datetime(visible["available_time"], errors="coerce")
            visible = visible.loc[
                visible["available_time"].notna()
                & (visible["available_time"] <= pd.Timestamp(observed_ts))
            ].copy()
            latest_available_as_of = (
                _parse_timestamp(visible["available_time"].max())
                if not visible.empty
                else None
            )
        elif not visible.empty:
            latest_available_as_of = _parse_timestamp(visible["datum"].max())

    coverage_window_start = pd.Timestamp(observed_date) - pd.Timedelta(days=max(int(coverage_window_days) - 1, 0))
    recent = (
        visible.loc[visible["datum"] >= coverage_window_start].copy()
        if visible is not None and not visible.empty
        else None
    )
    available_points = int(visible["datum"].nunique()) if visible is not None and not visible.empty else 0
    observed_points = int(recent["datum"].nunique()) if recent is not None and not recent.empty else 0
    expected_points = max(int(ceil(float(max(int(coverage_window_days), 1)) / max(int(cadence_days), 1))), 1)
    coverage_ratio = round(min(float(observed_points) / float(expected_points), 1.0), 4) if expected_points else 0.0
    if available_points == 0:
        coverage_status = "critical"
    elif int(minimum_points) > 0:
        coverage_status = "ok" if available_points >= int(minimum_points) else "critical"
    else:
        coverage_status = "critical" if observed_points == 0 else service._coverage_status(coverage_ratio)
    age_days = _day_delta(observed_ts, latest_available_as_of)
    fresh_days, warning_days = service._source_freshness_windows(cadence_days=cadence_days)
    freshness_status = service._age_status(
        age_days,
        fresh_days=fresh_days,
        warning_days=warning_days,
        missing_status="critical",
    )
    return {
        "source_id": source_id,
        "label": label,
        "criticality": criticality,
        "observed_points": observed_points,
        "expected_points": expected_points,
        "coverage_ratio": coverage_ratio,
        "coverage_status": coverage_status,
        "latest_available_as_of": latest_available_as_of,
        "age_days": age_days,
        "freshness_status": freshness_status,
    }


def aggregate_live_source_state(
    service,
    *,
    source_states: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    critical_states = [state for state in source_states.values() if state.get("criticality") == "critical"]
    advisory_states = [state for state in source_states.values() if state.get("criticality") == "advisory"]
    required_live_sources = [str(state.get("source_id")) for state in critical_states]
    optional_live_sources = [str(state.get("source_id")) for state in advisory_states]
    missing_required_live_sources = [
        str(state.get("source_id"))
        for state in critical_states
        if str(state.get("coverage_status") or "critical") == "critical"
    ]

    required_coverage_floor = (
        min(float(state.get("coverage_ratio") or 0.0) for state in critical_states)
        if critical_states
        else None
    )
    optional_coverage_floor = (
        min(float(state.get("coverage_ratio") or 0.0) for state in advisory_states)
        if advisory_states
        else None
    )
    required_coverage_status = (
        service._worst_status(state.get("coverage_status") for state in critical_states)
        if critical_states
        else "unknown"
    )
    optional_coverage_raw_status = (
        service._worst_status(state.get("coverage_status") for state in advisory_states)
        if advisory_states
        else "unknown"
    )
    required_freshness_status = (
        service._worst_status(state.get("freshness_status") for state in critical_states)
        if critical_states
        else "unknown"
    )
    optional_freshness_raw_status = (
        service._worst_status(state.get("freshness_status") for state in advisory_states)
        if advisory_states
        else "unknown"
    )

    optional_coverage_status = (
        "unknown"
        if not advisory_states
        else ("ok" if optional_coverage_raw_status == "ok" else "warning")
    )
    optional_freshness_status = (
        "unknown"
        if not advisory_states
        else ("ok" if optional_freshness_raw_status == "ok" else "warning")
    )
    live_source_coverage_status = service._worst_status(
        [
            required_coverage_status,
            "warning" if optional_coverage_raw_status in {"warning", "critical"} else "ok",
        ]
    )
    live_source_freshness_status = service._worst_status(
        [
            required_freshness_status,
            "warning" if optional_freshness_raw_status in {"warning", "critical"} else "ok",
        ]
    )
    driver_state = max(
        critical_states or advisory_states or [{}],
        key=lambda state: int(state.get("age_days")) if state.get("age_days") is not None else -1,
    )

    blockers: list[str] = []
    advisories: list[str] = []
    for state in critical_states:
        source_id = str(state.get("source_id") or "source")
        coverage_ratio = float(state.get("coverage_ratio") or 0.0)
        age_days = state.get("age_days")
        if str(state.get("coverage_status") or "unknown") == "critical":
            blockers.append(f"Critical live source coverage is missing or too low: {source_id}.")
        elif str(state.get("coverage_status") or "unknown") == "warning":
            advisories.append(f"Critical live source coverage is below the ideal threshold: {source_id}={coverage_ratio:.4f}.")
        if str(state.get("freshness_status") or "unknown") == "critical":
            blockers.append(f"Critical live source is stale: {source_id}.")
        elif str(state.get("freshness_status") or "unknown") == "warning":
            advisories.append(f"Critical live source freshness is outside the ideal window: {source_id} age={age_days}d.")
    for state in advisory_states:
        source_id = str(state.get("source_id") or "source")
        coverage_ratio = float(state.get("coverage_ratio") or 0.0)
        age_days = state.get("age_days")
        if str(state.get("coverage_status") or "unknown") != "ok":
            advisories.append(f"Advisory live source coverage needs attention: {source_id}={coverage_ratio:.4f}.")
        if str(state.get("freshness_status") or "unknown") != "ok":
            advisories.append(f"Advisory live source freshness needs attention: {source_id} age={age_days}d.")

    blockers = list(dict.fromkeys(blockers))
    advisories = list(dict.fromkeys(advisories))
    if blockers:
        message = blockers[0]
    elif advisories:
        message = "Live source coverage or freshness has active warnings."
    else:
        message = "Live source coverage and freshness evaluated."

    return {
        "status": live_source_freshness_status,
        "message": message,
        "latest_available_as_of": driver_state.get("latest_available_as_of"),
        "source_age_days": driver_state.get("age_days"),
        "source_coverage_floor": required_coverage_floor,
        "required_coverage_floor": required_coverage_floor,
        "optional_coverage_floor": optional_coverage_floor,
        "source_coverage_required_status": required_coverage_status,
        "source_coverage_optional_status": optional_coverage_status,
        "required_live_sources": required_live_sources,
        "optional_live_sources": optional_live_sources,
        "missing_required_live_sources": missing_required_live_sources,
        "live_source_coverage_status": live_source_coverage_status,
        "live_source_freshness_status": live_source_freshness_status,
        "blockers": blockers,
        "advisories": advisories,
        "source_criticality": {
            str(source_id): str((state or {}).get("criticality") or "unknown")
            for source_id, state in source_states.items()
        },
        "live_source_coverage": {
            str(source_id): {
                "criticality": str((state or {}).get("criticality") or "unknown"),
                "observed_points": int((state or {}).get("observed_points") or 0),
                "expected_points": int((state or {}).get("expected_points") or 0),
                "coverage_ratio": round(float((state or {}).get("coverage_ratio") or 0.0), 4),
                "status": str((state or {}).get("coverage_status") or "unknown"),
            }
            for source_id, state in source_states.items()
        },
        "live_source_freshness": {
            str(source_id): {
                "criticality": str((state or {}).get("criticality") or "unknown"),
                "latest_available_as_of": (
                    (state or {}).get("latest_available_as_of").isoformat()
                    if (state or {}).get("latest_available_as_of") is not None
                    else None
                ),
                "age_days": (state or {}).get("age_days"),
                "status": str((state or {}).get("freshness_status") or "unknown"),
            }
            for source_id, state in source_states.items()
        },
    }


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def _day_delta(later: datetime | None, earlier: datetime | None) -> int | None:
    if later is None or earlier is None:
        return None
    return max((later.date() - earlier.date()).days, 0)
