from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.media_routes_cockpit_phase_lead import router
from app.api.media_routes_cockpit_snapshot import require_cockpit_auth
from app.db.session import get_db


def test_phase_lead_snapshot_endpoint_uses_live_database_builder() -> None:
    app = FastAPI()

    def override_get_db():
        yield "db-session"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_cockpit_auth] = lambda: {"principal": "test"}
    app.include_router(router, prefix="/api/v1/media")
    client = TestClient(app)
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
