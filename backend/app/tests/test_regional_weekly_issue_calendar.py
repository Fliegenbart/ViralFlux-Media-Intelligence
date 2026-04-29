from __future__ import annotations

import datetime as _datetime
import sys
import types
import unittest

if not hasattr(_datetime, "UTC"):
    _datetime.UTC = _datetime.timezone.utc
sys.modules["datetime"].UTC = _datetime.UTC
sys.modules.setdefault(
    "xgboost",
    types.SimpleNamespace(XGBClassifier=object, XGBRegressor=object),
)

import pandas as pd

from app.services.ml.regional_features_builders import (
    _build_issue_calendar,
    _visible_asof_frame,
    build_rows,
    lagged_incidence_feature_family,
)
from app.services.ml.regional_features_manifests import signal_bundle_metadata
from app.services.ml.regional_panel_utils import ALL_BUNDESLAENDER
from app.services.ml.regional_trainer_backtest import _build_backtest_policy, _build_panel_evaluation


class _FakeNowcastService:
    def evaluate_frame(
        self,
        *,
        frame: pd.DataFrame,
        value_column: str,
        **_: object,
    ) -> dict[str, float]:
        if frame is None or frame.empty or value_column not in frame.columns:
            return {"value": 0.0}
        return {"value": float(frame.iloc[-1][value_column] or 0.0)}

    def preferred_value(self, result: dict[str, float], **_: object) -> float:
        return float(result.get("value") or 0.0)


class _FakeWeeklyRowBuilder:
    nowcast_service = _FakeNowcastService()

    def _target_date(self, cutoff: pd.Timestamp, horizon: int) -> pd.Timestamp:
        return pd.Timestamp(cutoff).normalize() + pd.Timedelta(days=int(horizon))

    def _latest_wastewater_snapshot_by_state(
        self,
        wastewater_by_state: dict[str, pd.DataFrame],
        as_of: pd.Timestamp,
    ) -> dict[str, dict[str, float]]:
        snapshots: dict[str, dict[str, float]] = {}
        for state, frame in wastewater_by_state.items():
            visible = frame.loc[frame["datum"] <= as_of]
            if visible.empty:
                continue
            latest = visible.iloc[-1]
            snapshots[state] = {
                "viral_load": float(latest.get("viral_load") or 0.0),
                "slope7d": 0.0,
                "acceleration7d": 0.0,
            }
        return snapshots

    def _use_revision_adjusted_for_source(self, **_: object) -> bool:
        return False

    def _build_feature_row(
        self,
        *,
        visible_ww: pd.DataFrame,
        visible_are: pd.DataFrame | None,
        visible_influenza_ifsg: pd.DataFrame | None,
        visible_rsv_ifsg: pd.DataFrame | None,
        **_: object,
    ) -> dict[str, float]:
        return {
            "ww_level": float(visible_ww.iloc[-1].get("viral_load") or 0.0),
            "are_consult_missing": float(visible_are is None or visible_are.empty),
            "ifsg_influenza_missing": float(
                visible_influenza_ifsg is None or visible_influenza_ifsg.empty
            ),
            "ifsg_rsv_missing": float(visible_rsv_ifsg is None or visible_rsv_ifsg.empty),
        }


