"""Diagnostic site-level early-warning rules for AMELAG wastewater data."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping

from sqlalchemy.orm import Session

from app.models.database import WastewaterData

METHOD = "local_baseline_pct_v1"
MODE = "diagnostic_only"
STAGE_RANK = {"red": 2, "yellow": 1, "none": 0}


@dataclass(frozen=True)
class SiteEarlyWarningConfig:
    baseline_window: int = 4
    min_baseline_points: int = 3
    yellow_increase_pct: float = 100.0
    red_increase_pct: float = 200.0
    min_current_value: float = 1000.0
    active_max_age_days: int = 14
    max_active_alerts: int = 50
    max_region_alerts: int = 5
    metric: str = "viruslast_normalisiert"
    fallback_metric: str = "viruslast"
    block_current_under_bg: bool = True
    exclude_under_bg_from_baseline: bool = True
    promote_consecutive_yellow_to_red: bool = True


@dataclass(frozen=True)
class _Measurement:
    standort: str
    bundesland: str
    datum: date
    virus_typ: str
    value: float
    metric: str
    viruslast: float | None
    viruslast_normalisiert: float | None
    vorhersage: float | None
    einwohner: int | None
    unter_bg: bool | None
    laborwechsel: bool | None


def build_site_early_warning(
    db: Session | None = None,
    *,
    rows: Iterable[Any] | None = None,
    virus_typ: str,
    config: SiteEarlyWarningConfig | None = None,
) -> dict[str, Any]:
    """Build a diagnostic local AMELAG early-warning payload.

    The result is intentionally diagnostic-only. It may explain local wastewater
    signals, but it must not grant budget permission or alter media gates.
    """
    config = config or SiteEarlyWarningConfig()
    source_rows = list(rows) if rows is not None else _load_rows(db, virus_typ=virus_typ)
    evaluated = evaluate_site_measurements(source_rows, config)
    latest = _latest_status(evaluated)
    latest_date = max((_parse_date(row.get("datum")) for row in latest), default=None)
    active_since = latest_date - timedelta(days=config.active_max_age_days) if latest_date else None
    active_alerts = [
        row
        for row in latest
        if row.get("stage") in {"yellow", "red"}
        and active_since is not None
        and (_parse_date(row.get("datum")) or date.min) >= active_since
    ]
    active_alerts = _sort_alerts(active_alerts)[: config.max_active_alerts]
    regions = _build_region_payloads(active_alerts, config=config)

    return {
        "mode": MODE,
        "can_change_budget": False,
        "budget_impact": {
            "mode": MODE,
            "can_change_budget": False,
            "reason": "site_level_amelag_alerts_are_diagnostic_only",
        },
        "method": METHOD,
        "virus_typ": virus_typ,
        "latest_measurement_date": latest_date.isoformat() if latest_date else None,
        "active_since_date": active_since.isoformat() if active_since else None,
        "measurement_count": len(evaluated),
        "site_virus_series": len(latest),
        "historical_alert_count": sum(1 for row in evaluated if row.get("stage") in {"yellow", "red"}),
        "active_alert_count": len(active_alerts),
        "active_red_alert_count": sum(1 for row in active_alerts if row.get("stage") == "red"),
        "active_yellow_alert_count": sum(1 for row in active_alerts if row.get("stage") == "yellow"),
        "active_alerts": active_alerts,
        "regions": regions,
        "config": {
            "baseline_window": config.baseline_window,
            "min_baseline_points": config.min_baseline_points,
            "yellow_increase_pct": config.yellow_increase_pct,
            "red_increase_pct": config.red_increase_pct,
            "min_current_value": config.min_current_value,
            "active_max_age_days": config.active_max_age_days,
            "metric": config.metric,
            "fallback_metric": config.fallback_metric,
        },
    }


def empty_region_site_early_warning() -> dict[str, Any]:
    return {
        "mode": MODE,
        "can_change_budget": False,
        "method": METHOD,
        "active_alert_count": 0,
        "active_red_alert_count": 0,
        "active_yellow_alert_count": 0,
        "top_alerts": [],
    }


def region_site_early_warning(payload: Mapping[str, Any], code: str) -> dict[str, Any]:
    regions = payload.get("regions") if isinstance(payload.get("regions"), Mapping) else {}
    region_payload = regions.get(str(code).upper()) if isinstance(regions, Mapping) else None
    if isinstance(region_payload, Mapping):
        return dict(region_payload)
    return empty_region_site_early_warning()


def evaluate_site_measurements(
    rows: Iterable[Any],
    config: SiteEarlyWarningConfig | None = None,
) -> list[dict[str, Any]]:
    config = config or SiteEarlyWarningConfig()
    measurements = _parse_measurements(rows, config)
    grouped: dict[tuple[str, str, str], list[_Measurement]] = defaultdict(list)
    for measurement in measurements:
        grouped[(measurement.standort, measurement.bundesland, measurement.virus_typ)].append(measurement)

    results: list[dict[str, Any]] = []
    for group_rows in grouped.values():
        results.extend(_evaluate_group(group_rows, config))
    return sorted(results, key=lambda item: (item["standort"], item["virus_typ"], item["datum"]))


def _load_rows(db: Session | None, *, virus_typ: str) -> list[WastewaterData]:
    if db is None:
        return []
    return (
        db.query(WastewaterData)
        .filter(WastewaterData.virus_typ == virus_typ)
        .order_by(WastewaterData.standort, WastewaterData.bundesland, WastewaterData.datum)
        .all()
    )


def _parse_measurements(rows: Iterable[Any], config: SiteEarlyWarningConfig) -> list[_Measurement]:
    measurements: list[_Measurement] = []
    for row in rows:
        metric, value = _extract_value(row, config)
        datum = _parse_date(_get(row, "datum"))
        if value is None or datum is None:
            continue
        measurements.append(
            _Measurement(
                standort=str(_get(row, "standort") or "").strip(),
                bundesland=str(_get(row, "bundesland") or "").strip().upper(),
                datum=datum,
                virus_typ=str(_get(row, "virus_typ") or _get(row, "typ") or "").strip(),
                value=value,
                metric=metric,
                viruslast=_safe_float(_get(row, "viruslast")),
                viruslast_normalisiert=_safe_float(_get(row, "viruslast_normalisiert")),
                vorhersage=_safe_float(_get(row, "vorhersage")),
                einwohner=_safe_int(_get(row, "einwohner")),
                unter_bg=_safe_bool(_get(row, "unter_bg")),
                laborwechsel=_safe_bool(_get(row, "laborwechsel")),
            )
        )
    return sorted(measurements, key=lambda item: (item.standort, item.bundesland, item.virus_typ, item.datum))


def _evaluate_group(measurements: list[_Measurement], config: SiteEarlyWarningConfig) -> list[dict[str, Any]]:
    clean_baseline_values: list[float] = []
    previous_measurement: _Measurement | None = None
    previous_alert_stage = "none"
    results: list[dict[str, Any]] = []

    for measurement in sorted(measurements, key=lambda item: item.datum):
        baseline_values = clean_baseline_values[-config.baseline_window :]
        baseline_value = (
            statistics.median(baseline_values)
            if len(baseline_values) >= config.min_baseline_points
            else None
        )
        stage, change_pct, quality_flags = _classify(
            measurement=measurement,
            baseline_value=baseline_value,
            previous_alert_stage=previous_alert_stage,
            config=config,
        )
        if measurement.laborwechsel:
            quality_flags.append("laborwechsel")

        results.append(
            {
                "standort": measurement.standort,
                "bundesland": measurement.bundesland,
                "datum": measurement.datum.isoformat(),
                "virus_typ": measurement.virus_typ,
                "stage": stage,
                "metric": measurement.metric,
                "current_value": _round_float(measurement.value),
                "baseline_value": _round_float(baseline_value),
                "change_pct": _round_float(change_pct),
                "previous_value": _round_float(previous_measurement.value if previous_measurement else None),
                "previous_date": previous_measurement.datum.isoformat() if previous_measurement else None,
                "viruslast": _round_float(measurement.viruslast),
                "viruslast_normalisiert": _round_float(measurement.viruslast_normalisiert),
                "vorhersage": _round_float(measurement.vorhersage),
                "einwohner": measurement.einwohner,
                "unter_bg": bool(measurement.unter_bg),
                "laborwechsel": bool(measurement.laborwechsel),
                "quality_flags": quality_flags,
                "mode": MODE,
                "can_change_budget": False,
            }
        )

        previous_measurement = measurement
        previous_alert_stage = stage
        if not config.exclude_under_bg_from_baseline or not measurement.unter_bg:
            clean_baseline_values.append(measurement.value)

    return results


def _classify(
    *,
    measurement: _Measurement,
    baseline_value: float | None,
    previous_alert_stage: str,
    config: SiteEarlyWarningConfig,
) -> tuple[str, float | None, list[str]]:
    if baseline_value is None:
        return "none", None, ["too_few_baseline_points"]
    if baseline_value <= 0:
        return "none", None, ["invalid_baseline"]

    change_pct = ((measurement.value - baseline_value) / baseline_value) * 100.0
    quality_flags: list[str] = []
    if measurement.value < config.min_current_value:
        quality_flags.append("below_min_current_value")
    if config.block_current_under_bg and measurement.unter_bg:
        quality_flags.append("current_under_bg")
    if quality_flags:
        return "none", change_pct, quality_flags

    if change_pct >= config.red_increase_pct:
        return "red", change_pct, ["red_pct_threshold"]
    if change_pct >= config.yellow_increase_pct:
        quality_flags.append("yellow_pct_threshold")
        if config.promote_consecutive_yellow_to_red and previous_alert_stage in {"yellow", "red"}:
            return "red", change_pct, quality_flags + ["consecutive_alert"]
        return "yellow", change_pct, quality_flags
    return "none", change_pct, ["below_alert_threshold"]


def _latest_status(results: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in results:
        key = (str(row.get("standort")), str(row.get("bundesland")), str(row.get("virus_typ")))
        current = latest.get(key)
        if current is None or str(row.get("datum")) > str(current.get("datum")):
            latest[key] = row
    return sorted(latest.values(), key=lambda item: (item.get("bundesland") or "", item.get("standort") or "", item.get("virus_typ") or ""))


def _sort_alerts(alerts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(alert) for alert in alerts],
        key=lambda item: (
            str(item.get("datum") or ""),
            STAGE_RANK.get(str(item.get("stage") or "none"), 0),
            float(item.get("change_pct") or 0.0),
            str(item.get("standort") or ""),
            str(item.get("virus_typ") or ""),
        ),
        reverse=True,
    )


def _build_region_payloads(active_alerts: Iterable[dict[str, Any]], *, config: SiteEarlyWarningConfig) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for alert in active_alerts:
        code = str(alert.get("bundesland") or "").strip().upper()
        if code:
            grouped[code].append(dict(alert))

    regions: dict[str, dict[str, Any]] = {}
    for code, alerts in grouped.items():
        sorted_alerts = _sort_alerts(alerts)
        regions[code] = {
            "mode": MODE,
            "can_change_budget": False,
            "method": METHOD,
            "active_alert_count": len(sorted_alerts),
            "active_red_alert_count": sum(1 for alert in sorted_alerts if alert.get("stage") == "red"),
            "active_yellow_alert_count": sum(1 for alert in sorted_alerts if alert.get("stage") == "yellow"),
            "top_alerts": sorted_alerts[: config.max_region_alerts],
        }
    return regions


def _extract_value(row: Any, config: SiteEarlyWarningConfig) -> tuple[str, float | None]:
    for metric in (config.metric, config.fallback_metric):
        value = _safe_float(_get(row, metric))
        if value is not None:
            return metric, value
    return config.metric, None


def _get(row: Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _safe_float(value: Any) -> float | None:
    if value in {None, "", "NA", "na"}:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def _safe_int(value: Any) -> int | None:
    number = _safe_float(value)
    if number is None:
        return None
    return int(number)


def _safe_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"ja", "true", "1", "yes"}:
        return True
    if text in {"nein", "false", "0", "no"}:
        return False
    return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value[:10]).date()
        except ValueError:
            return None
    return None


def _round_float(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)
