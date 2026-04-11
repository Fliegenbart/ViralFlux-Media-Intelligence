import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import (
    AREKonsultation,
    Base,
    GoogleTrendsData,
    MarketingOpportunity,
    NotaufnahmeSyndromData,
    WastewaterData,
    WeatherData,
)
from app.services.media.cockpit.recommendations import (
    build_recommendation_section,
    build_region_recommendation_refs,
)
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
        self.assertEqual(
            snapshot["national"]["field_contracts"]["signal_score"]["source"],
            "RankingSignal",
        )
        self.assertEqual(
            snapshot["top_region"]["field_contracts"]["signal_score"]["source"],
            "RankingSignal",
        )

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

    def test_recommendation_section_wrapper_delegates_via_module_path(self) -> None:
        service = MediaCockpitService(db=object())
        expected = {"total": 1, "cards": [{"id": "patched"}]}

        with patch(
            "app.services.media.cockpit.recommendations.build_recommendation_section",
            return_value=expected,
        ) as build_mock:
            payload = service._recommendation_section()

        self.assertIs(payload, expected)
        build_mock.assert_called_once_with(service.db)

    def test_region_recommendation_refs_wrapper_delegates_via_module_path(self) -> None:
        service = MediaCockpitService(db=object())
        expected = {"SH": {"card_id": "patched"}}

        with patch(
            "app.services.media.cockpit.recommendations.build_region_recommendation_refs",
            return_value=expected,
        ) as build_mock:
            payload = service._region_recommendation_refs()

        self.assertIs(payload, expected)
        build_mock.assert_called_once_with(service.db)

    def test_extract_region_codes_wrapper_delegates_via_module_path(self) -> None:
        service = MediaCockpitService(db=None)
        row = MarketingOpportunity(opportunity_id="opp-wrapper")
        expected = ["SH", "HH"]

        with patch(
            "app.services.media.cockpit.recommendations.extract_region_codes_from_row",
            return_value=expected,
        ) as extract_mock:
            payload = service._extract_region_codes_from_row(row)

        self.assertIs(payload, expected)
        extract_mock.assert_called_once_with(row)

    def test_get_cockpit_payload_exposes_neutral_ranking_signal_alias(self) -> None:
        service = MediaCockpitService(db=object())
        ranking_signal = {"national_score": 71.0, "national_band": "high"}
        peix_service = unittest.mock.Mock()
        peix_service.build.return_value = ranking_signal

        with (
            patch("app.services.media.cockpit_service.RankingSignalService", return_value=peix_service),
            patch.object(service, "_data_freshness", return_value={}),
            patch.object(service, "_source_status", return_value={"items": []}),
            patch.object(service, "_region_recommendation_refs", return_value={}),
            patch.object(service, "_map_section", return_value={}),
            patch.object(service, "_signal_snapshot_section", return_value={}),
            patch.object(service, "_bento_section", return_value={}),
            patch.object(service, "_source_freshness_summary", return_value={}),
            patch.object(service, "_campaign_refs_section", return_value={}),
            patch.object(service, "_recommendation_section", return_value={}),
            patch.object(service, "_backtest_summary", return_value={}),
        ):
            payload = service.get_cockpit_payload(virus_typ="Influenza A")

        self.assertEqual(payload["ranking_signal"], ranking_signal)
        self.assertEqual(payload["peix_epi_score"], ranking_signal)


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
        self.assertEqual(payload["regions"]["SH"]["ranking_signal_score"], 78.0)
        self.assertEqual(payload["regions"]["SH"]["tooltip"]["ranking_signal_score"], 78.0)
        self.assertEqual(payload["regions"]["SH"]["tooltip"]["signal_band"], "high")
        self.assertEqual(
            payload["activation_suggestions"][0]["field_contracts"]["signal_score"]["source"],
            "RankingSignal",
        )


