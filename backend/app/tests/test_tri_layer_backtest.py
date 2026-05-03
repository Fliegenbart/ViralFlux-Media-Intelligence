from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, SurvstatWeeklyData, WastewaterAggregated
from app.services.research.tri_layer.backtest import (
    TriLayerBacktestConfig,
    run_tri_layer_backtest_from_db,
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


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    return db, engine


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


def test_db_backtest_uses_point_in_time_observations_and_ignores_future_rows(tmp_path: Path) -> None:
    db, engine = _session()
    try:
        db.add_all(
            [
                WastewaterAggregated(
                    datum=datetime(2024, 1, 1),
                    available_time=datetime(2024, 1, 2),
                    virus_typ="Influenza A",
                    n_standorte=8,
                    anteil_bev=0.5,
                    viruslast=10.0,
                ),
                WastewaterAggregated(
                    datum=datetime(2024, 1, 8),
                    available_time=datetime(2024, 1, 9),
                    virus_typ="Influenza A",
                    n_standorte=8,
                    anteil_bev=0.5,
                    viruslast=20.0,
                ),
                WastewaterAggregated(
                    datum=datetime(2024, 1, 15),
                    available_time=datetime(2024, 1, 16),
                    virus_typ="Influenza A",
                    n_standorte=8,
                    anteil_bev=0.5,
                    viruslast=999.0,
                ),
                SurvstatWeeklyData(
                    week_label="2024_01",
                    week_start=datetime(2024, 1, 1),
                    available_time=datetime(2024, 1, 8),
                    year=2024,
                    week=1,
                    bundesland="Hamburg",
                    disease="influenza, saisonal",
                    disease_cluster="RESPIRATORY",
                    age_group="Gesamt",
                    incidence=10.0,
                ),
                SurvstatWeeklyData(
                    week_label="2024_02",
                    week_start=datetime(2024, 1, 8),
                    available_time=datetime(2024, 1, 15),
                    year=2024,
                    week=2,
                    bundesland="Hamburg",
                    disease="influenza, saisonal",
                    disease_cluster="RESPIRATORY",
                    age_group="Gesamt",
                    incidence=20.0,
                ),
                SurvstatWeeklyData(
                    week_label="2024_03",
                    week_start=datetime(2024, 1, 22),
                    available_time=datetime(2024, 1, 29),
                    year=2024,
                    week=3,
                    bundesland="Hamburg",
                    disease="influenza, saisonal",
                    disease_cluster="RESPIRATORY",
                    age_group="Gesamt",
                    incidence=65.0,
                ),
            ]
        )
        db.commit()

        report = run_tri_layer_backtest_from_db(
            db,
            TriLayerBacktestConfig(
                virus_typ="Influenza A",
                horizon_days=14,
                start_date="2024-01-15",
                end_date="2024-01-15",
                include_sales=False,
                output_dir=tmp_path,
                run_id="db-pit",
            ),
        )

        assert report["status"] == "complete"
        assert report["cutoffs"] == 1
        row = next(item for item in report["cutoff_results"] if item["region_code"] == "HH")
        assert row["realized_onset"] is True
        for source in row["source_inputs"]:
            if source["available_at"] is not None:
                assert source["available_at"] <= "2024-01-15"
        wastewater_input = next(source for source in row["source_inputs"] if source["source"] == "wastewater")
        assert wastewater_input["available_at"] == "2024-01-09"
        assert (tmp_path / "db-pit.json").exists()
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_scientific_report_contains_source_ablation_and_forbids_commercial_claims(tmp_path: Path) -> None:
    report = run_tri_layer_backtest_panel(
        _panel(),
        TriLayerBacktestConfig(
            start_date="2024-10-01",
            end_date="2024-10-10",
            include_sales=False,
            output_dir=tmp_path,
            run_id="scientific-panel",
        ),
    )

    assert report["source_availability"]["sales"]["status"] == "not_connected"
    for model_name in [
        "persistence",
        "clinical_only",
        "wastewater_only",
        "wastewater_plus_clinical",
        "forecast_proxy_only",
        "tri_layer_epi_no_sales",
    ]:
        assert model_name in report["models"]
        assert "brier_score" in report["models"][model_name]
    assert "wastewater_vs_clinical_only" in report["incremental_value"]
    assert report["claim_readiness"]["commercially_validated"] == "fail"
    assert report["claim_readiness"]["budget_ready"] == "fail"
    assert "Commercial lift validated." in report["forbidden_claims"]
    assert "Budget optimization validated." in report["forbidden_claims"]
    assert "ROI improvement proven." in report["forbidden_claims"]


def test_epidemiological_claim_is_allowed_only_when_incremental_metrics_pass(tmp_path: Path) -> None:
    improving_report = run_tri_layer_backtest_panel(
        _panel(),
        TriLayerBacktestConfig(
            start_date="2024-10-01",
            end_date="2024-10-10",
            include_sales=False,
            output_dir=tmp_path,
            run_id="claim-pass",
        ),
    )
    assert "Earlier epidemiological warning in this backtest window." in improving_report["allowed_claims"]

    weak_panel = [
        {
            "region": "Hamburg",
            "region_code": "HH",
            "source": "clinical",
            "signal_date": "2024-10-01",
            "available_date": "2024-10-01",
            "signal": 0.8,
            "intensity": 0.8,
            "growth": 0.2,
            "observed_phase": "early_growth",
            "observed_onset": True,
        },
        {
            "region": "Hamburg",
            "region_code": "HH",
            "source": "wastewater",
            "signal_date": "2024-10-01",
            "available_date": "2024-10-01",
            "signal": 0.1,
            "intensity": 0.1,
            "growth": -0.1,
            "observed_phase": "early_growth",
            "observed_onset": True,
        },
    ]
    weak_report = run_tri_layer_backtest_panel(
        weak_panel,
        TriLayerBacktestConfig(
            start_date="2024-10-01",
            end_date="2024-10-10",
            include_sales=False,
            output_dir=tmp_path,
            run_id="claim-fail",
        ),
    )

    assert "Abwasser improves forecast." in weak_report["forbidden_claims"]
    assert "Earlier epidemiological warning in this backtest window." not in weak_report["allowed_claims"]


def test_metrics_are_null_when_positive_labels_are_insufficient(tmp_path: Path) -> None:
    report = run_tri_layer_backtest_panel(
        [
            {
                "region": "Hamburg",
                "region_code": "HH",
                "source": "clinical",
                "signal_date": "2024-10-01",
                "available_date": "2024-10-01",
                "signal": 0.2,
                "intensity": 0.2,
                "growth": 0.0,
                "observed_phase": "baseline",
                "observed_onset": False,
            }
        ],
        TriLayerBacktestConfig(
            start_date="2024-10-01",
            end_date="2024-10-10",
            include_sales=False,
            output_dir=tmp_path,
        ),
    )

    assert report["models"]["tri_layer_epi_no_sales"]["pr_auc"] is None
    assert report["models"]["tri_layer_epi_no_sales"]["phase_macro_f1"] is None
    assert report["metrics"]["pr_auc"] is None
