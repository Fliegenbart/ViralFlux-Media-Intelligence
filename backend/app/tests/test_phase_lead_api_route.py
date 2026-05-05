import json
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.media_routes_cockpit_phase_lead import router
from app.api.media_routes_cockpit_snapshot import require_cockpit_auth
from app.db.session import get_db


def _phase_lead_client() -> tuple[FastAPI, TestClient]:
    app = FastAPI()

    def override_get_db():
        yield "db-session"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_cockpit_auth] = lambda: {"principal": "test"}
    app.include_router(router, prefix="/api/v1/media")
    return app, TestClient(app)


def test_phase_lead_snapshot_endpoint_prefers_cached_map_artifact(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PHASE_LEAD_ARTIFACT_DIR", str(tmp_path))
    cached_snapshot = {
        "module": "phase_lead_graph_renewal_filter",
        "version": "plgrf_live_v0",
        "mode": "research",
        "as_of": "2026-05-04",
        "virus_typ": "Influenza A",
        "horizons": [3, 7, 14],
        "summary": {
            "data_source": "live_database",
            "fit_mode": "map_optimization",
            "observation_count": 877,
            "window_start": "2026-02-12",
            "window_end": "2026-04-22",
            "converged": False,
            "objective_value": 1406.3,
            "data_vintage_hash": "data-hash",
            "config_hash": "config-hash",
            "top_region": "NI",
            "warning_count": 1,
        },
        "sources": {},
        "regions": [{"region_code": "NI", "region": "Niedersachsen"}],
        "rankings": {"Influenza A": [{"region_id": "NI", "gegb": 43.9}]},
        "warnings": ["optimizer warning"],
    }
    (tmp_path / "manual_phase_lead_influenza_a_latest.json").write_text(
        '{"manual_run":{"virus_typ":"Influenza A","window_days":70,"n_samples":80,"max_iter":250},'
        '"snapshot":'
        + json.dumps(cached_snapshot)
        + "}",
        encoding="utf-8",
    )
    app, client = _phase_lead_client()

    try:
        with patch(
            "app.api.media_routes_cockpit_phase_lead.build_live_phase_lead_snapshot",
            return_value={"module": "fallback"},
        ) as builder:
            response = client.get(
                "/api/v1/media/cockpit/phase-lead/snapshot"
                "?virus_typ=Influenza%20A&window_days=70&n_samples=80&max_iter=0"
            )
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == cached_snapshot
    builder.assert_not_called()


def test_phase_lead_snapshot_endpoint_uses_live_database_builder(monkeypatch) -> None:
    monkeypatch.delenv("PHASE_LEAD_ARTIFACT_DIR", raising=False)
    app, client = _phase_lead_client()
    expected = {
        "module": "phase_lead_graph_renewal_filter",
        "summary": {"data_source": "live_database"},
    }

    try:
        with patch(
            "app.api.media_routes_cockpit_phase_lead.build_live_phase_lead_snapshot",
            return_value=expected,
        ) as builder:
            response = client.get(
                "/api/v1/media/cockpit/phase-lead/snapshot"
                "?virus_typ=Influenza%20A&window_days=42&n_samples=12&max_iter=7"
            )
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == expected
    builder.assert_called_once()
    assert builder.call_args.args == ("db-session",)
    assert builder.call_args.kwargs["virus_typ"] == "Influenza A"
    assert builder.call_args.kwargs["window_days"] == 42
    assert builder.call_args.kwargs["n_samples"] == 12
    assert builder.call_args.kwargs["max_iter"] == 7
    assert builder.call_args.kwargs["max_fun"] == 250_000
