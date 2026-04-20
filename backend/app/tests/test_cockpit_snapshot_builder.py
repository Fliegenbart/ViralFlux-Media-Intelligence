"""Tests for app.services.media.cockpit.snapshot_builder.

After the 2026-04-17 two-story refactor, modelStatus carries two blocks:
  * ``ranking``: precision/pr_auc/ece from the regional h7 training summary
  * ``lead``: best_lag/corr/coverage from a backtest_runs row against a fast
    truth source (default ATEMWEGSINDEX at h=14)

These tests cover:
  * lead block is populated from backtest_runs with the configured target,
  * ranking block comes from the patched training-summary reader,
  * forecastReadiness synthesises GO_RANKING / RANKING_OK / LEAD_ONLY / WATCH
    correctly,
  * regions come from regional h7 regardless of the lead horizon,
  * mediaPlan.connected stays false.
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
        horizon_days: int = 14,
        target_source: str = "ATEMWEGSINDEX",
        readiness: str = "WATCH",
        overall_passed: bool = False,
        baseline_passed: bool = True,
        best_lag_days: int = 0,
        calibration_skipped: bool = True,
        skip_reason: str = "heuristic_event_score_only",
        corr_at_horizon: float = 0.73,
        corr_at_best_lag: float = 0.95,
        mae_vs_persistence_pct: float = 5.94,
        mae_vs_seasonal_pct: float = 6.07,
        coverage_80: float = 82.1,
        coverage_95: float = 92.3,
        end_date: str = "2026-03-30",
    ) -> None:
        self.db.add(
            BacktestRun(
                run_id=f"bt_test_{virus_typ}_{horizon_days}_{target_source}",
                mode="walk_forward",
                status="success",
                virus_typ=virus_typ,
                target_source=target_source,
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
                        "corr_at_horizon": corr_at_horizon,
                        "corr_at_best_lag": corr_at_best_lag,
                    },
                    "interval_coverage": {
                        "coverage_80_pct": coverage_80,
                        "coverage_95_pct": coverage_95,
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
                    "mae_vs_seasonal_pct": mae_vs_seasonal_pct,
                },
                created_at=datetime.utcnow(),
            )
        )
        self.db.commit()

    def _patch_external(self, *, ranking_metrics: dict | None = None, training_panel: dict | None = None):
        """Patch sources/freshness + _read_ranking_metrics with stable returns."""
        if ranking_metrics is None:
            ranking_metrics = {
                "precisionAtTop3": 0.777,
                "prAuc": 0.810,
                "ece": 0.027,
                "dataPoints": 39,
                "trainedAt": "2026-04-16T22:51:00",
            }
        if training_panel is None:
            training_panel = {
                "trainingSamples": 103,
                "maturityTier": "beta",
                "maturityLabel": "Beta-Pilot · N=103",
                "trainedAt": "2026-03-09T08:23:48.108240",
                "modelVersion": "xgb_stack_v1_20260309T0823",
            }

        return [
            patch.object(snapshot_builder, "build_source_status", return_value={"items": []}),
            patch.object(snapshot_builder, "build_data_freshness", return_value={}),
            patch.object(snapshot_builder, "_read_ranking_metrics", return_value=dict(ranking_metrics)),
            patch.object(snapshot_builder, "_read_training_panel", return_value=dict(training_panel)),
        ]

    def _build(self, **overrides) -> dict:
        """Helper: build a snapshot with all external deps patched."""
        defaults = dict(
            virus_typ="Influenza A",
            horizon_days=14,
            regional_forecast_service=_FakeRegionalForecastService({"predictions": []}),
        )
        defaults.update(overrides)
        patches = self._patch_external()
        for p in patches:
            p.start()
        try:
            return snapshot_builder.build_cockpit_snapshot(self.db, **defaults)
        finally:
            for p in patches:
                p.stop()

    # ---------- ranking + lead blocks ----------

    def test_lead_block_pulled_from_atemwegsindex_backtest_by_default(self) -> None:
        # Seed a lead-time backtest against ATEMWEGSINDEX at h=14.
        self._insert_backtest(
            virus_typ="Influenza A",
            horizon_days=14,
            target_source="ATEMWEGSINDEX",
            best_lag_days=0,
            corr_at_horizon=0.73,
            corr_at_best_lag=0.95,
            mae_vs_persistence_pct=5.94,
        )
        payload = self._build()
        lead = payload["modelStatus"]["lead"]
        self.assertEqual(lead["horizonDays"], 14)
        self.assertEqual(lead["targetSource"], "ATEMWEGSINDEX")
        self.assertIn("Notaufnahme", lead["targetLabel"])
        self.assertEqual(lead["bestLagDays"], 0)
        self.assertAlmostEqual(lead["correlationAtHorizon"], 0.73)
        self.assertAlmostEqual(lead["correlationAtBestLag"], 0.95)
        self.assertAlmostEqual(lead["maeVsPersistencePct"], 5.94)
        self.assertTrue(lead["hasRun"])

    def test_ranking_block_filled_from_training_summary(self) -> None:
        self._insert_backtest(virus_typ="Influenza A", target_source="ATEMWEGSINDEX")
        payload = self._build()
        ranking = payload["modelStatus"]["ranking"]
        self.assertEqual(ranking["horizonDays"], 7)
        self.assertAlmostEqual(ranking["precisionAtTop3"], 0.777)
        self.assertAlmostEqual(ranking["prAuc"], 0.810)
        self.assertAlmostEqual(ranking["ece"], 0.027)
        self.assertIn("panel", (ranking.get("sourceLabel") or "").lower())

    def test_forecast_readiness_go_ranking_when_both_blocks_pass(self) -> None:
        # precision>=0.65 AND best_lag>=0 => GO_RANKING
        self._insert_backtest(
            virus_typ="Influenza A",
            target_source="ATEMWEGSINDEX",
            best_lag_days=0,
        )
        payload = self._build()
        self.assertEqual(payload["modelStatus"]["forecastReadiness"], "GO_RANKING")

    def test_forecast_readiness_ranking_ok_when_lead_lags(self) -> None:
        """precision>=0.65 but best_lag<0 => RANKING_OK (ranking defensible,
        lead-time weak against the selected target)."""
        self._insert_backtest(
            virus_typ="Influenza A",
            horizon_days=7,
            target_source="RKI_ARE",
            best_lag_days=-7,
        )
        patches = self._patch_external()
        for p in patches:
            p.start()
        try:
            payload = snapshot_builder.build_cockpit_snapshot(
                self.db,
                virus_typ="Influenza A",
                horizon_days=7,
                lead_target_source="RKI_ARE",
                regional_forecast_service=_FakeRegionalForecastService({"predictions": []}),
            )
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(payload["modelStatus"]["forecastReadiness"], "RANKING_OK")
        self.assertEqual(payload["modelStatus"]["lead"]["bestLagDays"], -7)

    def test_forecast_readiness_watch_when_no_backtest_and_no_ranking(self) -> None:
        # Neither ranking metrics (patched empty) nor lead backtest => WATCH
        patches = self._patch_external(ranking_metrics={})  # no precision value
        for p in patches:
            p.start()
        try:
            payload = snapshot_builder.build_cockpit_snapshot(
                self.db,
                virus_typ="RSV A",
                horizon_days=14,
                regional_forecast_service=_FakeRegionalForecastService({"predictions": []}),
            )
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(payload["modelStatus"]["forecastReadiness"], "WATCH")
        self.assertFalse(payload["modelStatus"]["regionalAvailable"])

    def test_headline_aliases_match_lead_block(self) -> None:
        self._insert_backtest(
            virus_typ="Influenza A",
            target_source="ATEMWEGSINDEX",
            best_lag_days=0,
            mae_vs_persistence_pct=5.94,
        )
        payload = self._build()
        ms = payload["modelStatus"]
        self.assertEqual(ms["horizonDays"], ms["lead"]["horizonDays"])
        self.assertEqual(ms["bestLagDays"], ms["lead"]["bestLagDays"])
        self.assertEqual(ms["maeVsPersistencePct"], ms["lead"]["maeVsPersistencePct"])
        self.assertEqual(ms["intervalCoverage80Pct"], ms["lead"]["intervalCoverage80Pct"])

    def test_calibration_mode_heuristic_when_skip_reason_matches(self) -> None:
        self._insert_backtest(
            virus_typ="Influenza A",
            target_source="ATEMWEGSINDEX",
            calibration_skipped=True,
            skip_reason="heuristic_event_score_only",
        )
        payload = self._build()
        self.assertEqual(payload["modelStatus"]["calibrationMode"], "heuristic")

    def test_calibration_mode_calibrated_when_isotonic_applied(self) -> None:
        self._insert_backtest(
            virus_typ="Influenza A",
            target_source="ATEMWEGSINDEX",
            calibration_skipped=False,
            skip_reason="",
        )
        payload = self._build()
        self.assertEqual(payload["modelStatus"]["calibrationMode"], "calibrated")

    # ---------- training panel (transparency badge) ----------

    def test_training_panel_pilot_tier_for_low_sample_model(self) -> None:
        """N<100 samples must surface as a 'pilot' tier badge."""
        self._insert_backtest(virus_typ="RSV A", target_source="ATEMWEGSINDEX")
        training_panel = {
            "trainingSamples": 57,
            "maturityTier": "pilot",
            "maturityLabel": "Phase-1-Pilot · N=57",
            "trainedAt": "2026-03-09T08:24:00",
            "modelVersion": "xgb_stack_v1_20260309T0824",
        }
        patches = self._patch_external(training_panel=training_panel)
        for p in patches:
            p.start()
        try:
            payload = snapshot_builder.build_cockpit_snapshot(
                self.db,
                virus_typ="RSV A",
                horizon_days=14,
                regional_forecast_service=_FakeRegionalForecastService({"predictions": []}),
            )
        finally:
            for p in patches:
                p.stop()
        panel = payload["modelStatus"]["trainingPanel"]
        self.assertEqual(panel["maturityTier"], "pilot")
        self.assertEqual(panel["trainingSamples"], 57)
        self.assertIn("N=57", panel["maturityLabel"])

    def test_training_panel_beta_tier_passed_through(self) -> None:
        """The structured block must reach the payload verbatim from _read_training_panel."""
        self._insert_backtest(virus_typ="Influenza A", target_source="ATEMWEGSINDEX")
        payload = self._build()
        panel = payload["modelStatus"]["trainingPanel"]
        self.assertEqual(panel["maturityTier"], "beta")
        self.assertEqual(panel["trainingSamples"], 103)
        self.assertEqual(panel["modelVersion"], "xgb_stack_v1_20260309T0823")

    def test_classify_maturity_thresholds(self) -> None:
        """Coarse guard around the boundary values."""
        from app.services.media.cockpit.snapshot_builder import _classify_maturity

        self.assertEqual(_classify_maturity(None)[0], "unknown")
        self.assertEqual(_classify_maturity(0)[0], "pilot")
        self.assertEqual(_classify_maturity(99)[0], "pilot")
        self.assertEqual(_classify_maturity(100)[0], "beta")
        self.assertEqual(_classify_maturity(199)[0], "beta")
        self.assertEqual(_classify_maturity(200)[0], "production")
        self.assertEqual(_classify_maturity(500)[0], "production")

    # ---------- regions ----------

    def test_rsv_a_returns_empty_regions_and_explanatory_note(self) -> None:
        self._insert_backtest(virus_typ="RSV A", target_source="ATEMWEGSINDEX")
        fake = _FakeRegionalForecastService({"predictions": []})
        patches = self._patch_external()
        for p in patches:
            p.start()
        try:
            payload = snapshot_builder.build_cockpit_snapshot(
                self.db,
                virus_typ="RSV A",
                horizon_days=14,
                regional_forecast_service=fake,
            )
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(payload["regions"], [])
        self.assertEqual(fake.calls, [])  # regional service not invoked when regionalAvailable=false
        self.assertTrue(
            any("kein regionales modell" in n.lower() for n in payload["notes"]),
            payload["notes"],
        )

    def test_regions_pulled_via_regional_service_at_h7_not_lead_horizon(self) -> None:
        """Even when the lead horizon is 14, BL ranking still runs at h=7."""
        self._insert_backtest(virus_typ="Influenza A", target_source="ATEMWEGSINDEX")
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
                        "reason_trace": {"why": ["strong signal"]},
                        "change_pct": 20.0,
                    },
                ],
            }
        )
        patches = self._patch_external()
        for p in patches:
            p.start()
        try:
            payload = snapshot_builder.build_cockpit_snapshot(
                self.db,
                virus_typ="Influenza A",
                horizon_days=14,  # lead horizon
                regional_forecast_service=fake,
            )
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0]["horizon_days"], 7)  # ranking horizon, not 14
        self.assertEqual(payload["regions"][0]["code"], "BY")

    # ---------- media plan honesty ----------

    def test_media_plan_stays_disconnected(self) -> None:
        self._insert_backtest(virus_typ="Influenza A", target_source="ATEMWEGSINDEX")
        payload = self._build()
        self.assertFalse(payload["mediaPlan"]["connected"])
        self.assertIsNone(payload["totalSpendEur"])
        self.assertIsNone(payload["primaryRecommendation"])

    # ---------- timeline ----------

    def test_timeline_spans_minus14_to_lead_horizon(self) -> None:
        self._insert_backtest(virus_typ="Influenza A", target_source="ATEMWEGSINDEX")
        today = datetime.utcnow().date()
        for offset in (-10, 0, 7, 14):
            self.db.add(
                MLForecast(
                    forecast_date=datetime.combine(today + timedelta(days=offset), datetime.min.time()),
                    virus_typ="Influenza A",
                    predicted_value=100.0 + offset,
                    lower_bound=90.0 + offset,
                    upper_bound=110.0 + offset,
                    model_version="xgb",
                )
            )
        self.db.commit()
        payload = self._build(horizon_days=14)
        # -14..+14 inclusive = 29 points
        self.assertEqual(len(payload["timeline"]), 29)


if __name__ == "__main__":
    unittest.main()
