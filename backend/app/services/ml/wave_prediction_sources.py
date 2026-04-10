"""Source and panel-building helpers for wave prediction service."""

from __future__ import annotations

from typing import Any


def load_source_frames(
    service,
    *,
    pathogen: str,
    start_date,
    end_date,
) -> dict[str, Any]:
    return {
        "wastewater": service.feature_builder._load_wastewater_daily(pathogen, start_date),
        "truth": service.feature_builder._load_truth_series(pathogen, start_date),
        "grippeweb": service.feature_builder._load_grippeweb_signals(start_date, end_date),
        "influenza_ifsg": service.feature_builder._load_influenza_ifsg(start_date, end_date),
        "rsv_ifsg": service.feature_builder._load_rsv_ifsg(start_date, end_date),
        "are_consultation": service.feature_builder._load_are_konsultation(start_date, end_date),
        "weather": service.feature_builder._load_weather(start_date, end_date),
        "holidays": service.feature_builder._load_holidays(),
        "populations": service.feature_builder._load_state_population_map(),
    }


def build_rows_for_pathogen(
    service,
    *,
    pathogen: str,
    source_frames: dict[str, Any],
    start_date,
    end_date,
    horizon_days: int,
    region_code: str | None,
    wave_label_config_for_pathogen_fn,
    build_daily_signal_features_fn,
    weather_context_features_fn,
    school_holiday_features_fn,
    bundesland_names,
    pathogen_slug_fn,
    pd_module,
    np_module,
) -> list[dict[str, Any]]:
    truth = service._coerce_frame(source_frames.get("truth"))
    if truth.empty:
        return []

    wastewater = service._coerce_frame(source_frames.get("wastewater"))
    grippeweb = service._coerce_frame(source_frames.get("grippeweb"))
    influenza_ifsg = service._coerce_frame(source_frames.get("influenza_ifsg"))
    rsv_ifsg = service._coerce_frame(source_frames.get("rsv_ifsg"))
    are_consultation = service._coerce_frame(source_frames.get("are_consultation"))
    weather = service._coerce_frame(source_frames.get("weather"))
    holidays = source_frames.get("holidays") or {}
    populations = source_frames.get("populations") or {}
    label_config = wave_label_config_for_pathogen_fn(pathogen, service.settings)

    truth_by_state = {
        state: frame.sort_values("week_start").reset_index(drop=True)
        for state, frame in truth.groupby("bundesland")
    }
    wastewater_by_state = service._group_by_state(wastewater)
    influenza_by_state = service._group_by_state(influenza_ifsg)
    rsv_by_state = service._group_by_state(rsv_ifsg)
    are_consultation_by_state = service._group_by_state(are_consultation)
    weather_by_state = service._group_by_state(weather)
    grippeweb_by_key = (
        {
            (signal_type, state): frame.sort_values("datum").reset_index(drop=True)
            for (signal_type, state), frame in grippeweb.dropna(subset=["bundesland"]).groupby(["signal_type", "bundesland"])
        }
        if not grippeweb.empty
        else {}
    )

    rows: list[dict[str, Any]] = []
    target_regions = [region_code] if region_code else sorted(truth_by_state.keys())
    date_index = pd_module.date_range(start_date, end_date, freq="D")
    for state in target_regions:
        truth_state = truth_by_state.get(state)
        if truth_state is None or truth_state.empty:
            continue

        wastewater_state = wastewater_by_state.get(state, pd_module.DataFrame())
        influenza_state = influenza_by_state.get(state, pd_module.DataFrame())
        rsv_state = rsv_by_state.get(state, pd_module.DataFrame())
        are_state = are_consultation_by_state.get(state, pd_module.DataFrame())
        weather_state = weather_by_state.get(state, pd_module.DataFrame())
        grippeweb_are_state = grippeweb_by_key.get(("ARE", state), pd_module.DataFrame())
        grippeweb_ili_state = grippeweb_by_key.get(("ILI", state), pd_module.DataFrame())

        truth_feature_frame = truth_state.assign(
            datum=pd_module.to_datetime(truth_state["available_date"]).dt.normalize()
        )
        for as_of in date_index:
            visible_truth = truth_state.loc[truth_state["available_date"] <= as_of].copy()
            if visible_truth.empty:
                continue

            target_date = (as_of + pd_module.Timedelta(days=horizon_days)).normalize()
            target_week_start = target_date - pd_module.Timedelta(days=target_date.weekday())
            target_row = truth_state.loc[truth_state["week_start"] == target_week_start]
            if target_row.empty:
                continue

            future_truth = truth_state.loc[
                (truth_state["week_start"] > as_of)
                & (truth_state["week_start"] <= as_of + pd_module.Timedelta(days=horizon_days))
            ].copy()
            current_truth = visible_truth.iloc[-1]
            from app.services.ml.wave_prediction_utils import label_wave_start  # local import keeps module lean

            wave_label, wave_event_date = label_wave_start(future_truth, visible_truth, label_config)

            wastewater_visible = service._visible_as_of(wastewater_state, as_of)
            influenza_visible = service._visible_as_of(influenza_state, as_of)
            rsv_visible = service._visible_as_of(rsv_state, as_of)
            are_visible = service._visible_as_of(are_state, as_of)
            grippeweb_are_visible = service._visible_as_of(grippeweb_are_state, as_of)
            grippeweb_ili_visible = service._visible_as_of(grippeweb_ili_state, as_of)

            truth_features = build_daily_signal_features_fn(
                truth_feature_frame.loc[truth_feature_frame["available_date"] <= as_of].assign(
                    datum=pd_module.to_datetime(truth_feature_frame["datum"]).dt.normalize(),
                    value=truth_feature_frame["incidence"].astype(float),
                ),
                as_of=as_of,
                prefix="truth",
                date_col="datum",
                value_col="value",
            )
            wastewater_features = build_daily_signal_features_fn(
                wastewater_visible.assign(
                    signal_date=pd_module.to_datetime(wastewater_visible["available_time"]).dt.normalize(),
                    value=wastewater_visible["viral_load"].astype(float),
                ) if not wastewater_visible.empty else wastewater_visible,
                as_of=as_of,
                prefix="wastewater",
                date_col="signal_date",
                value_col="value",
            )
            symptom_are_features = build_daily_signal_features_fn(
                grippeweb_are_visible.assign(
                    signal_date=pd_module.to_datetime(grippeweb_are_visible["available_time"]).dt.normalize(),
                    value=grippeweb_are_visible["incidence"].astype(float),
                ) if not grippeweb_are_visible.empty else grippeweb_are_visible,
                as_of=as_of,
                prefix="grippeweb_are",
                date_col="signal_date",
                value_col="value",
            )
            symptom_ili_features = build_daily_signal_features_fn(
                grippeweb_ili_visible.assign(
                    signal_date=pd_module.to_datetime(grippeweb_ili_visible["available_time"]).dt.normalize(),
                    value=grippeweb_ili_visible["incidence"].astype(float),
                ) if not grippeweb_ili_visible.empty else grippeweb_ili_visible,
                as_of=as_of,
                prefix="grippeweb_ili",
                date_col="signal_date",
                value_col="value",
            )
            consultation_features = build_daily_signal_features_fn(
                are_visible.assign(
                    signal_date=pd_module.to_datetime(are_visible["available_time"]).dt.normalize(),
                    value=are_visible["incidence"].astype(float),
                ) if not are_visible.empty else are_visible,
                as_of=as_of,
                prefix="consultation_are",
                date_col="signal_date",
                value_col="value",
            )
            virus_ifsg_frame = (
                influenza_visible
                if pathogen in {"Influenza A", "Influenza B"}
                else rsv_visible if pathogen == "RSV A" else pd_module.DataFrame()
            )
            virus_ifsg_features = build_daily_signal_features_fn(
                virus_ifsg_frame.assign(
                    signal_date=pd_module.to_datetime(virus_ifsg_frame["available_time"]).dt.normalize(),
                    value=virus_ifsg_frame["incidence"].astype(float),
                ) if not virus_ifsg_frame.empty else virus_ifsg_frame,
                as_of=as_of,
                prefix="virus_ifsg",
                date_col="signal_date",
                value_col="value",
            )
            weather_features = weather_context_features_fn(
                weather_state,
                as_of=as_of,
                enable_forecast_weather=bool(service.settings.WAVE_PREDICTION_ENABLE_FORECAST_WEATHER),
            )
            holiday_features = school_holiday_features_fn(
                holidays.get(state, []),
                as_of=as_of,
                horizon_days=horizon_days,
            )

            row = {
                "as_of_date": as_of,
                "region": state,
                "region_name": bundesland_names.get(state, state),
                "pathogen": pathogen,
                "pathogen_slug": pathogen_slug_fn(pathogen),
                "horizon_days": horizon_days,
                "target_date": target_date,
                "target_week_start": target_week_start,
                "target_window_end": as_of + pd_module.Timedelta(days=horizon_days),
                "source_truth_week_start": pd_module.Timestamp(current_truth["week_start"]).normalize(),
                "source_truth_available_date": pd_module.Timestamp(current_truth["available_date"]).normalize(),
                "truth_source": str(current_truth.get("truth_source") or "unknown"),
                "target_regression": float(target_row.iloc[0]["incidence"] or 0.0),
                "target_regression_log": float(np_module.log1p(max(float(target_row.iloc[0]["incidence"] or 0.0), 0.0))),
                "target_wave14": int(wave_label),
                "wave_event_date": wave_event_date,
                "wave_event_reason": "ruleset_event" if wave_label else None,
                "future_truth_max": float(future_truth["incidence"].max() or 0.0) if not future_truth.empty else 0.0,
                "future_truth_growth_ratio": service._growth_ratio(future_truth),
                "raw_truth_incidence": float(current_truth["incidence"] or 0.0),
                "raw_wastewater_level": service._latest_column_value(wastewater_visible, "viral_load"),
                "raw_grippeweb_are": service._latest_column_value(grippeweb_are_visible, "incidence"),
                "raw_grippeweb_ili": service._latest_column_value(grippeweb_ili_visible, "incidence"),
                "raw_consultation_are": service._latest_column_value(are_visible, "incidence"),
                "raw_virus_ifsg": service._latest_column_value(virus_ifsg_frame, "incidence"),
                "raw_weather_temp": service._latest_column_value(
                    weather_state.loc[weather_state["datum"] <= as_of] if not weather_state.empty else weather_state,
                    "temp",
                ),
                "raw_weather_humidity": service._latest_column_value(
                    weather_state.loc[weather_state["datum"] <= as_of] if not weather_state.empty else weather_state,
                    "humidity",
                ),
            }
            row.update(truth_features)
            row.update(wastewater_features)
            row.update(symptom_are_features)
            row.update(symptom_ili_features)
            row.update(consultation_features)
            row.update(virus_ifsg_features)
            row.update(weather_features)
            row.update(holiday_features)
            if bool(service.settings.WAVE_PREDICTION_ENABLE_DEMOGRAPHICS):
                row["population"] = float(populations.get(state) or 0.0)
            if bool(service.settings.WAVE_PREDICTION_ENABLE_INTERACTIONS):
                symptom_level = max(
                    float(row.get("consultation_are_level") or 0.0),
                    float(row.get("grippeweb_are_level") or 0.0),
                )
                row["wastewater_x_humidity"] = float(row.get("wastewater_level", 0.0) * row.get("avg_humidity_7", 0.0))
                row["incidence_x_holiday"] = float(row.get("truth_level", 0.0) * row.get("is_school_holiday", 0.0))
                row["symptomburden_x_weather"] = float(symptom_level * row.get("avg_temp_7", 0.0))
                row["wastewater_minus_incidence_zscore"] = float(
                    row.get("wastewater_zscore_28", 0.0) - row.get("truth_zscore_28", 0.0)
                )

            row["month"] = float(as_of.month)
            row["week_of_year"] = float(as_of.isocalendar().week)
            row["quarter"] = float(as_of.quarter)
            row["day_of_year"] = float(as_of.dayofyear)
            rows.append(row)
    return rows


