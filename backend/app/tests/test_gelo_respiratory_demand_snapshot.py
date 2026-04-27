from datetime import date, datetime, timedelta, timezone
import unittest

try:
    from backend.scripts.run_gelo_respiratory_demand_snapshot import (
        _fetch_h5_forecasts,
        build_gelo_respiratory_demand_snapshot,
    )
except ModuleNotFoundError:
    from scripts.run_gelo_respiratory_demand_snapshot import (
        _fetch_h5_forecasts,
        build_gelo_respiratory_demand_snapshot,
    )


class GeloRespiratoryDemandSnapshotTests(unittest.TestCase):
    def test_fetch_query_uses_sqlalchemy_safe_date_cast_for_target_window(self):
        class FakeRows:
            def mappings(self):
                return self

            def all(self):
                return []

        class FakeDb:
            statement = ""

            def execute(self, statement, params):
                self.statement = str(statement)
                return FakeRows()

        db = FakeDb()

        _fetch_h5_forecasts(
            db,
            horizon_days=5,
            target_start=datetime(2026, 1, 20).date(),
            target_days=5,
        )

        self.assertNotIn(":target_start::date", db.statement)
        self.assertIn("cast(:target_start as date)", db.statement)

    def test_fetch_returns_ordered_daily_curves_instead_of_last_day_only(self):
        generated_at = datetime(2026, 1, 20, 9, 0, tzinfo=timezone.utc)

        class FakeRows:
            def mappings(self):
                return self

            def all(self):
                return [
                    {
                        "virus_typ": "RSV A",
                        "region": "BE",
                        "forecast_date": date(2026, 1, 21),
                        "predicted_value": 2.0,
                        "created_at": generated_at,
                    },
                    {
                        "virus_typ": "RSV A",
                        "region": "BE",
                        "forecast_date": date(2026, 1, 20),
                        "predicted_value": 1.0,
                        "created_at": generated_at,
                    },
                ]

        class FakeDb:
            statement = ""

            def execute(self, statement, params):
                self.statement = str(statement)
                return FakeRows()

        db = FakeDb()

        forecasts_by_virus, latest_created_at = _fetch_h5_forecasts(
            db,
            horizon_days=5,
            target_start=datetime(2026, 1, 20).date(),
            target_days=5,
        )

        self.assertIn(
            "partition by virus_typ, region, forecast_date::date",
            db.statement,
        )
        self.assertEqual(latest_created_at, generated_at)
        self.assertEqual(
            forecasts_by_virus["RSV A"]["Berlin"],
            [
                {"forecast_date": "2026-01-20", "predicted_value": 1.0},
                {"forecast_date": "2026-01-21", "predicted_value": 2.0},
            ],
        )

    def test_normalises_short_state_codes_to_customer_readable_names(self):
        generated_at = datetime(2026, 1, 20, 9, 0, tzinfo=timezone.utc)

        snapshot = build_gelo_respiratory_demand_snapshot(
            {
                "Influenza A": {"HH": 10.0, "ST": 1.0},
                "RSV A": {"HH": 8.0, "ST": 2.0},
            },
            generated_at=generated_at,
            latest_created_at=generated_at,
            min_regions=2,
            min_components=2,
        )

        self.assertEqual(snapshot["rankings"][0]["region"], "Hamburg")

    def test_builds_ranked_index_from_influenza_rsv_and_covid_components(self):
        generated_at = datetime(2026, 1, 20, 9, 0, tzinfo=timezone.utc)
        forecasts_by_virus = {
            "Influenza A": {
                "Bayern": 80.0,
                "Berlin": 5.0,
                "Hessen": 20.0,
            },
            "Influenza B": {
                "Bayern": 20.0,
                "Berlin": 2.0,
                "Hessen": 5.0,
            },
            "RSV A": {
                "Bayern": 1.0,
                "Berlin": 40.0,
                "Hessen": 5.0,
            },
            "SARS-CoV-2": {
                "Bayern": 1.0,
                "Berlin": 8.0,
                "Hessen": 4.0,
            },
        }

        snapshot = build_gelo_respiratory_demand_snapshot(
            forecasts_by_virus,
            generated_at=generated_at,
            latest_created_at=generated_at - timedelta(hours=2),
            min_regions=3,
            min_components=2,
        )

        rankings = snapshot["rankings"]

        self.assertEqual(rankings[0]["region"], "Berlin")
        self.assertAlmostEqual(rankings[0]["demand_score"], 0.55)
        self.assertEqual(
            set(rankings[0]["component_contributions"]),
            {"influenza", "rsv", "covid"},
        )
        self.assertEqual(
            rankings[0]["component_contributions"]["influenza"]["label"],
            "Influenza gesamt",
        )
        self.assertTrue(snapshot["quality_gate"]["budget_eligible"])

    def test_curve_mode_ranks_visible_rise_above_high_but_falling_level(self):
        generated_at = datetime(2026, 1, 20, 9, 0, tzinfo=timezone.utc)
        forecasts_by_virus = {
            "Influenza A": {
                "Bayern": [
                    {"forecast_date": "2026-01-20", "predicted_value": 100.0},
                    {"forecast_date": "2026-01-24", "predicted_value": 90.0},
                ],
                "Berlin": [
                    {"forecast_date": "2026-01-20", "predicted_value": 10.0},
                    {"forecast_date": "2026-01-24", "predicted_value": 30.0},
                ],
            },
            "RSV A": {
                "Bayern": [
                    {"forecast_date": "2026-01-20", "predicted_value": 50.0},
                    {"forecast_date": "2026-01-24", "predicted_value": 45.0},
                ],
                "Berlin": [
                    {"forecast_date": "2026-01-20", "predicted_value": 5.0},
                    {"forecast_date": "2026-01-24", "predicted_value": 15.0},
                ],
            },
        }

        snapshot = build_gelo_respiratory_demand_snapshot(
            forecasts_by_virus,
            generated_at=generated_at,
            latest_created_at=generated_at,
            min_regions=2,
            min_components=2,
        )

        rankings = snapshot["rankings"]
        berlin = rankings[0]
        bayern = next(row for row in rankings if row["region"] == "Bayern")

        self.assertEqual(snapshot["scope"]["score_mode"], "forecast_curve_rise")
        self.assertEqual(berlin["region"], "Berlin")
        self.assertGreater(berlin["demand_score"], bayern["demand_score"])
        self.assertAlmostEqual(
            berlin["component_contributions"]["influenza"]["forecast_start_value"],
            10.0,
        )
        self.assertAlmostEqual(
            berlin["component_contributions"]["influenza"]["forecast_end_value"],
            30.0,
        )
        self.assertAlmostEqual(
            berlin["component_contributions"]["influenza"]["absolute_change"],
            20.0,
        )
        self.assertAlmostEqual(
            berlin["component_contributions"]["influenza"]["relative_change_pct"],
            200.0,
        )
        self.assertAlmostEqual(
            bayern["component_contributions"]["influenza"]["signal_value"],
            0.0,
        )

    def test_marks_snapshot_not_budget_eligible_when_forecasts_are_stale(self):
        generated_at = datetime(2026, 1, 20, 9, 0, tzinfo=timezone.utc)
        forecasts_by_virus = {
            "Influenza A": {"Bayern": 10.0, "Berlin": 1.0, "Hessen": 3.0},
            "RSV A": {"Bayern": 1.0, "Berlin": 10.0, "Hessen": 2.0},
        }

        snapshot = build_gelo_respiratory_demand_snapshot(
            forecasts_by_virus,
            generated_at=generated_at,
            latest_created_at=generated_at - timedelta(hours=96),
            max_age_hours=72,
            min_regions=3,
            min_components=2,
        )

        self.assertFalse(snapshot["quality_gate"]["data_fresh"])
        self.assertFalse(snapshot["quality_gate"]["budget_eligible"])
        self.assertTrue(
            snapshot["quality_gate"]["gate_paths"]["regional_forecast_ensemble"]
        )
        self.assertTrue(snapshot["rankings"])
        self.assertFalse(snapshot["rankings"][0]["budget_eligible"])

    def test_blocks_regions_with_unrealistic_component_forecasts(self):
        generated_at = datetime(2026, 1, 20, 9, 0, tzinfo=timezone.utc)
        forecasts_by_virus = {
            "Influenza A": {
                "Hamburg": 12976.0,
                "Bayern": 10.0,
                "Berlin": 9.0,
            },
            "Influenza B": {
                "Hamburg": 10000.0,
                "Bayern": 5.0,
                "Berlin": 3.0,
            },
            "RSV A": {
                "Hamburg": 17621.0,
                "Bayern": 4.0,
                "Berlin": 2.0,
            },
        }

        snapshot = build_gelo_respiratory_demand_snapshot(
            forecasts_by_virus,
            generated_at=generated_at,
            latest_created_at=generated_at,
            min_regions=3,
            min_components=2,
        )

        hamburg = next(
            row for row in snapshot["rankings"] if row["region"] == "Hamburg"
        )

        self.assertFalse(hamburg["budget_eligible"])
        self.assertIn("outlier", hamburg["blocked_reasons"])
        self.assertIn(
            "outlier regions: Hamburg",
            snapshot["quality_gate"]["notes"],
        )

    def test_feature_staleness_blocks_budget_even_when_forecast_row_is_fresh(self):
        generated_at = datetime(2026, 1, 20, 9, 0, tzinfo=timezone.utc)
        forecasts_by_virus = {
            "Influenza A": {"Bayern": 10.0, "Berlin": 1.0, "Hessen": 3.0},
            "RSV A": {"Bayern": 1.0, "Berlin": 10.0, "Hessen": 2.0},
        }

        snapshot = build_gelo_respiratory_demand_snapshot(
            forecasts_by_virus,
            generated_at=generated_at,
            latest_created_at=generated_at,
            feature_as_of=date(2026, 1, 10),
            max_feature_age_days=7,
            min_regions=3,
            min_components=2,
        )

        self.assertFalse(snapshot["quality_gate"]["feature_fresh"])
        self.assertFalse(snapshot["quality_gate"]["budget_eligible"])
        self.assertFalse(snapshot["rankings"][0]["budget_eligible"])
        self.assertIn("feature freshness gate is red", snapshot["quality_gate"]["notes"])

    def test_watch_component_gate_blocks_budget_eligibility(self):
        generated_at = datetime(2026, 1, 20, 9, 0, tzinfo=timezone.utc)
        forecasts_by_virus = {
            "Influenza A": {"Bayern": 10.0, "Berlin": 1.0, "Hessen": 3.0},
            "RSV A": {"Bayern": 1.0, "Berlin": 10.0, "Hessen": 2.0},
        }

        snapshot = build_gelo_respiratory_demand_snapshot(
            forecasts_by_virus,
            generated_at=generated_at,
            latest_created_at=generated_at,
            component_quality_gates={"influenza": "GO", "rsv": "WATCH"},
            min_regions=3,
            min_components=2,
        )

        self.assertFalse(snapshot["quality_gate"]["component_quality"])
        self.assertFalse(snapshot["quality_gate"]["budget_eligible"])
        self.assertFalse(snapshot["rankings"][0]["budget_eligible"])
        self.assertEqual(
            snapshot["component_weights"]["rsv"]["quality_gate"],
            "WATCH",
        )


if __name__ == "__main__":
    unittest.main()
