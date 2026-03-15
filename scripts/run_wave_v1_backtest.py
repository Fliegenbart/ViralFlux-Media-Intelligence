#!/usr/bin/env python3
"""Run the wave-v1 evaluation harness against fixtures or a real DB."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("OPENWEATHER_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error

from app.db.session import get_db_context
from app.services.ml.training_contract import normalize_virus_type
from app.services.ml.wave_prediction_fixtures import (
    FIXTURE_WAVE_SETTINGS,
    FixtureWavePredictionService,
    wave_fixture_names,
)
from app.services.ml.wave_prediction_service import WavePredictionService
from app.services.ml.wave_prediction_utils import (
    build_backtest_splits,
    get_classification_feature_columns,
    get_regression_feature_columns,
    json_safe,
    safe_mape,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = _resolve_output_dir(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        if args.source == "db":
            with get_db_context() as db:
                service = WavePredictionService(
                    db=db,
                    models_dir=output_dir / "model_artifacts",
                )
                return _run_harness(
                    args=args,
                    output_dir=output_dir,
                    service=service,
                    source_label="db",
                )

        service = FixtureWavePredictionService(
            fixture=args.fixture,
            models_dir=output_dir / "model_artifacts",
            settings=FIXTURE_WAVE_SETTINGS,
        )
        return _run_harness(
            args=args,
            output_dir=output_dir,
            service=service,
            source_label=f"fixture:{args.fixture}",
        )
    except Exception as exc:
        _write_json(
            output_dir / "fold_metrics.json",
            {
                "status": "error",
                "source": args.source,
                "fixture": args.fixture if args.source == "fixture" else None,
                "pathogen": args.pathogen,
                "region": args.region,
                "horizon_days": int(args.horizon),
                "error": str(exc),
            },
        )
        print(f"Wave harness failed: {exc}")
        return 1


def _run_harness(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    service: WavePredictionService,
    source_label: str,
) -> int:
    lookback_days = int(service.settings.WAVE_PREDICTION_LOOKBACK_DAYS)
    source_status = _build_source_status(
        service=service,
        pathogen=args.pathogen,
        lookback_days=lookback_days,
        horizon_days=args.horizon,
    )

    panel = service.build_wave_panel(
        pathogen=args.pathogen,
        region=args.region,
        lookback_days=lookback_days,
        horizon_days=args.horizon,
    )
    training_frame = panel.dropna(subset=["target_regression", "target_wave14"]).copy()

    panel_summary = _build_panel_summary(
        panel=panel,
        training_frame=training_frame,
        settings=service.settings,
        source_status=source_status,
        source_label=source_label,
    )
    _write_json(output_dir / "panel_summary.json", panel_summary)

    leakage_spotcheck = _build_leakage_spotcheck(panel)
    leakage_spotcheck.to_csv(output_dir / "leakage_spotcheck.csv", index=False)

    data_error = _preflight_error(
        training_frame=training_frame,
        settings=service.settings,
        source_label=source_label,
        source_status=source_status,
    )
    if data_error is not None:
        _write_json(
            output_dir / "fold_metrics.json",
            {
                "status": "error",
                "source": source_label,
                "pathogen": args.pathogen,
                "region": args.region,
                "horizon_days": int(args.horizon),
                "error": data_error,
                "panel_summary": panel_summary,
            },
        )
        print(data_error)
        return 2

    backtest = service.run_wave_backtest(
        pathogen=args.pathogen,
        region=args.region,
        lookback_days=lookback_days,
        horizon_days=args.horizon,
        panel=training_frame,
        include_oof_predictions=True,
    )
    if backtest.get("status") != "ok":
        _write_json(
            output_dir / "fold_metrics.json",
            {
                "status": "error",
                "source": source_label,
                "pathogen": args.pathogen,
                "region": args.region,
                "horizon_days": int(args.horizon),
                "error": backtest.get("error") or "Wave backtest failed.",
                "panel_summary": panel_summary,
            },
        )
        print(backtest.get("error") or "Wave backtest failed.")
        return 2

    predictions = pd.DataFrame(backtest.get("oof_predictions") or [])
    predictions, prediction_output = _normalize_prediction_output(predictions)
    predictions.to_csv(output_dir / "predictions.csv", index=False)

    baseline_metrics = _baseline_report(training_frame=training_frame, settings=service.settings)
    fold_metrics_payload = {
        "status": "ok",
        "source": source_label,
        "pathogen": args.pathogen,
        "region": args.region,
        "horizon_days": int(args.horizon),
        "folds": backtest.get("folds") or [],
        "aggregate_metrics": backtest.get("aggregate_metrics") or {},
        "confusion_matrix": ((backtest.get("aggregate_metrics") or {}).get("confusion_matrix") or {}),
        "baseline_metrics": baseline_metrics,
        "calibration_summary": {
            "probability_output_folds": int(
                ((backtest.get("aggregate_metrics") or {}).get("probability_output_folds") or 0)
            ),
            "decision_output_field": prediction_output["decision_output_field"],
            "mixed_fold_outputs": prediction_output["mixed_fold_outputs"],
            "oof_rows": int(backtest.get("oof_rows") or 0),
        },
    }
    _write_json(output_dir / "fold_metrics.json", fold_metrics_payload)

    training_result = service.train_models(
        pathogen=args.pathogen,
        region=args.region,
        lookback_days=lookback_days,
        horizon_days=args.horizon,
        persist=True,
    )
    if training_result.get("status") != "ok":
        _write_json(
            output_dir / "top_features.json",
            {
                "status": "error",
                "error": training_result.get("error") or "Training failed after successful backtest.",
            },
        )
        print(training_result.get("error") or "Training failed after successful backtest.")
        return 2

    top_features_payload = {
        "status": "ok",
        "pathogen": training_result.get("pathogen"),
        "rows": training_result.get("rows"),
        "positives": training_result.get("positives"),
        "top_features": ((training_result.get("metadata") or {}).get("top_features") or {}),
    }
    _write_json(output_dir / "top_features.json", top_features_payload)

    if args.region:
        prediction_preview = service.run_wave_prediction(
            pathogen=args.pathogen,
            region=args.region,
            horizon_days=args.horizon,
        )
        _write_json(output_dir / "prediction_preview.json", prediction_preview)

    print(f"Wrote evaluation artifacts to {output_dir}")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the wave-v1 evaluation harness.")
    parser.add_argument("--pathogen", default="Influenza A", help="Pathogen to evaluate.")
    parser.add_argument("--region", default="BY", help="Bundesland code to evaluate.")
    parser.add_argument("--horizon", type=int, default=14, help="Prediction horizon in days.")
    parser.add_argument(
        "--source",
        choices=("fixture", "db"),
        default="fixture",
        help="Use synthetic fixtures or the configured Postgres DB.",
    )
    parser.add_argument(
        "--fixture",
        default="default",
        choices=wave_fixture_names(),
        help="Synthetic fixture to load when --source=fixture.",
    )
    parser.add_argument(
        "--output-dir",
        help="Optional output directory. Defaults to data/processed/wave_eval/<timestamp>.",
    )
    return parser.parse_args(argv)


def _resolve_output_dir(raw_output_dir: str | None) -> Path:
    if raw_output_dir:
        return Path(raw_output_dir).expanduser().resolve()
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return (REPO_ROOT / "data" / "processed" / "wave_eval" / timestamp).resolve()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(json_safe(payload), handle, indent=2, ensure_ascii=True)


def _build_panel_summary(
    *,
    panel: pd.DataFrame,
    training_frame: pd.DataFrame,
    settings: Any,
    source_status: dict[str, Any],
    source_label: str,
) -> dict[str, Any]:
    feature_columns = sorted(
        set(get_regression_feature_columns(panel)) | set(get_classification_feature_columns(panel))
    ) if not panel.empty else []
    missing_rates = (
        panel[feature_columns].isna().mean().sort_values(ascending=False)
        if feature_columns
        else pd.Series(dtype=float)
    )
    availability = {
        column: round(float(panel[column].mean()), 6)
        for column in panel.columns
        if column.endswith("_available")
    }
    positive_by_region = (
        training_frame.groupby("region")["target_wave14"].sum().sort_values(ascending=False).astype(int).to_dict()
        if not training_frame.empty
        else {}
    )
    positive_by_pathogen = (
        training_frame.groupby("pathogen")["target_wave14"].sum().sort_values(ascending=False).astype(int).to_dict()
        if not training_frame.empty
        else {}
    )

    warnings: list[str] = []
    if panel.empty:
        warnings.append("Panel is empty.")
    if len(training_frame) < int(settings.WAVE_PREDICTION_MIN_TRAIN_ROWS):
        warnings.append(
            f"Training rows below minimum: {len(training_frame)} < {int(settings.WAVE_PREDICTION_MIN_TRAIN_ROWS)}."
        )
    positives = int(training_frame["target_wave14"].sum()) if not training_frame.empty else 0
    if positives < int(settings.WAVE_PREDICTION_MIN_POSITIVE_ROWS):
        warnings.append(
            f"Positive rows below minimum: {positives} < {int(settings.WAVE_PREDICTION_MIN_POSITIVE_ROWS)}."
        )
    for region, count in positive_by_region.items():
        if int(count) <= 1:
            warnings.append(f"Region {region} has {int(count)} positive wave_start rows.")

    return {
        "source": source_label,
        "rows": int(len(panel)),
        "training_rows": int(len(training_frame)),
        "date_range": {
            "start": str(panel["as_of_date"].min()) if not panel.empty else None,
            "end": str(panel["as_of_date"].max()) if not panel.empty else None,
        },
        "positive_rows": positives,
        "positive_rate": (
            round(float(training_frame["target_wave14"].mean()), 6)
            if not training_frame.empty
            else None
        ),
        "positive_by_region": positive_by_region,
        "positive_by_pathogen": positive_by_pathogen,
        "source_coverage": availability,
        "top_missing_features": [
            {"feature": str(feature), "missing_rate": round(float(rate), 6)}
            for feature, rate in missing_rates.head(20).items()
        ],
        "source_status": source_status,
        "thin_series_warnings": warnings,
    }


def _build_leakage_spotcheck(panel: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "as_of_date",
        "region",
        "pathogen",
        "source_truth_week_start",
        "source_truth_available_date",
        "target_week_start",
        "wave_event_date",
        "target_wave14",
        "target_regression",
        "raw_truth_incidence",
        "truth_level",
        "truth_lag_7",
        "truth_rolling_mean_7",
        "truth_rolling_mean_14",
        "raw_wastewater_level",
        "wastewater_level",
        "wastewater_lag_7",
        "wastewater_rolling_mean_7",
        "raw_grippeweb_are",
        "grippeweb_are_level",
        "raw_consultation_are",
        "consultation_are_level",
        "avg_temp_7",
        "weather_forecast_avg_temp_next_7",
        "avg_humidity_7",
        "weather_forecast_avg_humidity_next_7",
        "is_school_holiday",
        "days_until_next_holiday_start",
    ]
    if panel.empty:
        return pd.DataFrame(columns=columns)

    frame = panel.sort_values("as_of_date").reset_index(drop=True)
    positive_positions = frame.index[frame["target_wave14"] == 1].tolist()
    if positive_positions:
        start = max(int(positive_positions[0]) - 15, 0)
    else:
        start = max(len(frame) - 30, 0)
    spotcheck = frame.iloc[start : start + 30].copy()
    visible_columns = [column for column in columns if column in spotcheck.columns]
    return spotcheck.loc[:, visible_columns]


def _preflight_error(
    *,
    training_frame: pd.DataFrame,
    settings: Any,
    source_label: str,
    source_status: dict[str, Any],
) -> str | None:
    truth_rows = int((source_status.get("truth") or {}).get("rows") or 0)
    truth_hint = ""
    if source_label == "db" and truth_rows == 0:
        truth_hint = (
            " SurvStat truth is currently missing; wave evaluation needs weekly or kreis-level SurvStat "
            "imported via /api/v1/ingest/survstat-local or /api/v1/ingest/survstat-upload."
        )
    if training_frame.empty:
        return f"No training rows available after dropping rows without targets.{truth_hint}"
    if len(training_frame) < int(settings.WAVE_PREDICTION_MIN_TRAIN_ROWS):
        return (
            f"Insufficient training rows for {source_label} run: "
            f"{len(training_frame)} < {int(settings.WAVE_PREDICTION_MIN_TRAIN_ROWS)}.{truth_hint}"
        )
    positives = int(training_frame["target_wave14"].sum())
    if positives < int(settings.WAVE_PREDICTION_MIN_POSITIVE_ROWS):
        return (
            f"Insufficient positive wave_start rows for {source_label} run: "
            f"{positives} < {int(settings.WAVE_PREDICTION_MIN_POSITIVE_ROWS)}.{truth_hint}"
        )
    return None


def _build_source_status(
    *,
    service: WavePredictionService,
    pathogen: str,
    lookback_days: int,
    horizon_days: int,
) -> dict[str, Any]:
    normalized_pathogen = normalize_virus_type(pathogen)
    end_date = service._panel_end_date()
    start_date = end_date - pd.Timedelta(days=lookback_days)
    history_start = start_date - pd.Timedelta(days=730)
    source_frames = service._load_source_frames(
        pathogen=normalized_pathogen,
        start_date=history_start,
        end_date=end_date + pd.Timedelta(days=horizon_days),
    )

    status: dict[str, Any] = {}
    for name, payload in source_frames.items():
        if isinstance(payload, pd.DataFrame):
            status[name] = _frame_source_status(payload)
        elif isinstance(payload, dict):
            status[name] = {
                "entries": int(len(payload)),
                "sample_keys": sorted(str(key) for key in list(payload.keys())[:5]),
            }
        else:
            status[name] = {"type": type(payload).__name__}
    return status


def _frame_source_status(frame: pd.DataFrame) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {"rows": 0}

    payload: dict[str, Any] = {"rows": int(len(frame))}
    for column in ("week_start", "datum", "available_date", "available_time"):
        if column in frame.columns:
            series = pd.to_datetime(frame[column], errors="coerce").dropna()
            if not series.empty:
                payload[f"{column}_min"] = str(series.min())
                payload[f"{column}_max"] = str(series.max())
    if "bundesland" in frame.columns:
        payload["regions"] = int(frame["bundesland"].dropna().nunique())
    elif "region" in frame.columns:
        payload["regions"] = int(frame["region"].dropna().nunique())
    return payload


def _baseline_report(*, training_frame: pd.DataFrame, settings: Any) -> dict[str, Any]:
    unique_dates = sorted(pd.to_datetime(training_frame["as_of_date"]).dt.normalize().unique())
    splits = build_backtest_splits(
        unique_dates,
        n_splits=int(settings.WAVE_PREDICTION_BACKTEST_FOLDS),
        min_train_periods=int(settings.WAVE_PREDICTION_MIN_TRAIN_PERIODS),
        min_test_periods=int(settings.WAVE_PREDICTION_MIN_TEST_PERIODS),
    )
    if not splits:
        return {}

    baselines = {
        "persistence": {"folds": []},
        "climatology": {"folds": []},
    }
    for fold_idx, (train_dates, test_dates) in enumerate(splits, start=1):
        train_frame = training_frame.loc[training_frame["as_of_date"].isin(train_dates)].copy()
        test_frame = training_frame.loc[training_frame["as_of_date"].isin(test_dates)].copy()
        if train_frame.empty or test_frame.empty:
            continue

        y_true = test_frame["target_regression"].astype(float).to_numpy()
        persistence_pred = test_frame["raw_truth_incidence"].astype(float).to_numpy()
        climatology_pred = _climatology_prediction(train_frame=train_frame, test_frame=test_frame)

        baselines["persistence"]["folds"].append(
            _regression_metrics_payload(
                fold_idx=fold_idx,
                y_true=y_true,
                y_pred=persistence_pred,
            )
        )
        baselines["climatology"]["folds"].append(
            _regression_metrics_payload(
                fold_idx=fold_idx,
                y_true=y_true,
                y_pred=climatology_pred,
            )
        )

    for payload in baselines.values():
        payload["aggregate"] = _aggregate_regression_metrics(payload["folds"])
    return baselines


def _climatology_prediction(*, train_frame: pd.DataFrame, test_frame: pd.DataFrame) -> np.ndarray:
    working = train_frame.copy()
    working["target_iso_week"] = pd.to_datetime(working["target_week_start"]).dt.isocalendar().week.astype(int)
    by_region_week = (
        working.groupby(["region", "target_iso_week"])["target_regression"].median().to_dict()
    )
    by_region = working.groupby("region")["target_regression"].median().to_dict()
    global_median = float(working["target_regression"].median())

    predictions: list[float] = []
    for item in test_frame.itertuples(index=False):
        iso_week = int(pd.Timestamp(item.target_week_start).isocalendar().week)
        prediction = by_region_week.get((item.region, iso_week))
        if prediction is None:
            prediction = by_region.get(item.region, global_median)
        predictions.append(float(prediction))
    return np.asarray(predictions, dtype=float)


def _regression_metrics_payload(*, fold_idx: int, y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    return {
        "fold": int(fold_idx),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(np.mean((y_true - y_pred) ** 2))),
        "mape": safe_mape(y_true, y_pred),
    }


def _aggregate_regression_metrics(folds: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate: dict[str, Any] = {"fold_count": int(len(folds))}
    for key in ("mae", "rmse", "mape"):
        values = [float(item[key]) for item in folds if item.get(key) is not None]
        aggregate[key] = float(np.mean(values)) if values else None
    return aggregate


def _normalize_prediction_output(predictions: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    summary = {
        "decision_output_field": None,
        "mixed_fold_outputs": False,
    }
    if predictions.empty:
        return predictions, summary

    has_probability = "wave_probability" in predictions.columns
    has_score = "wave_score" in predictions.columns
    if has_probability and has_score:
        probability_non_null = predictions["wave_probability"].notna()
        score_non_null = predictions["wave_score"].notna()
        if probability_non_null.all() and not score_non_null.any():
            predictions = predictions.drop(columns=["wave_score"])
            summary["decision_output_field"] = "wave_probability"
        elif score_non_null.all() and not probability_non_null.any():
            predictions = predictions.drop(columns=["wave_probability"])
            summary["decision_output_field"] = "wave_score"
        else:
            predictions["wave_score"] = predictions["decision_score"].astype(float)
            predictions = predictions.drop(columns=["wave_probability"])
            summary["decision_output_field"] = "wave_score"
            summary["mixed_fold_outputs"] = True
    elif has_probability:
        summary["decision_output_field"] = "wave_probability"
    elif has_score:
        summary["decision_output_field"] = "wave_score"
    elif "decision_score" in predictions.columns:
        predictions["wave_score"] = predictions["decision_score"].astype(float)
        summary["decision_output_field"] = "wave_score"

    return predictions, summary


if __name__ == "__main__":
    raise SystemExit(main())
