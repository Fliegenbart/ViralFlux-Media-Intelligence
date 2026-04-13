from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.services.ml.exogenous_feature_contracts import observed_as_of_only_rows
from app.services.ml.forecast_horizon_utils import ensure_supported_horizon
from app.services.ml.nowcast_contracts import NowcastResult
from app.services.ml.regional_panel_utils import (
    BUNDESLAND_NAMES,
    EVENT_DEFINITION_VERSION,
    REGIONAL_NEIGHBORS,
    event_definition_config_for_virus,
    seasonal_baseline_and_mad,
)


def build_rows(
    builder: Any,
    *,
    virus_typ: str,
    wastewater: pd.DataFrame,
    wastewater_context: dict[str, pd.DataFrame],
    truth: pd.DataFrame,
    grippeweb: pd.DataFrame,
    influenza_ifsg: pd.DataFrame,
    rsv_ifsg: pd.DataFrame,
    are: pd.DataFrame,
    notaufnahme: pd.DataFrame,
    trends: pd.DataFrame,
    weather: pd.DataFrame,
    pollen: pd.DataFrame,
    holidays: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]],
    state_populations: dict[str, float],
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    horizon_days: int,
    include_targets: bool,
    include_nowcast: bool,
    use_revision_adjusted: bool,
    revision_policy: str,
    source_revision_policy: dict[str, str] | None,
    weather_forecast_vintage_mode: str,
    weather_forecast_metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    if wastewater.empty or truth.empty:
        return []
    horizon = ensure_supported_horizon(horizon_days)
    event_config = event_definition_config_for_virus(virus_typ)

    wastewater_by_state = {
        state: frame.sort_values("datum").reset_index(drop=True)
        for state, frame in wastewater.groupby("bundesland")
    }
    wastewater_context_by_virus_state = {
        candidate_virus: {
            state: frame.sort_values("datum").reset_index(drop=True)
            for state, frame in candidate_frame.groupby("bundesland")
        }
        for candidate_virus, candidate_frame in wastewater_context.items()
        if candidate_frame is not None and not candidate_frame.empty
    }
    truth_by_state = {
        state: frame.sort_values("week_start").reset_index(drop=True)
        for state, frame in truth.groupby("bundesland")
    }
    grippeweb_by_state = {
        (signal_type, state): frame.sort_values("datum").reset_index(drop=True)
        for (signal_type, state), frame in grippeweb.dropna(subset=["bundesland"]).groupby(
            ["signal_type", "bundesland"]
        )
    } if not grippeweb.empty else {}
    grippeweb_national = {
        signal_type: frame.sort_values("datum").reset_index(drop=True)
        for signal_type, frame in grippeweb.loc[grippeweb["bundesland"].isna()].groupby("signal_type")
    } if not grippeweb.empty else {}
    influenza_by_state = {
        state: frame.sort_values("datum").reset_index(drop=True)
        for state, frame in influenza_ifsg.groupby("bundesland")
    } if not influenza_ifsg.empty else {}
    rsv_by_state = {
        state: frame.sort_values("datum").reset_index(drop=True)
        for state, frame in rsv_ifsg.groupby("bundesland")
    } if not rsv_ifsg.empty else {}
    are_by_state = {
        state: frame.sort_values("datum").reset_index(drop=True)
        for state, frame in are.groupby("bundesland")
    } if not are.empty else {}
    national_notaufnahme = notaufnahme.sort_values("datum").reset_index(drop=True) if not notaufnahme.empty else None
    national_trends = trends.sort_values("datum").reset_index(drop=True) if not trends.empty else None
    weather_by_state = {
        state: frame.sort_values("datum").reset_index(drop=True)
        for state, frame in weather.groupby("bundesland")
    } if not weather.empty else {}
    pollen_by_state = {
        state: frame.sort_values("datum").reset_index(drop=True)
        for state, frame in pollen.groupby("bundesland")
    } if not pollen.empty else {}

    max_sites = {
        state: max(int(frame["site_count"].max() or 0), 1)
        for state, frame in wastewater_by_state.items()
    }
    latest_ww_snapshot_cache: dict[pd.Timestamp, dict[str, dict[str, float]]] = {}
    latest_cross_virus_snapshot_cache: dict[tuple[str, pd.Timestamp], dict[str, dict[str, float]]] = {}

    rows: list[dict[str, Any]] = []
    for state in sorted(set(wastewater_by_state) & set(truth_by_state)):
        ww_frame = wastewater_by_state[state]
        truth_frame = truth_by_state[state]
        candidate_dates = ww_frame.loc[
            (ww_frame["datum"] >= start_date) & (ww_frame["datum"] <= end_date),
            "datum",
        ].drop_duplicates().sort_values()

        for as_of in candidate_dates:
            visible_ww = ww_frame.loc[
                (ww_frame["datum"] <= as_of) & (ww_frame["available_time"] <= as_of)
            ].copy()
            if len(visible_ww) < 8:
                continue

            visible_truth = truth_frame.loc[truth_frame["available_date"] <= as_of].copy()
            if len(visible_truth) < 8:
                continue

            visible_grippeweb_state = {
                signal_type: builder._visible_signal_frame(
                    grippeweb_by_state.get((signal_type, state)),
                    as_of=as_of,
                )
                for signal_type in ("ARE", "ILI")
            }
            visible_grippeweb_national = {
                signal_type: builder._visible_signal_frame(
                    grippeweb_national.get(signal_type),
                    as_of=as_of,
                )
                for signal_type in ("ARE", "ILI")
            }
            visible_influenza_ifsg = builder._visible_signal_frame(
                influenza_by_state.get(state),
                as_of=as_of,
            )
            visible_rsv_ifsg = builder._visible_signal_frame(
                rsv_by_state.get(state),
                as_of=as_of,
            )
            visible_are = None
            if virus_typ == "SARS-CoV-2":
                are_frame = are_by_state.get(state)
                if are_frame is not None and not are_frame.empty:
                    visible_are = are_frame.loc[
                        (are_frame["datum"] <= as_of) & (are_frame["available_time"] <= as_of)
                    ].copy()
                else:
                    visible_are = pd.DataFrame()

            visible_notaufnahme = None
            if virus_typ == "SARS-CoV-2" and national_notaufnahme is not None:
                visible_notaufnahme = national_notaufnahme.loc[
                    (national_notaufnahme["datum"] <= as_of)
                    & (national_notaufnahme["available_time"] <= as_of)
                ].copy()

            visible_trends = None
            if virus_typ == "SARS-CoV-2" and national_trends is not None:
                visible_trends = observed_as_of_only_rows(
                    national_trends,
                    as_of=as_of,
                )

            target_date = builder._target_date(as_of, horizon)
            target_week_start = builder._target_week_start(as_of, horizon)

            target_row = truth_frame.loc[truth_frame["week_start"] == target_week_start]

            current_truth = visible_truth.iloc[-1]
            next_truth = target_row.iloc[0] if not target_row.empty else None
            truth_source = str(current_truth.get("truth_source") or "survstat_weekly")
            truth_nowcast = builder.nowcast_service.evaluate_frame(
                source_id=truth_source,
                signal_id=truth_source,
                frame=visible_truth,
                as_of_date=as_of,
                value_column="incidence",
                reference_column="week_start",
                available_column="available_date",
                region_code=state,
                metadata={"truth_source": truth_source},
            )
            effective_current_incidence = builder.nowcast_service.preferred_value(
                truth_nowcast,
                use_revision_adjusted=builder._use_revision_adjusted_for_source(
                    source_id=truth_source,
                    result=truth_nowcast,
                    revision_policy=revision_policy,
                    source_revision_policy=source_revision_policy,
                    fallback_use_revision_adjusted=use_revision_adjusted,
                ),
            )
            baseline, mad = seasonal_baseline_and_mad(
                truth_frame,
                target_week_start,
                max_history_weeks=event_config.baseline_max_history_weeks,
                upper_quantile_cap=event_config.baseline_upper_quantile_cap,
            )
            if as_of not in latest_ww_snapshot_cache:
                latest_ww_snapshot_cache[as_of] = builder._latest_wastewater_snapshot_by_state(
                    wastewater_by_state,
                    as_of,
                )
            latest_ww_snapshot = latest_ww_snapshot_cache[as_of]
            latest_cross_virus_snapshots: dict[str, dict[str, dict[str, float]]] = {}
            for candidate_virus, candidate_frames in wastewater_context_by_virus_state.items():
                if candidate_virus == virus_typ:
                    continue
                cache_key = (candidate_virus, as_of)
                if cache_key not in latest_cross_virus_snapshot_cache:
                    latest_cross_virus_snapshot_cache[cache_key] = builder._latest_wastewater_snapshot_by_state(
                        candidate_frames,
                        as_of,
                    )
                latest_cross_virus_snapshots[candidate_virus] = latest_cross_virus_snapshot_cache[cache_key]
            feature_row = builder._build_feature_row(
                virus_typ=virus_typ,
                state=state,
                as_of=as_of,
                visible_ww=visible_ww,
                visible_truth=visible_truth,
                visible_grippeweb_state=visible_grippeweb_state,
                visible_grippeweb_national=visible_grippeweb_national,
                visible_influenza_ifsg=visible_influenza_ifsg,
                visible_rsv_ifsg=visible_rsv_ifsg,
                visible_are=visible_are,
                visible_notaufnahme=visible_notaufnahme,
                visible_trends=visible_trends,
                weather_frame=weather_by_state.get(state),
                pollen_frame=pollen_by_state.get(state),
                holiday_ranges=holidays.get(state, []),
                latest_ww_snapshot=latest_ww_snapshot,
                latest_cross_virus_snapshots=latest_cross_virus_snapshots,
                state_population=float(state_populations.get(state, 0.0)),
                max_site_count=max_sites.get(state, 1),
                horizon_days=horizon,
                target_week_start=target_week_start,
                current_known_incidence=float(effective_current_incidence),
                seasonal_baseline=float(baseline),
                seasonal_mad=float(mad),
                include_nowcast=include_nowcast,
                use_revision_adjusted=use_revision_adjusted,
                revision_policy=revision_policy,
                source_revision_policy=source_revision_policy,
                weather_forecast_vintage_mode=weather_forecast_vintage_mode,
                weather_forecast_metadata=weather_forecast_metadata,
                truth_nowcast=truth_nowcast,
            )
            if feature_row is None:
                continue

            row_payload = {
                "virus_typ": virus_typ,
                "bundesland": state,
                "bundesland_name": BUNDESLAND_NAMES.get(state, state),
                "as_of_date": pd.Timestamp(as_of).normalize(),
                "target_date": pd.Timestamp(target_date).normalize(),
                "target_week_start": pd.Timestamp(target_week_start).normalize(),
                "target_window_days": [horizon, horizon],
                "horizon_days": horizon,
                "event_definition_version": EVENT_DEFINITION_VERSION,
                "truth_source": str(
                    (next_truth.get("truth_source") if next_truth is not None else None)
                    or current_truth.get("truth_source")
                    or "survstat_weekly"
                ),
                "current_known_incidence": float(effective_current_incidence),
                "next_week_incidence": (
                    float(next_truth["incidence"] or 0.0)
                    if include_targets and next_truth is not None
                    else np.nan
                ),
                "seasonal_baseline": float(baseline),
                "seasonal_mad": float(mad),
                **feature_row,
            }
            rows.append(row_payload)

    return rows


