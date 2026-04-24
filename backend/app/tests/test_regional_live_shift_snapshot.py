import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, MLForecast
from app.services.ml.regional_live_shift_snapshot import RegionalLiveShiftSnapshotService


class RegionalLiveShiftSnapshotServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def _add_forecast_run(
        self,
        *,
        virus_typ: str = "Influenza A",
        region: str = "BY",
        values: list[float],
        model_version: str = "xgb_stack_direct_h5_inline",
        feature_as_of: str = "2026-04-20",
        issue_date: str = "2026-04-24",
        extension_reason: str = "extended",
        created_at: datetime | None = None,
    ) -> None:
        created_at = created_at or datetime(2026, 4, 24, 8, 0, 0)
        start_date = datetime(2026, 4, 25)
        for index, value in enumerate(values):
            self.db.add(
                MLForecast(
                    created_at=created_at,
                    forecast_date=start_date + timedelta(days=index),
                    virus_typ=virus_typ,
                    region=region,
                    horizon_days=5,
                    predicted_value=value,
                    lower_bound=max(0.0, value * 0.8),
                    upper_bound=value * 1.2,
                    confidence=0.72,
                    model_version=model_version,
                    outbreak_risk_score=0.61,
                    features_used={
                        "feature_freshness": {
                            "feature_as_of": feature_as_of,
                            "issue_date": issue_date,
                            "extension_reason": extension_reason,
                            "extension_applied": extension_reason == "extended",
                        }
                    },
                )
            )
        self.db.commit()

    def test_inline_h5_riser_is_ranked_but_not_budget_releasable(self) -> None:
        self._add_forecast_run(region="BY", values=[100.0, 115.0, 130.0, 145.0, 160.0])

        payload = RegionalLiveShiftSnapshotService(self.db).build_snapshot(
            virus_types=["Influenza A"],
            horizon_days=5,
            max_feature_gap_days=10,
        )

        region = payload["viruses"]["Influenza A"]["regions"][0]
        self.assertEqual(region["region"], "BY")
        self.assertTrue(region["increase_detected"])
        self.assertEqual(region["change_pct"], 60.0)
        self.assertEqual(region["budget_release_status"], "candidate_only")
        self.assertFalse(region["budget_releasable"])
        self.assertIn("model_not_promoted_inline", region["blockers"])
        self.assertEqual(payload["viruses"]["Influenza A"]["top_candidates"][0]["region"], "BY")

    def test_promoted_fresh_riser_can_be_budget_releasable(self) -> None:
        self._add_forecast_run(
            region="NW",
            values=[200.0, 230.0, 260.0, 290.0, 320.0],
            model_version="xgb_stack_direct_h5_promoted",
        )

        payload = RegionalLiveShiftSnapshotService(self.db).build_snapshot(
            virus_types=["Influenza A"],
            horizon_days=5,
            max_feature_gap_days=10,
        )

        region = payload["viruses"]["Influenza A"]["regions"][0]
        self.assertEqual(region["region"], "NW")
        self.assertEqual(region["budget_release_status"], "go")
        self.assertTrue(region["budget_releasable"])
        self.assertEqual(region["blockers"], [])

    def test_stale_or_gap_too_large_features_block_budget(self) -> None:
        self._add_forecast_run(
            region="HH",
            values=[100.0, 130.0, 160.0, 190.0, 220.0],
            feature_as_of="2026-04-01",
            issue_date="2026-04-24",
            extension_reason="gap_too_large",
        )

        payload = RegionalLiveShiftSnapshotService(self.db).build_snapshot(
            virus_types=["Influenza A"],
            horizon_days=5,
            max_feature_gap_days=10,
        )

        region = payload["viruses"]["Influenza A"]["regions"][0]
        self.assertEqual(region["region"], "HH")
        self.assertEqual(region["feature_gap_days"], 23)
        self.assertEqual(region["budget_release_status"], "blocked")
        self.assertFalse(region["budget_releasable"])
        self.assertIn("feature_gap_too_large", region["blockers"])
        self.assertIn("feature_extension_failed", region["blockers"])

    def test_missing_regions_are_reported_per_virus(self) -> None:
        self._add_forecast_run(
            virus_typ="RSV A",
            region="BY",
            values=[20.0, 21.0, 23.0, 25.0, 26.0],
            model_version="xgb_stack_direct_h5_promoted",
        )

        payload = RegionalLiveShiftSnapshotService(self.db).build_snapshot(
            virus_types=["RSV A"],
            horizon_days=5,
        )

        missing = payload["summary"]["missing_regions_by_virus"]["RSV A"]
        self.assertIn("BW", missing)
        self.assertIn("BE", missing)
        self.assertNotIn("BY", missing)


if __name__ == "__main__":
    unittest.main()
