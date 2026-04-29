from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.services.ml.exogenous_feature_contracts import observed_as_of_only_rows
from app.services.ml.forecast_horizon_utils import ensure_supported_horizon
from app.services.ml.nowcast_contracts import NowcastResult
from app.services.ml.regional_panel_utils import (
    ALL_BUNDESLAENDER,
    BUNDESLAND_NAMES,
    EVENT_DEFINITION_VERSION,
    REGIONAL_NEIGHBORS,
    event_definition_config_for_virus,
    seasonal_baseline_and_mad,
)


def _week_start(value: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value).normalize()
    return (ts - pd.Timedelta(days=int(ts.weekday()))).normalize()


def _build_issue_calendar(
    *,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    horizon_days: int,
) -> pd.DataFrame:
    horizon = ensure_supported_horizon(horizon_days)
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if pd.isna(start) or pd.isna(end) or start > end:
        return pd.DataFrame(
            columns=[
                "forecast_issue_week_start",
                "forecast_issue_cutoff_date",
                "target_week_start",
            ]
        )

    first_week_start = _week_start(start)
    last_week_start = _week_start(end)
    issue_week_starts = pd.date_range(first_week_start, last_week_start, freq="7D")
    rows: list[dict[str, pd.Timestamp]] = []
    for issue_week_start in issue_week_starts:
        cutoff = min(issue_week_start + pd.Timedelta(days=6), end)
        if cutoff < start:
            continue
        target = _week_start(cutoff + pd.Timedelta(days=horizon))
        rows.append(
            {
                "forecast_issue_week_start": pd.Timestamp(issue_week_start).normalize(),
                "forecast_issue_cutoff_date": pd.Timestamp(cutoff).normalize(),
                "target_week_start": pd.Timestamp(target).normalize(),
            }
        )
    return pd.DataFrame(rows)


def _build_state_issue_calendar(
    *,
    wastewater_by_state: dict[str, pd.DataFrame],
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    horizon_days: int,
) -> pd.DataFrame:
    horizon = ensure_supported_horizon(horizon_days)
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if pd.isna(start) or pd.isna(end) or start > end:
        return pd.DataFrame(
            columns=[
                "bundesland",
                "forecast_issue_week_start",
                "forecast_issue_cutoff_date",
                "target_week_start",
            ]
        )

    rows: list[dict[str, pd.Timestamp | str]] = []
    for state, frame in wastewater_by_state.items():
        if frame is None or frame.empty or "datum" not in frame.columns:
            continue
        candidate_dates = (
            pd.to_datetime(frame["datum"], errors="coerce")
            .dt.normalize()
            .dropna()
            .drop_duplicates()
            .sort_values()
        )
        for cutoff in candidate_dates:
            cutoff = pd.Timestamp(cutoff).normalize()
            if cutoff < start or cutoff > end:
                continue
            rows.append(
                {
                    "bundesland": state,
                    "forecast_issue_week_start": _week_start(cutoff),
                    "forecast_issue_cutoff_date": cutoff,
                    "target_week_start": _week_start(cutoff + pd.Timedelta(days=horizon)),
                }
            )
    return pd.DataFrame(rows)


def _visible_asof_frame(
    frame: pd.DataFrame | None,
    *,
    cutoff: pd.Timestamp,
    date_column: str = "datum",
) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    if date_column not in frame.columns:
        return frame.iloc[0:0].copy()
    visible = frame.copy()
    normalized_cutoff = pd.Timestamp(cutoff).normalize()
    visible = visible.loc[pd.to_datetime(visible[date_column]).dt.normalize() <= normalized_cutoff]
    for availability_column in ("available_time", "available_date", "published_at", "fetched_at"):
        if availability_column in visible.columns:
            visible = visible.loc[
                pd.to_datetime(visible[availability_column], errors="coerce").dt.normalize()
                <= normalized_cutoff
            ]
    if visible.empty:
        return visible.copy()
    return visible.sort_values(date_column).reset_index(drop=True)


def _feature_age_days(
    frame: pd.DataFrame | None,
    *,
    cutoff: pd.Timestamp,
    date_column: str = "datum",
) -> float:
    if frame is None or frame.empty or date_column not in frame.columns:
        return float("nan")
    latest = pd.to_datetime(frame[date_column], errors="coerce").dropna()
    if latest.empty:
        return float("nan")
    return float(max((pd.Timestamp(cutoff).normalize() - pd.Timestamp(latest.max()).normalize()).days, 0))


def _feature_missing(frame: pd.DataFrame | None) -> float:
    return float(frame is None or frame.empty)