def build_feature_row(
    builder: Any,
    *,
    virus_typ: str,
    state: str,
    as_of: pd.Timestamp,
    visible_ww: pd.DataFrame,
    visible_truth: pd.DataFrame,
    visible_grippeweb_state: dict[str, pd.DataFrame],
    visible_grippeweb_national: dict[str, pd.DataFrame],
    visible_influenza_ifsg: pd.DataFrame | None,
    visible_rsv_ifsg: pd.DataFrame | None,
    visible_are: pd.DataFrame | None,
    visible_notaufnahme: pd.DataFrame | None,
    visible_trends: pd.DataFrame | None,
    weather_frame: pd.DataFrame | None,
    pollen_frame: pd.DataFrame | None,
    holiday_ranges: list[tuple[pd.Timestamp, pd.Timestamp]],
    latest_ww_snapshot: dict[str, dict[str, float]],
    latest_cross_virus_snapshots: dict[str, dict[str, dict[str, float]]],
    state_population: float,
    max_site_count: int,
    horizon_days: int,
    target_week_start: pd.Timestamp,
    current_known_incidence: float,
    seasonal_baseline: float,
    seasonal_mad: float,
    include_nowcast: bool,
    use_revision_adjusted: bool,
    revision_policy: str,
    source_revision_policy: dict[str, str] | None,
    weather_forecast_vintage_mode: str,
    weather_forecast_metadata: dict[str, Any],
    truth_nowcast: NowcastResult,
) -> dict[str, Any] | None:
    nowcast_features: dict[str, float] = {}
    ww_latest = visible_ww.iloc[-1]
    ww_nowcast = builder.nowcast_service.evaluate_frame(
        source_id="wastewater",
        signal_id=virus_typ,
        frame=visible_ww,
        as_of_date=as_of,
        value_column="viral_load",
        region_code=state,
        metadata={"virus_typ": virus_typ},
    )
    ww_level = builder.nowcast_service.preferred_value(
        ww_nowcast,
        use_revision_adjusted=builder._use_revision_adjusted_for_source(
            source_id="wastewater",
            result=ww_nowcast,
            revision_policy=revision_policy,
            source_revision_policy=source_revision_policy,
            fallback_use_revision_adjusted=use_revision_adjusted,
        ),
    )
    ww_lag4 = builder._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=4), "viral_load")
    ww_lag7 = builder._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=7), "viral_load")
    ww_lag14 = builder._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=14), "viral_load")
    ww_site_lag7 = builder._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=7), "site_count")
    ww_under_bg_lag7 = builder._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=7), "under_bg_share")
    ww_dispersion_lag7 = builder._latest_value_as_of(visible_ww, as_of - pd.Timedelta(days=7), "viral_std")
    ww_window7 = visible_ww.loc[visible_ww["datum"] >= as_of - pd.Timedelta(days=7)]
    ww_window28 = visible_ww.loc[visible_ww["datum"] >= as_of - pd.Timedelta(days=28)]
    ww_site_count = float(ww_latest["site_count"] or 0.0)
    ww_slope7d = float((ww_level - ww_lag7) / max(abs(ww_lag7), 1.0))
    ww_slope14d = float((ww_lag7 - ww_lag14) / max(abs(ww_lag14), 1.0))
    ww_acceleration7d = float(ww_slope7d - ww_slope14d)
    if include_nowcast:
        nowcast_features.update(builder._nowcast_feature_family("ww_level", ww_nowcast))
        nowcast_features.update(
            builder._nowcast_feature_family("survstat_current_incidence", truth_nowcast)
        )

    truth_lag1 = builder._latest_truth_value(visible_truth, lag_weeks=1)
    truth_lag2 = builder._latest_truth_value(visible_truth, lag_weeks=2)
    truth_lag4 = builder._latest_truth_value(visible_truth, lag_weeks=4)
    truth_lag8 = builder._latest_truth_value(visible_truth, lag_weeks=8)

    neighbor_values = [
        snapshot["viral_load"]
        for code in REGIONAL_NEIGHBORS.get(state, [])
        if (snapshot := latest_ww_snapshot.get(code))
    ]
    neighbor_slopes = [
        snapshot["slope7d"]
        for code in REGIONAL_NEIGHBORS.get(state, [])
        if (snapshot := latest_ww_snapshot.get(code))
    ]
    national_values = [snapshot["viral_load"] for snapshot in latest_ww_snapshot.values()]
    national_slopes = [snapshot["slope7d"] for snapshot in latest_ww_snapshot.values()]
    national_accelerations = [snapshot["acceleration7d"] for snapshot in latest_ww_snapshot.values()]
    neighbor_mean = float(np.mean(neighbor_values)) if neighbor_values else 0.0
    national_mean = float(np.mean(national_values)) if national_values else 0.0
    site_coverage_vs_28d = float(
        ww_site_count / max(float(ww_window28["site_count"].median() or 0.0), 1.0)
    )
    state_population_millions = float(state_population / 1_000_000.0) if state_population > 0 else 0.0
    cross_virus_features = builder._cross_virus_features(
        target_virus=virus_typ,
        state=state,
        latest_cross_virus_snapshots=latest_cross_virus_snapshots,
    )

    weather_features = builder._weather_features(
        weather_frame,
        as_of,
        horizon_days=horizon_days,
        vintage_mode=weather_forecast_vintage_mode,
        vintage_metadata=weather_forecast_metadata,
    )
    pollen_context = builder._pollen_context(pollen_frame, as_of)
    holiday_share = builder._holiday_share_in_target_window(
        holiday_ranges,
        as_of,
        horizon_days=horizon_days,
    )
    grippeweb_features = builder._grippeweb_context_features(
        state=state,
        as_of=as_of,
        visible_state_signals=visible_grippeweb_state,
        visible_national_signals=visible_grippeweb_national,
        current_known_incidence=current_known_incidence,
        seasonal_baseline=seasonal_baseline,
        seasonal_mad=seasonal_mad,
        include_nowcast=include_nowcast,
        use_revision_adjusted=use_revision_adjusted,
        revision_policy=revision_policy,
        source_revision_policy=source_revision_policy,
    )
    virus_specific_ifsg_features = builder._virus_specific_ifsg_features(
        virus_typ=virus_typ,
        state=state,
        as_of=as_of,
        visible_influenza_ifsg=visible_influenza_ifsg,
        visible_rsv_ifsg=visible_rsv_ifsg,
        current_known_incidence=current_known_incidence,
        seasonal_baseline=seasonal_baseline,
        seasonal_mad=seasonal_mad,
        include_nowcast=include_nowcast,
        use_revision_adjusted=use_revision_adjusted,
        revision_policy=revision_policy,
        source_revision_policy=source_revision_policy,
    )
    sars_context_features = builder._sars_context_features(
        virus_typ=virus_typ,
        state=state,
        as_of=as_of,
        visible_are=visible_are,
        visible_notaufnahme=visible_notaufnahme,
        visible_trends=visible_trends,
        ww_level=ww_level,
        ww_slope7d=ww_slope7d,
        current_known_incidence=current_known_incidence,
        seasonal_baseline=seasonal_baseline,
        seasonal_mad=seasonal_mad,
        include_nowcast=include_nowcast,
        use_revision_adjusted=use_revision_adjusted,
        revision_policy=revision_policy,
        source_revision_policy=source_revision_policy,
    )
    if include_nowcast:
        weather_nowcast = builder._manual_nowcast_result(
            source_id="weather",
            signal_id="forecast_temp_3_7",
            region_code=state,
            as_of=as_of,
            raw_value=float(weather_features.get("weather_forecast_temp_3_7") or 0.0),
            reference_date=builder._latest_reference_date(weather_frame, as_of=as_of),
            available_time=builder._latest_available_time(weather_frame, as_of=as_of),
            coverage_ratio=1.0 if weather_frame is not None and not weather_frame.empty else 0.0,
        )
        pollen_nowcast = builder._manual_nowcast_result(
            source_id="pollen",
            signal_id="context_score",
            region_code=state,
            as_of=as_of,
            raw_value=float(pollen_context),
            reference_date=builder._latest_reference_date(pollen_frame, as_of=as_of),
            available_time=builder._latest_available_time(pollen_frame, as_of=as_of),
            coverage_ratio=1.0 if pollen_frame is not None and not pollen_frame.empty else 0.0,
        )
        holiday_nowcast = builder._manual_nowcast_result(
            source_id="school_holidays",
            signal_id="target_window_share",
            region_code=state,
            as_of=as_of,
            raw_value=float(holiday_share),
            reference_date=as_of,
            available_time=as_of,
            coverage_ratio=1.0,
        )
        nowcast_features.update(builder._nowcast_feature_family("weather_context", weather_nowcast))
        nowcast_features.update(builder._nowcast_feature_family("pollen_context", pollen_nowcast))
        nowcast_features.update(builder._nowcast_feature_family("holiday_context", holiday_nowcast))

    return {
        "ww_level": ww_level,
        "ww_lag4d": float(ww_lag4),
        "ww_lag7d": float(ww_lag7),
        "ww_lag14d": float(ww_lag14),
        "ww_slope7d": ww_slope7d,
        "ww_acceleration7d": ww_acceleration7d,
        "ww_mean7d": float(ww_window7["viral_load"].mean() or 0.0),
        "ww_std7d": float(ww_window7["viral_load"].std(ddof=0) or 0.0),
        "ww_level_vs_28d_median": float(
            ww_level - float(ww_window28["viral_load"].median() or 0.0)
        ),
        "ww_site_count": ww_site_count,
        "ww_site_coverage_ratio": float(ww_site_count / max(float(max_site_count), 1.0)),
        "ww_site_coverage_vs_28d": site_coverage_vs_28d,
        "ww_site_count_delta7d": float(ww_site_count - ww_site_lag7),
        "ww_site_count_ratio7d": float((ww_site_count - ww_site_lag7) / max(abs(ww_site_lag7), 1.0)),
        "ww_missing_days7d": builder._missing_days_in_window(visible_ww, as_of, 7),
        "ww_missing_days14d": builder._missing_days_in_window(visible_ww, as_of, 14),
        "ww_observation_lag_days": float(max((pd.Timestamp(as_of) - pd.Timestamp(ww_latest["datum"])).days, 0)),
        "ww_coverage_break_flag": float(site_coverage_vs_28d < 0.75),
        "ww_under_bg_share7d": float(ww_window7["under_bg_share"].mean() or 0.0),
        "ww_under_bg_trend7d": float(float(ww_latest["under_bg_share"] or 0.0) - ww_under_bg_lag7),
        "ww_regional_dispersion7d": float(ww_window7["viral_std"].mean() or 0.0),
        "ww_regional_dispersion_delta7d": float(float(ww_latest["viral_std"] or 0.0) - ww_dispersion_lag7),
        "survstat_current_incidence": float(current_known_incidence),
        "survstat_lag1w": float(truth_lag1),
        "survstat_lag2w": float(truth_lag2),
        "survstat_lag4w": float(truth_lag4),
        "survstat_lag8w": float(truth_lag8),
        "survstat_momentum_2w": float((truth_lag1 - truth_lag2) / max(abs(truth_lag2), 1.0)),
        "survstat_momentum_4w": float((truth_lag1 - truth_lag4) / max(abs(truth_lag4), 1.0)),
        "survstat_seasonal_baseline": float(seasonal_baseline),
        "survstat_seasonal_mad": float(seasonal_mad),
        "survstat_baseline_gap": float(current_known_incidence - seasonal_baseline),
        "survstat_baseline_zscore": float((current_known_incidence - seasonal_baseline) / max(seasonal_mad, 1.0)),
        "neighbor_ww_level": neighbor_mean,
        "neighbor_ww_slope7d": float(np.mean(neighbor_slopes)) if neighbor_slopes else 0.0,
        "national_ww_level": national_mean,
        "national_ww_slope7d": float(np.mean(national_slopes)) if national_slopes else 0.0,
        "national_ww_acceleration7d": float(np.mean(national_accelerations)) if national_accelerations else 0.0,
        "ww_relative_to_neighbor_mean": float(ww_level - neighbor_mean),
        "ww_relative_to_national": float(ww_level - national_mean),
        "ww_share_of_national": float(ww_level / max(abs(national_mean), 1.0)),
        "state_population_millions": state_population_millions,
        "ww_sites_per_million": float(ww_site_count / max(state_population_millions, 0.1)),
        "state_neighbor_count": float(len(REGIONAL_NEIGHBORS.get(state, []))),
        "state_is_city_state": float(state in {"BE", "HB", "HH"}),
        "target_holiday_share": float(holiday_share),
        "target_holiday_any": float(holiday_share > 0.0),
        "target_week_iso": float(target_week_start.isocalendar().week),
        "pollen_context_score": float(pollen_context),
        **weather_features,
        **cross_virus_features,
        **grippeweb_features,
        **virus_specific_ifsg_features,
        **sars_context_features,
        **nowcast_features,
    }
