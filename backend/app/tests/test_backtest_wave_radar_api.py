import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.backtest import router
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.database import Base, SurvstatWeeklyData


class WaveRadarApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()

        app = FastAPI()

        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db
        app.include_router(router, prefix="/api/v1/backtest")
        self.app = app
        self.client = TestClient(app)
        self.admin_headers = self._auth_headers(role="admin")
        self.user_headers = self._auth_headers(role="user")

    def tearDown(self) -> None:
        self.client.close()
        self.app.dependency_overrides.clear()
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _auth_headers(self, role: str = "admin") -> dict[str, str]:
        token = create_access_token(
            data={"sub": f"{role}@example.com", "role": role},
            expires_delta=timedelta(minutes=15),
        )
        return {"Authorization": f"Bearer {token}"}

    def _add_survstat_point(
        self,
        week_start: datetime,
        bundesland: str,
        incidence: float,
        disease: str = "Influenza, saisonal",
    ) -> None:
        iso_year, iso_week, _ = week_start.isocalendar()
        self.db.add(
            SurvstatWeeklyData(
                week_label=f"{iso_year}_{iso_week:02d}",
                week_start=week_start,
                available_time=week_start,
                year=iso_year,
                week=iso_week,
                bundesland=bundesland,
                disease=disease,
                disease_cluster="RESPIRATORY",
                age_group="Gesamt",
                incidence=incidence,
                source_file="test://wave-radar",
            )
        )

    def test_backtest_read_endpoint_requires_authentication(self) -> None:
        response = self.client.get("/api/v1/backtest/wave-radar?disease=influenza")

        self.assertEqual(response.status_code, 401)

    def test_backtest_run_requires_admin_role(self) -> None:
        response = self.client.post("/api/v1/backtest/market", headers=self.user_headers)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Not enough privileges")

    def test_backtest_run_allows_admin_role(self) -> None:
        with patch(
            "app.services.ml.backtester.BacktestService.run_market_simulation",
            return_value={"status": "ok"},
        ):
            response = self.client.post("/api/v1/backtest/market", headers=self.admin_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_wave_radar_returns_ranked_onsets_and_spread_summary(self) -> None:
        baseline_points = [
            (datetime(2024, 2, 5), "Berlin", 10.0),
            (datetime(2024, 2, 12), "Berlin", 12.0),
            (datetime(2024, 2, 5), "Hamburg", 10.0),
            (datetime(2024, 2, 12), "Hamburg", 12.0),
            (datetime(2024, 2, 5), "Bayern", 12.0),
            (datetime(2024, 2, 12), "Bayern", 14.0),
        ]
        season_points = [
            (datetime(2025, 10, 6), "Berlin", 13.0),
            (datetime(2025, 10, 13), "Berlin", 18.0),
            (datetime(2025, 10, 6), "Hamburg", 12.0),
            (datetime(2025, 10, 20), "Hamburg", 17.0),
            (datetime(2025, 10, 6), "Bayern", 14.0),
            (datetime(2025, 10, 27), "Bayern", 21.0),
        ]

        for week_start, bundesland, incidence in baseline_points + season_points:
            self._add_survstat_point(week_start, bundesland, incidence)
        self.db.commit()

        response = self.client.get(
            "/api/v1/backtest/wave-radar?disease=influenza",
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["season"], "2025/2026")
        self.assertEqual(body["summary"]["first_onset"]["bundesland"], "Berlin")
        self.assertEqual(body["summary"]["first_onset"]["date"], "2025-10-13")
        self.assertEqual(body["summary"]["last_onset"]["bundesland"], "Bayern")
        self.assertEqual(body["summary"]["last_onset"]["date"], "2025-10-27")
        self.assertEqual(body["summary"]["spread_days"], 14)
        self.assertEqual(body["summary"]["regions_affected"], 3)

        ranked_regions = [region for region in body["regions"] if region["wave_rank"] is not None][:3]
        self.assertEqual(
            [region["bundesland"] for region in ranked_regions],
            ["Berlin", "Hamburg", "Bayern"],
        )

        berlin = next(region for region in body["regions"] if region["bundesland"] == "Berlin")
        self.assertEqual(berlin["wave_rank"], 1)
        self.assertEqual(berlin["wave_start"], "2025-10-13")
        self.assertEqual(berlin["baseline_avg"], 11.0)
        self.assertEqual(berlin["threshold"], 16.5)

        heatmap_row = next(row for row in body["heatmap"] if row["week_label"] == "2025_42")
        self.assertEqual(heatmap_row["Berlin"], 18.0)
        self.assertEqual(heatmap_row["Hamburg"], 0.0)

    def test_wave_radar_returns_available_aliases_when_no_regional_data_exist(self) -> None:
        response = self.client.get(
            "/api/v1/backtest/wave-radar?disease=influenza",
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("Keine regionalen Daten", body["error"])
        self.assertIn("influenza", body["available"])
