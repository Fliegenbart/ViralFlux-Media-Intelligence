"""Coverage helpers for weather vintage comparison runs."""

from __future__ import annotations

from typing import Any


def load_weather_identity_frame(
    db: Any,
    *,
    start_date: Any,
    end_date: Any,
    weather_data_model: Any,
    pd_module: Any,
) -> Any:
    rows = (
        db.query(
            weather_data_model.datum,
            weather_data_model.available_time,
            weather_data_model.forecast_run_timestamp,
            weather_data_model.forecast_run_id,
            weather_data_model.forecast_run_identity_source,
            weather_data_model.forecast_run_identity_quality,
            weather_data_model.data_type,
        )
        .filter(
            weather_data_model.data_type == "DAILY_FORECAST",
            weather_data_model.datum >= start_date.to_pydatetime(),
            weather_data_model.datum <= end_date.to_pydatetime(),
        )
        .all()
    )
    if not rows:
        return pd_module.DataFrame(
            columns=[
                "datum",
                "available_time",
                "forecast_run_timestamp",
                "forecast_run_id",
                "forecast_run_identity_source",
                "forecast_run_identity_quality",
                "data_type",
            ]
        )
    return pd_module.DataFrame(
        [
            {
                "datum": row.datum,
                "available_time": row.available_time,
                "forecast_run_timestamp": row.forecast_run_timestamp,
                "forecast_run_id": row.forecast_run_id,
                "forecast_run_identity_source": row.forecast_run_identity_source,
                "forecast_run_identity_quality": row.forecast_run_identity_quality,
                "data_type": row.data_type,
            }
            for row in rows
        ]
    )


