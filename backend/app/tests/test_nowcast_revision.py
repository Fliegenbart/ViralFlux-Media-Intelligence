import unittest
from datetime import datetime

import pandas as pd

from app.services.ml.nowcast_contracts import NowcastObservation
from app.services.ml.nowcast_revision import NOWCAST_SOURCE_CONFIGS, NowcastRevisionService


class NowcastRevisionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = NowcastRevisionService()
        self.as_of = datetime(2026, 3, 17)

    def test_freshness_score_declines_linearly_until_zero(self) -> None:
        config = NOWCAST_SOURCE_CONFIGS["weather"]

        self.assertEqual(self.service._freshness_score(config=config, freshness_days=0), 1.0)
        self.assertAlmostEqual(
            self.service._freshness_score(config=config, freshness_days=2),
            0.6,
            places=6,
        )
        self.assertEqual(self.service._freshness_score(config=config, freshness_days=6), 0.0)

    def test_revision_risk_and_adjusted_value_follow_bucket_config(self) -> None:
        observation = NowcastObservation(
            source_id="survstat_kreis",
            signal_id="Influenza A",
            region_code="BY",
            reference_date=datetime(2026, 3, 10),
            as_of_date=self.as_of,
            raw_value=10.0,
            effective_available_time=self.as_of,
            timing_provenance="weekly_publication_lag",
            coverage_ratio=1.0,
        )

        result = self.service.evaluate(observation)

        self.assertTrue(result.correction_applied)
        self.assertAlmostEqual(result.revision_risk_score, 0.65, places=6)
        self.assertAlmostEqual(result.revision_adjusted_value, 10.0 / 0.72, places=6)
        self.assertEqual(result.source_freshness_days, 0)
        self.assertAlmostEqual(result.usable_confidence_score, 0.35, places=6)
        self.assertTrue(result.usable_for_forecast)
        self.assertEqual(result.metadata["age_days"], 7)

    def test_usable_confidence_logic_penalizes_low_coverage_and_staleness(self) -> None:
        low_coverage_observation = NowcastObservation(
            source_id="weather",
            signal_id="CURRENT",
            region_code="BY",
            reference_date=datetime(2026, 3, 14),
            as_of_date=self.as_of,
            raw_value=11.0,
            effective_available_time=datetime(2026, 3, 14),
            timing_provenance="forecast_run_timestamp",
            coverage_ratio=0.5,
        )
        stale_observation = NowcastObservation(
            source_id="weather",
            signal_id="CURRENT",
            region_code="BY",
            reference_date=datetime(2026, 3, 11),
            as_of_date=self.as_of,
            raw_value=11.0,
            effective_available_time=datetime(2026, 3, 11),
            timing_provenance="forecast_run_timestamp",
            coverage_ratio=1.0,
        )

        low_coverage_result = self.service.evaluate(low_coverage_observation)
        stale_result = self.service.evaluate(stale_observation)

        self.assertAlmostEqual(low_coverage_result.usable_confidence_score, 0.2, places=6)
        self.assertFalse(low_coverage_result.usable_for_forecast)
        self.assertEqual(stale_result.source_freshness_days, 6)
        self.assertEqual(stale_result.usable_confidence_score, 0.0)
        self.assertFalse(stale_result.usable_for_forecast)

    def test_preferred_value_switches_between_raw_and_revision_adjusted(self) -> None:
        corrected_result = self.service.evaluate(
            NowcastObservation(
                source_id="survstat_kreis",
                signal_id="Influenza A",
                region_code="BY",
                reference_date=datetime(2026, 3, 10),
                as_of_date=self.as_of,
                raw_value=10.0,
                effective_available_time=self.as_of,
                timing_provenance="weekly_publication_lag",
                coverage_ratio=1.0,
            )
        )
        raw_only_result = self.service.evaluate(
            NowcastObservation(
                source_id="wastewater",
                signal_id="Influenza A",
                region_code="BY",
                reference_date=datetime(2026, 3, 17),
                as_of_date=self.as_of,
                raw_value=42.0,
                effective_available_time=self.as_of,
                timing_provenance="explicit_available_time",
                coverage_ratio=1.0,
            )
        )

        self.assertAlmostEqual(
            self.service.preferred_value(corrected_result, use_revision_adjusted=False),
            10.0,
            places=6,
        )
        self.assertAlmostEqual(
            self.service.preferred_value(corrected_result, use_revision_adjusted=True),
            corrected_result.revision_adjusted_value,
            places=6,
        )
        self.assertFalse(raw_only_result.correction_applied)
        self.assertEqual(
            self.service.preferred_value(raw_only_result, use_revision_adjusted=True),
            42.0,
        )

    def test_source_specific_config_behavior_is_explicit_for_raw_only_and_missing_cases(self) -> None:
        wastewater_result = self.service.evaluate(
            NowcastObservation(
                source_id="wastewater",
                signal_id="Influenza A",
                region_code="BY",
                reference_date=datetime(2026, 3, 17),
                as_of_date=self.as_of,
                raw_value=42.0,
                effective_available_time=self.as_of,
                timing_provenance="explicit_available_time",
                coverage_ratio=1.0,
            )
        )
        corrected_missing = self.service.evaluate_missing(
            source_id="survstat_kreis",
            signal_id="Influenza A",
            region_code="BY",
            as_of_date=self.as_of,
        )
        raw_missing = self.service.evaluate_missing(
            source_id="weather",
            signal_id="CURRENT",
            region_code="BY",
            as_of_date=self.as_of,
        )

        self.assertFalse(wastewater_result.correction_applied)
        self.assertEqual(wastewater_result.revision_adjusted_value, wastewater_result.raw_observed_value)
        self.assertEqual(wastewater_result.revision_risk_score, 0.0)
        self.assertEqual(corrected_missing.revision_risk_score, 1.0)
        self.assertEqual(corrected_missing.source_freshness_days, NOWCAST_SOURCE_CONFIGS["survstat_kreis"].max_staleness_days)
        self.assertEqual(raw_missing.revision_risk_score, 0.0)
        self.assertFalse(corrected_missing.usable_for_forecast)
        self.assertFalse(raw_missing.usable_for_forecast)

    def test_evaluate_frame_uses_latest_visible_row_and_computes_coverage(self) -> None:
        frame = pd.DataFrame(
            {
                "datum": pd.to_datetime(["2026-03-15", "2026-03-16", "2026-03-17"]),
                "available_time": pd.to_datetime(["2026-03-15", "2026-03-16", "2026-03-18"]),
                "interest_score": [40.0, 50.0, 60.0],
            }
        )

        result = self.service.evaluate_frame(
            source_id="google_trends",
            signal_id="influenza",
            frame=frame,
            as_of_date=datetime(2026, 3, 17),
            value_column="interest_score",
            region_code="DE",
        )

        self.assertEqual(result.raw_observed_value, 50.0)
        self.assertEqual(result.source_freshness_days, 1)
        self.assertAlmostEqual(result.coverage_ratio, 2.0 / 21.0, places=6)
        self.assertEqual(result.metadata["timing_provenance"], "platform_delay")


if __name__ == "__main__":
    unittest.main()
