import unittest

import pandas as pd

from app.services.ml.regional_features_sources import (
    _select_wastewater_alias_rows,
    _wastewater_virus_candidates,
)


class RegionalFeaturesSourcesTests(unittest.TestCase):
    def test_wastewater_candidates_only_expand_rsv_a(self) -> None:
        self.assertEqual(_wastewater_virus_candidates("Influenza A"), ("Influenza A",))
        self.assertEqual(
            _wastewater_virus_candidates("RSV A"),
            ("RSV A", "RSV A/B", "RSV A+B"),
        )

    def test_select_wastewater_alias_rows_prefers_exact_rsv_a(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "source_virus_typ": "RSV A/B",
                    "bundesland": "BY",
                    "datum": pd.Timestamp("2026-04-15"),
                    "available_time": pd.Timestamp("2026-04-16"),
                    "viral_load": 10.0,
                    "site_count": 2,
                    "under_bg_share": 0.25,
                    "viral_std": 1.1,
                },
                {
                    "source_virus_typ": "RSV A",
                    "bundesland": "BY",
                    "datum": pd.Timestamp("2026-04-15"),
                    "available_time": pd.Timestamp("2026-04-17"),
                    "viral_load": 20.0,
                    "site_count": 1,
                    "under_bg_share": 0.0,
                    "viral_std": 0.7,
                },
                {
                    "source_virus_typ": "RSV A/B",
                    "bundesland": "BE",
                    "datum": pd.Timestamp("2026-04-15"),
                    "available_time": pd.Timestamp("2026-04-16"),
                    "viral_load": 30.0,
                    "site_count": 3,
                    "under_bg_share": 0.1,
                    "viral_std": 1.4,
                },
            ]
        )

        result = _select_wastewater_alias_rows(frame, "RSV A")

        by_row = result[result["bundesland"] == "BY"].iloc[0]
        be_row = result[result["bundesland"] == "BE"].iloc[0]
        self.assertEqual(list(result["bundesland"]), ["BE", "BY"])
        self.assertEqual(by_row["source_virus_typ"], "RSV A")
        self.assertEqual(by_row["viral_load"], 20.0)
        self.assertEqual(be_row["source_virus_typ"], "RSV A/B")
        self.assertEqual(be_row["viral_load"], 30.0)


if __name__ == "__main__":
    unittest.main()