class RegionalWeeklyIssueCalendarTests(unittest.TestCase):
    def test_async_region_dates_in_same_issue_week_build_one_weekly_panel(self) -> None:
        frame = pd.DataFrame(
            {
                "virus_typ": ["Influenza A"] * 3,
                "bundesland": ["BE", "BW", "BY"],
                "as_of_date": pd.to_datetime(["2024-11-10", "2024-11-11", "2024-11-13"]),
                "forecast_issue_week_start": [pd.Timestamp("2024-11-11")] * 3,
                "forecast_issue_cutoff_date": [pd.Timestamp("2024-11-17")] * 3,
                "target_week_start": [pd.Timestamp("2024-11-18")] * 3,
                "horizon_days": [7, 7, 7],
                "event_label": [1, 0, 0],
                "event_probability_calibrated": [0.9, 0.4, 0.3],
                "current_known_incidence": [12.0, 8.0, 7.0],
            }
        )

        panel = _build_panel_evaluation(frame, region_universe=["BE", "BW", "BY"])

        self.assertEqual(panel["issue_calendar_type"], "weekly_shared_issue_calendar")
        self.assertEqual(len(panel["rows"]), 1)
        row = panel["rows"][0]
        self.assertEqual(row["forecast_issue_week_start"], "2024-11-11")
        self.assertEqual(row["forecast_issue_cutoff_date"], "2024-11-17")
        self.assertEqual(row["target_week_start"], "2024-11-18")
        self.assertEqual(row["scored_regions"], ["BE", "BW", "BY"])

    def test_asof_feature_retrieval_uses_latest_value_at_or_before_cutoff(self) -> None:
        frame = pd.DataFrame(
            {
                "datum": pd.to_datetime(["2024-11-09", "2024-11-13", "2024-11-18"]),
                "available_time": pd.to_datetime(["2024-11-09", "2024-11-13", "2024-11-18"]),
                "viral_load": [10.0, 20.0, 99.0],
            }
        )

        visible = _visible_asof_frame(frame, cutoff=pd.Timestamp("2024-11-17"))

        self.assertEqual(float(visible.iloc[-1]["viral_load"]), 20.0)

    def test_asof_feature_retrieval_excludes_rows_after_cutoff(self) -> None:
        frame = pd.DataFrame(
            {
                "datum": pd.to_datetime(["2024-11-13", "2024-11-18"]),
                "available_time": pd.to_datetime(["2024-11-13", "2024-11-18"]),
                "viral_load": [20.0, 99.0],
            }
        )

        visible = _visible_asof_frame(frame, cutoff=pd.Timestamp("2024-11-17"))

        self.assertEqual(visible["datum"].dt.strftime("%Y-%m-%d").tolist(), ["2024-11-13"])

    def test_asof_feature_retrieval_respects_publication_metadata(self) -> None:
        frame = pd.DataFrame(
            {
                "datum": pd.to_datetime(["2024-11-12", "2024-11-13"]),
                "available_time": pd.to_datetime(["2024-11-12", "2024-11-13"]),
                "published_at": pd.to_datetime(["2024-11-18", "2024-11-14"]),
                "viral_load": [99.0, 20.0],
            }
        )

        visible = _visible_asof_frame(frame, cutoff=pd.Timestamp("2024-11-17"))

        self.assertEqual(float(visible.iloc[-1]["viral_load"]), 20.0)
        self.assertNotIn(99.0, visible["viral_load"].tolist())

    def test_issue_calendar_uses_weekly_target_week_start(self) -> None:
        calendar = _build_issue_calendar(
            start_date=pd.Timestamp("2024-11-10"),
            end_date=pd.Timestamp("2024-11-24"),
            horizon_days=7,
        )

        self.assertEqual(calendar.iloc[0]["forecast_issue_week_start"], pd.Timestamp("2024-11-04"))
        self.assertEqual(calendar.iloc[0]["forecast_issue_cutoff_date"], pd.Timestamp("2024-11-10"))
        self.assertEqual(calendar.iloc[0]["target_week_start"], pd.Timestamp("2024-11-11"))

    def test_non_event_regions_remain_in_weekly_panel(self) -> None:
        frame = pd.DataFrame(
            {
                "virus_typ": ["Influenza A"] * 3,
                "bundesland": ["BE", "BW", "BY"],
                "as_of_date": [pd.Timestamp("2024-11-17")] * 3,
                "forecast_issue_week_start": [pd.Timestamp("2024-11-11")] * 3,
                "forecast_issue_cutoff_date": [pd.Timestamp("2024-11-17")] * 3,
                "target_week_start": [pd.Timestamp("2024-11-18")] * 3,
                "horizon_days": [7, 7, 7],
                "event_label": [1, 0, 0],
                "event_probability_calibrated": [0.9, 0.1, 0.2],
                "current_known_incidence": [12.0, 8.0, 7.0],
            }
        )

        panel = _build_panel_evaluation(frame, region_universe=["BE", "BW", "BY"])
        row = panel["rows"][0]

        self.assertEqual(row["scored_region_count"], 3)
        self.assertEqual(row["observed_event_regions"], ["BE"])
        self.assertEqual(row["observed_event_count"], 1)

    def test_panel_rows_follow_issue_weeks_not_raw_region_dates(self) -> None:
        frame = pd.DataFrame(
            {
                "virus_typ": ["Influenza A"] * 6,
                "bundesland": ["BE", "BW", "BY", "BE", "BW", "BY"],
                "as_of_date": pd.to_datetime(
                    ["2024-11-10", "2024-11-11", "2024-11-13", "2024-11-17", "2024-11-18", "2024-11-20"]
                ),
                "forecast_issue_week_start": [pd.Timestamp("2024-11-11")] * 3
                + [pd.Timestamp("2024-11-18")] * 3,
                "forecast_issue_cutoff_date": [pd.Timestamp("2024-11-17")] * 3
                + [pd.Timestamp("2024-11-24")] * 3,
                "target_week_start": [pd.Timestamp("2024-11-18")] * 3
                + [pd.Timestamp("2024-11-25")] * 3,
                "horizon_days": [7] * 6,
                "event_label": [1, 0, 0, 0, 1, 0],
                "event_probability_calibrated": [0.9, 0.2, 0.1, 0.1, 0.8, 0.2],
                "current_known_incidence": [12.0, 8.0, 7.0, 5.0, 11.0, 8.0],
            }
        )

        panel = _build_panel_evaluation(frame, region_universe=["BE", "BW", "BY"])

        self.assertEqual(len(panel["rows"]), 2)
        self.assertNotEqual(len(panel["rows"]), frame["as_of_date"].nunique())

    def test_full_sixteen_region_weekly_panel_is_evaluable(self) -> None:
        regions = ["BB", "BE", "BW", "BY", "HB", "HE", "HH", "MV", "NI", "NW", "RP", "SH", "SL", "SN", "ST", "TH"]
        frame = pd.DataFrame(
            {
                "virus_typ": ["Influenza A"] * 16,
                "bundesland": regions,
                "as_of_date": [pd.Timestamp("2024-11-17")] * 16,
                "forecast_issue_week_start": [pd.Timestamp("2024-11-11")] * 16,
                "forecast_issue_cutoff_date": [pd.Timestamp("2024-11-17")] * 16,
                "target_week_start": [pd.Timestamp("2024-11-18")] * 16,
                "horizon_days": [7] * 16,
                "event_label": [1] + [0] * 15,
                "event_probability_calibrated": list(reversed([idx / 100.0 for idx in range(16)])),
                "current_known_incidence": list(reversed([float(idx) for idx in range(16)])),
            }
        )

        panel = _build_panel_evaluation(frame)

        self.assertTrue(panel["rows"][0]["is_evaluable_top3_panel"])

    def test_missing_rki_features_do_not_drop_bundesland_grid(self) -> None:
        regions = list(ALL_BUNDESLAENDER)
        ww_rows = []
        truth_rows = []
        for state in regions:
            for date in pd.date_range("2024-11-10", "2024-11-17", freq="D"):
                ww_rows.append(
                    {
                        "bundesland": state,
                        "datum": date,
                        "available_time": date,
                        "viral_load": 10.0,
                        "site_count": 1,
                        "under_bg_share": 0.0,
                        "viral_std": 0.0,
                    }
                )
            for week in pd.date_range("2024-09-23", "2024-11-18", freq="7D"):
                truth_rows.append(
                    {
                        "bundesland": state,
                        "week_start": week,
                        "available_date": week,
                        "incidence": 5.0,
                        "truth_source": "survstat_weekly",
                    }
                )

        rows = build_rows(
            _FakeWeeklyRowBuilder(),
            virus_typ="Influenza A",
            wastewater=pd.DataFrame(ww_rows),
            wastewater_context={},
            truth=pd.DataFrame(truth_rows),
            grippeweb=pd.DataFrame(),
            influenza_ifsg=pd.DataFrame(),
            rsv_ifsg=pd.DataFrame(),
            are=pd.DataFrame(),
            notaufnahme=pd.DataFrame(),
            trends=pd.DataFrame(),
            weather=pd.DataFrame(),
            pollen=pd.DataFrame(),
            holidays={},
            state_populations={state: 1_000_000.0 for state in regions},
            start_date=pd.Timestamp("2024-11-11"),
            end_date=pd.Timestamp("2024-11-17"),
            horizon_days=7,
            include_targets=True,
            include_nowcast=False,
            use_revision_adjusted=False,
            revision_policy="raw",
            source_revision_policy=None,
            weather_forecast_vintage_mode="disabled",
            weather_forecast_metadata={},
        )

        self.assertEqual(len(rows), 16)
        self.assertEqual(sorted(row["bundesland"] for row in rows), sorted(regions))
        self.assertEqual({str(row["forecast_issue_cutoff_date"].date()) for row in rows}, {"2024-11-17"})
        self.assertTrue(all(row["are_consult_missing"] == 1.0 for row in rows))
        self.assertTrue(all(row["ifsg_influenza_feature_missing"] == 1.0 for row in rows))

    def test_lagged_rki_features_do_not_use_target_or_future_week(self) -> None:
        frame = pd.DataFrame(
            {
                "datum": pd.to_datetime(["2024-11-03", "2024-11-10", "2024-11-17", "2024-11-18"]),
                "incidence": [5.0, 20.0, 70.0, 99.0],
            }
        )

        features = lagged_incidence_feature_family(
            prefix="ifsg_influenza",
            frame=frame,
            as_of=pd.Timestamp("2024-11-17"),
        )

        self.assertEqual(features["ifsg_influenza_incidence_lag_1"], 20.0)
        self.assertEqual(features["ifsg_influenza_incidence_lag_2"], 5.0)
        self.assertNotEqual(features["ifsg_influenza_incidence_lag_1"], 70.0)
        self.assertNotEqual(features["ifsg_influenza_incidence_lag_1"], 99.0)

    def test_signal_bundle_metadata_lists_feature_families_and_source_lineage(self) -> None:
        panel = pd.DataFrame(
            {
                "as_of_date": pd.to_datetime(["2024-11-17"]),
                "ww_feature_age_days": [2.0],
                "are_feature_age_days": [8.0],
                "ifsg_influenza_feature_age_days": [7.0],
                "are_consult_incidence_lag_1": [12.0],
                "ifsg_influenza_incidence_lag_1": [4.0],
                "grippeweb_are_lag_1": [20.0],
            }
        )
        feature_columns = [
            "are_consult_incidence_lag_1",
            "ifsg_influenza_incidence_lag_1",
            "grippeweb_are_lag_1",
        ]

        metadata = signal_bundle_metadata(
            virus_typ="Influenza A",
            panel=panel,
            feature_columns=feature_columns,
        )

        self.assertIn("are_konsultation", metadata["active_feature_families"])
        self.assertIn("ifsg_influenza", metadata["active_feature_families"])
        self.assertIn("grippeweb", metadata["active_feature_families"])
        self.assertIn("source_lineage", metadata)
        self.assertTrue(metadata["source_lineage"]["are_konsultation"]["lag_safe"])
        self.assertEqual(
            metadata["source_lineage"]["are_konsultation"]["join_policy"],
            "left_join_asof_latest_available_at_or_before_cutoff",
        )
        self.assertFalse(metadata["source_lineage"]["are_konsultation"]["can_drop_region_rows"])

    def test_backtest_policy_records_calendar_limits_and_leakage_guards(self) -> None:
        prepared = pd.DataFrame(
            {
                "as_of_date": pd.date_range("2024-01-07", periods=110, freq="7D"),
                "ww_feature_age_days": [2.0] * 110,
                "are_feature_age_days": [8.0] * 110,
            }
        )
        oof = pd.DataFrame(
            {
                "as_of_date": pd.date_range("2026-01-04", periods=6, freq="7D"),
            }
        )
        panel_evaluation = {
            "issue_calendar_type": "weekly_shared_issue_calendar",
            "rows": [
                {"is_evaluable_top3_panel": True},
                {"is_evaluable_top3_panel": False},
            ],
        }

        policy = _build_backtest_policy(
            prepared_frame=prepared,
            oof_frame=oof,
            panel_evaluation=panel_evaluation,
            feature_columns=["ww_level", "are_consult_incidence_lag_1"],
            event_feature_columns=[
                "ww_level",
                "current_known_incidence",
                "survstat_current_incidence",
            ],
        )

        self.assertEqual(policy["issue_calendar_type"], "weekly_shared_issue_calendar")
        self.assertEqual(policy["prepared_issue_weeks"], 110)
        self.assertEqual(policy["actual_test_weeks"], 6)
        self.assertEqual(policy["evaluable_panel_weeks"], 1)
        self.assertEqual(policy["max_possible_test_weeks"], max(0, 110 - policy["min_train_weeks"]))
        self.assertEqual(policy["historical_evidence_level"], "limited")
        self.assertEqual(policy["data_start_by_source"]["wastewater"], "2024-01-05")
        guards = policy["target_leakage_guards"]
        self.assertTrue(guards["passed"])
        self.assertTrue(guards["event_label_not_in_feature_columns"])
        self.assertTrue(guards["next_week_incidence_not_in_feature_columns"])
        self.assertTrue(guards["target_week_survstat_not_used_as_feature"])
        self.assertEqual(
            guards["current_known_incidence_policy"],
            "allowed_only_as_asof_safe_event_anchor",
        )


if __name__ == "__main__":
    unittest.main()
