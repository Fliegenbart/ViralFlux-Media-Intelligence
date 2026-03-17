"""Targeted h7-only pilot training and calibration experiment helpers."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
from xgboost import XGBClassifier, XGBRegressor

from app.services.ml.forecast_horizon_utils import (
    regional_horizon_pilot_status,
    regional_model_artifact_dir,
)
from app.services.ml.regional_trainer import (
    REGIONAL_CLASSIFIER_CONFIG,
    REGIONAL_REGRESSOR_CONFIG,
    CALIBRATION_GUARD_EPSILON,
    RegionalModelTrainer,
    _json_safe,
    _virus_slug,
)

logger = logging.getLogger(__name__)

DAY_ONE_PILOT_VIRUS_TYPES: tuple[str, str, str] = (
    "Influenza A",
    "Influenza B",
    "RSV A",
)
H7_PILOT_ONLY_HORIZON = 7
DEFAULT_H7_PILOT_MODELS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "ml_models" / "regional_panel_h7_pilot_only"
)
_DEFAULT_BASELINE_MODELS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "ml_models" / "regional_panel"
)


def _clip_probabilities(raw_probabilities: Sequence[float]) -> np.ndarray:
    return np.clip(np.asarray(raw_probabilities, dtype=float), 0.001, 0.999)


def _format_decimal_token(value: float) -> str:
    text = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return text.replace("-", "m").replace(".", "p")


@dataclass(frozen=True)
class CalibrationExperimentSpec:
    """One local calibration family for a pilot-only experiment."""

    strategy: str
    temperatures: tuple[float, ...] = ()
    alphas: tuple[float, ...] = ()
    quantile_bins: int = 8
    smoothing: float = 4.0


@dataclass(frozen=True)
class FeatureSelectionSpec:
    """Column selection rules for a pilot-only feature subset."""

    include_columns: tuple[str, ...] = ()
    include_prefixes: tuple[str, ...] = ()
    exclude_columns: tuple[str, ...] = ()
    exclude_prefixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PilotExperimentSpec:
    """Configuration for one h7-only pilot experiment run."""

    name: str
    description: str
    lookback_days: int = 900
    feature_selection: FeatureSelectionSpec | None = None
    recency_weight_half_life_days: float | None = None
    signal_agreement_weight: float = 0.0
    classifier_overrides: dict[str, Any] | None = None
    regressor_overrides: dict[str, dict[str, Any]] | None = None
    calibration_experiments: tuple[CalibrationExperimentSpec, ...] = ()


@dataclass
class LogitTemperatureCalibration:
    """Monotone temperature-like logit remapping."""

    temperature: float

    def predict(self, raw_probabilities: Sequence[float]) -> np.ndarray:
        probabilities = _clip_probabilities(raw_probabilities)
        logits = np.log(probabilities / (1.0 - probabilities))
        scaled = logits / max(float(self.temperature), 0.05)
        return 1.0 / (1.0 + np.exp(-scaled))


@dataclass
class ShrinkageBlendCalibration:
    """Blend raw probabilities toward a fitted prior rate."""

    alpha: float
    prior: float

    def predict(self, raw_probabilities: Sequence[float]) -> np.ndarray:
        probabilities = _clip_probabilities(raw_probabilities)
        alpha = max(0.0, min(1.0, float(self.alpha)))
        return np.clip(((1.0 - alpha) * probabilities) + (alpha * float(self.prior)), 0.001, 0.999)


@dataclass
class QuantileSmoothingCalibration:
    """Smoothed monotone quantile-bin remapping."""

    edges: tuple[float, ...]
    values: tuple[float, ...]

    def predict(self, raw_probabilities: Sequence[float]) -> np.ndarray:
        probabilities = _clip_probabilities(raw_probabilities)
        if len(self.edges) < 2 or len(self.values) == 0:
            return probabilities
        bucket_ids = np.digitize(probabilities, np.asarray(self.edges[1:-1], dtype=float), right=True)
        values = np.asarray(self.values, dtype=float)
        return np.clip(values[np.clip(bucket_ids, 0, len(values) - 1)], 0.001, 0.999)


RSV_SIGNAL_PREFIXES = (
    "ifsg_rsv_",
    "survstat_",
    "ww_",
    "neighbor_ww_",
    "national_ww_",
    "grippeweb_ili_",
    "grippeweb_are_",
)

RSV_CONTEXT_PREFIXES = RSV_SIGNAL_PREFIXES + ("state_",)
RSV_SHARED_CONTEXT_COLUMNS = (
    "state_population_millions",
    "ww_sites_per_million",
    "state_neighbor_count",
    "state_is_city_state",
    "target_week_iso",
    "target_holiday_share",
    "target_holiday_any",
)

RSV_SIGNAL_CORE_SELECTION = FeatureSelectionSpec(
    include_prefixes=RSV_SIGNAL_PREFIXES,
    include_columns=RSV_SHARED_CONTEXT_COLUMNS,
    exclude_prefixes=(
        "weather_",
        "pollen_",
        "xdisease_",
        "sars_",
    ),
)

RSV_SIGNAL_CONTEXT_SELECTION = FeatureSelectionSpec(
    include_prefixes=RSV_CONTEXT_PREFIXES,
    include_columns=RSV_SHARED_CONTEXT_COLUMNS,
    exclude_prefixes=(
        "weather_",
        "pollen_",
        "xdisease_",
        "sars_",
    ),
)


BASELINE_GUARD_SPEC = PilotExperimentSpec(
    name="baseline_guard",
    description="Current live-compatible guarded calibration path with raw/isotonic only.",
)

INFLUENZA_H7_CALIBRATION_SPECS: tuple[PilotExperimentSpec, ...] = (
    BASELINE_GUARD_SPEC,
    PilotExperimentSpec(
        name="logit_temperature_grid",
        description="Threshold-neutral monotone temperature remapping grid.",
        calibration_experiments=(
            CalibrationExperimentSpec(
                strategy="logit_temperature",
                temperatures=(1.1, 1.25, 1.5, 1.75, 2.0),
            ),
        ),
    ),
    PilotExperimentSpec(
        name="shrinkage_blend_grid",
        description="Probability shrinkage toward the fitted event rate.",
        calibration_experiments=(
            CalibrationExperimentSpec(
                strategy="shrinkage_blend",
                alphas=(0.05, 0.1, 0.15, 0.2, 0.25, 0.3),
            ),
        ),
    ),
    PilotExperimentSpec(
        name="quantile_smoothing_q8",
        description="Quantile-binned monotone smoothing with Laplace-style regularization.",
        calibration_experiments=(
            CalibrationExperimentSpec(
                strategy="quantile_smoothing",
                quantile_bins=8,
                smoothing=4.0,
            ),
        ),
    ),
)


RSV_H7_RANKING_SPECS: tuple[PilotExperimentSpec, ...] = (
    BASELINE_GUARD_SPEC,
    PilotExperimentSpec(
        name="rsv_signal_core",
        description="RSV-only signal subset that trims noisy weather, pollen, and cross-virus features.",
        feature_selection=RSV_SIGNAL_CORE_SELECTION,
    ),
    PilotExperimentSpec(
        name="rsv_signal_core_weighted",
        description="RSV signal subset with stronger recency and signal-agreement weighting.",
        feature_selection=RSV_SIGNAL_CORE_SELECTION,
        recency_weight_half_life_days=180.0,
        signal_agreement_weight=0.35,
    ),
    PilotExperimentSpec(
        name="rsv_signal_context_regularized",
        description="RSV signal subset with state-context dummies and tighter tree regularization.",
        feature_selection=RSV_SIGNAL_CONTEXT_SELECTION,
        recency_weight_half_life_days=120.0,
        signal_agreement_weight=0.45,
        classifier_overrides={
            "n_estimators": 220,
            "max_depth": 3,
            "learning_rate": 0.04,
            "subsample": 0.85,
            "colsample_bytree": 0.8,
            "min_child_weight": 4.0,
            "gamma": 0.15,
            "reg_lambda": 1.5,
            "reg_alpha": 0.05,
        },
    ),
)


def default_h7_pilot_specs_by_virus(
    virus_types: Sequence[str] | None = None,
) -> dict[str, tuple[PilotExperimentSpec, ...]]:
    selected = tuple(virus_types or DAY_ONE_PILOT_VIRUS_TYPES)
    return {
        virus_typ: (BASELINE_GUARD_SPEC,)
        for virus_typ in selected
    }


def default_h7_influenza_calibration_specs_by_virus(
    virus_types: Sequence[str] | None = None,
) -> dict[str, tuple[PilotExperimentSpec, ...]]:
    selected = tuple(virus_types or ("Influenza A", "Influenza B"))
    spec_map: dict[str, tuple[PilotExperimentSpec, ...]] = {}
    for virus_typ in selected:
        if virus_typ in {"Influenza A", "Influenza B"}:
            spec_map[virus_typ] = INFLUENZA_H7_CALIBRATION_SPECS
        else:
            spec_map[virus_typ] = (BASELINE_GUARD_SPEC,)
    return spec_map


def default_h7_rsv_ranking_specs_by_virus(
    virus_types: Sequence[str] | None = None,
) -> dict[str, tuple[PilotExperimentSpec, ...]]:
    selected = tuple(virus_types or ("RSV A",))
    spec_map: dict[str, tuple[PilotExperimentSpec, ...]] = {}
    for virus_typ in selected:
        if virus_typ == "RSV A":
            spec_map[virus_typ] = RSV_H7_RANKING_SPECS
        else:
            spec_map[virus_typ] = (BASELINE_GUARD_SPEC,)
    return spec_map


class PilotH7ExperimentTrainer(RegionalModelTrainer):
    """Regional trainer variant for h7-only pilot experiments."""

    def __init__(
        self,
        db,
        *,
        models_dir: Path | None = None,
        feature_selection: FeatureSelectionSpec | None = None,
        recency_weight_half_life_days: float | None = None,
        signal_agreement_weight: float = 0.0,
        classifier_config: dict[str, Any] | None = None,
        regressor_config: dict[str, dict[str, Any]] | None = None,
        calibration_experiments: Sequence[CalibrationExperimentSpec] | None = None,
    ) -> None:
        super().__init__(db, models_dir=models_dir)
        self.feature_selection = feature_selection
        self.recency_weight_half_life_days = recency_weight_half_life_days
        self.signal_agreement_weight = float(signal_agreement_weight or 0.0)
        self.classifier_config = deepcopy(classifier_config or REGIONAL_CLASSIFIER_CONFIG)
        self.regressor_config = deepcopy(regressor_config or REGIONAL_REGRESSOR_CONFIG)
        self.calibration_experiments = tuple(calibration_experiments or ())

    def _feature_columns(self, panel) -> list[str]:
        columns = super()._feature_columns(panel)
        if self.feature_selection is None or not columns:
            return columns

        selection = self.feature_selection
        include_columns = set(selection.include_columns)
        include_prefixes = selection.include_prefixes
        exclude_columns = set(selection.exclude_columns)
        exclude_prefixes = selection.exclude_prefixes

        filtered: list[str] = []
        for column in columns:
            if include_columns or include_prefixes:
                if column not in include_columns and not any(
                    column.startswith(prefix) for prefix in include_prefixes
                ):
                    continue
            if column in exclude_columns or any(column.startswith(prefix) for prefix in exclude_prefixes):
                continue
            filtered.append(column)
        return filtered

    def _sample_weights(self, frame) -> np.ndarray | None:
        if frame is None or frame.empty:
            return None

        weights = np.ones(len(frame), dtype=float)
        if self.recency_weight_half_life_days:
            dates = np.asarray(pd.to_datetime(frame["as_of_date"]).values, dtype="datetime64[ns]")
            if len(dates) > 0:
                latest = dates.max()
                age_days = (latest - dates).astype("timedelta64[D]").astype(float)
                half_life = max(float(self.recency_weight_half_life_days), 1.0)
                recency = np.power(0.5, age_days / half_life)
                weights *= np.clip(recency.astype(float), 0.05, 1.0)

        if self.signal_agreement_weight > 0.0:
            agreement = self._signal_agreement_score(frame)
            weights *= np.clip(1.0 + (self.signal_agreement_weight * agreement), 0.5, 1.75)

        return np.clip(weights, 0.05, 2.0)

    @staticmethod
    def _signal_agreement_score(frame) -> np.ndarray:
        candidate_columns = (
            "ifsg_rsv_baseline_zscore",
            "ifsg_rsv_momentum_1w",
            "ifsg_rsv_survstat_zscore_gap",
            "survstat_baseline_zscore",
            "survstat_momentum_2w",
            "survstat_momentum_4w",
            "ww_slope7d",
            "ww_acceleration7d",
            "ww_relative_to_national",
            "ww_relative_to_neighbor_mean",
            "grippeweb_ili_baseline_zscore",
            "grippeweb_ili_momentum_1w",
            "grippeweb_are_baseline_zscore",
            "grippeweb_are_momentum_1w",
            "national_ww_slope7d",
            "neighbor_ww_slope7d",
        )
        selected = [column for column in candidate_columns if column in frame.columns]
        if not selected:
            return np.zeros(len(frame), dtype=float)

        values = np.asarray(frame[selected].to_numpy(dtype=float), dtype=float)
        values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
        if values.size == 0:
            return np.zeros(len(frame), dtype=float)

        directional_agreement = np.maximum(
            np.mean(values > 0.0, axis=1) - np.mean(values < 0.0, axis=1),
            0.0,
        )
        strength = np.clip(np.mean(np.abs(np.tanh(values)), axis=1), 0.0, 1.0)
        return np.clip((0.55 * directional_agreement) + (0.45 * strength), 0.0, 1.0)

    def _fit_classifier(self, X: np.ndarray, y: np.ndarray, sample_weight: np.ndarray | None = None) -> XGBClassifier:
        positives = max(int(np.sum(y == 1)), 1)
        negatives = max(int(np.sum(y == 0)), 1)
        config = deepcopy(self.classifier_config)
        config["scale_pos_weight"] = float(negatives / positives)
        model = XGBClassifier(**config)
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
    ) -> XGBRegressor:
        alpha = config.get("quantile_alpha")
        override = None
        for candidate in self.regressor_config.values():
            if candidate.get("quantile_alpha") == alpha:
                override = candidate
                break
        merged_config = deepcopy(override or config)
        model = XGBRegressor(**merged_config)
        fit_kwargs: dict[str, Any] = {}
        if sample_weight is not None:
            fit_kwargs["sample_weight"] = sample_weight
        model.fit(X, y, **fit_kwargs)
        return model

    def _extra_guarded_calibration_candidates(
        self,
        *,
        raw_probabilities: np.ndarray,
        labels: np.ndarray,
    ) -> list[tuple[str, Any]]:
        candidates: list[tuple[str, Any]] = []
        for experiment in self.calibration_experiments:
            if experiment.strategy == "logit_temperature":
                for temperature in experiment.temperatures:
                    if np.isclose(float(temperature), 1.0):
                        continue
                    candidates.append(
                        (
                            f"logit_temp_guarded_t{_format_decimal_token(float(temperature))}",
                            LogitTemperatureCalibration(temperature=float(temperature)),
                        )
                    )
                continue

            if experiment.strategy == "shrinkage_blend":
                prior = float(np.mean(labels.astype(float)))
                for alpha in experiment.alphas:
                    if alpha <= 0.0:
                        continue
                    candidates.append(
                        (
                            f"shrinkage_guarded_a{_format_decimal_token(float(alpha))}",
                            ShrinkageBlendCalibration(alpha=float(alpha), prior=prior),
                        )
                    )
                continue

            if experiment.strategy == "quantile_smoothing":
                calibration = self._fit_quantile_smoothing(
                    raw_probabilities=raw_probabilities,
                    labels=labels,
                    quantile_bins=experiment.quantile_bins,
                    smoothing=experiment.smoothing,
                )
                if calibration is not None:
                    candidates.append(
                        (
                            "quantile_smooth_guarded_"
                            f"q{int(experiment.quantile_bins)}_s{_format_decimal_token(float(experiment.smoothing))}",
                            calibration,
                        )
                    )
                continue

            raise ValueError(f"Unsupported calibration experiment strategy: {experiment.strategy}")
        return candidates

    @staticmethod
    def _fit_quantile_smoothing(
        *,
        raw_probabilities: Sequence[float],
        labels: Sequence[int],
        quantile_bins: int,
        smoothing: float,
    ) -> QuantileSmoothingCalibration | None:
        probabilities = _clip_probabilities(raw_probabilities)
        y_true = np.asarray(labels, dtype=int)
        if len(probabilities) < 20 or len(np.unique(y_true)) < 2:
            return None

        bin_count = max(3, int(quantile_bins))
        quantiles = np.linspace(0.0, 1.0, bin_count + 1)
        edges = np.quantile(probabilities, quantiles)
        edges[0] = 0.0
        edges[-1] = 1.0
        unique_edges = np.unique(edges)
        if len(unique_edges) < 3:
            return None

        bucket_ids = np.digitize(probabilities, unique_edges[1:-1], right=True)
        global_rate = float(np.mean(y_true.astype(float)))
        values: list[float] = []
        for bucket in range(len(unique_edges) - 1):
            mask = bucket_ids == bucket
            count = int(np.sum(mask))
            positives = int(np.sum(y_true[mask]))
            smoothed = (
                (positives + (float(smoothing) * global_rate))
                / max(float(count) + float(smoothing), 1.0)
            )
            values.append(smoothed)
        monotone_values = np.maximum.accumulate(np.asarray(values, dtype=float))
        return QuantileSmoothingCalibration(
            edges=tuple(float(value) for value in unique_edges.tolist()),
            values=tuple(float(value) for value in np.clip(monotone_values, 0.001, 0.999).tolist()),
        )

    @staticmethod
    def _guard_compatible_candidate(
        *,
        raw_metrics: dict[str, float],
        candidate_metrics: dict[str, float],
    ) -> bool:
        return (
            candidate_metrics["brier_score"] <= raw_metrics["brier_score"] + CALIBRATION_GUARD_EPSILON
            and candidate_metrics["ece"] < raw_metrics["ece"] - CALIBRATION_GUARD_EPSILON
            and candidate_metrics["precision_at_top3"] + CALIBRATION_GUARD_EPSILON
            >= raw_metrics["precision_at_top3"]
            and candidate_metrics["activation_false_positive_rate"]
            <= raw_metrics["activation_false_positive_rate"] + CALIBRATION_GUARD_EPSILON
        )

    def _select_guarded_calibration(
        self,
        *,
        calibration_frame,
        raw_probability_col: str,
        action_threshold: float | None = None,
        min_recall_for_threshold: float = 0.35,
        label_col: str = "event_label",
        date_col: str = "as_of_date",
    ):
        if not self.calibration_experiments:
            return super()._select_guarded_calibration(
                calibration_frame=calibration_frame,
                raw_probability_col=raw_probability_col,
                action_threshold=action_threshold,
                min_recall_for_threshold=min_recall_for_threshold,
                label_col=label_col,
                date_col=date_col,
            )

        if calibration_frame.empty:
            return None, "raw_passthrough"

        working = calibration_frame[[date_col, label_col, raw_probability_col]].copy()
        working[date_col] = __import__("pandas").to_datetime(working[date_col]).dt.normalize()

        guard_split = self._calibration_guard_split_dates(working[date_col].tolist())
        if not guard_split:
            return None, "raw_passthrough"
        fit_dates, guard_dates = guard_split
        fit_df = working.loc[working[date_col].isin(fit_dates)].copy()
        guard_df = working.loc[working[date_col].isin(guard_dates)].copy()
        if fit_df.empty or guard_df.empty:
            return None, "raw_passthrough"

        fit_raw = fit_df[raw_probability_col].to_numpy(dtype=float)
        fit_labels = fit_df[label_col].to_numpy(dtype=int)
        guard_raw = guard_df[raw_probability_col].to_numpy(dtype=float)
        guard_labels = guard_df[label_col].to_numpy(dtype=int)
        raw_guard = self._apply_calibration(None, guard_raw)
        effective_threshold = float(action_threshold) if action_threshold is not None else float(
            __import__(
                "app.services.ml.regional_panel_utils",
                fromlist=["choose_action_threshold"],
            ).choose_action_threshold(
                raw_guard,
                guard_labels,
                min_recall=min_recall_for_threshold,
            )[0]
        )
        raw_metrics = self._calibration_guard_metrics(
            as_of_dates=guard_df[date_col].to_numpy(),
            labels=guard_labels,
            probabilities=raw_guard,
            action_threshold=effective_threshold,
        )

        candidate_calibrations: list[tuple[str, Any]] = []
        isotonic = self._fit_isotonic(fit_raw, fit_labels)
        if isotonic is not None:
            candidate_calibrations.append(("isotonic_guarded", isotonic))
        candidate_calibrations.extend(
            self._extra_guarded_calibration_candidates(
                raw_probabilities=fit_raw,
                labels=fit_labels,
            )
        )

        best_candidate: dict[str, Any] | None = None
        for mode, calibration in candidate_calibrations:
            calibrated_guard = self._apply_calibration(calibration, guard_raw)
            candidate_metrics = self._calibration_guard_metrics(
                as_of_dates=guard_df[date_col].to_numpy(),
                labels=guard_labels,
                probabilities=calibrated_guard,
                action_threshold=effective_threshold,
            )
            if not self._guard_compatible_candidate(
                raw_metrics=raw_metrics,
                candidate_metrics=candidate_metrics,
            ):
                continue
            candidate_key = (
                float(candidate_metrics["ece"]),
                float(candidate_metrics["brier_score"]),
                -float(candidate_metrics["precision_at_top3"]),
                float(candidate_metrics["activation_false_positive_rate"]),
                mode,
            )
            if best_candidate is None or candidate_key < best_candidate["key"]:
                best_candidate = {
                    "key": candidate_key,
                    "mode": mode,
                    "calibration": calibration,
                }

        if best_candidate is None:
            return None, "raw_passthrough"
        return best_candidate["calibration"], best_candidate["mode"]


def _selected_calibration_mode(calibration_version: str | None) -> str | None:
    text = str(calibration_version or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) >= 3 and parts[1].startswith("h"):
        return parts[0]
    if len(parts) >= 2:
        return ":".join(parts[:-1]) or parts[0]
    return text


def _quality_gate_summary(quality_gate: dict[str, Any] | None) -> dict[str, Any]:
    gate = quality_gate or {}
    return {
        "overall_passed": bool(gate.get("overall_passed")),
        "forecast_readiness": gate.get("forecast_readiness"),
        "failed_checks": list(gate.get("failed_checks") or []),
        "profile": gate.get("profile"),
    }


def _metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    deltas: dict[str, float] = {}
    for metric in (
        "precision_at_top3",
        "activation_false_positive_rate",
        "pr_auc",
        "brier_score",
        "ece",
    ):
        if metric in candidate and metric in baseline:
            deltas[metric] = round(float(candidate[metric]) - float(baseline[metric]), 6)
    return deltas


def _gate_outcome(quality_gate: dict[str, Any] | None) -> str | None:
    gate = quality_gate or {}
    outcome = gate.get("forecast_readiness")
    if outcome:
        return str(outcome)
    if gate.get("overall_passed") is not None:
        return "GO" if bool(gate.get("overall_passed")) else "WATCH"
    return None


def _retention_status(
    *,
    candidate_metrics: dict[str, Any],
    baseline_metrics: dict[str, Any],
    epsilon: float = 1e-6,
) -> tuple[bool, str]:
    checks = {
        "precision_at_top3": (
            float(candidate_metrics.get("precision_at_top3") or 0.0)
            > float(baseline_metrics.get("precision_at_top3") or 0.0) + epsilon
        ),
        "activation_false_positive_rate": (
            float(candidate_metrics.get("activation_false_positive_rate") or 1.0)
            <= float(baseline_metrics.get("activation_false_positive_rate") or 1.0) + epsilon
        ),
        "ece": (
            float(candidate_metrics.get("ece") or 1.0)
            <= float(baseline_metrics.get("ece") or 1.0) + epsilon
        ),
        "brier_score": (
            float(candidate_metrics.get("brier_score") or 1.0)
            <= float(baseline_metrics.get("brier_score") or 1.0) + epsilon
        ),
    }
    if all(checks.values()):
        return True, "precision_at_top3 improved without unbounded calibration or activation regression"
    failed = next((name for name, passed in checks.items() if not passed), "unknown")
    return False, f"failed_{failed}"


def _feature_selection_payload(selection: FeatureSelectionSpec | None) -> dict[str, Any] | None:
    if selection is None:
        return None
    return {
        "include_columns": list(selection.include_columns),
        "include_prefixes": list(selection.include_prefixes),
        "exclude_columns": list(selection.exclude_columns),
        "exclude_prefixes": list(selection.exclude_prefixes),
    }


def _flatten_comparison_metrics(metrics: dict[str, Any] | None) -> dict[str, Any]:
    payload = metrics or {}
    return {
        "precision_at_top3": payload.get("precision_at_top3"),
        "activation_false_positive_rate": payload.get("activation_false_positive_rate"),
        "pr_auc": payload.get("pr_auc"),
        "brier_score": payload.get("brier_score"),
        "ece": payload.get("ece"),
    }


class H7PilotExperimentRunner:
    """Run h7-only pilot training and comparison output per virus."""

    def __init__(
        self,
        db,
        *,
        baseline_models_dir: Path | None = None,
        experiment_models_dir: Path | None = None,
    ) -> None:
        self.db = db
        self.baseline_models_dir = baseline_models_dir or _DEFAULT_BASELINE_MODELS_DIR
        self.experiment_models_dir = experiment_models_dir or DEFAULT_H7_PILOT_MODELS_DIR

    def run(
        self,
        *,
        virus_types: Sequence[str] | None = None,
        specs_by_virus: dict[str, Sequence[PilotExperimentSpec]] | None = None,
        summary_output: Path | None = None,
    ) -> dict[str, Any]:
        selected_viruses = tuple(virus_types or DAY_ONE_PILOT_VIRUS_TYPES)
        spec_map = specs_by_virus or default_h7_pilot_specs_by_virus(selected_viruses)
        summary = {
            "status": "success",
            "horizon_days": H7_PILOT_ONLY_HORIZON,
            "pilot_viruses": list(selected_viruses),
            "generated_at": datetime.utcnow().isoformat(),
            "baseline_models_dir": str(self.baseline_models_dir),
            "experiment_models_dir": str(self.experiment_models_dir),
            "viruses": {
                virus_typ: self._run_single_virus(
                    virus_typ=virus_typ,
                    specs=tuple(spec_map.get(virus_typ) or (BASELINE_GUARD_SPEC,)),
                )
                for virus_typ in selected_viruses
            },
        }
        if summary_output is not None:
            summary_output.parent.mkdir(parents=True, exist_ok=True)
            summary_output.write_text(json.dumps(_json_safe(summary), indent=2))
        return summary

    def _run_single_virus(
        self,
        *,
        virus_typ: str,
        specs: Sequence[PilotExperimentSpec],
    ) -> dict[str, Any]:
        pilot_status = regional_horizon_pilot_status(virus_typ, H7_PILOT_ONLY_HORIZON)
        baseline_trainer = RegionalModelTrainer(self.db, models_dir=self.baseline_models_dir)
        baseline_payload = baseline_trainer.load_artifacts(virus_typ, horizon_days=H7_PILOT_ONLY_HORIZON)
        baseline_row = self._baseline_row(
            virus_typ=virus_typ,
            payload=baseline_payload,
        )
        baseline_metrics = baseline_row.get("metrics") or {}

        runs: list[dict[str, Any]] = []
        for spec in specs:
            experiment_root = self.experiment_models_dir / _virus_slug(virus_typ) / spec.name
            trainer = PilotH7ExperimentTrainer(
                self.db,
                models_dir=experiment_root,
                feature_selection=spec.feature_selection,
                recency_weight_half_life_days=spec.recency_weight_half_life_days,
                signal_agreement_weight=spec.signal_agreement_weight,
                classifier_config=self._merged_classifier_config(spec),
                regressor_config=self._merged_regressor_config(spec),
                calibration_experiments=spec.calibration_experiments,
            )
            result = trainer.train_all_regions(
                virus_typ=virus_typ,
                lookback_days=spec.lookback_days,
                persist=True,
                horizon_days=H7_PILOT_ONLY_HORIZON,
            )
            runs.append(
                self._experiment_row(
                    virus_typ=virus_typ,
                    spec=spec,
                    result=result,
                    baseline_metrics=baseline_metrics,
                )
            )

        ranked_runs = sorted(
            runs,
            key=lambda item: (
                bool(item.get("retained")),
                bool((item.get("gate_summary") or {}).get("overall_passed")),
                float((item.get("metrics") or {}).get("precision_at_top3") or 0.0),
                float((item.get("metrics") or {}).get("pr_auc") or 0.0),
                -float((item.get("metrics") or {}).get("ece") or 1.0),
                -float((item.get("metrics") or {}).get("activation_false_positive_rate") or 1.0),
            ),
            reverse=True,
        )
        best_retained = next((item for item in ranked_runs if item.get("retained")), None)
        comparison_table = [baseline_row, *ranked_runs]
        return {
            "virus_typ": virus_typ,
            "horizon_days": H7_PILOT_ONLY_HORIZON,
            "pilot_status": pilot_status,
            "baseline": baseline_row,
            "experiment_count": len(ranked_runs),
            "best_experiment": ranked_runs[0]["name"] if ranked_runs else None,
            "best_retained_experiment": best_retained["name"] if best_retained else None,
            "runs": ranked_runs,
            "comparison_table": comparison_table,
        }

    def _baseline_row(
        self,
        *,
        virus_typ: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = payload.get("metadata") or {}
        backtest = payload.get("backtest") or {}
        metrics = (metadata.get("aggregate_metrics") or backtest.get("aggregate_metrics") or {}).copy()
        quality_gate = (metadata.get("quality_gate") or backtest.get("quality_gate") or {}).copy()
        calibration_version = metadata.get("calibration_version")
        row = {
            "name": "live_baseline",
            "source": "baseline",
            "virus_typ": virus_typ,
            "horizon_days": H7_PILOT_ONLY_HORIZON,
            "artifact_dir": str(
                regional_model_artifact_dir(
                    self.baseline_models_dir,
                    virus_typ=virus_typ,
                    horizon_days=H7_PILOT_ONLY_HORIZON,
                )
            ),
            "status": "available" if metadata else "missing",
            "calibration_version": calibration_version,
            "selected_calibration_mode": _selected_calibration_mode(calibration_version),
            "calibration_mode": _selected_calibration_mode(calibration_version),
            "metrics": metrics,
            "gate_summary": _quality_gate_summary(quality_gate),
            "gate_outcome": _gate_outcome(quality_gate),
            "retained": True,
            "retention_reason": "baseline_reference",
            "delta_vs_baseline": {},
            "feature_selection": None,
            "recency_weight_half_life_days": None,
            "signal_agreement_weight": None,
        }
        row.update(_flatten_comparison_metrics(metrics))
        return row

    @staticmethod
    def _merged_classifier_config(spec: PilotExperimentSpec) -> dict[str, Any]:
        config = deepcopy(REGIONAL_CLASSIFIER_CONFIG)
        if spec.classifier_overrides:
            config.update(spec.classifier_overrides)
        return config

    @staticmethod
    def _merged_regressor_config(spec: PilotExperimentSpec) -> dict[str, dict[str, Any]]:
        config = deepcopy(REGIONAL_REGRESSOR_CONFIG)
        if spec.regressor_overrides:
            for key, overrides in spec.regressor_overrides.items():
                if key in config:
                    config[key].update(overrides)
        return config

    @staticmethod
    def _experiment_row(
        *,
        virus_typ: str,
        spec: PilotExperimentSpec,
        result: dict[str, Any],
        baseline_metrics: dict[str, Any],
    ) -> dict[str, Any]:
        metrics = (result.get("aggregate_metrics") or {}).copy()
        calibration_version = result.get("calibration_version")
        retained, retention_reason = _retention_status(
            candidate_metrics=metrics,
            baseline_metrics=baseline_metrics,
        )
        row = {
            "name": spec.name,
            "description": spec.description,
            "source": "experiment",
            "virus_typ": virus_typ,
            "horizon_days": H7_PILOT_ONLY_HORIZON,
            "artifact_dir": result.get("model_dir"),
            "status": result.get("status"),
            "calibration_version": calibration_version,
            "selected_calibration_mode": (
                result.get("selected_calibration_mode")
                or _selected_calibration_mode(calibration_version)
            ),
            "calibration_mode": (
                result.get("selected_calibration_mode")
                or _selected_calibration_mode(calibration_version)
            ),
            "metrics": metrics,
            "gate_summary": _quality_gate_summary(result.get("quality_gate") or {}),
            "gate_outcome": _gate_outcome(result.get("quality_gate") or {}),
            "retained": retained,
            "retention_reason": retention_reason,
            "delta_vs_baseline": _metric_delta(metrics, baseline_metrics),
            "feature_selection": _feature_selection_payload(spec.feature_selection),
            "recency_weight_half_life_days": spec.recency_weight_half_life_days,
            "signal_agreement_weight": spec.signal_agreement_weight,
        }
        row.update(_flatten_comparison_metrics(metrics))
        return row
