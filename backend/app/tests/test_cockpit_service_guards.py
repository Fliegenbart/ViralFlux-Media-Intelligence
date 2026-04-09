import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, WastewaterData
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


class CockpitMapSectionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()
        self.service = MediaCockpitService(self.db)

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_map_section_returns_empty_payload_without_wastewater_data(self) -> None:
        payload = self.service._map_section(
            virus_typ="Influenza A",
            peix_score={"regions": {}},
            region_recommendations={},
        )

        self.assertFalse(payload["has_data"])
        self.assertEqual(payload["regions"], {})
        self.assertEqual(payload["top_regions"], [])
        self.assertEqual(payload["activation_suggestions"], [])

    def test_map_section_keeps_top_region_and_peix_only_fallback_region(self) -> None:
        current_date = datetime(2026, 3, 10)
        previous_date = datetime(2026, 3, 3)
        self.db.add_all([
            WastewaterData(
                standort="plant-sh-current",
                bundesland="SH",
                datum=current_date,
                available_time=current_date,
                virus_typ="Influenza A",
                viruslast=120.0,
                viruslast_normalisiert=62.0,
                vorhersage=156.0,
                einwohner=100000,
            ),
            WastewaterData(
                standort="plant-sh-previous",
                bundesland="SH",
                datum=previous_date,
                available_time=previous_date,
                virus_typ="Influenza A",
                viruslast=90.0,
                viruslast_normalisiert=51.0,
                vorhersage=95.0,
                einwohner=100000,
            ),
        ])
        self.db.commit()

        payload = self.service._map_section(
            virus_typ="Influenza A",
            peix_score={
                "regions": {
                    "SH": {
                        "score_0_100": 78.0,
                        "risk_band": "high",
                        "top_drivers": [{"label": "AMELAG"}],
                    },
                    "BE": {
                        "score_0_100": 61.0,
                        "risk_band": "elevated",
                        "top_drivers": [{"label": "Forecast"}],
                    },
                },
            },
            region_recommendations={},
        )

        self.assertTrue(payload["has_data"])
        self.assertEqual(payload["top_regions"][0]["code"], "SH")
        self.assertIn("BE", payload["regions"])
        self.assertEqual(payload["regions"]["BE"]["avg_viruslast"], 0.0)
        self.assertTrue(any(item["region"] == "SH" for item in payload["activation_suggestions"]))


if __name__ == "__main__":
    unittest.main()
