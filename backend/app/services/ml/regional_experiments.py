"""Offline experiment runner for regional pooled panel forecasting."""

from __future__ import annotations

import argparse
import json
import logging
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.db.session import get_db_context
from app.services.ml.regional_trainer import (
    REGIONAL_CLASSIFIER_CONFIG,
    REGIONAL_REGRESSOR_CONFIG,
    RegionalModelTrainer,
    _json_safe,
    _virus_slug,
)

logger = logging.getLogger(__name__)

_DEFAULT_EXPERIMENTS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "ml_models" / "regional_panel_experiments"
)


@dataclass
class ExperimentSpec:
    """Configuration for one offline experiment candidate."""

    name: str
    lookback_days: int = 900
    classifier_overrides: dict[str, Any] | None = None
    regressor_overrides: dict[str, dict[str, Any]] | None = None
    recency_weight_half_life_days: float | None = None


DEFAULT_EXPERIMENT_SPECS: list[ExperimentSpec] = [
    ExperimentSpec(name="baseline"),
    ExperimentSpec(
        name="recency_180d",
        recency_weight_half_life_days=180.0,
    ),
    ExperimentSpec(
        name="recency_120d_more_trees",
        recency_weight_half_life_days=120.0,
        classifier_overrides={
            "n_estimators": 220,
            "max_depth": 5,
            "learning_rate": 0.04,
            "subsample": 0.85,
            "colsample_bytree": 0.85,
        },
    ),
]