class CockpitBentoSectionContractTests(unittest.TestCase):
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

    def test_bento_section_exposes_tiles_with_live_status_and_top_region(self) -> None:
        current_date = datetime(2026, 3, 10)
        self.db.add_all([
            AREKonsultation(
                datum=current_date,
                available_time=current_date,
                kalenderwoche=11,
                saison="2025/2026",
                altersgruppe="00+",
                bundesland="Bundesweit",
                konsultationsinzidenz=2400,
            ),
            NotaufnahmeSyndromData(
                datum=current_date,
                ed_type="all",
                age_group="00+",
                syndrome="ILI",
                relative_cases=8.2,
                relative_cases_7day_ma=9.1,
            ),
            GoogleTrendsData(
                datum=current_date,
                available_time=current_date,
                keyword="influenza",
                region="DE",
                interest_score=64,
            ),
            WeatherData(
                datum=current_date,
                available_time=current_date,
                city="Berlin",
                temperatur=4.0,
                luftfeuchtigkeit=82.0,
                uv_index=1.0,
            ),
        ])
        self.db.commit()

        source_status = {
            "items": [
                {"source_key": "wastewater", "is_live": True, "last_updated": current_date.isoformat()},
                {"source_key": "bfarm_shortage", "is_live": False, "last_updated": None},
            ],
        }

        with patch(
            "app.services.media.cockpit.bento_section.get_cached_signals",
            return_value={"current_risk_score": 55.0, "wave_type": "Versorgungslage"},
        ):
            payload = self.service._bento_section(
                virus_typ="Influenza A",
                map_section={
                    "max_viruslast": 180000.0,
                    "top_regions": [
                        {"name": "Schleswig-Holstein", "signal_score": 68.0},
                    ],
                },
                peix_score={"national_score": 72.0, "national_band": "high"},
                source_status=source_status,
            )

        self.assertEqual(payload["count"], 10)
        tiles_by_id = {tile["id"]: tile for tile in payload["tiles"]}
        self.assertEqual(tiles_by_id["map_top_region"]["value"], "Schleswig-Holstein")
        self.assertTrue(tiles_by_id["map_top_region"]["is_live"])
        self.assertEqual(tiles_by_id["map_top_region"]["last_updated"], current_date.isoformat())
        self.assertEqual(tiles_by_id["bfarm"]["subtitle"], "Versorgungslage")
        self.assertEqual(tiles_by_id["peix_national"]["field_contracts"]["signal_score"]["source"], "RankingSignal")
        self.assertEqual(tiles_by_id["map_top_region"]["field_contracts"]["signal_score"]["source"], "RankingSignal")

    def test_bento_section_keeps_pollen_tile_as_stale_fallback_without_recent_pollen_data(self) -> None:
        current_date = datetime(2026, 3, 10)
        source_status = {"items": [{"source_key": "pollen", "is_live": False, "last_updated": None}]}

        with patch(
            "app.services.media.cockpit.bento_section.get_cached_signals",
            return_value={},
        ):
            payload = self.service._bento_section(
                virus_typ="Influenza A",
                map_section={"max_viruslast": 0.0, "top_regions": []},
                peix_score={"national_score": 0.0, "national_band": "low"},
                source_status=source_status,
            )

        pollen_tile = next(tile for tile in payload["tiles"] if tile["id"] == "pollen")
        self.assertEqual(pollen_tile["product_scope"], "GeloSitin")
        self.assertIn("Saison-Pause", pollen_tile["subtitle"])
        self.assertFalse(pollen_tile["is_live"])


class CockpitRecommendationSectionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        TestingSessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = TestingSessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_recommendation_section_builds_card_with_workflow_status_and_signal_contract(self) -> None:
        created_at = datetime(2026, 3, 10, 8, 0, 0)
        self.db.add(
            MarketingOpportunity(
                opportunity_id="opp-001",
                opportunity_type="regional_push",
                status="URGENT",
                urgency_score=74.0,
                brand="gelo",
                product="GeloMyrtol",
                region_target={"states": ["Schleswig-Holstein"]},
                budget_shift_pct=22.0,
                activation_start=datetime(2026, 3, 11, 0, 0, 0),
                activation_end=datetime(2026, 3, 24, 0, 0, 0),
                recommendation_reason="Abverkauf lokal verstärken",
                created_at=created_at,
                campaign_payload={
                    "campaign": {"campaign_name": "Nordfenster nutzen"},
                    "budget_plan": {"weekly_budget_eur": 12000, "budget_shift_pct": 22.0},
                    "measurement_plan": {"primary_kpi": "ROAS"},
                    "activation_window": {"start": "2026-03-11T00:00:00", "end": "2026-03-24T00:00:00"},
                    "product_mapping": {
                        "recommended_product": "GeloMyrtol forte",
                        "mapping_status": "approved",
                        "condition_key": "bronchitis_husten",
                        "condition_label": "Bronchitis & Husten",
                    },
                    "peix_context": {"signal_score": 68.0},
                    "trigger_snapshot": {"source": "Abwasser", "event": "peak"},
                },
            )
        )
        self.db.commit()

        payload = build_recommendation_section(self.db)

        self.assertEqual(payload["total"], 1)
        card = payload["cards"][0]
        self.assertEqual(card["status"], "DRAFT")
        self.assertEqual(card["region_codes"], ["SH"])
        self.assertEqual(card["campaign_preview"]["recommended_product"], "GeloMyrtol forte")
        self.assertEqual(card["field_contracts"]["signal_confidence_pct"]["source"], "Abwasser")
        self.assertEqual(card["ranking_signal_context"], card["peix_context"])

    def test_region_recommendation_refs_skip_archived_cards_and_expand_national_scope(self) -> None:
        created_at = datetime(2026, 3, 10, 8, 0, 0)
        self.db.add_all(
            [
                MarketingOpportunity(
                    opportunity_id="opp-dismissed",
                    opportunity_type="regional_push",
                    status="DISMISSED",
                    urgency_score=91.0,
                    brand="gelo",
                    product="GeloMyrtol",
                    region_target={"states": ["HH"]},
                    created_at=created_at,
                ),
                MarketingOpportunity(
                    opportunity_id="opp-national",
                    opportunity_type="regional_push",
                    status="READY",
                    urgency_score=65.0,
                    brand="gelo",
                    product="GeloMyrtol",
                    region_target={"states": ["deutschland"]},
                    created_at=created_at + timedelta(hours=1),
                ),
            ]
        )
        self.db.commit()

        refs = build_region_recommendation_refs(self.db)

        self.assertNotIn("opp-dismissed", {item["card_id"] for item in refs.values()})
        self.assertEqual(len(refs), 16)
        self.assertEqual(refs["SH"]["card_id"], "opp-national")
        self.assertEqual(refs["SH"]["status"], "READY")

    def test_recommendation_section_uses_neutral_partner_brand_fallback(self) -> None:
        created_at = datetime(2026, 3, 10, 8, 0, 0)
        self.db.add(
            MarketingOpportunity(
                opportunity_id="opp-no-brand",
                opportunity_type="regional_push",
                status="READY",
                urgency_score=54.0,
                brand=None,
                product="GeloMyrtol",
                region_target={"states": ["Hamburg"]},
                created_at=created_at,
                campaign_payload={
                    "campaign": {"campaign_name": "Nordfenster nutzen"},
                    "product_mapping": {
                        "recommended_product": "GeloMyrtol forte",
                        "mapping_status": "approved",
                    },
                    "trigger_snapshot": {"source": "Abwasser", "event": "peak"},
                },
            )
        )
        self.db.commit()

        payload = build_recommendation_section(self.db)

        self.assertEqual(payload["cards"][0]["brand"], "Partner Brand")


if __name__ == "__main__":
    unittest.main()
