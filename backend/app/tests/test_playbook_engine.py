from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app.services.media.playbook_engine import PlaybookEngine


class PlaybookEngineWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PlaybookEngine(db=object())

    def test_mycoplasma_candidates_wrapper_delegates_via_module_path(self) -> None:
        expected = [{"playbook_key": "MYCOPLASMA_JAEGER"}]

        with patch(
            "app.services.media.playbook_engine_candidates.mycoplasma_candidates",
            return_value=expected,
        ) as build_mock:
            payload = self.engine._mycoplasma_candidates(
                peix_regions={"SH": {"score_0_100": 77.0}},
                allowed_regions=["SH"],
            )

        self.assertIs(payload, expected)
        build_mock.assert_called_once_with(
            self.engine,
            peix_regions={"SH": {"score_0_100": 77.0}},
            allowed_regions=["SH"],
        )

    def test_supply_candidates_wrapper_delegates_via_module_path(self) -> None:
        expected = [{"playbook_key": "SUPPLY_SHOCK_ATTACK"}]

        with patch(
            "app.services.media.playbook_engine_candidates.supply_candidates",
            return_value=expected,
        ) as build_mock:
            payload = self.engine._supply_candidates(
                peix_regions={"BY": {"score_0_100": 64.0}},
                allowed_regions=["BY"],
            )

        self.assertIs(payload, expected)
        build_mock.assert_called_once_with(
            self.engine,
            peix_regions={"BY": {"score_0_100": 64.0}},
            allowed_regions=["BY"],
        )

    def test_weather_candidates_wrapper_delegates_via_module_path(self) -> None:
        expected = [{"playbook_key": "WETTER_REFLEX"}]

        with patch(
            "app.services.media.playbook_engine_candidates.weather_candidates",
            return_value=expected,
        ) as build_mock:
            payload = self.engine._wetter_candidates(
                peix_regions={"HH": {"score_0_100": 52.0}},
                allowed_regions=["HH"],
            )

        self.assertIs(payload, expected)
        build_mock.assert_called_once_with(
            self.engine,
            peix_regions={"HH": {"score_0_100": 52.0}},
            allowed_regions=["HH"],
        )

    def test_allergy_candidates_wrapper_delegates_via_module_path(self) -> None:
        expected = [{"playbook_key": "ALLERGIE_BREMSE"}]

        with patch(
            "app.services.media.playbook_engine_candidates.allergy_candidates",
            return_value=expected,
        ) as build_mock:
            payload = self.engine._allergy_candidates(
                peix_regions={"NI": {"score_0_100": 31.0}},
                allowed_regions=["NI"],
            )

        self.assertIs(payload, expected)
        build_mock.assert_called_once_with(
            self.engine,
            peix_regions={"NI": {"score_0_100": 31.0}},
            allowed_regions=["NI"],
        )

    def test_halsschmerz_candidates_wrapper_delegates_via_module_path(self) -> None:
        expected = [{"playbook_key": "HALSSCHMERZ_HUNTER"}]

        with patch(
            "app.services.media.playbook_engine_candidates.halsschmerz_candidates",
            return_value=expected,
        ) as build_mock:
            payload = self.engine._halsschmerz_candidates(
                peix_regions={"SN": {"score_0_100": 70.0}},
                allowed_regions=["SN"],
            )

        self.assertIs(payload, expected)
        build_mock.assert_called_once_with(
            self.engine,
            peix_regions={"SN": {"score_0_100": 70.0}},
            allowed_regions=["SN"],
        )

    def test_erkaeltungswelle_candidates_wrapper_delegates_via_module_path(self) -> None:
        expected = [{"playbook_key": "ERKAELTUNGSWELLE"}]

        with patch(
            "app.services.media.playbook_engine_candidates.erkaeltungswelle_candidates",
            return_value=expected,
        ) as build_mock:
            payload = self.engine._erkaeltungswelle_candidates(
                peix_regions={"ST": {"score_0_100": 70.0}},
                allowed_regions=["ST"],
            )

        self.assertIs(payload, expected)
        build_mock.assert_called_once_with(
            self.engine,
            peix_regions={"ST": {"score_0_100": 70.0}},
            allowed_regions=["ST"],
        )

    def test_sinus_candidates_wrapper_delegates_via_module_path(self) -> None:
        expected = [{"playbook_key": "SINUS_DEFENDER"}]

        with patch(
            "app.services.media.playbook_engine_candidates.sinus_candidates",
            return_value=expected,
        ) as build_mock:
            payload = self.engine._sinus_candidates(
                peix_regions={"TH": {"score_0_100": 58.0}},
                allowed_regions=["TH"],
            )

        self.assertIs(payload, expected)
        build_mock.assert_called_once_with(
            self.engine,
            peix_regions={"TH": {"score_0_100": 58.0}},
            allowed_regions=["TH"],
        )

    def test_are_growth_by_region_wrapper_delegates_via_module_path(self) -> None:
        expected = {"SH": 0.24}

        with patch(
            "app.services.media.playbook_engine_signals.are_growth_by_region",
            return_value=expected,
        ) as build_mock:
            payload = self.engine._are_growth_by_region()

        self.assertIs(payload, expected)
        build_mock.assert_called_once_with(self.engine)

    def test_weather_burden_by_region_wrapper_delegates_via_module_path(self) -> None:
        expected = {"HH": 63.5}

        with patch(
            "app.services.media.playbook_engine_signals.weather_burden_by_region",
            return_value=expected,
        ) as build_mock:
            payload = self.engine._weather_burden_by_region()

        self.assertIs(payload, expected)
        build_mock.assert_called_once_with(self.engine)

    def test_pollen_by_region_wrapper_delegates_via_module_path(self) -> None:
        expected = {"BY": 88.0}

        with patch(
            "app.services.media.playbook_engine_signals.pollen_by_region",
            return_value=expected,
        ) as build_mock:
            payload = self.engine._pollen_by_region()

        self.assertIs(payload, expected)
        build_mock.assert_called_once_with(self.engine)

    def test_google_signal_score_wrapper_delegates_via_module_path(self) -> None:
        expected = {"current": 42.0, "previous": 31.0, "delta": 11.0}

        with patch(
            "app.services.media.playbook_engine_signals.google_signal_score",
            return_value=expected,
        ) as build_mock:
            payload = self.engine._google_signal_score(["husten", "bronchitis"])

        self.assertIs(payload, expected)
        build_mock.assert_called_once_with(self.engine, ["husten", "bronchitis"])

    def test_select_candidates_uses_neutral_ranking_signal_service(self) -> None:
        ranking_service = Mock()
        ranking_service.build.return_value = {
            "regions": {"SH": {"score_0_100": 77.0}},
            "generated_at": "2026-04-10T09:00:00Z",
        }

        with (
            patch("app.services.media.playbook_engine.RankingSignalService", return_value=ranking_service),
            patch.object(self.engine, "_mycoplasma_candidates", return_value=[]),
            patch.object(self.engine, "_supply_candidates", return_value=[]),
            patch.object(self.engine, "_wetter_candidates", return_value=[]),
            patch.object(self.engine, "_allergy_candidates", return_value=[]),
            patch.object(self.engine, "_halsschmerz_candidates", return_value=[]),
            patch.object(self.engine, "_erkaeltungswelle_candidates", return_value=[]),
            patch.object(self.engine, "_sinus_candidates", return_value=[]),
        ):
            payload = self.engine.select_candidates(virus_typ="Influenza A")

        self.assertEqual(payload["selected"], [])
        self.assertEqual(payload["peix_generated_at"], "2026-04-10T09:00:00Z")
        self.assertEqual(payload["ranking_signal_generated_at"], "2026-04-10T09:00:00Z")

    def test_candidate_payload_exposes_neutral_signal_aliases(self) -> None:
        payload = self.engine._candidate_payload(
            playbook_key="SUPPLY_SHOCK_ATTACK",
            region_code="SH",
            peix_entry={
                "score_0_100": 78.0,
                "risk_band": "high",
                "top_drivers": [{"label": "AMELAG"}],
            },
            trigger_strength=66.0,
            confidence=81.0,
            priority_score=72.0,
            budget_shift_pct=18.0,
            trigger_snapshot={"event": "SUPPLY_SHOCK_WINDOW"},
        )

        self.assertEqual(payload["ranking_signal_score"], 78.0)
        self.assertEqual(payload["signal_band"], "high")
        self.assertEqual(payload["signal_drivers"], [{"label": "AMELAG"}])


if __name__ == "__main__":
    unittest.main()