def summarize_backtest_weather_identity_coverage(
    *,
    panel: Any,
    weather_frame: Any,
    horizon_days: int,
    time_based_panel_splits_fn: Any,
    min_test_coverage: float,
    min_train_coverage: float,
    time_block_days: int,
    json_safe_fn: Any,
    pd_module: Any,
) -> dict[str, Any]:
    if panel.empty:
        return {
            "coverage_status": "no_panel",
            "insufficient_for_comparison": True,
            "coverage_overall": 0.0,
            "coverage_train": 0.0,
            "coverage_test": 0.0,
            "coverage_by_fold": [],
            "coverage_by_time_block": [],
            "first_available_run_identity_date": None,
            "last_available_run_identity_date": None,
            "first_covered_as_of_date": None,
            "last_covered_as_of_date": None,
            "unique_as_of_dates": 0,
            "rows_in_panel": 0,
        }

    working = panel.copy()
    working["as_of_date"] = pd_module.to_datetime(working["as_of_date"]).dt.normalize()
    if "target_date" in working.columns:
        working["target_date"] = pd_module.to_datetime(working["target_date"]).dt.normalize()
    else:
        working["target_date"] = working["as_of_date"] + pd_module.to_timedelta(
            int(horizon_days), unit="D"
        )

    by_as_of = (
        working.loc[:, ["as_of_date", "target_date"]]
        .drop_duplicates()
        .sort_values(["as_of_date", "target_date"])
        .groupby("as_of_date", as_index=False)
        .first()
    )

    weather = weather_frame.copy()
    if weather.empty:
        weather = pd_module.DataFrame(
            columns=[
                "datum",
                "available_time",
                "forecast_run_timestamp",
                "forecast_run_id",
                "forecast_run_identity_source",
                "forecast_run_identity_quality",
                "data_type",
            ]
        )
    else:
        weather["datum"] = pd_module.to_datetime(weather["datum"]).dt.normalize()
        weather["available_time"] = pd_module.to_datetime(weather["available_time"])
        weather["forecast_run_timestamp"] = pd_module.to_datetime(
            weather["forecast_run_timestamp"]
        )
        weather = weather.loc[
            weather["forecast_run_timestamp"].notna()
            & weather["available_time"].notna()
            & (weather["data_type"] == "DAILY_FORECAST")
        ].copy()

    availability_records: list[dict[str, Any]] = []
    for row in by_as_of.itertuples(index=False):
        as_of_date = pd_module.Timestamp(row.as_of_date).normalize()
        target_date = pd_module.Timestamp(row.target_date).normalize()
        covered = False
        if not weather.empty:
            covered = bool(
                not weather.loc[
                    (weather["datum"] == target_date)
                    & (weather["available_time"] <= as_of_date)
                    & (weather["forecast_run_timestamp"] <= as_of_date)
                ].empty
            )
        availability_records.append(
            {
                "as_of_date": as_of_date,
                "target_date": target_date,
                "covered": covered,
            }
        )

    availability = pd_module.DataFrame(availability_records)
    if availability.empty:
        availability = pd_module.DataFrame(columns=["as_of_date", "target_date", "covered"])

    unique_dates = [
        pd_module.Timestamp(value).normalize() for value in availability["as_of_date"].tolist()
    ]
    coverage_overall = (
        round(float(availability["covered"].mean() or 0.0), 4)
        if not availability.empty
        else 0.0
    )

    train_total_dates = 0
    train_covered_dates = 0
    test_total_dates = 0
    test_covered_dates = 0
    coverage_by_fold: list[dict[str, Any]] = []
    for fold_index, (train_dates, test_dates) in enumerate(
        time_based_panel_splits_fn(
            unique_dates,
            n_splits=5,
            min_train_periods=90,
            min_test_periods=21,
        ),
        start=1,
    ):
        train_mask = availability["as_of_date"].isin(train_dates)
        test_mask = availability["as_of_date"].isin(test_dates)
        train_fraction = round(float(availability.loc[train_mask, "covered"].mean() or 0.0), 4)
        test_fraction = round(float(availability.loc[test_mask, "covered"].mean() or 0.0), 4)
        train_rows = int(train_mask.sum())
        test_rows = int(test_mask.sum())
        train_total_dates += train_rows
        test_total_dates += test_rows
        train_covered_dates += int(availability.loc[train_mask, "covered"].sum()) if train_rows else 0
        test_covered_dates += int(availability.loc[test_mask, "covered"].sum()) if test_rows else 0
        coverage_by_fold.append(
            {
                "fold": int(fold_index),
                "train_start": str(min(train_dates)) if train_dates else None,
                "train_end": str(max(train_dates)) if train_dates else None,
                "test_start": str(min(test_dates)) if test_dates else None,
                "test_end": str(max(test_dates)) if test_dates else None,
                "coverage_train": train_fraction,
                "coverage_test": test_fraction,
                "train_dates": train_rows,
                "test_dates": test_rows,
            }
        )

    coverage_train = (
        round(float(train_covered_dates / train_total_dates), 4) if train_total_dates else 0.0
    )
    coverage_test = (
        round(float(test_covered_dates / test_total_dates), 4) if test_total_dates else 0.0
    )

    block_start = pd_module.Timestamp(min(unique_dates)).normalize() if unique_dates else None
    block_end = pd_module.Timestamp(max(unique_dates)).normalize() if unique_dates else None
    coverage_by_time_block: list[dict[str, Any]] = []
    if block_start is not None and block_end is not None:
        current_start = block_start
        while current_start <= block_end:
            current_end = min(
                current_start + pd_module.Timedelta(days=time_block_days - 1),
                block_end,
            )
            block_mask = (
                (availability["as_of_date"] >= current_start)
                & (availability["as_of_date"] <= current_end)
            )
            block_rows = int(block_mask.sum())
            coverage_by_time_block.append(
                {
                    "start": str(current_start),
                    "end": str(current_end),
                    "coverage": round(
                        float(availability.loc[block_mask, "covered"].mean() or 0.0),
                        4,
                    )
                    if block_rows
                    else 0.0,
                    "as_of_dates": block_rows,
                }
            )
            current_start = current_end + pd_module.Timedelta(days=1)

    covered_dates = availability.loc[availability["covered"], "as_of_date"].sort_values()
    if coverage_test >= min_test_coverage and coverage_train >= min_train_coverage:
        coverage_status = "sufficient"
    elif coverage_overall <= 0.0:
        coverage_status = "none"
    else:
        coverage_status = "insufficient"

    return json_safe_fn(
        {
            "coverage_status": coverage_status,
            "insufficient_for_comparison": coverage_status != "sufficient",
            "coverage_overall": coverage_overall,
            "coverage_train": coverage_train,
            "coverage_test": coverage_test,
            "coverage_by_fold": coverage_by_fold,
            "coverage_by_time_block": coverage_by_time_block,
            "first_available_run_identity_date": str(weather["datum"].min()) if not weather.empty else None,
            "last_available_run_identity_date": str(weather["datum"].max()) if not weather.empty else None,
            "first_covered_as_of_date": str(covered_dates.min()) if not covered_dates.empty else None,
            "last_covered_as_of_date": str(covered_dates.max()) if not covered_dates.empty else None,
            "unique_as_of_dates": int(len(unique_dates)),
            "rows_in_panel": int(len(panel)),
            "weather_rows_with_run_identity": int(len(weather)),
        }
    )


def analyze_scope_coverage(
    *,
    trainer: Any,
    virus_typ: str,
    horizon_days: int,
    lookback_days: int,
    weather_forecast_vintage_run_timestamp_v1: str,
    pd_module: Any,
    load_weather_identity_frame_fn: Any,
    summarize_backtest_weather_identity_coverage_fn: Any,
) -> dict[str, Any]:
    panel = trainer._build_training_panel(
        virus_typ=virus_typ,
        lookback_days=int(lookback_days),
        horizon_days=int(horizon_days),
        weather_forecast_vintage_mode=weather_forecast_vintage_run_timestamp_v1,
    )
    panel = trainer._prepare_horizon_panel(panel, horizon_days=int(horizon_days))
    if panel.empty:
        return summarize_backtest_weather_identity_coverage_fn(
            panel=panel,
            weather_frame=pd_module.DataFrame(),
            horizon_days=int(horizon_days),
        )

    weather_frame = load_weather_identity_frame_fn(
        start_date=pd_module.Timestamp(panel["as_of_date"].min()).normalize()
        + pd_module.Timedelta(days=1),
        end_date=pd_module.Timestamp(panel["target_date"].max()).normalize(),
    )
    return summarize_backtest_weather_identity_coverage_fn(
        panel=panel,
        weather_frame=weather_frame,
        horizon_days=int(horizon_days),
    )
