import unittest
from datetime import datetime, timedelta

from app.services.media.cockpit_service import MediaCockpitService


class CockpitServiceGuardTests(unittest.TestCase):
    def test_normalize_freshness_timestamp_clamps_future_values(self) -> None:
        now = datetime(2026, 3, 5, 12, 0, 0)
        future = now + timedelta(days=3)

        normalized = MediaCockpitService._normalize_freshness_timestamp(future, now=now)

        self.assertEqual(normalized, now.isoformat())

    def test_normalize_freshness_timestamp_keeps_past_values(self) -> None:
        now = datetime(2026, 3, 5, 12, 0, 0)
        past = now - timedelta(days=2)

        normalized = MediaCockpitService._normalize_freshness_timestamp(past, now=now)

        self.assertEqual(normalized, past.isoformat())

    def test_primary_signal_score_prefers_signal_score_over_legacy_alias(self) -> None:
        score = MediaCockpitService._primary_signal_score({
            "signal_score": 67.0,
            "peix_score": 63.0,
            "impact_probability": 88.0,
        })

        self.assertEqual(score, 67.0)

    def test_ranking_signal_fields_mark_legacy_alias_as_deprecated(self) -> None:
        payload = MediaCockpitService(None)._ranking_signal_fields(
            signal_score=67.0,
            legacy_alias=88.0,
            source="PeixEpiScore",
        )

        self.assertEqual(payload["score_semantics"], "ranking_signal")
        self.assertEqual(payload["impact_probability_semantics"], "ranking_signal")
        self.assertTrue(payload["impact_probability_deprecated"])
        self.assertEqual(payload["signal_score"], 67.0)
        self.assertEqual(payload["impact_probability"], 88.0)


if __name__ == "__main__":
    unittest.main()
