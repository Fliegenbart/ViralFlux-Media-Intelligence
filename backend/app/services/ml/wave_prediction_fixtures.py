"""Synthetic fixtures for the wave prediction evaluation harness."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd

from app.services.ml.wave_prediction_service import WavePredictionService

FIXTURE_WAVE_SETTINGS = SimpleNamespace(
    WAVE_PREDICTION_HORIZON_DAYS=14,
    WAVE_PREDICTION_LOOKBACK_DAYS=120,
    WAVE_PREDICTION_MIN_TRAIN_ROWS=20,
    WAVE_PREDICTION_MIN_POSITIVE_ROWS=2,
    WAVE_PREDICTION_MODEL_VERSION="wave_prediction_v1",
    WAVE_PREDICTION_BACKTEST_FOLDS=3,
    WAVE_PREDICTION_MIN_TRAIN_PERIODS=30,
    WAVE_PREDICTION_MIN_TEST_PERIODS=7,
    WAVE_PREDICTION_CLASSIFICATION_THRESHOLD=0.5,
    WAVE_PREDICTION_ENABLE_FORECAST_WEATHER=True,
    WAVE_PREDICTION_ENABLE_DEMOGRAPHICS=True,
    WAVE_PREDICTION_ENABLE_INTERACTIONS=True,
    WAVE_PREDICTION_LABEL_ABSOLUTE_THRESHOLD=10.0,
    WAVE_PREDICTION_LABEL_SEASONAL_ZSCORE=1.5,
    WAVE_PREDICTION_LABEL_GROWTH_OBSERVATIONS=2,
    WAVE_PREDICTION_LABEL_GROWTH_MIN_RELATIVE_INCREASE=0.2,
    WAVE_PREDICTION_LABEL_MAD_FLOOR=1.0,
    WAVE_PREDICTION_CALIBRATION_HOLDOUT_FRACTION=0.2,
    WAVE_PREDICTION_MIN_CALIBRATION_ROWS=10,
    WAVE_PREDICTION_MIN_CALIBRATION_POSITIVES=2,
)

SUPPORTED_WAVE_FIXTURES: tuple[str, ...] = ("default", "sparse")
FIXTURE_END_DATE = pd.Timestamp("2026-03-15")
FIXTURE_REGIONS: tuple[str, ...] = ("BY", "HH")


def wave_fixture_names() -> tuple[str, ...]:
    return SUPPORTED_WAVE_FIXTURES


class FixtureWavePredictionService(WavePredictionService):
    """Wave service that loads deterministic synthetic source frames."""

    def __init__(
        self,
        fixture: str = "default",
        *,
        models_dir=None,
        settings: Any | None = None,
    ) -> None:
        if fixture not in SUPPORTED_WAVE_FIXTURES:
            raise ValueError(f"Unsupported wave fixture '{fixture}'.")
        self.fixture = fixture
        super().__init__(
            db=None,
            models_dir=models_dir,
            settings=settings or FIXTURE_WAVE_SETTINGS,
        )

    def _panel_end_date(self) -> pd.Timestamp:
        return FIXTURE_END_DATE.normalize()

    def _load_source_frames(
        self,
        *,
        pathogen: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> dict[str, Any]:
        del pathogen
        return build_fixture_source_frames(
            fixture=self.fixture,
            start_date=start_date,
            end_date=end_date,
        )


def build_fixture_source_frames(
    *,
    fixture: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> dict[str, Any]:
    if fixture not in SUPPORTED_WAVE_FIXTURES:
        raise ValueError(f"Unsupported wave fixture '{fixture}'.")

    truth = _build_truth_frame(fixture=fixture)
    wastewater = _build_wastewater_frame(truth=truth, start_date=start_date, end_date=end_date)
    grippeweb = _build_grippeweb_frame(truth=truth)
    are_consultation = _build_are_frame(truth=truth)
    weather = _build_weather_frame(start_date=start_date, end_date=end_date)
    holidays = {
        "BY": [
            (pd.Timestamp("2025-12-24"), pd.Timestamp("2026-01-06")),
            (pd.Timestamp("2026-02-16"), pd.Timestamp("2026-02-20")),
        ],
        "HH": [
            (pd.Timestamp("2025-12-22"), pd.Timestamp("2026-01-02")),
            (pd.Timestamp("2026-03-02"), pd.Timestamp("2026-03-06")),
        ],
    }
    populations = {"BY": 13_500_000.0, "HH": 1_900_000.0}
    return {
        "wastewater": wastewater,
        "truth": truth,
        "grippeweb": grippeweb,
        "influenza_ifsg": pd.DataFrame(),
        "rsv_ifsg": pd.DataFrame(),
        "are_consultation": are_consultation,
        "weather": weather,
        "holidays": holidays,
        "populations": populations,
    }


def _build_truth_frame(*, fixture: str) -> pd.DataFrame:
    week_starts = pd.date_range("2025-08-04", periods=36, freq="7D")
    rows: list[dict[str, Any]] = []
    for region in FIXTURE_REGIONS:
        state_offset = 1.0 if region == "BY" else 0.65
        week_index = np.arange(len(week_starts), dtype=float)
        if fixture == "default":
            baseline = 3.5 + 0.25 * np.sin(week_index / 2.8)
            wave_1 = 10.5 * np.exp(-((week_index - 18.0) ** 2) / 16.0)
            wave_2 = 9.5 * np.exp(-((week_index - 28.0) ** 2) / 14.0)
            values = baseline + state_offset + wave_1 + wave_2
        else:
            baseline = 4.2 + 0.25 * np.sin(week_index / 3.0)
            wave_1 = 1.1 * np.exp(-((week_index - 19.0) ** 2) / 25.0)
            wave_2 = 0.9 * np.exp(-((week_index - 29.0) ** 2) / 20.0)
            values = baseline + state_offset * 0.2 + wave_1 + wave_2

        for week_start, incidence in zip(week_starts, values, strict=False):
            rows.append(
                {
                    "bundesland": region,
                    "week_start": pd.Timestamp(week_start),
                    "available_date": pd.Timestamp(week_start) + pd.Timedelta(days=7),
                    "incidence": round(float(max(incidence, 0.1)), 3),
                    "truth_source": "survstat_weekly",
                }
            )
    return pd.DataFrame(rows)


def _build_wastewater_frame(
    *,
    truth: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    daily_dates = pd.date_range(start_date.normalize(), end_date.normalize(), freq="D")
    for region in FIXTURE_REGIONS:
        weekly_truth = truth.loc[truth["bundesland"] == region].sort_values("week_start")
        lead_index = weekly_truth["week_start"] - pd.Timedelta(days=7)
        lead_signal = weekly_truth["incidence"].astype(float).to_numpy() * 0.35
        interpolated = _interpolate_daily(lead_index, lead_signal, daily_dates)
        regional_bias = 0.4 if region == "BY" else 0.15
        for datum, value in zip(daily_dates, interpolated, strict=False):
            rows.append(
                {
                    "bundesland": region,
                    "datum": pd.Timestamp(datum),
                    "available_time": pd.Timestamp(datum),
                    "viral_load": round(float(max(value + regional_bias, 0.0)), 4),
                }
            )
    return pd.DataFrame(rows)


def _build_grippeweb_frame(*, truth: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for region in FIXTURE_REGIONS:
        weekly_truth = truth.loc[truth["bundesland"] == region].sort_values("week_start")
        for item in weekly_truth.itertuples(index=False):
            base = float(item.incidence)
            rows.append(
                {
                    "bundesland": region,
                    "datum": pd.Timestamp(item.week_start) + pd.Timedelta(days=2),
                    "available_time": pd.Timestamp(item.week_start) + pd.Timedelta(days=7),
                    "signal_type": "ARE",
                    "incidence": round(base * 10.0 + (15.0 if region == "BY" else 8.0), 3),
                }
            )
            rows.append(
                {
                    "bundesland": region,
                    "datum": pd.Timestamp(item.week_start) + pd.Timedelta(days=2),
                    "available_time": pd.Timestamp(item.week_start) + pd.Timedelta(days=7),
                    "signal_type": "ILI",
                    "incidence": round(base * 6.0 + (9.0 if region == "BY" else 4.0), 3),
                }
            )
    return pd.DataFrame(rows)


def _build_are_frame(*, truth: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for region in FIXTURE_REGIONS:
        weekly_truth = truth.loc[truth["bundesland"] == region].sort_values("week_start")
        for item in weekly_truth.itertuples(index=False):
            rows.append(
                {
                    "bundesland": region,
                    "datum": pd.Timestamp(item.week_start) + pd.Timedelta(days=3),
                    "available_time": pd.Timestamp(item.week_start) + pd.Timedelta(days=7),
                    "incidence": round(float(item.incidence) * 7.5 + (11.0 if region == "BY" else 6.0), 3),
                }
            )
    return pd.DataFrame(rows)


def _build_weather_frame(
    *,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    daily_dates = pd.date_range(start_date.normalize(), end_date.normalize() + pd.Timedelta(days=7), freq="D")
    for region in FIXTURE_REGIONS:
        region_offset = 0.8 if region == "BY" else -0.4
        for index, datum in enumerate(daily_dates):
            seasonal = np.sin(index / 7.0)
            temp = 2.5 + region_offset + seasonal * 6.0
            humidity = 72.0 - seasonal * 8.0 + (1.5 if region == "HH" else 0.0)
            rows.append(
                {
                    "bundesland": region,
                    "datum": pd.Timestamp(datum),
                    "available_time": pd.Timestamp(datum),
                    "data_type": "CURRENT",
                    "temp": round(float(temp), 3),
                    "humidity": round(float(humidity), 3),
                }
            )
            rows.append(
                {
                    "bundesland": region,
                    "datum": pd.Timestamp(datum),
                    "available_time": pd.Timestamp(datum) - pd.Timedelta(days=2),
                    "data_type": "DAILY_FORECAST",
                    "temp": round(float(temp + 0.9), 3),
                    "humidity": round(float(humidity - 1.7), 3),
                }
            )
    return pd.DataFrame(rows)


def _interpolate_daily(
    weekly_dates: pd.Series | pd.DatetimeIndex,
    weekly_values: np.ndarray,
    daily_dates: pd.DatetimeIndex,
) -> np.ndarray:
    series = pd.Series(
        np.asarray(weekly_values, dtype=float),
        index=pd.DatetimeIndex(pd.to_datetime(weekly_dates)).normalize(),
    ).sort_index()
    reindexed = series.reindex(daily_dates)
    interpolated = reindexed.interpolate(method="time").ffill().bfill()
    return interpolated.to_numpy(dtype=float)
