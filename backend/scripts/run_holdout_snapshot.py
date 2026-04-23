#!/usr/bin/env python3
"""Read-only peak-week holdout snapshot for regional forecasts.

The script compares persisted regional forecasts in ``ml_forecasts`` against
observed weekly SURVSTAT incidence in ``survstat_weekly_data``. It is designed
as an investor/audit artifact: no model training, no writes, no side effects.
By default, it only evaluates forecasts issued strictly before
``target_week_start - horizon_days`` so the report is a genuine holdout and not
a mid-week peek. Use ``--allow-midweek-forecasts`` only for intentional
diagnostic comparisons against the old, non-holdout behavior.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text


BACKEND_ROOT = Path(__file__).resolve().parents[1]


DEFAULT_VIRUS_DISEASE_MAP = {
    "Influenza A": "Influenza, saisonal",
    "Influenza B": "Influenza, saisonal",
    "RSV A": "RSV (Meldepflicht gemäß IfSG)",
    "SARS-CoV-2": "COVID-19",
}

DEFAULT_EXCLUDED_REGIONS = {"Gesamt", "Bundesweit", "DE", ""}

REGION_ALIASES = {
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
class WeekMetrics:
    week_start: str
    actual_regions: int
    forecast_regions: int
    overlap_regions: int
    precision_at_3: float | None
    mape: float | None
    correlation: float | None
    actual_top3: list[str]
    forecast_top3: list[str]
    notes: list[str]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only holdout snapshot for persisted ViralFlux regional "
            "forecasts against SURVSTAT peak weeks."
        )
    )
    parser.add_argument("--virus", default="Influenza A")
    parser.add_argument("--disease", default=None)
    parser.add_argument("--horizon-days", type=int, default=7)
    parser.add_argument("--peak-weeks", type=int, default=8)
    parser.add_argument(
        "--min-regions",
        type=int,
        default=8,
        help="Minimum overlapping regions needed before week metrics are trusted.",
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
    parser.add_argument(
        "--allow-midweek-forecasts",
        action="store_true",
        help=(
            "Use forecasts persisted during the target week too. Default is a "
            "strict holdout cutoff before week_start - horizon_days."
        ),
    )
    return parser.parse_args()


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


def _safe_mean(values: list[float]) -> float | None:
    clean = [v for v in values if not math.isnan(v) and not math.isinf(v)]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    dx = [x - mean_x for x in xs]
    dy = [y - mean_y for y in ys]
    denom_x = math.sqrt(sum(x * x for x in dx))
    denom_y = math.sqrt(sum(y * y for y in dy))
    denom = denom_x * denom_y
    if denom == 0:
        return None
    return sum(x * y for x, y in zip(dx, dy)) / denom


def _round_or_none(value: float | None, ndigits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, ndigits)


def _normalise_region(region: Any) -> str:
    value = str(region or "").strip()
    return REGION_ALIASES.get(value, value)


def _fetch_peak_weeks(db, disease: str, limit: int) -> list[date]:
    aggregate_rows = db.execute(
        text(
            """
            select week_start::date as week_start, max(incidence) as incidence
            from survstat_weekly_data
            where disease = :disease
              and bundesland in ('Gesamt', 'Bundesweit', 'DE')
              and incidence is not null
            group by week_start::date
            order by incidence desc nulls last, week_start desc
            limit :limit
            """
        ),
        {"disease": disease, "limit": limit},
    ).mappings().all()

    if aggregate_rows:
        return [row["week_start"] for row in aggregate_rows]

    regional_rows = db.execute(
        text(
            """
            select week_start::date as week_start, avg(incidence) as incidence
            from survstat_weekly_data
            where disease = :disease
              and coalesce(bundesland, '') not in ('Gesamt', 'Bundesweit', 'DE', '')
              and incidence is not null
            group by week_start::date
            order by incidence desc nulls last, week_start desc
            limit :limit
            """
        ),
        {"disease": disease, "limit": limit},
    ).mappings().all()
    return [row["week_start"] for row in regional_rows]


def _fetch_actuals(db, disease: str, week_start: date) -> dict[str, float]:
    rows = db.execute(
        text(
            """
            select bundesland as region, max(incidence) as actual_value
            from survstat_weekly_data
            where disease = :disease
              and week_start::date = :week_start
              and coalesce(bundesland, '') not in ('Gesamt', 'Bundesweit', 'DE', '')
              and incidence is not null
            group by bundesland
            """
        ),
        {"disease": disease, "week_start": week_start},
    ).mappings().all()
    return {
        _normalise_region(row["region"]): float(row["actual_value"])
        for row in rows
        if _normalise_region(row["region"]) not in DEFAULT_EXCLUDED_REGIONS
        and _as_float(row["actual_value"]) is not None
    }


def _fetch_forecasts(
    db,
    *,
    virus: str,
    horizon_days: int,
    week_start: date,
    allow_midweek_forecasts: bool = False,
) -> dict[str, float]:
    holdout_cutoff_clause = (
        ""
        if allow_midweek_forecasts
        else "and created_at::date < (:week_start::date - (:horizon_days || ' days')::interval)"
    )
    rows = db.execute(
        text(
            f"""
            with ranked as (
                select
                    region,
                    predicted_value,
                    created_at,
                    row_number() over (
                        partition by region
                        order by created_at desc, id desc
                    ) as rn
                from ml_forecasts
                where virus_typ = :virus
                  and horizon_days = :horizon_days
                  and forecast_date::date >= :week_start
                  and forecast_date::date < (:week_start::date + interval '7 days')
                  {holdout_cutoff_clause}
                  and coalesce(region, '') not in ('Gesamt', 'Bundesweit', 'DE', '')
                  and predicted_value is not null
            )
            select region, predicted_value
            from ranked
            where rn = 1
            """
        ),
        {
            "virus": virus,
            "horizon_days": horizon_days,
            "week_start": week_start,
        },
    ).mappings().all()
    return {
        _normalise_region(row["region"]): float(row["predicted_value"])
        for row in rows
        if _normalise_region(row["region"]) not in DEFAULT_EXCLUDED_REGIONS
        and _as_float(row["predicted_value"]) is not None
    }


def _precision_at_k(
    actuals: dict[str, float],
    forecasts: dict[str, float],
    *,
    k: int = 3,
) -> tuple[float | None, list[str], list[str]]:
    if not actuals or not forecasts:
        return None, [], []
    actual_top = [
        region
        for region, _ in sorted(
            actuals.items(), key=lambda item: item[1], reverse=True
        )[:k]
    ]
    forecast_top = [
        region
        for region, _ in sorted(
            forecasts.items(), key=lambda item: item[1], reverse=True
        )[:k]
    ]
    if not actual_top or not forecast_top:
        return None, actual_top, forecast_top
    denom = min(k, len(actual_top))
    return len(set(actual_top).intersection(forecast_top)) / denom, actual_top, forecast_top


def _evaluate_week(
    db,
    *,
    disease: str,
    virus: str,
    horizon_days: int,
    week_start: date,
    min_regions: int,
    allow_midweek_forecasts: bool,
) -> WeekMetrics:
    actuals = _fetch_actuals(db, disease, week_start)
    forecasts = _fetch_forecasts(
        db,
        virus=virus,
        horizon_days=horizon_days,
        week_start=week_start,
        allow_midweek_forecasts=allow_midweek_forecasts,
    )
    overlap = sorted(set(actuals).intersection(forecasts))
    notes: list[str] = []

    if not forecasts:
        notes.append("no regional forecasts found for this target week")
    if len(overlap) < min_regions:
        notes.append(
            f"low region overlap: {len(overlap)} matched, minimum {min_regions}"
        )

    p_at_3, actual_top3, forecast_top3 = _precision_at_k(actuals, forecasts)

    mape_values: list[float] = []
    actual_vector: list[float] = []
    forecast_vector: list[float] = []
    for region in overlap:
        actual = actuals[region]
        predicted = forecasts[region]
        actual_vector.append(actual)
        forecast_vector.append(predicted)
        denom = max(abs(actual), 1e-6)
        mape_values.append(abs(predicted - actual) / denom)

    return WeekMetrics(
        week_start=week_start.isoformat(),
        actual_regions=len(actuals),
        forecast_regions=len(forecasts),
        overlap_regions=len(overlap),
        precision_at_3=_round_or_none(p_at_3),
        mape=_round_or_none(_safe_mean(mape_values)),
        correlation=_round_or_none(_pearson(actual_vector, forecast_vector)),
        actual_top3=actual_top3,
        forecast_top3=forecast_top3,
        notes=notes,
    )


def _aggregate_report(args: argparse.Namespace) -> dict[str, Any]:
    disease = args.disease or DEFAULT_VIRUS_DISEASE_MAP.get(args.virus, args.virus)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    session_local = _session_factory()

    with session_local() as db:
        _validate_disease_exists(db, disease)
        peak_weeks = _fetch_peak_weeks(db, disease, args.peak_weeks)
        week_metrics = [
            _evaluate_week(
                db,
                disease=disease,
                virus=args.virus,
                horizon_days=args.horizon_days,
                week_start=week_start,
                min_regions=args.min_regions,
                allow_midweek_forecasts=args.allow_midweek_forecasts,
            )
            for week_start in peak_weeks
        ]

    trusted_weeks = [w for w in week_metrics if w.overlap_regions >= args.min_regions]
    report = {
        "generated_at": generated_at,
        "mode": "read_only_holdout_snapshot",
        "scope": {
            "virus": args.virus,
            "survstat_disease": disease,
            "horizon_days": args.horizon_days,
            "peak_weeks_requested": args.peak_weeks,
            "peak_weeks_found": len(peak_weeks),
            "min_regions": args.min_regions,
            "allow_midweek_forecasts": args.allow_midweek_forecasts,
        },
        "summary": {
            "weeks_evaluated": len(week_metrics),
            "trusted_weeks": len(trusted_weeks),
            "mean_precision_at_3": _round_or_none(
                _safe_mean(
                    [
                        w.precision_at_3
                        for w in trusted_weeks
                        if w.precision_at_3 is not None
                    ]
                )
            ),
            "mean_mape": _round_or_none(
                _safe_mean([w.mape for w in trusted_weeks if w.mape is not None])
            ),
            "mean_correlation": _round_or_none(
                _safe_mean(
                    [w.correlation for w in trusted_weeks if w.correlation is not None]
                )
            ),
            "blocking_warnings": sorted(
                {
                    note
                    for week in week_metrics
                    for note in week.notes
                    if note.startswith("no regional forecasts")
                    or note.startswith("low region overlap")
                }
            ),
        },
        "weeks": [asdict(week) for week in week_metrics],
    }
    return report


def _validate_disease_exists(db, disease: str) -> None:
    rows = db.execute(
        text(
            """
            select distinct disease
            from survstat_weekly_data
            where disease is not null
            order by disease
            """
        )
    ).mappings().all()
    known_diseases = {str(row["disease"]) for row in rows}
    if disease not in known_diseases:
        sample = ", ".join(sorted(known_diseases)[:10]) or "no diseases found"
        raise ValueError(
            f"SURVSTAT disease '{disease}' was not found in survstat_weekly_data. "
            f"Use --disease with one of the database values. Examples: {sample}"
        )


def _session_factory():
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from app.db.session import SessionLocal

    return SessionLocal


def _print_text(report: dict[str, Any]) -> None:
    scope = report["scope"]
    summary = report["summary"]
    print("ViralFlux peak-week holdout snapshot")
    print(f"Generated: {report['generated_at']}")
    print(
        "Scope: "
        f"virus={scope['virus']} | disease={scope['survstat_disease']} | "
        f"horizon={scope['horizon_days']}d | peak_weeks={scope['peak_weeks_found']}"
    )
    print("")
    print("Summary")
    print(f"  weeks_evaluated: {summary['weeks_evaluated']}")
    print(f"  trusted_weeks: {summary['trusted_weeks']}")
    print(f"  mean_precision_at_3: {summary['mean_precision_at_3']}")
    print(f"  mean_mape: {summary['mean_mape']}")
    print(f"  mean_correlation: {summary['mean_correlation']}")
    if summary["blocking_warnings"]:
        print(f"  blocking_warnings: {', '.join(summary['blocking_warnings'])}")
    print("")
    print("Weeks")
    for week in report["weeks"]:
        notes = "; ".join(week["notes"]) if week["notes"] else "ok"
        print(
            f"  {week['week_start']}: "
            f"p@3={week['precision_at_3']} "
            f"mape={week['mape']} "
            f"corr={week['correlation']} "
            f"overlap={week['overlap_regions']}/{week['actual_regions']} "
            f"notes={notes}"
        )
        print(
            f"    actual_top3={week['actual_top3']} "
            f"forecast_top3={week['forecast_top3']}"
        )


def main() -> int:
    args = _parse_args()
    try:
        report = _aggregate_report(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

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
