"""Tests for app.services.media.cockpit.snapshot_builder.

These tests verify the contract that the frontend relies on:

* ``model_status`` is populated from the most recent successful backtest
  run for (virus_typ, horizon_days, RKI_ARE).
* ``calibration_mode`` is ``"heuristic"`` when the backtest recorded
  ``skip_reason = "heuristic_event_score_only"`` — the audit found this
  is what the live system produces for every champion scope as of
  2026-04-16, so it MUST map correctly.
* ``regions`` is empty for a virus without a regional model (RSV A) and
  populated from ``predict_all_regions`` output for Influenza A.
* EUR fields and ``mediaPlan.connected`` stay null/false until a real
  media plan is connected.

The tests use an in-memory SQLite database following the same pattern
as app/tests/test_cockpit_service_guards.py.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, BacktestRun, MLForecast
from app.services.media.cockpit import snapshot_builder


class _FakeRegionalForecastService:
    """Stand-in for RegionalForecastService.predict_all_regions()."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def __call__(self, *, virus_typ: str, brand: str, horizon_days: int) -> dict:
        self.calls.append(
            {"virus_typ": virus_typ, "brand": brand, "horizon_days": horizon_days}
        )
        return self.payload


class CockpitSnapshotBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    # ---------- helpers ----------

    def _insert_backtest(
        self,
        *,
        virus_typ: str,
        horizon_days: int = 7,
        readiness: str = "WATCH",
        overall_passed: bool = False,
        baseline_passed: bool = False,
        best_lag_days: int = -7,
        calibration_skipped: bool = True,
        skip_reason: str = "heuristic_event_score_only",
        mae_vs_persistence_pct: float = -3.97,
        end_date: str = "2026-03-30",
    ) -> None:
        self.db.add(
            BacktestRun(
                run_id=f"bt_test_{virus_typ}_{horizon_days}",
                mode="walk_forward",
                status="success",
                virus_typ=virus_typ,
                target_source="RKI_ARE",
                horizon_days=horizon_days,
                min_train_points=10,
                strict_vintage_mode=True,
                metrics={
                    "date_range": {"start": "2025-07-07", "end": end_date},
                    "quality_gate": {
                        "forecast_readiness": readiness,
                        "overall_passed": overall_passed,
                        "baseline_passed": baseline_passed,
                    },
                    "timing_metrics": {
                        "best_lag_days": best_lag_days,
                        "corr_at_horizon": 0.672,
                    },
                    "interval_coverage": {
                        "coverage_80_pct": 82.1,
                        "coverage_95_pct": 92.3,
                    },
                    "event_calibration": {
                        "calibration_skipped": calibration_skipped,
                        "skip_reason": skip_reason,
                        "calibration_method": "skipped_heuristic_event_score" if calibration_skipped else "isotonic",
                    },
                },
                baseline_metrics={},
                improvement_vs_baselines={
                    "mae_vs_persistence_pct": mae_vs_persistence_pct,
                    "mae_vs_seasonal_pct": 13.85,
                },
                created_at=datetime.utcnow(),
            )
        )
        self.db.commit()

    # ---------- model status ----------

    def test_model_status_flags_watch_and_heuristic_calibration(self) -> None:
        self._insert_backtest(virus_typ="RSV A")

        with patch.object(snapshot_builder, "build_source_status", return_value={"items": []}), \
             patch.object(snapshot_builder, "build_data_freshness", return_value={}):
            payload = snapshot_builder.build_cockpit_snapshot(
                self.db,
                virus_typ="RSV A",
                horizon_days=7,
                regional_forecast_service=_FakeRegionalForecastService({"predictions": []}),
            )

        status = payload["modelStatus"]
        self.assertEqual(status["forecast_readiness"], "WATCH")
        self.assertFalse(status["overall_passed"])
        self.assertFalse(status["baseline_passed"])
        self.assertEqual(status["best_lag_days"], -7)
        self.assertAlmostEqual(status["correlation_at_horizon"], 0.672)
        self.assertAlmostEqual(status["mae_vs_persistence_pct"], -3.97)
        self.assertEqual(status["calibration_mode"], "heuristic")
        self.assertEqual(status["interval_coverage_80_pct"], 82.1)
        self.assertEqual(status["interval_coverage_95_pct"], 92.3)
        self.assertFalse(status["regional_available"])  # RSV A is national-only
        self.assertIn("heuristisch", (status["note"] or "").lower())

    def test_model_status_marks_calibrated_when_no_skip(self) -> None:
        self._insert_backtest(
            virus_typ="Influenza A",
            calibration_skipped=False,
            skip_reason="",
        )

        with patch.object(snapshot_builder, "build_source_status", return_value={"items": []}), \
             patch.object(snapshot_builder, "build_data_freshness", return_value={}):
            payload = snapshot_builder.build_cockpit_snapshot(
                self.db,
                virus_typ="Influenza A",
                horizon_days=7,
                regional_forecast_service=_FakeRegionalForecastService({"predictions": []}),
            )

        self.assertEqual(payload["modelStatus"]["calibration_mode"], "calibrated")
        self.assertTrue(payload["modelStatus"]["regional_available"])

    def test_missing_backtest_returns_unknown_readiness(self) -> None:
        with patch.object(snapshot_builder, "build_source_status", return_value={"items": []}), \
             patch.object(snapshot_builder, "build_data_freshness", return_value={}):
            payload = snapshot_builder.build_cockpit_snapshot(
                self.db,
                virus_typ="RSV A",
                horizon_days=7,
                regional_forecast_service=_FakeRegionalForecastService({"predictions": []}),
            )

        self.assertEqual(payload["modelStatus"]["forecast_readiness"], "UNKNOWN")
        self.assertEqual(payload["modelStatus"]["calibration_mode"], "unknown")

    # ---------- regions & notes ----------

    def test_rsv_a_returns_empty_regions_and_explanatory_note(self) -> None:
        self._insert_backtest(virus_typ="RSV A")
        fake = _FakeRegionalForecastService({"predictions": []})

        with patch.object(snapshot_builder, "build_source_status", return_value={"items": []}), \
             patch.object(snapshot_builder, "build_data_freshness", return_value={}):
            payload = snapshot_builder.build_cockpit_snapshot(
                self.db,
                virus_typ="RSV A",
                horizon_days=7,
                regional_forecast_service=fake,
            )

        self.assertEqual(payload["regions"], [])
        self.assertEqual(fake.calls, [])  # regional service should not be invoked
        self.assertTrue(
            any("kein regionales modell" in n.lower() for n in payload["notes"]),
            payload["notes"],
        )

    def test_influenza_regions_mapped_from_prediction_payload(self) -> None:
        self._insert_backtest(virus_typ="Influenza A")
        fake = _FakeRegionalForecastService(
            {
                "status": "success",
                "predictions": [
                    {
                        "bundesland": "BY",
                        "event_probability": 0.78,
                        "expected_next_week_incidence": 120.0,
                        "current_incidence": 100.0,
                        "prediction_interval": {"lower": 108.0, "upper": 132.0},
                        "decision_label": "Activate",
                        "reason_trace": {
                            "signals": [
                                {"message": "Abwasser +40%"},
                                {"message": "Trends 2.1×"},
                            ]
                        },
                    },
                    {
                        "bundesland": "NW",
                        "event_probability": 0.28,
                        "expected_next_week_incidence": 90.0,
                        "current_incidence": 100.0,
                        "prediction_interval": {"lower": 84.0, "upper": 99.0},
                        "decision_label": "Watch",
                        "reason_trace": {"signals": [{"message": "Welle abklingend"}]},
                    },
                ],
            }
        )

        with patch.object(snapshot_builder, "build_source_status", return_value={"items": []}), \
             patch.object(snapshot_builder, "build_data_freshness", return_value={}):
            payload = snapshot_builder.build_cockpit_snapshot(
                self.db,
                virus_typ="Influenza A",
                horizon_days=7,
                regional_forecast_service=fake,
            )

        self.assertEqual(len(payload["regions"]), 2)
        by = next(r for r in payload["regions"] if r["code"] == "BY")
        self.assertEqual(by["name"], "Bayern")
        self.assertAlmostEqual(by["pRising"], 0.78)
        self.assertEqual(by["decisionLabel"], "Activate")
        self.assertAlmostEqual(by["delta7d"], 0.2, places=3)  # (120/100) - 1
        self.assertIsNotNone(by["forecast"])
        self.assertEqual(by["forecast"]["q50"], 100.0)
        self.assertEqual(by["drivers"][:2], ["Abwasser +40%", "Trends 2.1×"])
        self.assertIsNone(by["currentSpendEur"])
        self.assertIsNone(by["recommendedShiftEur"])

    # ---------- media plan honesty ----------

    def test_media_plan_block_is_not_connected(self) -> None:
        self._insert_backtest(virus_typ="RSV A")
        with patch.object(snapshot_builder, "build_source_status", return_value={"items": []}), \
             patch.object(snapshot_builder, "build_data_freshness", return_value={}):
            payload = snapshot_builder.build_cockpit_snapshot(
                self.db,
                virus_typ="RSV A",
                horizon_days=7,
                regional_forecast_service=_FakeRegionalForecastService({"predictions": []}),
            )

        self.assertFalse(payload["mediaPlan"]["connected"])
        self.assertIsNone(payload["mediaPlan"]["totalWeeklySpendEur"])
        self.assertIsNone(payload["totalSpendEur"])
        self.assertIsNone(payload["primaryRecommendation"])
        self.assertEqual(payload["secondaryRecommendations"], [])

    # ---------- timeline ----------

    def test_timeline_uses_ml_forecasts_rows(self) -> None:
        self._insert_backtest(virus_typ="RSV A")
        today = datetime.utcnow().date()
        for offset in (-5, 0, 3, 7):
            self.db.add(
                MLForecast(
                    forecast_date=datetime.combine(today + timedelta(days=offset), datetime.min.time()),
                    virus_typ="RSV A",
                    predicted_value=100.0 + offset,
                    lower_bound=90.0 + offset,
                    upper_bound=110.0 + offset,
                    model_version="xgb_stack_v1",
                )
            )
        self.db.commit()

        with patch.object(snapshot_builder, "build_source_status", return_value={"items": []}), \
             patch.object(snapshot_builder, "build_data_freshness", return_value={}):
            payload = snapshot_builder.build_cockpit_snapshot(
                self.db,
                virus_typ="RSV A",
                horizon_days=7,
                regional_forecast_service=_FakeRegionalForecastService({"predictions": []}),
            )

        self.assertEqual(len(payload["timeline"]), 22)  # -14..+7 inclusive
        today_point = next(p for p in payload["timeline"] if p["horizonDays"] == 0)
        self.assertAlmostEqual(today_point["q50"], 100.0)
        future_point = next(p for p in payload["timeline"] if p["horizonDays"] == 7)
        self.assertAlmostEqual(future_point["q50"], 107.0)


if __name__ == "__main__":
    unittest.main()