class RegionalExperimentTrainer(RegionalModelTrainer):
    """Regional trainer variant with configurable sample weighting and model params."""

    def __init__(
        self,
        db,
        *,
        models_dir: Path | None = None,
        classifier_config: dict[str, Any] | None = None,
        regressor_config: dict[str, dict[str, Any]] | None = None,
        recency_weight_half_life_days: float | None = None,
    ) -> None:
        super().__init__(db, models_dir=models_dir)
        self.classifier_config = deepcopy(classifier_config or REGIONAL_CLASSIFIER_CONFIG)
        self.regressor_config = deepcopy(regressor_config or REGIONAL_REGRESSOR_CONFIG)
        self.recency_weight_half_life_days = recency_weight_half_life_days

    def _fit_classifier(
        self,
        X: np.ndarray,
        y: np.ndarray,
        sample_weight: np.ndarray | None = None,
    ):
        positives = max(int(np.sum(y == 1)), 1)
        negatives = max(int(np.sum(y == 0)), 1)
        config = dict(self.classifier_config)
        config["scale_pos_weight"] = float(negatives / positives)
        model = __import__("xgboost").XGBClassifier(**config)
        fit_kwargs: dict[str, Any] = {}
        if sample_weight is not None:
            fit_kwargs["sample_weight"] = sample_weight
        model.fit(X, y, **fit_kwargs)
        return model

    def _fit_regressor(
        self,
        X: np.ndarray,
        y: np.ndarray,
        *,
        config: dict[str, Any],
        sample_weight: np.ndarray | None = None,
    ):
        merged_config = deepcopy(config)
        model = __import__("xgboost").XGBRegressor(**merged_config)
        fit_kwargs: dict[str, Any] = {}
        if sample_weight is not None:
            fit_kwargs["sample_weight"] = sample_weight
        model.fit(X, y, **fit_kwargs)
        return model

    def _sample_weights(self, as_of_dates) -> np.ndarray | None:
        if not self.recency_weight_half_life_days:
            return None
        dates = np.asarray(as_of_dates, dtype="datetime64[ns]")
        if len(dates) == 0:
            return None
        latest = dates.max()
        age_days = (latest - dates).astype("timedelta64[D]").astype(float)
        half_life = max(float(self.recency_weight_half_life_days), 1.0)
        weights = np.power(0.5, age_days / half_life)
        return np.clip(weights.astype(float), 0.05, 1.0)

    def _fit_classifier_from_frame(self, frame, feature_columns):
        return self._fit_classifier(
            frame[feature_columns].to_numpy(),
            frame["event_label"].to_numpy(),
            sample_weight=self._sample_weights(frame["as_of_date"].to_numpy()),
        )

    def _fit_regressor_from_frame(self, frame, feature_columns, config):
        return self._fit_regressor(
            frame[feature_columns].to_numpy(),
            frame["y_next_log"].to_numpy(),
            config=config,
            sample_weight=self._sample_weights(frame["as_of_date"].to_numpy()),
        )

    def _oof_classification_predictions(
        self,
        *,
        panel,
        labels,
        feature_columns,
    ):
        working = panel.copy()
        working["event_label"] = labels.astype(int)
        working["as_of_date"] = __import__("pandas").to_datetime(working["as_of_date"]).dt.normalize()
        splits = __import__("app.services.ml.regional_panel_utils", fromlist=["time_based_panel_splits"]).time_based_panel_splits(
            working["as_of_date"],
            n_splits=5,
            min_train_periods=90,
            min_test_periods=21,
        )
        if not splits:
            return None

        oof_frames = []
        for fold_idx, (train_dates, test_dates) in enumerate(splits):
            train_mask = working["as_of_date"].isin(train_dates)
            test_mask = working["as_of_date"].isin(test_dates)
            train_df = working.loc[train_mask].copy()
            test_df = working.loc[test_mask].copy()
            if train_df.empty or test_df.empty or train_df["event_label"].nunique() < 2:
                continue

            calib_split = self._calibration_split_dates(train_dates)
            if not calib_split:
                continue
            model_train_dates, cal_dates = calib_split
            model_train_df = train_df.loc[train_df["as_of_date"].isin(model_train_dates)].copy()
            cal_df = train_df.loc[train_df["as_of_date"].isin(cal_dates)].copy()
            if model_train_df.empty or cal_df.empty or model_train_df["event_label"].nunique() < 2:
                continue

            classifier = self._fit_classifier_from_frame(model_train_df, feature_columns)
            calibration = self._fit_calibrator(
                classifier.predict_proba(cal_df[feature_columns].to_numpy())[:, 1],
                cal_df["event_label"].to_numpy(),
            )
            raw_probs = classifier.predict_proba(test_df[feature_columns].to_numpy())[:, 1]
            calibrated_probs = self._apply_calibration(calibration, raw_probs)

            oof_frames.append(
                __import__("pandas").DataFrame(
                    {
                        "fold": fold_idx,
                        "as_of_date": test_df["as_of_date"].values,
                        "event_label": test_df["event_label"].values,
                        "event_probability_calibrated": calibrated_probs,
                        "event_probability_raw": raw_probs,
                    }
                )
            )

        if not oof_frames:
            return None
        return __import__("pandas").concat(oof_frames, ignore_index=True)

    def _build_backtest_bundle(
        self,
        *,
        panel,
        feature_columns,
        ww_only_columns,
        tau,
        kappa,
        action_threshold,
    ):
        working = panel.copy()
        working["event_label"] = self._event_labels(working, tau=tau, kappa=kappa)
        working["y_next_log"] = np.log1p(working["next_week_incidence"].astype(float).clip(lower=0.0))
        working["as_of_date"] = __import__("pandas").to_datetime(working["as_of_date"]).dt.normalize()
        working["target_week_start"] = __import__("pandas").to_datetime(working["target_week_start"]).dt.normalize()

        from app.services.ml.regional_panel_utils import time_based_panel_splits

        splits = time_based_panel_splits(
            working["as_of_date"],
            n_splits=5,
            min_train_periods=90,
            min_test_periods=21,
        )
        if not splits:
            raise ValueError("Unable to build time-based backtest splits for regional panel.")

        fold_frames = []
        fold_selection_summary = []
        for fold_idx, (train_dates, test_dates) in enumerate(splits):
            train_df = working.loc[working["as_of_date"].isin(train_dates)].copy()
            test_df = working.loc[working["as_of_date"].isin(test_dates)].copy()
            if train_df.empty or test_df.empty:
                continue

            fold_selection = self._select_event_definition(panel=train_df, feature_columns=feature_columns)
            fold_tau = float(fold_selection["tau"])
            fold_kappa = float(fold_selection["kappa"])
            fold_threshold = float(fold_selection["action_threshold"])

            train_df["event_label"] = self._event_labels(train_df, tau=fold_tau, kappa=fold_kappa)
            test_df["event_label"] = self._event_labels(test_df, tau=fold_tau, kappa=fold_kappa)
            if train_df["event_label"].nunique() < 2:
                continue

            calib_split = self._calibration_split_dates(train_dates)
            if not calib_split:
                continue
            model_train_dates, cal_dates = calib_split
            model_train_df = train_df.loc[train_df["as_of_date"].isin(model_train_dates)].copy()
            cal_df = train_df.loc[train_df["as_of_date"].isin(cal_dates)].copy()
            if model_train_df.empty or cal_df.empty or model_train_df["event_label"].nunique() < 2:
                continue

            classifier = self._fit_classifier_from_frame(model_train_df, feature_columns)
            calibration = self._fit_calibrator(
                classifier.predict_proba(cal_df[feature_columns].to_numpy())[:, 1],
                cal_df["event_label"].to_numpy(),
            )
            raw_prob = classifier.predict_proba(test_df[feature_columns].to_numpy())[:, 1]
            calibrated_prob = self._apply_calibration(calibration, raw_prob)

            ww_prob = self._amelag_only_probabilities(
                train_df=train_df,
                test_df=test_df,
                feature_columns=ww_only_columns,
            )

            reg_median = self._fit_regressor_from_frame(
                train_df,
                feature_columns,
                self.regressor_config["median"],
            )
            reg_lower = self._fit_regressor_from_frame(
                train_df,
                feature_columns,
                self.regressor_config["lower"],
            )
            reg_upper = self._fit_regressor_from_frame(
                train_df,
                feature_columns,
                self.regressor_config["upper"],
            )

            pred_log = reg_median.predict(test_df[feature_columns].to_numpy())
            pred_lo = reg_lower.predict(test_df[feature_columns].to_numpy())
            pred_hi = reg_upper.predict(test_df[feature_columns].to_numpy())
            pred_next = np.expm1(pred_log)
            pred_next_lo = np.expm1(pred_lo)
            pred_next_hi = np.expm1(pred_hi)

            persistence_prob = self._event_probability_from_prediction(
                predicted_next=test_df["current_known_incidence"].to_numpy(),
                current_known=test_df["current_known_incidence"].to_numpy(),
                baseline=test_df["seasonal_baseline"].to_numpy(),
                mad=test_df["seasonal_mad"].to_numpy(),
                tau=fold_tau,
                kappa=fold_kappa,
            )
            climatology_prob = self._event_probability_from_prediction(
                predicted_next=test_df["seasonal_baseline"].to_numpy(),
                current_known=test_df["current_known_incidence"].to_numpy(),
                baseline=test_df["seasonal_baseline"].to_numpy(),
                mad=test_df["seasonal_mad"].to_numpy(),
                tau=fold_tau,
                kappa=fold_kappa,
            )

            fold_selection_summary.append(
                {
                    "fold": fold_idx,
                    "train_start": str(min(train_dates)),
                    "train_end": str(max(train_dates)),
                    "test_start": str(min(test_dates)),
                    "test_end": str(max(test_dates)),
                    "selected_tau": fold_tau,
                    "selected_kappa": fold_kappa,
                    "action_threshold": fold_threshold,
                    "selection_precision": fold_selection.get("precision"),
                    "selection_recall": fold_selection.get("recall"),
                    "selection_pr_auc": fold_selection.get("pr_auc"),
                }
            )
            fold_frames.append(
                __import__("pandas").DataFrame(
                    {
                        "fold": fold_idx,
                        "virus_typ": test_df["virus_typ"].values,
                        "bundesland": test_df["bundesland"].values,
                        "bundesland_name": test_df["bundesland_name"].values,
                        "as_of_date": test_df["as_of_date"].values,
                        "target_week_start": test_df["target_week_start"].values,
                        "event_label": test_df["event_label"].values.astype(int),
                        "event_probability_calibrated": calibrated_prob,
                        "event_probability_raw": raw_prob,
                        "amelag_only_probability": ww_prob,
                        "persistence_probability": persistence_prob,
                        "climatology_probability": climatology_prob,
                        "current_known_incidence": test_df["current_known_incidence"].values.astype(float),
                        "next_week_incidence": test_df["next_week_incidence"].values.astype(float),
                        "expected_next_week_incidence": pred_next,
                        "prediction_interval_lower": pred_next_lo,
                        "prediction_interval_upper": pred_next_hi,
                        "selected_tau": fold_tau,
                        "selected_kappa": fold_kappa,
                        "action_threshold": fold_threshold,
                    }
                )
            )

        if not fold_frames:
            raise ValueError("Regional backtest produced no valid folds.")

        oof_frame = __import__("pandas").concat(fold_frames, ignore_index=True)
        aggregate_metrics = self._aggregate_metrics(frame=oof_frame, action_threshold=action_threshold)
        baselines = self._baseline_metrics(frame=oof_frame, action_threshold=action_threshold)
        quality_gate = __import__("app.services.ml.regional_panel_utils", fromlist=["quality_gate_from_metrics"]).quality_gate_from_metrics(
            metrics=aggregate_metrics,
            baseline_metrics=baselines,
        )
        backtest_payload = self._build_backtest_payload(
            frame=oof_frame,
            aggregate_metrics=aggregate_metrics,
            baselines=baselines,
            quality_gate=quality_gate,
            tau=tau,
            kappa=kappa,
            action_threshold=action_threshold,
            fold_selection_summary=fold_selection_summary,
        )
        return {
            "oof_frame": oof_frame,
            "aggregate_metrics": aggregate_metrics,
            "quality_gate": quality_gate,
            "backtest_payload": backtest_payload,
        }

    def _fit_final_models(
        self,
        *,
        panel,
        feature_columns,
        oof_frame,
    ):
        classifier = self._fit_classifier_from_frame(panel, feature_columns)
        calibration = self._fit_calibrator(
            oof_frame["event_probability_raw"].to_numpy(),
            oof_frame["event_label"].to_numpy(),
        )
        reg_median = self._fit_regressor_from_frame(panel, feature_columns, self.regressor_config["median"])
        reg_lower = self._fit_regressor_from_frame(panel, feature_columns, self.regressor_config["lower"])
        reg_upper = self._fit_regressor_from_frame(panel, feature_columns, self.regressor_config["upper"])
        return {
            "classifier": classifier,
            "calibration": calibration,
            "regressor_median": reg_median,
            "regressor_lower": reg_lower,
            "regressor_upper": reg_upper,
        }


