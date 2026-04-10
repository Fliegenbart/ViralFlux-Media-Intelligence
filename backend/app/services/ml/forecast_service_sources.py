from __future__ import annotations

from typing import Any


def region_variants(
    region: str,
    *,
    normalize_forecast_region_fn: Any,
    default_forecast_region: str,
    bundesland_names: dict[str, str],
) -> list[str]:
    region_code = normalize_forecast_region_fn(region)
    if region_code == default_forecast_region:
        return [default_forecast_region]

    variants = [region_code]
    state_name = bundesland_names.get(region_code)
    if state_name:
        variants.append(state_name)
    return variants


def survstat_region_values(
    region: str,
    *,
    region_variants_fn: Any,
    normalize_forecast_region_fn: Any,
    default_forecast_region: str,
) -> list[str]:
    region_code = normalize_forecast_region_fn(region)
    if region_code == default_forecast_region:
        return ["Gesamt", default_forecast_region]
    values = region_variants_fn(region_code)
    if "Gesamt" not in values:
        values.append("Gesamt")
    return values


def load_wastewater_training_frame(
    service: Any,
    *,
    virus_typ: str,
    start_date: Any,
    region: str,
    normalize_forecast_region_fn: Any,
    default_forecast_region: str,
    region_variants_fn: Any,
    wastewater_aggregated_model: Any,
    wastewater_data_model: Any,
    func_module: Any,
    pd_module: Any,
) -> Any:
    region_code = normalize_forecast_region_fn(region)
    if region_code == default_forecast_region:
        wastewater = (
            service.db.query(wastewater_aggregated_model)
            .filter(
                wastewater_aggregated_model.virus_typ == virus_typ,
                wastewater_aggregated_model.datum >= start_date,
            )
            .order_by(wastewater_aggregated_model.datum.asc())
            .all()
        )
        return pd_module.DataFrame(
            [
                {
                    "ds": w.datum,
                    "y": w.viruslast,
                    "viruslast_normalized": w.viruslast_normalisiert,
                    "amelag_pred": w.vorhersage,
                }
                for w in wastewater
            ]
        )

    wastewater = (
        service.db.query(
            wastewater_data_model.datum.label("ds"),
            func_module.avg(wastewater_data_model.viruslast).label("y"),
            func_module.avg(wastewater_data_model.viruslast_normalisiert).label("viruslast_normalized"),
            func_module.avg(wastewater_data_model.vorhersage).label("amelag_pred"),
        )
        .filter(
            wastewater_data_model.virus_typ == virus_typ,
            wastewater_data_model.datum >= start_date,
            wastewater_data_model.bundesland.in_(region_variants_fn(region_code)),
        )
        .group_by(wastewater_data_model.datum)
        .order_by(wastewater_data_model.datum.asc())
        .all()
    )
    return pd_module.DataFrame(
        [
            {
                "ds": row.ds,
                "y": float(row.y or 0.0),
                "viruslast_normalized": float(row.viruslast_normalized or 0.0),
                "amelag_pred": float(row.amelag_pred or 0.0),
            }
            for row in wastewater
        ]
    )


def load_google_trends_rows(
    service: Any,
    *,
    keywords: list[str],
    start_date: Any,
    region: str,
    normalize_forecast_region_fn: Any,
    default_forecast_region: str,
    region_variants_fn: Any,
    google_trends_data_model: Any,
) -> list[Any]:
    region_code = normalize_forecast_region_fn(region)
    region_variants = region_variants_fn(region_code)

    if region_code != default_forecast_region:
        region_rows = (
            service.db.query(google_trends_data_model)
            .filter(
                google_trends_data_model.keyword.in_(keywords),
                google_trends_data_model.datum >= start_date,
                google_trends_data_model.region.in_(region_variants),
            )
            .all()
        )
        if region_rows:
            return region_rows

    return (
        service.db.query(google_trends_data_model)
        .filter(
            google_trends_data_model.keyword.in_(keywords),
            google_trends_data_model.datum >= start_date,
            google_trends_data_model.region == default_forecast_region,
        )
        .all()
    )


def is_holiday(
    service: Any,
    datum: Any,
    *,
    region: str,
    normalize_forecast_region_fn: Any,
    default_forecast_region: str,
    region_variants_fn: Any,
    school_holidays_model: Any,
) -> bool:
    query = service.db.query(school_holidays_model).filter(
        school_holidays_model.start_datum <= datum,
        school_holidays_model.end_datum >= datum,
    )
    region_code = normalize_forecast_region_fn(region)
    if region_code != default_forecast_region:
        query = query.filter(
            school_holidays_model.bundesland.in_(region_variants_fn(region_code)),
        )
    return query.first() is not None
