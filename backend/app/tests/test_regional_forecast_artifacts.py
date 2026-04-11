from pathlib import Path

from app.services.ml import regional_forecast_artifacts


def test_missing_scope_returns_bootstrap_diagnostic(tmp_path: Path) -> None:
    diagnostic = regional_forecast_artifacts.build_artifact_diagnostic(
        virus_typ="Influenza A",
        horizon_days=5,
        artifact_dir=tmp_path / "influenza_a" / "horizon_5",
        missing_files=[],
        load_error="",
        supported_horizons=[3, 5, 7],
    )

    assert diagnostic["status"] == "missing"
    assert diagnostic["bootstrap_required"] is True
    assert diagnostic["artifact_scope"] == {"virus_typ": "Influenza A", "horizon_days": 5}
    assert "backfill_regional_model_artifacts.py" in diagnostic["bootstrap_command"]


def test_incomplete_scope_lists_missing_files(tmp_path: Path) -> None:
    diagnostic = regional_forecast_artifacts.build_artifact_diagnostic(
        virus_typ="RSV A",
        horizon_days=7,
        artifact_dir=tmp_path / "rsv_a" / "horizon_7",
        missing_files=["classifier.json", "calibration.pkl"],
        load_error="Artefakt-Bundle für RSV A/h7 ist unvollständig.",
        supported_horizons=[5, 7],
    )

    assert diagnostic["status"] == "incomplete"
    assert diagnostic["missing_files"] == ["classifier.json", "calibration.pkl"]
    assert "classifier.json" in diagnostic["operator_message"]
