from __future__ import annotations

from typing import Any


def augment_with_internal_history(
    service,
    *,
    df,
    virus_typ: str,
    start_date,
    region: str,
):
    history_df = service._load_internal_history_frame(
        virus_typ=virus_typ,
        start_date=start_date,
        region=region,
    )
    features = service._build_internal_history_feature_frame(df["ds"], history_df)
    combined = service.pd.concat([df.reset_index(drop=True), features], axis=1) if hasattr(service, "pd") else None
    if combined is None:
        import pandas as pd

        combined = pd.concat([df.reset_index(drop=True), features], axis=1)
    combined["lab_positivity_lag7"] = combined["lab_positivity_rate"].shift(7)
    return combined


def load_internal_history_frame(
    service,
    *,
    virus_typ: str,
    start_date,
    region: str,
    internal_history_test_map,
    ganzimmun_model,
    normalize_forecast_region_fn,
    default_forecast_region,
    func_module,
    timedelta_cls,
    pd_module,
):
    aliases = internal_history_test_map.get(virus_typ, [])
    if not aliases:
        return pd_module.DataFrame()

    query = (
        service.db.query(ganzimmun_model)
        .filter(
            ganzimmun_model.datum >= start_date - timedelta_cls(days=365 * 5),
            ganzimmun_model.anzahl_tests.isnot(None),
            ganzimmun_model.anzahl_tests > 0,
            func_module.lower(ganzimmun_model.test_typ).in_(aliases),
        )
    )
    region_code = normalize_forecast_region_fn(region)
    if region_code != default_forecast_region:
        query = query.filter(
            ganzimmun_model.region.in_(service._region_variants(region_code)),
        )
    rows = query.order_by(ganzimmun_model.datum.asc()).all()
    if not rows:
        return pd_module.DataFrame()

    return pd_module.DataFrame(
        [
            {
                "datum": pd_module.to_datetime(row.datum),
                "available_time": pd_module.to_datetime(row.available_time)
                if row.available_time
                else pd_module.NaT,
                "anzahl_tests": int(row.anzahl_tests or 0),
                "positive_ergebnisse": int(row.positive_ergebnisse or 0),
            }
            for row in rows
        ]
    )


def build_internal_history_feature_frame(
    ds_index,
    history_df,
    *,
    pd_module,
    timedelta_cls,
):
    columns = [
        "lab_positivity_rate",
        "lab_signal_available",
        "lab_baseline_mean",
        "lab_baseline_zscore",
    ]
    if history_df.empty:
        return pd_module.DataFrame(0.0, index=range(len(ds_index)), columns=columns)

    history = history_df.copy()
    history["datum"] = pd_module.to_datetime(history["datum"])
    history["available_time"] = pd_module.to_datetime(history["available_time"])
    history["effective_available"] = history["available_time"].fillna(history["datum"])
    history["anzahl_tests"] = pd_module.to_numeric(
        history["anzahl_tests"], errors="coerce"
    ).fillna(0).clip(lower=0)
    history["positive_ergebnisse"] = pd_module.to_numeric(
        history["positive_ergebnisse"], errors="coerce"
    ).fillna(0).clip(lower=0)
    history = history.loc[history["anzahl_tests"] > 0].copy()
    if history.empty:
        return pd_module.DataFrame(0.0, index=range(len(ds_index)), columns=columns)

    history["rate"] = history["positive_ergebnisse"] / history["anzahl_tests"]
    iso = history["datum"].dt.isocalendar()
    history["iso_week"] = iso.week.astype(int)
    history["iso_year"] = iso.year.astype(int)

    rows: list[dict[str, float]] = []
    for ds in pd_module.to_datetime(ds_index):
        visible = history.loc[(history["datum"] <= ds) & (history["effective_available"] <= ds)]
        if visible.empty:
            rows.append({name: 0.0 for name in columns})
            continue

        recent = visible.loc[visible["datum"] > ds - timedelta_cls(days=14)]
        total_tests = float(recent["anzahl_tests"].sum())
        positivity = (
            float(recent["positive_ergebnisse"].sum() / total_tests) if total_tests > 0 else 0.0
        )

        ds_iso = ds.isocalendar()
        baseline_pool = visible.loc[
            (visible["iso_week"] == int(ds_iso.week))
            & (visible["iso_year"] < int(ds_iso.year))
        ]
        if len(baseline_pool) >= 2:
            baseline_mean = float(baseline_pool["rate"].mean())
            baseline_std = float(baseline_pool["rate"].std()) or 0.01
            z_score = (positivity - baseline_mean) / baseline_std
        else:
            baseline_mean = 0.0
            z_score = 0.0

        rows.append(
            {
                "lab_positivity_rate": positivity,
                "lab_signal_available": 1.0 if total_tests > 0 else 0.0,
                "lab_baseline_mean": baseline_mean,
                "lab_baseline_zscore": float(z_score),
            }
        )

    return pd_module.DataFrame(rows, columns=columns)
