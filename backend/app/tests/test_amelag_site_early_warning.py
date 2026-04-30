import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, WastewaterData
from app.services.media.cockpit.amelag_site_early_warning import (
    SiteEarlyWarningConfig,
    build_site_early_warning,
    evaluate_site_measurements,
)
from app.services.media.cockpit.map_section import build_map_section


def _measurement(
    value: float | None,
    *,
    datum: str,
    standort: str = "Aachen",
    bundesland: str = "NW",
    virus_typ: str = "SARS-CoV-2",
    normalisiert: float | None = None,
    unter_bg: bool | None = False,
    laborwechsel: bool | None = False,
    vorhersage: float | None = None,
) -> dict:
    normalized_value = value if normalisiert is None else normalisiert
    return {
        "standort": standort,
        "bundesland": bundesland,
        "datum": datetime.fromisoformat(datum),
        "virus_typ": virus_typ,
        "viruslast": value,
        "viruslast_normalisiert": normalized_value,
        "vorhersage": vorhersage,
        "einwohner": 206424,
        "unter_bg": unter_bg,
        "laborwechsel": laborwechsel,
    }


class AmelagSiteEarlyWarningUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = SiteEarlyWarningConfig(
            baseline_window=4,
            min_baseline_points=3,
            yellow_increase_pct=100.0,
            red_increase_pct=200.0,
            min_current_value=100.0,
            active_max_age_days=14,
        )

    def test_low_previous_value_alone_does_not_trigger_false_alarm(self) -> None:
        rows = [
            _measurement(100, datum="2026-01-01"),
            _measurement(100, datum="2026-01-03"),
            _measurement(100, datum="2026-01-05"),
            _measurement(50, datum="2026-01-07"),
            _measurement(190, datum="2026-01-09"),
        ]

        evaluated = evaluate_site_measurements(rows, self.config)

        latest = evaluated[-1]
        self.assertEqual(latest["stage"], "none")
        self.assertEqual(latest["baseline_value"], 100.0)
        self.assertEqual(latest["change_pct"], 90.0)

    def test_doubling_over_local_baseline_triggers_yellow(self) -> None:
        rows = [
            _measurement(100, datum="2026-01-01"),
            _measurement(120, datum="2026-01-03"),
            _measurement(80, datum="2026-01-05"),
            _measurement(100, datum="2026-01-07"),
            _measurement(220, datum="2026-01-09"),
        ]

        latest = evaluate_site_measurements(rows, self.config)[-1]

        self.assertEqual(latest["stage"], "yellow")
        self.assertEqual(latest["baseline_value"], 100.0)
        self.assertEqual(latest["change_pct"], 120.0)
        self.assertIn("yellow_pct_threshold", latest["quality_flags"])

    def test_large_local_increase_triggers_red(self) -> None:
        rows = [
            _measurement(100, datum="2026-01-01"),
            _measurement(100, datum="2026-01-03"),
            _measurement(100, datum="2026-01-05"),
            _measurement(350, datum="2026-01-07"),
        ]

        latest = evaluate_site_measurements(rows, self.config)[-1]

        self.assertEqual(latest["stage"], "red")
        self.assertEqual(latest["change_pct"], 250.0)
        self.assertIn("red_pct_threshold", latest["quality_flags"])

    def test_consecutive_yellow_measurements_promote_second_alert_to_red(self) -> None:
        rows = [
            _measurement(100, datum="2026-01-01"),
            _measurement(100, datum="2026-01-03"),
            _measurement(100, datum="2026-01-05"),
            _measurement(220, datum="2026-01-07"),
            _measurement(230, datum="2026-01-09"),
        ]

        evaluated = evaluate_site_measurements(rows, self.config)

        self.assertEqual(evaluated[-2]["stage"], "yellow")
        self.assertEqual(evaluated[-1]["stage"], "red")
        self.assertIn("consecutive_alert", evaluated[-1]["quality_flags"])

    def test_current_value_under_quantification_limit_blocks_alert(self) -> None:
        rows = [
            _measurement(100, datum="2026-01-01"),
            _measurement(100, datum="2026-01-03"),
            _measurement(100, datum="2026-01-05"),
            _measurement(400, datum="2026-01-07", unter_bg=True),
        ]

        latest = evaluate_site_measurements(rows, self.config)[-1]

        self.assertEqual(latest["stage"], "none")
        self.assertIn("current_under_bg", latest["quality_flags"])

    def test_missing_baseline_blocks_alert(self) -> None:
        rows = [
            _measurement(100, datum="2026-01-01"),
            _measurement(400, datum="2026-01-03"),
        ]

        latest = evaluate_site_measurements(rows, self.config)[-1]

        self.assertEqual(latest["stage"], "none")
        self.assertIn("too_few_baseline_points", latest["quality_flags"])

    def test_normalized_metric_falls_back_to_raw_viruslast(self) -> None:
        rows = [
            _measurement(100, datum="2026-01-01", normalisiert=None),
            _measurement(100, datum="2026-01-03", normalisiert=None),
            _measurement(100, datum="2026-01-05", normalisiert=None),
            _measurement(220, datum="2026-01-07", normalisiert=None),
        ]
        for row in rows:
            row["viruslast_normalisiert"] = None

        latest = evaluate_site_measurements(rows, self.config)[-1]

        self.assertEqual(latest["metric"], "viruslast")
        self.assertEqual(latest["stage"], "yellow")

    def test_latest_active_alerts_exclude_stale_site_alerts(self) -> None:
        rows = [
            _measurement(100, datum="2026-01-01", standort="Aachen"),
            _measurement(100, datum="2026-01-03", standort="Aachen"),
            _measurement(100, datum="2026-01-05", standort="Aachen"),
            _measurement(400, datum="2026-01-07", standort="Aachen"),
            _measurement(100, datum="2026-01-20", standort="Cottbus", bundesland="BB"),
            _measurement(100, datum="2026-01-22", standort="Cottbus", bundesland="BB"),
            _measurement(100, datum="2026-01-24", standort="Cottbus", bundesland="BB"),
            _measurement(400, datum="2026-02-01", standort="Cottbus", bundesland="BB"),
        ]

        payload = build_site_early_warning(rows=rows, virus_typ="SARS-CoV-2", config=self.config)

        self.assertEqual(payload["active_alert_count"], 1)
        self.assertEqual(payload["active_alerts"][0]["standort"], "Cottbus")
        self.assertEqual(payload["active_alerts"][0]["datum"], "2026-02-01")

    def test_laborwechsel_is_exposed_as_quality_flag_without_triggering_budget_power(self) -> None:
        rows = [
            _measurement(100, datum="2026-01-01"),
            _measurement(100, datum="2026-01-03"),
            _measurement(100, datum="2026-01-05"),
            _measurement(220, datum="2026-01-07", laborwechsel=True),
        ]

        payload = build_site_early_warning(rows=rows, virus_typ="SARS-CoV-2", config=self.config)

        alert = payload["active_alerts"][0]
        self.assertIn("laborwechsel", alert["quality_flags"])
        self.assertFalse(payload["can_change_budget"])
        self.assertEqual(payload["mode"], "diagnostic_only")


class AmelagSiteEarlyWarningMapIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

    def test_map_section_contains_diagnostic_site_early_warning_without_changing_ranking(self) -> None:
        db = self.Session()
        try:
            for row in [
                _measurement(1000, datum="2026-01-01", standort="Aachen", bundesland="NW"),
                _measurement(1000, datum="2026-01-03", standort="Aachen", bundesland="NW"),
                _measurement(1000, datum="2026-01-05", standort="Aachen", bundesland="NW"),
                _measurement(4000, datum="2026-01-07", standort="Aachen", bundesland="NW"),
                _measurement(1000, datum="2026-01-07", standort="Bonn", bundesland="NW"),
            ]:
                db.add(WastewaterData(**row))
            db.commit()

            payload = build_map_section(
                db,
                virus_typ="SARS-CoV-2",
                peix_score={"regions": {"NW": {"score_0_100": 55.0, "risk_band": "medium"}}},
                region_recommendations={},
            )

            self.assertIn("site_early_warning", payload)
            self.assertFalse(payload["site_early_warning"]["can_change_budget"])
            self.assertEqual(payload["site_early_warning"]["active_alert_count"], 1)
            self.assertEqual(payload["regions"]["NW"]["site_early_warning"]["active_alert_count"], 1)
            self.assertEqual(payload["activation_suggestions"][0]["budget_shift_pct"], 19.25)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
