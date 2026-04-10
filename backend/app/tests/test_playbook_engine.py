from __future__ import annotations

import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
