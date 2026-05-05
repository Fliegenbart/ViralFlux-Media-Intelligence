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


def _aggregate_snapshot(virus_typ: str, top_region: str = "HE") -> dict:
    return {
        "module": "phase_lead_graph_renewal_filter",
        "version": "plgrf_live_v0",
        "mode": "research",
        "as_of": "2026-05-05",
        "virus_typ": virus_typ,
        "horizons": [3, 5, 7, 10, 14],
        "summary": {
            "data_source": "live_database",
            "fit_mode": "map_optimization",
            "observation_count": 100,
            "window_start": "2026-02-17",
            "window_end": "2026-04-27",
            "converged": True,
            "objective_value": 100.0,
            "data_vintage_hash": f"data-{virus_typ}",
            "config_hash": f"config-{virus_typ}",
            "top_region": top_region,
            "warning_count": 0,
        },
        "sources": {
            "wastewater": {
                "rows": 100,
                "latest_event_date": "2026-05-01",
                "units": [top_region],
            }
        },
        "regions": [
            {
                "region_code": top_region,
                "region": "Hessen" if top_region == "HE" else top_region,
                "current_level": 3.0,
                "current_growth": 0.1,
                "p_up_h7": 0.8,
                "p_surge_h7": 0.4,
                "p_front": 0.2,
                "eeb": 10.0,
                "gegb": 40.0,
                "source_rows": 20,
            }
        ],
        "rankings": {virus_typ: [{"region_id": top_region, "gegb": 40.0}]},
        "warnings": [],
    }


def test_phase_lead_aggregate_endpoint_builds_total_from_cached_artifacts(monkeypatch) -> None:
    app, client = _phase_lead_client()

    try:
        with patch(
            "app.api.media_routes_cockpit_phase_lead.load_cached_phase_lead_map_snapshot",
            side_effect=lambda **kwargs: _aggregate_snapshot(kwargs["virus_typ"]),
        ) as loader, patch(
            "app.api.media_routes_cockpit_phase_lead.build_live_phase_lead_snapshot",
            return_value={"module": "fallback"},
        ) as live_builder:
            response = client.get(
                "/api/v1/media/cockpit/phase-lead/aggregate?window_days=70&n_samples=80"
            )
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["virus_typ"] == "Gesamt"
    assert body["version"] == "plgrf_aggregate_v0"
    assert body["aggregate"]["weighting"] == "data_quality"
    assert len(body["aggregate"]["virus_weights"]) == 4
    assert loader.call_count == 4
    live_builder.assert_not_called()


def test_phase_lead_aggregate_endpoint_uses_fast_fallback_without_map_optimization() -> None:
    app, client = _phase_lead_client()

    def cached_or_missing(**kwargs):
        if kwargs["virus_typ"] == "RSV A":
            return None
        return _aggregate_snapshot(kwargs["virus_typ"])

    try:
        with patch(
            "app.api.media_routes_cockpit_phase_lead.load_cached_phase_lead_map_snapshot",
            side_effect=cached_or_missing,
        ), patch(
            "app.api.media_routes_cockpit_phase_lead.build_live_phase_lead_snapshot",
            return_value=_aggregate_snapshot("RSV A", top_region="NI"),
        ) as live_builder:
            response = client.get(
                "/api/v1/media/cockpit/phase-lead/aggregate?window_days=70&n_samples=80"
            )
    finally:
        client.close()
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert any("RSV A" in warning and "Schnellmodus" in warning for warning in body["warnings"])
    live_builder.assert_called_once()
    assert live_builder.call_args.kwargs["virus_typ"] == "RSV A"
    assert live_builder.call_args.kwargs["max_iter"] == 0