class RegionalExperimentRunner:
    """Run offline experiment variants against the current persisted baseline."""

    def __init__(
        self,
        db,
        *,
        baseline_models_dir: Path | None = None,
        experiments_dir: Path | None = None,
    ) -> None:
        self.db = db
        self.baseline_models_dir = baseline_models_dir or (
            Path(__file__).resolve().parent.parent.parent / "ml_models" / "regional_panel"
        )
        self.experiments_dir = experiments_dir or _DEFAULT_EXPERIMENTS_DIR

    def run(
        self,
        *,
        virus_typ: str = "Influenza A",
        specs: list[ExperimentSpec] | None = None,
    ) -> dict[str, Any]:
        specs = specs or DEFAULT_EXPERIMENT_SPECS
        baseline_trainer = RegionalModelTrainer(self.db, models_dir=self.baseline_models_dir)
        baseline_payload = baseline_trainer.load_artifacts(virus_typ=virus_typ)
        baseline_metrics = ((baseline_payload.get("metadata") or {}).get("aggregate_metrics") or {})

        runs: list[dict[str, Any]] = []
        for spec in specs:
            model_dir = self.experiments_dir / _virus_slug(virus_typ) / spec.name
            trainer = RegionalExperimentTrainer(
                self.db,
                models_dir=model_dir,
                classifier_config=self._merged_classifier_config(spec),
                regressor_config=self._merged_regressor_config(spec),
                recency_weight_half_life_days=spec.recency_weight_half_life_days,
            )
            result = trainer.train_all_regions(
                virus_typ=virus_typ,
                lookback_days=spec.lookback_days,
                persist=True,
            )
            metrics = result.get("aggregate_metrics") or {}
            runs.append(
                {
                    "name": spec.name,
                    "lookback_days": spec.lookback_days,
                    "recency_weight_half_life_days": spec.recency_weight_half_life_days,
                    "classifier_overrides": spec.classifier_overrides or {},
                    "regressor_overrides": spec.regressor_overrides or {},
                    "aggregate_metrics": metrics,
                    "quality_gate": result.get("quality_gate") or {},
                    "delta_vs_baseline": self._metric_delta(metrics, baseline_metrics),
                    "model_dir": str(model_dir),
                }
            )

        ranking = sorted(
            runs,
            key=lambda item: (
                float((item.get("aggregate_metrics") or {}).get("precision_at_top3") or 0.0),
                float((item.get("aggregate_metrics") or {}).get("pr_auc") or 0.0),
                -float((item.get("aggregate_metrics") or {}).get("ece") or 1.0),
                -float((item.get("aggregate_metrics") or {}).get("activation_false_positive_rate") or 1.0),
            ),
            reverse=True,
        )

        summary = {
            "virus_typ": virus_typ,
            "baseline_metrics": baseline_metrics,
            "experiment_count": len(ranking),
            "best_experiment": ranking[0]["name"] if ranking else None,
            "generated_at": datetime.utcnow().isoformat(),
            "runs": ranking,
        }
        summary_path = self.experiments_dir / _virus_slug(virus_typ) / "summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(_json_safe(summary), indent=2))
        return summary

    @staticmethod
    def _merged_classifier_config(spec: ExperimentSpec) -> dict[str, Any]:
        config = deepcopy(REGIONAL_CLASSIFIER_CONFIG)
        if spec.classifier_overrides:
            config.update(spec.classifier_overrides)
        return config

    @staticmethod
    def _merged_regressor_config(spec: ExperimentSpec) -> dict[str, dict[str, Any]]:
        config = deepcopy(REGIONAL_REGRESSOR_CONFIG)
        if spec.regressor_overrides:
            for key, overrides in spec.regressor_overrides.items():
                if key in config:
                    config[key].update(overrides)
        return config

    @staticmethod
    def _metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
        deltas: dict[str, float] = {}
        for metric in (
            "precision_at_top3",
            "precision_at_top5",
            "pr_auc",
            "brier_score",
            "ece",
            "activation_false_positive_rate",
        ):
            if metric in candidate and metric in baseline:
                deltas[metric] = round(float(candidate[metric]) - float(baseline[metric]), 6)
        return deltas


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline regional panel experiments.")
    parser.add_argument("--virus", default="Influenza A", help="Virus type to evaluate.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    with get_db_context() as db:
        runner = RegionalExperimentRunner(db)
        summary = runner.run(virus_typ=args.virus)
    print(json.dumps(_json_safe(summary), indent=2))


if __name__ == "__main__":
    main()
