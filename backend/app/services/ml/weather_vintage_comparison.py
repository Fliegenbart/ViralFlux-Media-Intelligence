"""Small end-to-end weather vintage comparison runner and report helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from app.models.database import WeatherData
from app.services.ml.regional_panel_utils import time_based_panel_splits
from app.services.ml.forecast_horizon_utils import SUPPORTED_FORECAST_HORIZONS
from app.services.ml.regional_trainer import RegionalModelTrainer
from app.services.ml.training_contract import SUPPORTED_VIRUS_TYPES
from app.services.ml import weather_vintage_coverage
from app.services.ml import weather_vintage_health
from app.services.ml import weather_vintage_reporting
from app.services.ml.weather_forecast_vintage import (
    WEATHER_FORECAST_VINTAGE_DISABLED,
    WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
)

DEFAULT_WEATHER_VINTAGE_COMPARISON_VIRUS_TYPES = (
    "Influenza A",
    "SARS-CoV-2",
    "RSV A",
)
DEFAULT_WEATHER_VINTAGE_COMPARISON_HORIZONS = (3, 7)
DEFAULT_WEATHER_VINTAGE_PROSPECTIVE_VIRUS_TYPES = (
    "Influenza A",
    "SARS-CoV-2",
)
DEFAULT_WEATHER_VINTAGE_PROSPECTIVE_HORIZONS = (7,)
DEFAULT_WEATHER_VINTAGE_REVIEW_RUN_PURPOSES = ("scheduled_shadow",)
SUPPORTED_WEATHER_VINTAGE_RUN_PURPOSES = (
    "smoke",
    "manual_eval",
    "scheduled_shadow",
)
WEATHER_VINTAGE_MIN_TRAIN_COVERAGE = 0.5
WEATHER_VINTAGE_MIN_TEST_COVERAGE = 0.8
WEATHER_VINTAGE_TIME_BLOCK_DAYS = 90
WEATHER_VINTAGE_MIN_COMPARABLE_RUNS = 6
WEATHER_VINTAGE_HEALTH_MAX_RUN_AGE_HOURS = 36
WEATHER_VINTAGE_HEALTH_MAX_DAYS_WITHOUT_COMPARABLE = 14
WEATHER_VINTAGE_HEALTH_MAX_INSUFFICIENT_IDENTITY_STREAK = 3
WEATHER_VINTAGE_GATE_ORDER = {
    "NO_GO": 0,
    "WATCH": 1,
    "GO": 2,
}
WEATHER_VINTAGE_HEALTH_STATUS_ORDER = {
    "ok": 0,
    "warning": 1,
    "critical": 2,
}


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def normalize_weather_vintage_matrix(
    *,
    virus_types: list[str] | tuple[str, ...] | None,
    horizon_days_list: list[int] | tuple[int, ...] | None,
) -> tuple[list[str], list[int]]:
    selected_viruses = list(virus_types or DEFAULT_WEATHER_VINTAGE_COMPARISON_VIRUS_TYPES)
    selected_horizons = list(horizon_days_list or DEFAULT_WEATHER_VINTAGE_COMPARISON_HORIZONS)
    normalized_viruses = [
        virus_typ for virus_typ in selected_viruses if virus_typ in SUPPORTED_VIRUS_TYPES
    ]
    normalized_horizons = [
        int(horizon) for horizon in selected_horizons if int(horizon) in SUPPORTED_FORECAST_HORIZONS
    ]
    if not normalized_viruses:
        raise ValueError("No supported virus types selected for weather vintage comparison.")
    if not normalized_horizons:
        raise ValueError("No supported horizons selected for weather vintage comparison.")
    return normalized_viruses, normalized_horizons


def classify_weather_vintage_result(scope_payload: dict[str, Any]) -> str:
    if str(scope_payload.get("status") or "").lower() != "success":
        return str(scope_payload.get("status") or "unknown").lower() or "unknown"
    comparison = scope_payload.get("weather_vintage_comparison") or {}
    if str(comparison.get("comparison_status") or "").lower() != "ok":
        return str(comparison.get("comparison_status") or "degraded").lower()

    run_identity = (
        comparison.get("weather_vintage_run_identity_coverage", {})
        .get(WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1, {})
    )
    if not bool(run_identity.get("run_identity_present")):
        return "insufficient_identity"

    deltas = comparison.get("legacy_vs_vintage_metric_delta") or {}
    wis_delta = float(deltas.get("relative_wis", deltas.get("wis", 0.0)) or 0.0)
    crps_delta = float(deltas.get("crps", 0.0) or 0.0)
    if wis_delta <= -0.005 and crps_delta <= -0.001:
        return "better"
    if wis_delta >= 0.005 and crps_delta >= 0.001:
        return "worse"
    if abs(wis_delta) < 0.005 and abs(crps_delta) < 0.001:
        return "neutral"
    return "mixed"


def scope_report_from_training_result(
    *,
    virus_typ: str,
    horizon_days: int,
    result: dict[str, Any],
) -> dict[str, Any]:
    return weather_vintage_reporting.scope_report_from_training_result(
        virus_typ=virus_typ,
        horizon_days=horizon_days,
        result=result,
        weather_forecast_vintage_disabled=WEATHER_FORECAST_VINTAGE_DISABLED,
        weather_forecast_vintage_run_timestamp_v1=WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
        json_safe_fn=_json_safe,
        classify_weather_vintage_result_fn=classify_weather_vintage_result,
    )


def build_weather_vintage_report_summary(
    scope_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    return weather_vintage_reporting.build_weather_vintage_report_summary(scope_reports)


def _gate_rank(value: Any) -> int:
    return WEATHER_VINTAGE_GATE_ORDER.get(str(value or "").upper(), -1)


def determine_weather_vintage_comparison_eligibility(
    scope_payload: dict[str, Any],
) -> str:
    if str(scope_payload.get("status") or "").lower() != "success":
        return "failed"
    if str(scope_payload.get("comparison_status") or "").lower() != "ok":
        return "failed"

    run_identity = (
        scope_payload.get("weather_vintage_run_identity_coverage", {})
        .get(WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1, {})
    )
    backtest_coverage = scope_payload.get("weather_vintage_backtest_coverage") or {}
    if (not bool(run_identity.get("run_identity_present"))) or bool(
        backtest_coverage.get("insufficient_for_comparison")
    ):
        return "insufficient_identity"
    return "comparable"


def _extract_mode_snapshot(
    scope_payload: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    snapshot = ((scope_payload.get("modes") or {}).get(mode) or {}).copy()
    snapshot.setdefault("weather_forecast_vintage_mode", mode)
    return _json_safe(
        {
            "weather_forecast_vintage_mode": snapshot.get("weather_forecast_vintage_mode"),
            "aggregate_metrics": snapshot.get("aggregate_metrics") or {},
            "benchmark_metrics": snapshot.get("benchmark_metrics") or {},
            "quality_gate": snapshot.get("quality_gate") or {},
            "selected_tau": snapshot.get("selected_tau"),
            "selected_kappa": snapshot.get("selected_kappa"),
            "action_threshold": snapshot.get("action_threshold"),
            "calibration_mode": snapshot.get("calibration_mode"),
            "weather_forecast_run_identity_present": snapshot.get(
                "weather_forecast_run_identity_present"
            ),
        }
    )


def build_weather_vintage_shadow_summary(
    *,
    report: dict[str, Any],
    generated_at: str,
    run_id: str,
    run_purpose: str,
) -> dict[str, Any]:
    return weather_vintage_reporting.build_weather_vintage_shadow_summary(
        report=report,
        generated_at=generated_at,
        run_id=run_id,
        run_purpose=run_purpose,
        json_safe_fn=_json_safe,
        determine_weather_vintage_comparison_eligibility_fn=determine_weather_vintage_comparison_eligibility,
        extract_mode_snapshot_fn=_extract_mode_snapshot,
        weather_forecast_vintage_disabled=WEATHER_FORECAST_VINTAGE_DISABLED,
        weather_forecast_vintage_run_timestamp_v1=WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
    )


def render_weather_vintage_shadow_run_markdown(summary: dict[str, Any]) -> str:
    return weather_vintage_reporting.render_weather_vintage_shadow_run_markdown(summary)


def write_weather_vintage_shadow_archive(
    *,
    archive_dir: Path,
    report: dict[str, Any],
    generated_at: str,
    run_id: str,
    manifest: dict[str, Any],
) -> dict[str, Path]:
    return weather_vintage_reporting.write_weather_vintage_shadow_archive(
        archive_dir=archive_dir,
        report=report,
        generated_at=generated_at,
        run_id=run_id,
        manifest=manifest,
        json_module=json,
        json_safe_fn=_json_safe,
        render_weather_vintage_markdown_fn=render_weather_vintage_markdown,
        build_weather_vintage_shadow_summary_fn=build_weather_vintage_shadow_summary,
    )


def load_weather_vintage_shadow_summaries(
    output_root: Path,
    *,
    included_run_purposes: tuple[str, ...] | list[str] | None = None,
) -> list[dict[str, Any]]:
    return weather_vintage_reporting.load_weather_vintage_shadow_summaries(
        output_root,
        included_run_purposes=included_run_purposes,
    )


def determine_weather_vintage_review_status(scope_aggregate: dict[str, Any]) -> str:
    return weather_vintage_reporting.determine_weather_vintage_review_status(
        scope_aggregate,
        min_comparable_runs=WEATHER_VINTAGE_MIN_COMPARABLE_RUNS,
        min_test_coverage=WEATHER_VINTAGE_MIN_TEST_COVERAGE,
    )


def _scope_review_recommendation(scope_aggregate: dict[str, Any]) -> str:
    return weather_vintage_reporting.scope_review_recommendation(
        scope_aggregate,
        determine_weather_vintage_review_status_fn=determine_weather_vintage_review_status,
        min_comparable_runs=WEATHER_VINTAGE_MIN_COMPARABLE_RUNS,
        min_test_coverage=WEATHER_VINTAGE_MIN_TEST_COVERAGE,
    )


def build_weather_vintage_shadow_aggregate(
    run_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    return weather_vintage_reporting.build_weather_vintage_shadow_aggregate(
        run_summaries,
        gate_rank_fn=_gate_rank,
        json_safe_fn=_json_safe,
        determine_weather_vintage_review_status_fn=determine_weather_vintage_review_status,
        scope_review_recommendation_fn=_scope_review_recommendation,
        pd_module=pd,
    )


def render_weather_vintage_shadow_aggregate_markdown(aggregate: dict[str, Any]) -> str:
    return weather_vintage_reporting.render_weather_vintage_shadow_aggregate_markdown(
        aggregate
    )


def _parse_generated_at(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return pd.Timestamp(value).to_pydatetime()
    except Exception:
        return None


def _weather_health_status_exit_code(status: str) -> int:
    if status == "critical":
        return 2
    if status == "warning":
        return 1
    return 0


def _combine_weather_health_status(current: str, new: str) -> str:
    if WEATHER_VINTAGE_HEALTH_STATUS_ORDER.get(new, 0) > WEATHER_VINTAGE_HEALTH_STATUS_ORDER.get(
        current, 0
    ):
        return new
    return current


def build_weather_vintage_shadow_health_report(
    run_summaries: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    max_run_age_hours: int = WEATHER_VINTAGE_HEALTH_MAX_RUN_AGE_HOURS,
    max_days_without_comparable: int = WEATHER_VINTAGE_HEALTH_MAX_DAYS_WITHOUT_COMPARABLE,
    max_insufficient_identity_streak: int = WEATHER_VINTAGE_HEALTH_MAX_INSUFFICIENT_IDENTITY_STREAK,
) -> dict[str, Any]:
    return weather_vintage_health.build_weather_vintage_shadow_health_report(
        run_summaries,
        now=now,
        max_run_age_hours=max_run_age_hours,
        max_days_without_comparable=max_days_without_comparable,
        max_insufficient_identity_streak=max_insufficient_identity_streak,
        parse_generated_at_fn=_parse_generated_at,
        weather_health_status_exit_code_fn=_weather_health_status_exit_code,
        combine_weather_health_status_fn=_combine_weather_health_status,
        json_safe_fn=_json_safe,
    )


def render_weather_vintage_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Weather Vintage Comparison",
        "",
        "This report compares `legacy_issue_time_only` against `run_timestamp_v1` end-to-end on the regional training/backtest path.",
        "",
        "## Summary",
        "",
        f"- Total scopes: {int((report.get('summary') or {}).get('total_scopes') or 0)}",
    ]
    verdict_counts = (report.get("summary") or {}).get("verdict_counts") or {}
    for key in sorted(verdict_counts):
        lines.append(f"- {key}: {int(verdict_counts[key])}")
    coverage_status_counts = (report.get("summary") or {}).get("coverage_status_counts") or {}
    for key in sorted(coverage_status_counts):
        lines.append(f"- coverage_{key}: {int(coverage_status_counts[key])}")
    lines.extend(["", "## Scope Results", ""])
    for item in report.get("scopes") or []:
        delta = item.get("legacy_vs_vintage_metric_delta") or {}
        coverage = (
            item.get("weather_vintage_run_identity_coverage", {})
            .get(WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1, {})
        )
        backtest_coverage = item.get("weather_vintage_backtest_coverage") or {}
        lines.extend(
            [
                f"### {item['virus_typ']} / h{item['horizon_days']}",
                "",
                f"- Status: `{item.get('status')}`",
                f"- Verdict: `{item.get('verdict')}`",
                f"- Comparison status: `{item.get('comparison_status')}`",
                f"- Vintage run identity present: `{bool(coverage.get('run_identity_present'))}`",
                f"- Coverage status: `{backtest_coverage.get('coverage_status')}`",
                f"- Coverage overall: `{backtest_coverage.get('coverage_overall')}`",
                f"- Coverage train: `{backtest_coverage.get('coverage_train')}`",
                f"- Coverage test: `{backtest_coverage.get('coverage_test')}`",
                f"- First available run-identity date: `{backtest_coverage.get('first_available_run_identity_date')}`",
                f"- Last available run-identity date: `{backtest_coverage.get('last_available_run_identity_date')}`",
                f"- First covered as_of_date: `{backtest_coverage.get('first_covered_as_of_date')}`",
                f"- Last covered as_of_date: `{backtest_coverage.get('last_covered_as_of_date')}`",
                f"- Delta relative_wis: `{delta.get('relative_wis', delta.get('wis'))}`",
                f"- Delta crps: `{delta.get('crps')}`",
                f"- Quality gate change: `{(item.get('quality_gate_change') or {}).get('legacy_forecast_readiness')}` -> `{(item.get('quality_gate_change') or {}).get('vintage_forecast_readiness')}`",
                f"- Threshold change: `{item.get('threshold_change')}`",
                f"- Calibration change: `{(item.get('calibration_change') or {}).get('legacy')}` -> `{(item.get('calibration_change') or {}).get('vintage')}`",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


class WeatherVintageComparisonRunner:
    """Run the small weather vintage benchmark matrix against the regional trainer."""

    def __init__(
        self,
        db,
        *,
        trainer_factory: Callable[[Any], RegionalModelTrainer] | None = None,
        coverage_analyzer: Callable[[RegionalModelTrainer, str, int, int], dict[str, Any]] | None = None,
    ) -> None:
        self.db = db
        self.trainer_factory = trainer_factory or (lambda database: RegionalModelTrainer(database))
        self.coverage_analyzer = coverage_analyzer or self._analyze_scope_coverage

    def _load_weather_identity_frame(
        self,
        *,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
    ) -> pd.DataFrame:
        return weather_vintage_coverage.load_weather_identity_frame(
            self.db,
            start_date=start_date,
            end_date=end_date,
            weather_data_model=WeatherData,
            pd_module=pd,
        )

    @staticmethod
    def summarize_backtest_weather_identity_coverage(
        *,
        panel: pd.DataFrame,
        weather_frame: pd.DataFrame,
        horizon_days: int,
    ) -> dict[str, Any]:
        return weather_vintage_coverage.summarize_backtest_weather_identity_coverage(
            panel=panel,
            weather_frame=weather_frame,
            horizon_days=horizon_days,
            time_based_panel_splits_fn=time_based_panel_splits,
            min_test_coverage=WEATHER_VINTAGE_MIN_TEST_COVERAGE,
            min_train_coverage=WEATHER_VINTAGE_MIN_TRAIN_COVERAGE,
            time_block_days=WEATHER_VINTAGE_TIME_BLOCK_DAYS,
            json_safe_fn=_json_safe,
            pd_module=pd,
        )

    def _analyze_scope_coverage(
        self,
        trainer: RegionalModelTrainer,
        virus_typ: str,
        horizon_days: int,
        lookback_days: int,
    ) -> dict[str, Any]:
        return weather_vintage_coverage.analyze_scope_coverage(
            trainer=trainer,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            lookback_days=lookback_days,
            weather_forecast_vintage_run_timestamp_v1=WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
            pd_module=pd,
            load_weather_identity_frame_fn=self._load_weather_identity_frame,
            summarize_backtest_weather_identity_coverage_fn=self.summarize_backtest_weather_identity_coverage,
        )

    def run(
        self,
        *,
        virus_types: list[str] | tuple[str, ...] | None = None,
        horizon_days_list: list[int] | tuple[int, ...] | None = None,
        lookback_days: int = 900,
        output_json: Path | None = None,
        output_markdown: Path | None = None,
    ) -> dict[str, Any]:
        selected_viruses, selected_horizons = normalize_weather_vintage_matrix(
            virus_types=virus_types,
            horizon_days_list=horizon_days_list,
        )
        trainer = self.trainer_factory(self.db)
        scope_reports: list[dict[str, Any]] = []

        for virus_typ in selected_viruses:
            for horizon_days in selected_horizons:
                result = trainer.train_all_regions(
                    virus_typ=virus_typ,
                    lookback_days=int(lookback_days),
                    persist=False,
                    horizon_days=int(horizon_days),
                    weather_vintage_comparison=True,
                )
                scope_report = scope_report_from_training_result(
                    virus_typ=virus_typ,
                    horizon_days=int(horizon_days),
                    result=result or {},
                )
                scope_report["weather_vintage_backtest_coverage"] = self.coverage_analyzer(
                    trainer,
                    virus_typ,
                    int(horizon_days),
                    int(lookback_days),
                )
                scope_reports.append(_json_safe(scope_report))

        report = {
            "status": "ok",
            "comparison_type": "weather_vintage_end_to_end_training_backtest",
            "matrix": {
                "virus_types": selected_viruses,
                "horizon_days_list": selected_horizons,
                "lookback_days": int(lookback_days),
                "active_training_mode_default": WEATHER_FORECAST_VINTAGE_DISABLED,
                "shadow_mode": WEATHER_FORECAST_VINTAGE_RUN_TIMESTAMP_V1,
            },
            "scopes": scope_reports,
            "summary": build_weather_vintage_report_summary(scope_reports),
        }
        if output_json is not None:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(json.dumps(_json_safe(report), indent=2), encoding="utf-8")
        if output_markdown is not None:
            output_markdown.parent.mkdir(parents=True, exist_ok=True)
            output_markdown.write_text(render_weather_vintage_markdown(report), encoding="utf-8")
        return _json_safe(report)