def visible_as_of(frame, as_of, *, pd_module):
    if frame is None or frame.empty:
        return pd_module.DataFrame()
    visible = frame.copy()
    if "available_time" in visible.columns:
        visible = visible.loc[pd_module.to_datetime(visible["available_time"]) <= as_of].copy()
    if "datum" in visible.columns:
        visible = visible.loc[pd_module.to_datetime(visible["datum"]).dt.normalize() <= as_of].copy()
    return visible.sort_values("datum").reset_index(drop=True)


def group_by_state(frame) -> dict[str, Any]:
    if frame is None or frame.empty or "bundesland" not in frame.columns:
        return {}
    return {
        state: part.sort_values("datum").reset_index(drop=True)
        for state, part in frame.groupby("bundesland")
    }


def coerce_frame(frame):
    if frame is None:
        import pandas as pd

        return pd.DataFrame()
    return frame.copy()


def latest_column_value(frame, column: str) -> float:
    if frame is None or frame.empty or column not in frame.columns:
        return 0.0
    return float(frame.iloc[-1][column] or 0.0)


def growth_ratio(future_truth) -> float:
    if future_truth is None or future_truth.empty or len(future_truth) < 2:
        return 0.0
    values = future_truth["incidence"].astype(float)
    return float((values.iloc[-1] - values.iloc[0]) / max(abs(values.iloc[0]), 1.0))
