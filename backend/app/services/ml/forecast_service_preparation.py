from __future__ import annotations

from typing import Any


def prepare_training_data(
    service: Any,
    *,
    virus_typ: str,
    lookback_days: int,
    include_internal_history: bool,
    region: str,
    normalize_forecast_region_fn: Any,
    default_forecast_region: str,
    cross_disease_map: dict[str, list[str]],
    survstat_virus_map: dict[str, list[str]],
    wastewater_aggregated_model: Any,
    survstat_weekly_data_model: Any,
    func_module: Any,
    pd_module: Any,
    np_module: Any,
    datetime_cls: Any,
    timedelta_cls: Any,
    logger: Any,
) -> Any:
    region_code = normalize_forecast_region_fn(region)
    logger.info(f"Preparing training data for {virus_typ}/{region_code}")
    start_date = datetime_cls.now() - timedelta_cls(days=lookback_days)

    df = service._load_wastewater_training_frame(
        virus_typ=virus_typ,
        start_date=start_date,
        region=region_code,
    )
    if df.empty:
        logger.warning(f"No wastewater data found for {virus_typ}")
        return pd_module.DataFrame()

    df = df.sort_values("ds").reset_index(drop=True)
    df["ds"] = pd_module.to_datetime(df["ds"])

    trends_keywords = ["Grippe", "Erkältung", "Fieber"]
    trends = service._load_google_trends_rows(
        keywords=trends_keywords,
        start_date=start_date,
        region=region_code,
    )

    if trends:
        trends_df = pd_module.DataFrame(
            [{"ds": pd_module.to_datetime(t.datum), "interest_score": t.interest_score} for t in trends]
        )
        trends_avg = trends_df.groupby("ds")["interest_score"].mean().reset_index()
        trends_avg.columns = ["ds", "trends_score"]
        df = df.merge(trends_avg, on="ds", how="left")
    else:
        df["trends_score"] = 0.0

    df["schulferien"] = df["ds"].apply(
        lambda d: 1.0 if service._is_holiday(d, region=region_code) else 0.0
    )

    if include_internal_history:
        df = service._augment_with_internal_history(
            df=df,
            virus_typ=virus_typ,
            start_date=start_date,
            region=region_code,
        )
    else:
        df["lab_positivity_rate"] = 0.0
        df["lab_signal_available"] = 0.0
        df["lab_baseline_mean"] = 0.0
        df["lab_baseline_zscore"] = 0.0
        df["lab_positivity_lag7"] = 0.0

    df["lag1"] = df["y"].shift(1)
    df["lag2"] = df["y"].shift(2)
    df["lag3"] = df["y"].shift(3)
    df["ma3"] = df["y"].rolling(window=3, min_periods=1).mean().shift(1)
    df["ma5"] = df["y"].rolling(window=5, min_periods=1).mean().shift(1)
    df["roc"] = df["y"].pct_change().shift(1)

    y_shifted = df["y"].shift(7).replace(0, np_module.nan)
    df["trend_momentum_7d"] = df["y"].diff(periods=7) / y_shifted
    df["amelag_lag4"] = df["amelag_pred"].shift(4)
    df["amelag_lag7"] = df["amelag_pred"].shift(7)

    xdisease_viruses = cross_disease_map.get(virus_typ, [])
    if xdisease_viruses:
        xd_data = (
            service.db.query(
                wastewater_aggregated_model.datum,
                func_module.avg(wastewater_aggregated_model.viruslast_normalisiert).label("xd_load"),
            )
            .filter(
                wastewater_aggregated_model.virus_typ.in_(xdisease_viruses),
                wastewater_aggregated_model.datum >= start_date,
            )
            .group_by(wastewater_aggregated_model.datum)
            .all()
        )
        if xd_data:
            xd_df = pd_module.DataFrame(
                [{"ds": pd_module.to_datetime(r.datum), "xd_load": float(r.xd_load or 0)} for r in xd_data]
            )
            df = df.merge(xd_df, on="ds", how="left")
            df["xd_load"] = df["xd_load"].fillna(0.0)
        else:
            df["xd_load"] = 0.0
    else:
        df["xd_load"] = 0.0
    df["xdisease_lag7"] = df["xd_load"].shift(7)
    df["xdisease_lag14"] = df["xd_load"].shift(14)

    survstat_diseases = survstat_virus_map.get(virus_typ, [])
    if survstat_diseases:
        surv_rows = (
            service.db.query(
                survstat_weekly_data_model.week_start,
                func_module.sum(survstat_weekly_data_model.incidence).label("total_incidence"),
            )
            .filter(
                func_module.lower(survstat_weekly_data_model.disease).in_(survstat_diseases),
                survstat_weekly_data_model.bundesland.in_(service._survstat_region_values(region_code)),
                survstat_weekly_data_model.week > 0,
                survstat_weekly_data_model.week_start >= start_date,
            )
            .group_by(survstat_weekly_data_model.week_start)
            .order_by(survstat_weekly_data_model.week_start.asc())
            .all()
        )
        if surv_rows:
            surv_df = pd_module.DataFrame(
                [
                    {"ds": pd_module.to_datetime(r.week_start), "survstat_raw": float(r.total_incidence or 0)}
                    for r in surv_rows
                ]
            )
            surv_max = surv_df["survstat_raw"].max() or 1.0
            surv_df["survstat_incidence"] = surv_df["survstat_raw"] / surv_max
            surv_df = surv_df[["ds", "survstat_incidence"]]
            df = df.merge(surv_df, on="ds", how="left")
            df["survstat_incidence"] = df["survstat_incidence"].ffill().fillna(0.0)
        else:
            df["survstat_incidence"] = 0.0
    else:
        df["survstat_incidence"] = 0.0
    df["survstat_lag7"] = df["survstat_incidence"].shift(7)
    df["survstat_lag14"] = df["survstat_incidence"].shift(14)

    df = service._finalize_training_frame(df)
    df["region"] = region_code or default_forecast_region

    logger.info(f"Training data prepared: {len(df)} rows, {len(df.columns)} features")
    return df
