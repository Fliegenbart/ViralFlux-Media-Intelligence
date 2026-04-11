from pathlib import Path

from app.services.ml import regional_forecast_artifacts


class _FakeArtifactService:
    def __init__(self, *, models_dir: Path, missing_files: list[str] | None = None, payload=None) -> None:
        self.models_dir = models_dir
        self._missing_files = list(missing_files or [])
        self._payload = payload

    def _missing_artifact_files(self, model_dir: Path) -> list[str]:
        return list(self._missing_files)

    def _artifact_payload_from_dir(self, model_dir: Path):
        return dict(self._payload or {})

    def _target_window_for_horizon(self, horizon: int):
        return [horizon, horizon]

    def _invalid_inference_feature_columns(self, feature_columns: list[str]) -> list[str]:
        return [
            column
            for column in feature_columns
            if column == "target_incidence"
        ]


def _load_artifacts(
    *,
    service: _FakeArtifactService,
    virus_typ: str,
    horizon_days: int,
    regional_dir: Path,
) -> dict:
    return regional_forecast_artifacts.load_artifacts(
        service,
        virus_typ=virus_typ,
        horizon_days=horizon_days,
        ensure_supported_horizon_fn=lambda value: value,
        regional_model_artifact_dir_fn=lambda models_dir, *, virus_typ, horizon_days: regional_dir,
        supported_forecast_horizons=[3, 5, 7],
        target_window_days=[horizon_days, horizon_days],
        virus_slug_fn=lambda value: value.lower().replace(" ", "_"),
        training_only_panel_columns=["target_incidence"],
    )


def test_missing_scope_returns_bootstrap_diagnostic(tmp_path: Path) -> None:
    regional_dir = tmp_path / "influenza_a" / "horizon_5"
    service = _FakeArtifactService(models_dir=tmp_path)

    payload = _load_artifacts(
        service=service,
        virus_typ="Influenza A",
        horizon_days=5,
        regional_dir=regional_dir,
    )

    diagnostic = payload["artifact_diagnostic"]
    assert diagnostic["status"] == "missing"
    assert diagnostic["bootstrap_required"] is True
    assert diagnostic["artifact_scope"] == {"virus_typ": "Influenza A", "horizon_days": 5}
    assert "backfill_regional_model_artifacts.py" in diagnostic["bootstrap_command"]


def test_incomplete_scope_lists_missing_files(tmp_path: Path) -> None:
    regional_dir = tmp_path / "rsv_a" / "horizon_7"
    regional_dir.mkdir(parents=True)
    service = _FakeArtifactService(
        models_dir=tmp_path,
        missing_files=["classifier.json", "calibration.pkl"],
    )

    payload = _load_artifacts(
        service=service,
        virus_typ="RSV A",
        horizon_days=7,
        regional_dir=regional_dir,
    )

    diagnostic = payload["artifact_diagnostic"]
    assert diagnostic["status"] == "incomplete"
    assert diagnostic["missing_files"] == ["classifier.json", "calibration.pkl"]
    assert "classifier.json" in diagnostic["operator_message"]


def test_invalid_scope_keeps_only_load_error(tmp_path: Path) -> None:
    regional_dir = tmp_path / "influenza_a" / "horizon_7"
    regional_dir.mkdir(parents=True)
    service = _FakeArtifactService(
        models_dir=tmp_path,
        payload={
            "metadata": {
                "horizon_days": 7,
                "feature_columns": ["feature_a", "target_incidence"],
            }
        },
    )

    payload = _load_artifacts(
        service=service,
        virus_typ="Influenza A",
        horizon_days=7,
        regional_dir=regional_dir,
    )

    assert "load_error" in payload
    assert "artifact_diagnostic" not in payload
