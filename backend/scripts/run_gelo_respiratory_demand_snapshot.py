#!/usr/bin/env python3
"""Build a GELO respiratory demand snapshot from regional h5 forecasts.

The customer-facing value is not a single virus. It is regional respiratory
symptom pressure for the next five days, expressed as one Bundesland ranking.
Virus details remain available as explanation and model-control signals.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_EXCLUDED_REGIONS = {"Gesamt", "Bundesweit", "DE", ""}

DEFAULT_COMPONENT_OUTLIER_MAX_VALUES = {
    "influenza": 1000.0,
    "rsv": 1000.0,
    "covid": 1000.0,
}

GO_QUALITY_GATES = {"GO", "GREEN", "PASS", "PASSED"}

REGION_ALIASES = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
    "DE-BW": "Baden-Württemberg",
    "DE-BY": "Bayern",
    "DE-BE": "Berlin",
    "DE-BB": "Brandenburg",
    "DE-HB": "Bremen",
    "DE-HH": "Hamburg",
    "DE-HE": "Hessen",
    "DE-MV": "Mecklenburg-Vorpommern",
    "DE-NI": "Niedersachsen",
    "DE-NW": "Nordrhein-Westfalen",
    "DE-RP": "Rheinland-Pfalz",
    "DE-SL": "Saarland",
    "DE-SN": "Sachsen",
    "DE-ST": "Sachsen-Anhalt",
    "DE-SH": "Schleswig-Holstein",
    "DE-TH": "Thüringen",
}


@dataclass(frozen=True)
class GeloComponent:
    key: str
    label: str
    viruses: tuple[str, ...]
    weight: float


@dataclass(frozen=True)
class ComponentMetrics:
    forecast_start_value: float
    forecast_end_value: float
    absolute_change: float
    relative_change_pct: float
    signal_value: float
    max_forecast_value: float


DEFAULT_COMPONENTS = (
    GeloComponent(
        key="influenza",
        label="Influenza gesamt",
        viruses=("Influenza A", "Influenza B"),
        weight=0.45,
    ),
    GeloComponent(
        key="rsv",
        label="RSV",
        viruses=("RSV A",),
        weight=0.35,
    ),
    GeloComponent(
        key="covid",
        label="SARS-CoV-2",
        viruses=("SARS-CoV-2",),
        weight=0.20,
    ),
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only GELO respiratory demand snapshot from persisted "
            "regional 5-day forecasts."
        )
    )
    parser.add_argument("--horizon-days", type=int, default=5)
    parser.add_argument(
        "--target-start",
        type=_parse_date,
        default=date.today(),
        help="First target date to include, default: today.",
    )
    parser.add_argument(
        "--target-days",
        type=int,
        default=5,
        help="Number of forecast target days included in the snapshot.",
    )
    parser.add_argument("--min-regions", type=int, default=8)
    parser.add_argument("--min-components", type=int, default=2)
    parser.add_argument("--max-age-hours", type=int, default=72)
    parser.add_argument(
        "--feature-as-of",
        type=_parse_date,
        default=None,
        help="Latest source-data date used by the forecast, if known.",
    )
    parser.add_argument(
        "--max-feature-age-days",
        type=int,
        default=7,
        help="Maximum source-data age before budget eligibility is blocked.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path for a JSON report. The database is still read-only.",
    )
    return parser.parse_args()


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected ISO date, e.g. 2026-01-20") from exc


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def _normalise_region(region: Any) -> str:
    value = str(region or "").strip()
    return REGION_ALIASES.get(value, value)


def _to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_date(value: date | datetime | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _to_utc(value).date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _normalise_quality_gate(value: Any) -> str:
    return str(value or "GO").strip().upper()


def _date_sort_key(value: Any, fallback_index: int) -> tuple[int, str]:
    parsed = _as_date(value)
    if parsed is not None:
        return 0, parsed.isoformat()
    return 1, f"{fallback_index:06d}"


def _round(value: float, ndigits: int = 4) -> float:
    return round(value, ndigits)


def _normalise_forecast_curve(raw_value: Any) -> list[tuple[str | None, float]]:
    scalar_value = _as_float(raw_value)
    if scalar_value is not None:
        return [(None, scalar_value)]

    points: list[tuple[Any, float, int]] = []
    if isinstance(raw_value, dict):
        point_value = _as_float(
            raw_value.get("predicted_value", raw_value.get("value"))
        )
        if point_value is not None:
            return [
                (
                    raw_value.get("forecast_date", raw_value.get("date")),
                    point_value,
                )
            ]
        iterable = raw_value.items()
    elif isinstance(raw_value, (list, tuple)):
        iterable = enumerate(raw_value)
    else:
        return []

    for index, item in iterable:
        label: Any = index
        value: Any = item
        if isinstance(item, dict):
            label = item.get("forecast_date", item.get("date", index))
            value = item.get("predicted_value", item.get("value"))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            label = item[0]
            value = item[1]
        parsed_value = _as_float(value)
        if parsed_value is not None:
            points.append((label, parsed_value, len(points)))

    points.sort(key=lambda point: _date_sort_key(point[0], point[2]))
    return [
        (str(label) if label is not None else None, value)
        for label, value, _ in points
    ]


def _uses_forecast_curves(forecasts_by_virus: dict[str, dict[str, Any]]) -> bool:
    return any(
        len(_normalise_forecast_curve(raw_value)) > 1
        for forecasts_by_region in forecasts_by_virus.values()
        for raw_value in forecasts_by_region.values()
    )


def _component_metrics(
    forecasts_by_virus: dict[str, dict[str, Any]],
    component: GeloComponent,
    *,
    score_mode: str,
) -> dict[str, ComponentMetrics]:
    values: dict[str, dict[str, float]] = {}
    for virus in component.viruses:
        for raw_region, raw_value in forecasts_by_virus.get(virus, {}).items():
            region = _normalise_region(raw_region)
            if region in DEFAULT_EXCLUDED_REGIONS:
                continue
            curve = _normalise_forecast_curve(raw_value)
            if not curve:
                continue
            point_values = [max(value, 0.0) for _, value in curve]
            region_values = values.setdefault(
                region,
                {
                    "forecast_start_value": 0.0,
                    "forecast_end_value": 0.0,
                    "max_forecast_value": 0.0,
                },
            )
            region_values["forecast_start_value"] += point_values[0]
            region_values["forecast_end_value"] += point_values[-1]
            region_values["max_forecast_value"] += max(point_values)

    metrics: dict[str, ComponentMetrics] = {}
    for region, region_values in values.items():
        start_value = region_values["forecast_start_value"]
        end_value = region_values["forecast_end_value"]
        absolute_change = end_value - start_value
        relative_change_pct = absolute_change / max(abs(start_value), 1.0) * 100
        signal_value = (
            max(absolute_change, 0.0)
            if score_mode == "forecast_curve_rise"
            else end_value
        )
        metrics[region] = ComponentMetrics(
            forecast_start_value=start_value,
            forecast_end_value=end_value,
            absolute_change=absolute_change,
            relative_change_pct=relative_change_pct,
            signal_value=signal_value,
            max_forecast_value=region_values["max_forecast_value"],
        )
    return metrics


def _rank_scores(values: dict[str, float]) -> dict[str, float]:
    clean = {
        region: value
        for region, value in values.items()
        if not math.isnan(value) and not math.isinf(value)
    }
    if not clean:
        return {}

    unique_values = sorted(set(clean.values()))
    if len(unique_values) == 1:
        return {region: 0.5 for region in clean}

    max_rank = len(unique_values) - 1
    value_to_rank = {
        value: index / max_rank for index, value in enumerate(unique_values)
    }
    return {region: value_to_rank[value] for region, value in clean.items()}


def build_gelo_respiratory_demand_snapshot(
    forecasts_by_virus: dict[str, dict[str, Any]],
    *,
    generated_at: datetime | None = None,
    latest_created_at: datetime | None = None,
    feature_as_of: date | datetime | str | None = None,
    horizon_days: int = 5,
    target_start: date | None = None,
    target_days: int = 5,
    max_age_hours: int = 72,
    max_feature_age_days: int = 7,
    min_regions: int = 8,
    min_components: int = 2,
    component_quality_gates: dict[str, str] | None = None,
    component_outlier_max_values: dict[str, float] | None = None,
    components: tuple[GeloComponent, ...] = DEFAULT_COMPONENTS,
) -> dict[str, Any]:
    generated_at = _to_utc(generated_at or datetime.now(timezone.utc))
    latest_created_at = _to_utc(latest_created_at)
    feature_as_of_date = _as_date(feature_as_of)
    target_start = target_start or date.today()
    component_quality_gates = component_quality_gates or {}
    outlier_max_values = {
        **DEFAULT_COMPONENT_OUTLIER_MAX_VALUES,
        **(component_outlier_max_values or {}),
    }
    score_mode = (
        "forecast_curve_rise"
        if _uses_forecast_curves(forecasts_by_virus)
        else "forecast_level"
    )

    metrics_by_component = {
        component.key: _component_metrics(
            forecasts_by_virus,
            component,
            score_mode=score_mode,
        )
        for component in components
    }
    signal_by_component = {
        component.key: {
            region: metrics.signal_value
            for region, metrics in metrics_by_component[component.key].items()
        }
        for component in components
    }
    scores_by_component = {
        component.key: _rank_scores(signal_by_component[component.key])
        for component in components
    }

    available_components = [
        component for component in components if scores_by_component[component.key]
    ]
    regions = sorted(
        {
            region
            for scores in scores_by_component.values()
            for region in scores
        }
    )

    data_fresh = (
        latest_created_at is not None
        and generated_at - latest_created_at <= timedelta(hours=max_age_hours)
    )
    feature_age_days = (
        (generated_at.date() - feature_as_of_date).days
        if feature_as_of_date is not None
        else None
    )
    feature_fresh = (
        feature_age_days is None
        or (0 <= feature_age_days <= max_feature_age_days)
    )
    component_gate_by_key = {
        component.key: _normalise_quality_gate(
            component_quality_gates.get(component.key, "GO")
        )
        for component in components
    }
    component_quality = all(
        component_gate_by_key[component.key] in GO_QUALITY_GATES
        for component in available_components
    )
    regional_forecast_ensemble = (
        len(regions) >= min_regions and len(available_components) >= min_components
    )
    global_budget_eligible = (
        data_fresh
        and feature_fresh
        and component_quality
        and regional_forecast_ensemble
    )
    blocked_reasons_by_region: dict[str, set[str]] = {}
    for component in components:
        max_allowed = outlier_max_values.get(component.key)
        if max_allowed is None:
            continue
        for region, metrics in metrics_by_component[component.key].items():
            if abs(metrics.max_forecast_value) > max_allowed:
                blocked_reasons_by_region.setdefault(region, set()).add("outlier")

    rows: list[dict[str, Any]] = []
    for region in regions:
        weighted_score = 0.0
        weight_sum = 0.0
        contributions: dict[str, dict[str, Any]] = {}

        for component in components:
            component_score = scores_by_component[component.key].get(region)
            metrics = metrics_by_component[component.key].get(region)
            if component_score is None or metrics is None:
                continue

            weighted_score += component_score * component.weight
            weight_sum += component.weight
            contributions[component.key] = {
                "label": component.label,
                "raw_forecast_value": _round(metrics.forecast_end_value),
                "forecast_start_value": _round(metrics.forecast_start_value),
                "forecast_end_value": _round(metrics.forecast_end_value),
                "absolute_change": _round(metrics.absolute_change),
                "relative_change_pct": _round(metrics.relative_change_pct),
                "signal_value": _round(metrics.signal_value),
                "rank_score": _round(component_score),
                "weight": component.weight,
                "quality_gate": component_gate_by_key[component.key],
                "weighted_score": _round(component_score * component.weight),
            }

        if weight_sum == 0:
            continue

        demand_score = weighted_score / weight_sum
        components_present = len(contributions)
        blocked_reasons = sorted(blocked_reasons_by_region.get(region, set()))
        rows.append(
            {
                "region": region,
                "demand_score": _round(demand_score),
                "demand_index": _round(demand_score * 100, 2),
                "rank": 0,
                "budget_eligible": (
                    global_budget_eligible and components_present >= min_components
                    and not blocked_reasons
                ),
                "blocked_reasons": blocked_reasons,
                "components_present": components_present,
                "component_contributions": contributions,
            }
        )

    rows.sort(key=lambda row: (-row["demand_score"], row["region"]))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index

    missing_components = [
        component.label
        for component in components
        if not scores_by_component[component.key]
    ]
    notes = []
    if missing_components:
        notes.append(
            "missing component forecasts: " + ", ".join(sorted(missing_components))
        )
    if not data_fresh:
        notes.append("data freshness gate is red")
    if not feature_fresh:
        notes.append("feature freshness gate is red")
    if not component_quality:
        notes.append("component quality gate is red")
    if not regional_forecast_ensemble:
        notes.append("regional forecast ensemble gate is red")
    outlier_regions = sorted(blocked_reasons_by_region)
    if outlier_regions:
        notes.append("outlier regions: " + ", ".join(outlier_regions))

    return {
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "mode": "gelo_respiratory_demand",
        "scope": {
            "horizon_days": horizon_days,
            "target_start": target_start.isoformat(),
            "target_days": target_days,
            "score_mode": score_mode,
            "min_regions": min_regions,
            "min_components": min_components,
            "max_age_hours": max_age_hours,
            "max_feature_age_days": max_feature_age_days,
            "included_viruses": sorted(
                {virus for component in components for virus in component.viruses}
            ),
        },
        "quality_gate": {
            "budget_eligible": global_budget_eligible,
            "data_fresh": data_fresh,
            "feature_fresh": feature_fresh,
            "feature_as_of": feature_as_of_date.isoformat()
            if feature_as_of_date is not None
            else None,
            "feature_age_days": feature_age_days,
            "component_quality": component_quality,
            "latest_forecast_created_at": (
                latest_created_at.isoformat().replace("+00:00", "Z")
                if latest_created_at
                else None
            ),
            "gate_paths": {
                "regional_forecast_ensemble": regional_forecast_ensemble,
            },
            "notes": notes,
        },
        "component_weights": {
            component.key: {
                "label": component.label,
                "viruses": list(component.viruses),
                "weight": component.weight,
                "quality_gate": component_gate_by_key[component.key],
                "outlier_max_value": outlier_max_values.get(component.key),
            }
            for component in components
        },
        "rankings": rows,
    }


def _fetch_h5_forecasts(
    db,
    *,
    horizon_days: int,
    target_start: date,
    target_days: int,
    components: tuple[GeloComponent, ...] = DEFAULT_COMPONENTS,
) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], datetime | None]:
    virus_types = sorted(
        {virus for component in components for virus in component.viruses}
    )
    placeholders = ", ".join(
        f":virus_{index}" for index, _ in enumerate(virus_types)
    )
    params: dict[str, Any] = {
        "horizon_days": horizon_days,
        "target_start": target_start,
        "target_days": target_days,
    }
    params.update(
        {f"virus_{index}": virus for index, virus in enumerate(virus_types)}
    )

    rows = db.execute(
        text(
            f"""
            with ranked as (
                select
                    virus_typ,
                    region,
                    forecast_date::date as forecast_date,
                    predicted_value,
                    created_at,
                    row_number() over (
                        partition by virus_typ, region, forecast_date::date
                        order by created_at desc, id desc
                    ) as rn
                from ml_forecasts
                where virus_typ in ({placeholders})
                  and horizon_days = :horizon_days
                  and forecast_date::date >= cast(:target_start as date)
                  and forecast_date::date < (
                      cast(:target_start as date) + (:target_days * interval '1 day')
                  )
                  and coalesce(region, '') not in ('Gesamt', 'Bundesweit', 'DE', '')
                  and predicted_value is not null
            )
            select virus_typ, region, forecast_date, predicted_value, created_at
            from ranked
            where rn = 1
            order by virus_typ, region, forecast_date
            """
        ),
        params,
    ).mappings().all()

    forecasts_by_virus: dict[str, dict[str, list[dict[str, Any]]]] = {}
    latest_created_at: datetime | None = None
    for row in rows:
        value = _as_float(row["predicted_value"])
        if value is None:
            continue
        virus = str(row["virus_typ"])
        region = _normalise_region(row["region"])
        if region in DEFAULT_EXCLUDED_REGIONS:
            continue
        forecast_date = _as_date(row["forecast_date"])
        forecasts_by_virus.setdefault(virus, {}).setdefault(region, []).append(
            {
                "forecast_date": forecast_date.isoformat()
                if forecast_date is not None
                else str(row["forecast_date"]),
                "predicted_value": value,
            }
        )
        created_at = _to_utc(row["created_at"])
        if created_at is not None and (
            latest_created_at is None or created_at > latest_created_at
        ):
            latest_created_at = created_at

    for forecasts_by_region in forecasts_by_virus.values():
        for region, curve in forecasts_by_region.items():
            forecasts_by_region[region] = sorted(
                curve,
                key=lambda point: _date_sort_key(point["forecast_date"], 0),
            )

    return forecasts_by_virus, latest_created_at


def _session_factory():
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from app.db.session import SessionLocal

    return SessionLocal


def _aggregate_report(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0)
    session_local = _session_factory()

    with session_local() as db:
        forecasts_by_virus, latest_created_at = _fetch_h5_forecasts(
            db,
            horizon_days=args.horizon_days,
            target_start=args.target_start,
            target_days=args.target_days,
        )

    return build_gelo_respiratory_demand_snapshot(
        forecasts_by_virus,
        generated_at=generated_at,
        latest_created_at=latest_created_at,
        horizon_days=args.horizon_days,
        target_start=args.target_start,
        target_days=args.target_days,
        max_age_hours=args.max_age_hours,
        feature_as_of=args.feature_as_of,
        max_feature_age_days=args.max_feature_age_days,
        min_regions=args.min_regions,
        min_components=args.min_components,
    )


def _print_text(report: dict[str, Any]) -> None:
    scope = report["scope"]
    gate = report["quality_gate"]
    print("GELO Respiratory Demand Index")
    print(f"Generated: {report['generated_at']}")
    print(
        "Scope: "
        f"horizon={scope['horizon_days']}d | "
        f"target={scope['target_start']} +{scope['target_days']}d"
    )
    print("")
    print("Quality gate")
    print(f"  budget_eligible: {gate['budget_eligible']}")
    print(f"  data_fresh: {gate['data_fresh']}")
    print(
        "  regional_forecast_ensemble: "
        f"{gate['gate_paths']['regional_forecast_ensemble']}"
    )
    if gate["notes"]:
        print(f"  notes: {'; '.join(gate['notes'])}")
    print("")
    print("Bundesland ranking")
    for row in report["rankings"]:
        drivers = ", ".join(
            f"{value['label']}={value['rank_score']}"
            for value in row["component_contributions"].values()
        )
        print(
            f"  {row['rank']:>2}. {row['region']}: "
            f"index={row['demand_index']} "
            f"budget_eligible={row['budget_eligible']} "
            f"drivers=({drivers})"
        )


def main() -> int:
    args = _parse_args()
    report = _aggregate_report(args)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
