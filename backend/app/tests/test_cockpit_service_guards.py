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

    def test_signal_snapshot_prefers_signal_score_for_top_region(self) -> None:
        snapshot = MediaCockpitService(None)._signal_snapshot_section(
            virus_typ="Influenza A",
            peix_score={
                "national_band": "high",
                "top_drivers": [{"label": "AMELAG"}],
                "national_score": 72.0,
                "national_impact_probability": 84.0,
            },
            map_section={
                "top_regions": [
                    {
                        "code": "SH",
                        "name": "Schleswig-Holstein",
                        "trend": "steigend",
                        "signal_score": 68.0,
                        "impact_probability": 91.0,
                    },
                ],
            },
        )

        self.assertEqual(snapshot["national"]["signal_score"], 72.0)
        self.assertEqual(snapshot["national"]["impact_probability"], 84.0)
        self.assertEqual(snapshot["top_region"]["signal_score"], 68.0)
        self.assertEqual(snapshot["top_region"]["impact_probability"], 91.0)

    def test_campaign_refs_section_normalizes_and_sorts_references(self) -> None:
        payload = MediaCockpitService(None)._campaign_refs_section({
            "HH": {
                "card_id": "card-hh",
                "detail_url": "/kampagnen/card-hh",
                "status": "READY",
                "urgency_score": 52.0,
                "brand": "gelo",
                "product": "GeloProsed",
                "priority_score": 52.0,
                "ignored_field": "x",
            },
            "SH": {
                "card_id": "card-sh",
                "detail_url": "/kampagnen/card-sh",
                "status": "APPROVED",
                "urgency_score": 71.0,
                "brand": "gelo",
                "product": "GeloRevoice",
                "priority_score": 71.0,
            },
        })

        self.assertEqual(payload["regions_with_recommendations"], 2)
        self.assertEqual(payload["items"][0]["region_code"], "SH")
        self.assertNotIn("ignored_field", payload["items"][0])


if __name__ == "__main__":
    unittest.main()