def lagged_incidence_feature_family(
    *,
    prefix: str,
    frame: pd.DataFrame | None,
    as_of: pd.Timestamp,
) -> dict[str, float]:
    signal_frame = frame if frame is not None else pd.DataFrame()

    def _latest(cutoff: pd.Timestamp) -> float:
        if signal_frame.empty or "datum" not in signal_frame.columns or "incidence" not in signal_frame.columns:
            return 0.0
        visible = signal_frame.loc[
            pd.to_datetime(signal_frame["datum"], errors="coerce").dt.normalize()
            <= pd.Timestamp(cutoff).normalize()
        ]
        if visible.empty:
            return 0.0
        value = pd.to_numeric(visible.iloc[-1].get("incidence"), errors="coerce")
        return float(value) if pd.notna(value) else 0.0

    level = _latest(as_of)
    lag_1 = _latest(as_of - pd.Timedelta(days=7))
    lag_2 = _latest(as_of - pd.Timedelta(days=14))
    lag_3 = _latest(as_of - pd.Timedelta(days=21))
    baseline_frame = (
        signal_frame.loc[
            pd.to_datetime(signal_frame["datum"], errors="coerce").dt.normalize()
            <= as_of - pd.Timedelta(days=7)
        ]
        if not signal_frame.empty and "datum" in signal_frame.columns
        else signal_frame
    )
    values = (
        pd.to_numeric(baseline_frame.get("incidence"), errors="coerce").dropna().to_numpy()
        if not baseline_frame.empty and "incidence" in baseline_frame.columns
        else np.array([], dtype=float)
    )
    baseline = float(np.median(values)) if len(values) else 0.0
    mad = float(np.median(np.abs(values - baseline))) if len(values) else 1.0
    return {
        f"{prefix}_available": float(not signal_frame.empty),
        f"{prefix}_level": float(level),
        f"{prefix}_incidence_lag_1": float(lag_1),
        f"{prefix}_incidence_lag_2": float(lag_2),
        f"{prefix}_momentum_1w": float((level - lag_1) / max(abs(lag_1), 1.0)),
        f"{prefix}_delta_1w": float(lag_1 - lag_2),
        f"{prefix}_delta_2w": float(lag_2 - lag_3),
        f"{prefix}_growth_z": float((lag_1 - baseline) / max(mad, 1.0)),
        f"{prefix}_missing": float(signal_frame.empty),
    }


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

    if include_targets:
        issue_calendar = _build_issue_calendar(
            start_date=start_date,
            end_date=end_date,
            horizon_days=horizon,
        )
    else:
        issue_calendar = _build_state_issue_calendar(
            wastewater_by_state=wastewater_by_state,
            start_date=start_date,
            end_date=end_date,
            horizon_days=horizon,
        )

    rows: list[dict[str, Any]] = []
    for issue in issue_calendar.itertuples(index=False):
        issue_week_start = pd.Timestamp(issue.forecast_issue_week_start).normalize()
        cutoff = pd.Timestamp(issue.forecast_issue_cutoff_date).normalize()
        target_week_start = pd.Timestamp(issue.target_week_start).normalize()
        target_date = builder._target_date(cutoff, horizon)

        latest_ww_snapshot = builder._latest_wastewater_snapshot_by_state(wastewater_by_state, cutoff)
        latest_cross_virus_snapshots = {
            candidate_virus: builder._latest_wastewater_snapshot_by_state(candidate_frames, cutoff)
            for candidate_virus, candidate_frames in wastewater_context_by_virus_state.items()
            if candidate_virus != virus_typ
        }
        issue_state = getattr(issue, "bundesland", None)
        states = (
            [str(issue_state)]
            if issue_state is not None and not pd.isna(issue_state)
            else ALL_BUNDESLAENDER
        )

        for state in states:
            ww_frame = wastewater_by_state.get(state)
            truth_frame = truth_by_state.get(state)
            if ww_frame is None or truth_frame is None:
                continue

            visible_ww = _visible_asof_frame(ww_frame, cutoff=cutoff)
            if len(visible_ww) < 8:
                continue

            visible_truth = _visible_asof_frame(
                truth_frame,
                cutoff=cutoff,
                date_column="week_start",
            )
            if len(visible_truth) < 8:
                continue

            visible_grippeweb_state = {
                signal_type: _visible_asof_frame(
                    grippeweb_by_state.get((signal_type, state)),
                    cutoff=cutoff,
                )
                for signal_type in ("ARE", "ILI")
            }
            visible_grippeweb_national = {
                signal_type: _visible_asof_frame(
                    grippeweb_national.get(signal_type),
                    cutoff=cutoff,
                )
                for signal_type in ("ARE", "ILI")
            }
            visible_influenza_ifsg = _visible_asof_frame(
                influenza_by_state.get(state),
                cutoff=cutoff,
            )
            visible_rsv_ifsg = _visible_asof_frame(
                rsv_by_state.get(state),
                cutoff=cutoff,
            )
            visible_are = _visible_asof_frame(are_by_state.get(state), cutoff=cutoff)
            visible_notaufnahme = _visible_asof_frame(national_notaufnahme, cutoff=cutoff)

            if national_trends is not None and not national_trends.empty:
                visible_trends = observed_as_of_only_rows(
                    _visible_asof_frame(national_trends, cutoff=cutoff),
                    as_of=cutoff,
                )
            else:
                visible_trends = pd.DataFrame()

            target_row = truth_frame.loc[truth_frame["week_start"] == target_week_start]

            current_truth = visible_truth.iloc[-1]
            next_truth = target_row.iloc[0] if not target_row.empty else None
            truth_source = str(current_truth.get("truth_source") or "survstat_weekly")
            truth_nowcast = builder.nowcast_service.evaluate_frame(
                source_id=truth_source,
                signal_id=truth_source,
                frame=visible_truth,
                as_of_date=cutoff,
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
            feature_row = builder._build_feature_row(
                virus_typ=virus_typ,
                state=state,
                as_of=cutoff,
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
                "as_of_date": cutoff,
                "forecast_issue_week_start": issue_week_start,
                "forecast_issue_cutoff_date": cutoff,
                "target_date": pd.Timestamp(target_date).normalize(),
                "target_week_start": target_week_start,
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
                "ww_feature_age_days": _feature_age_days(visible_ww, cutoff=cutoff),
                "truth_feature_age_days": _feature_age_days(
                    visible_truth,
                    cutoff=cutoff,
                    date_column="week_start",
                ),
                "ww_feature_missing": float(visible_ww.empty),
                "truth_feature_missing": float(visible_truth.empty),
                "grippeweb_are_feature_age_days": _feature_age_days(
                    visible_grippeweb_state.get("ARE"),
                    cutoff=cutoff,
                ),
                "grippeweb_are_feature_missing": _feature_missing(
                    visible_grippeweb_state.get("ARE")
                ),
                "grippeweb_ili_feature_age_days": _feature_age_days(
                    visible_grippeweb_state.get("ILI"),
                    cutoff=cutoff,
                ),
                "grippeweb_ili_feature_missing": _feature_missing(
                    visible_grippeweb_state.get("ILI")
                ),
                "grippeweb_are_national_feature_age_days": _feature_age_days(
                    visible_grippeweb_national.get("ARE"),
                    cutoff=cutoff,
                ),
                "grippeweb_are_national_feature_missing": _feature_missing(
                    visible_grippeweb_national.get("ARE")
                ),
                "grippeweb_ili_national_feature_age_days": _feature_age_days(
                    visible_grippeweb_national.get("ILI"),
                    cutoff=cutoff,
                ),
                "grippeweb_ili_national_feature_missing": _feature_missing(
                    visible_grippeweb_national.get("ILI")
                ),
                "ifsg_influenza_feature_age_days": _feature_age_days(
                    visible_influenza_ifsg,
                    cutoff=cutoff,
                ),
                "ifsg_influenza_feature_missing": _feature_missing(visible_influenza_ifsg),
                "ifsg_rsv_feature_age_days": _feature_age_days(
                    visible_rsv_ifsg,
                    cutoff=cutoff,
                ),
                "ifsg_rsv_feature_missing": _feature_missing(visible_rsv_ifsg),
                "are_feature_age_days": _feature_age_days(visible_are, cutoff=cutoff),
                "are_feature_missing": _feature_missing(visible_are),
                "notaufnahme_feature_age_days": _feature_age_days(
                    visible_notaufnahme,
                    cutoff=cutoff,
                ),
                "notaufnahme_feature_missing": _feature_missing(visible_notaufnahme),
                "trends_feature_age_days": _feature_age_days(visible_trends, cutoff=cutoff),
                "trends_feature_missing": _feature_missing(visible_trends),
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
    survstat_momentum_2w = float((truth_lag1 - truth_lag2) / max(abs(truth_lag2), 1.0))
    survstat_momentum_4w = float((truth_lag1 - truth_lag4) / max(abs(truth_lag4), 1.0))

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
    neighbor_slope7d = float(np.mean(neighbor_slopes)) if neighbor_slopes else 0.0
    national_slope7d = float(np.mean(national_slopes)) if national_slopes else 0.0
    national_acceleration7d = float(np.mean(national_accelerations)) if national_accelerations else 0.0
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
    are_context_features = builder._are_context_features(
        as_of=as_of,
        visible_are=visible_are,
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
        ww_acceleration7d=ww_acceleration7d,
        neighbor_ww_slope7d=neighbor_slope7d,
        national_ww_slope7d=national_slope7d,
        national_ww_acceleration7d=national_acceleration7d,
        current_known_incidence=current_known_incidence,
        seasonal_baseline=seasonal_baseline,
        seasonal_mad=seasonal_mad,
        survstat_momentum_2w=survstat_momentum_2w,
        survstat_momentum_4w=survstat_momentum_4w,
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
        "survstat_momentum_2w": survstat_momentum_2w,
        "survstat_momentum_4w": survstat_momentum_4w,
        "survstat_seasonal_baseline": float(seasonal_baseline),
        "survstat_seasonal_mad": float(seasonal_mad),
        "survstat_baseline_gap": float(current_known_incidence - seasonal_baseline),
        "survstat_baseline_zscore": float((current_known_incidence - seasonal_baseline) / max(seasonal_mad, 1.0)),
        "neighbor_ww_level": neighbor_mean,
        "neighbor_ww_slope7d": neighbor_slope7d,
        "national_ww_level": national_mean,
        "national_ww_slope7d": national_slope7d,
        "national_ww_acceleration7d": national_acceleration7d,
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
        **are_context_features,
        **sars_context_features,
        **nowcast_features,
    }
