from __future__ import annotations

from pathlib import Path

from app.services.research.tri_layer.backtest import (
    TriLayerBacktestConfig,
    run_tri_layer_backtest_panel,
)
from app.services.research.tri_layer.tasks import run_tri_layer_backtest_task


def _panel() -> list[dict]:
    return [
        {
            "region": "Hamburg",
            "region_code": "HH",
            "source": "wastewater",
            "signal_date": "2024-10-01",
            "available_date": "2024-10-01",
            "signal": 0.82,
            "intensity": 0.76,
            "growth": 0.22,
            "observed_phase": "early_growth",
            "observed_onset": True,
            "observed_peak_date": "2024-10-08",
        },
        {
            "region": "Hamburg",
            "region_code": "HH",
            "source": "clinical",
            "signal_date": "2024-10-01",
            "available_date": "2024-10-03",
            "signal": 0.72,
            "intensity": 0.62,
            "growth": 0.16,
            "observed_phase": "early_growth",
            "observed_onset": True,
            "observed_peak_date": "2024-10-08",
        },
        {
            "region": "Hamburg",
            "region_code": "HH",
            "source": "clinical",
            "signal_date": "2024-10-01",
            "available_date": "2024-10-20",
            "signal": 0.99,
            "intensity": 0.99,
            "growth": 0.50,
            "observed_phase": "peak",
            "observed_onset": True,
            "observed_peak_date": "2024-10-08",
        },
        {
            "region": "Berlin",
            "region_code": "BE",
            "source": "clinical",
            "signal_date": "2024-10-03",
            "available_date": "2024-10-03",
            "signal": 0.18,
            "intensity": 0.2,
            "growth": 0.01,
            "observed_phase": "baseline",
            "observed_onset": False,
            "observed_peak_date": None,
        },
    ]


def test_tri_layer_backtest_task_can_be_imported() -> None:
    assert run_tri_layer_backtest_task.name == "run_tri_layer_backtest_task"


def test_backtest_runner_works_on_tiny_synthetic_panel(tmp_path: Path) -> None:
    report = run_tri_layer_backtest_panel(
        _panel(),
        TriLayerBacktestConfig(
            virus_typ="Influenza A",
            brand="gelo",
            horizon_days=7,
            start_date="2024-10-01",
            end_date="2024-10-10",
            include_sales=False,
            output_dir=tmp_path,
            run_id="synthetic-run",
        ),
    )

    assert report["status"] == "complete"
    assert report["run_id"] == "synthetic-run"
    assert report["metrics"]["number_of_cutoffs"] > 0
    assert report["metrics"]["number_of_regions"] == 2
    assert "tri_layer_with_budget_isolation" in report["baselines"]
    assert "tri_layer_without_budget_isolation" in report["baselines"]
    assert (tmp_path / "synthetic-run.json").exists()


def test_include_sales_false_keeps_max_permission_state_shadow_only(tmp_path: Path) -> None:
    report = run_tri_layer_backtest_panel(
        _panel(),
        TriLayerBacktestConfig(
            start_date="2024-10-01",
            end_date="2024-10-10",
            include_sales=False,
            output_dir=tmp_path,
        ),
    )

    assert report["max_budget_permission_state"] == "shadow_only"
    assert all(row["budget_can_change"] is False for row in report["cutoff_results"])
    assert report["metrics"]["gate_transition_counts"]["sales_calibration"]["not_available"] > 0


def test_include_sales_true_without_sales_data_fails_gracefully(tmp_path: Path) -> None:
    report = run_tri_layer_backtest_panel(
        _panel(),
        TriLayerBacktestConfig(
            start_date="2024-10-01",
            end_date="2024-10-10",
            include_sales=True,
            output_dir=tmp_path,
        ),
    )

    assert report["status"] == "complete"
    assert report["metrics"]["sales_lift_predictiveness"] is None
    assert report["metrics"]["budget_regret_reduction"] is None
    assert report["metrics"]["gate_transition_counts"]["sales_calibration"]["not_available"] > 0
    assert all(row["budget_can_change"] is False for row in report["cutoff_results"])


def test_historical_cutoff_does_not_use_future_observations(tmp_path: Path) -> None:
    report = run_tri_layer_backtest_panel(
        _panel(),
        TriLayerBacktestConfig(
            start_date="2024-10-01",
            end_date="2024-10-03",
            include_sales=False,
            output_dir=tmp_path,
        ),
    )

    for row in report["cutoff_results"]:
        cutoff = row["cutoff_date"]
        for source in row["source_inputs"]:
            if source["available_date"] is not None:
                assert source["available_date"] <= cutoff
    hh_first = next(
        row for row in report["cutoff_results"]
        if row["region_code"] == "HH" and row["cutoff_date"] == "2024-10-03"
    )
    clinical_input = next(source for source in hh_first["source_inputs"] if source["source"] == "clinical")
    assert clinical_input["signal"] == 0.72


def test_generated_report_contains_metrics_and_gate_counts(tmp_path: Path) -> None:
    report = run_tri_layer_backtest_panel(
        _panel(),
        TriLayerBacktestConfig(
            start_date="2024-10-01",
            end_date="2024-10-10",
            include_sales=False,
            output_dir=tmp_path,
        ),
    )

    metrics = report["metrics"]
    for key in [
        "onset_detection_gain",
        "peak_lead_time",
        "false_early_warning_rate",
        "phase_accuracy",
        "sales_lift_predictiveness",
        "budget_regret_reduction",
        "calibration_error",
        "number_of_cutoffs",
        "number_of_regions",
        "gate_transition_counts",
    ]:
        assert key in metrics
    assert metrics["sales_lift_predictiveness"] is None
    assert metrics["budget_regret_reduction"] is None
    assert "budget_isolation" in metrics["gate_transition_counts"]
