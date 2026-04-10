from __future__ import annotations

import importlib
import sys
import types
import unittest
from unittest.mock import patch


def _load_service_module():
    sys.modules.pop("app.services.media.pilot_readout_service", None)

    media_v2_module = types.ModuleType("app.services.media.v2_service")

    class DummyMediaV2Service:
        def __init__(self, db):
            self.db = db
            self.truth_gate_service = types.SimpleNamespace(evaluate=lambda payload: payload)

    media_v2_module.MediaV2Service = DummyMediaV2Service

    regional_forecast_module = types.ModuleType("app.services.ml.regional_forecast")

    class DummyRegionalForecastService:
        def __init__(self, db):
            self.db = db
            self.campaign_recommendation_service = types.SimpleNamespace(
                recommend_from_allocation=lambda **_: {}
            )

    regional_forecast_module.RegionalForecastService = DummyRegionalForecastService

    business_validation_module = types.ModuleType("app.services.media.business_validation_service")

    class DummyBusinessValidationService:
        def __init__(self, db):
            self.db = db

    business_validation_module.BusinessValidationService = DummyBusinessValidationService

    snapshot_store_module = types.ModuleType(
        "app.services.ops.regional_operational_snapshot_store"
    )

    class DummyRegionalOperationalSnapshotStore:
        def __init__(self, db):
            self.db = db

        @staticmethod
        def _normalized_metadata(payload):
            return payload

    snapshot_store_module.RegionalOperationalSnapshotStore = DummyRegionalOperationalSnapshotStore

    with patch.dict(
        sys.modules,
        {
            "app.services.media.v2_service": media_v2_module,
            "app.services.ml.regional_forecast": regional_forecast_module,
            "app.services.media.business_validation_service": business_validation_module,
            "app.services.ops.regional_operational_snapshot_store": snapshot_store_module,
        },
    ):
        module = importlib.import_module("app.services.media.pilot_readout_service")
        return importlib.reload(module)


class PilotReadoutRefactorGuardTests(unittest.TestCase):
    def test_region_rows_wrapper_delegates_to_sections_module(self) -> None:
        module = _load_service_module()
        service = module.PilotReadoutService(db=None)
        forecast = {"predictions": [{"bundesland": "BE"}], "quality_gate": {"overall_passed": True}}
        allocation = {"recommendations": []}
        recommendations = {"recommendations": []}

        with patch.object(
            module.pilot_readout_sections,
            "build_region_rows",
            return_value=[{"region_code": "BE"}],
        ) as mocked:
            result = service._region_rows(
                forecast=forecast,
                allocation=allocation,
                recommendations=recommendations,
            )

        self.assertEqual(result, [{"region_code": "BE"}])
        mocked.assert_called_once_with(
            service,
            forecast=forecast,
            allocation=allocation,
            recommendations=recommendations,
        )

    def test_executive_summary_wrapper_delegates_to_sections_module(self) -> None:
        module = _load_service_module()
        service = module.PilotReadoutService(db=None)

        with patch.object(
            module.pilot_readout_sections,
            "build_executive_summary",
            return_value={"scope_readiness": "WATCH"},
        ) as mocked:
            result = service._executive_summary(
                virus_typ="RSV A",
                horizon_days=7,
                weekly_budget_eur=120000.0,
                forecast={},
                allocation={},
                recommendations={},
                region_rows=[],
                forecast_readiness="WATCH",
                commercial_validation_status="WATCH",
                budget_mode="scenario_split",
                validation_disclaimer="pending",
                overall_scope_readiness="WATCH",
                gate_snapshot={"missing_requirements": []},
            )

        self.assertEqual(result, {"scope_readiness": "WATCH"})
        mocked.assert_called_once_with(
            service,
            virus_typ="RSV A",
            horizon_days=7,
            weekly_budget_eur=120000.0,
            forecast={},
            allocation={},
            recommendations={},
            region_rows=[],
            forecast_readiness="WATCH",
            commercial_validation_status="WATCH",
            budget_mode="scenario_split",
            validation_disclaimer="pending",
            overall_scope_readiness="WATCH",
            gate_snapshot={"missing_requirements": []},
        )

    def test_reason_trace_lines_wrapper_delegates_to_trace_module(self) -> None:
        module = _load_service_module()

        with patch.object(
            module.pilot_readout_trace,
            "reason_trace_lines",
            return_value=["delegated"],
        ) as mocked:
            result = module.PilotReadoutService._reason_trace_lines({"why": ["Berlin leads"]})

        self.assertEqual(result, ["delegated"])
        mocked.assert_called_once_with({"why": ["Berlin leads"]})

    def test_trace_module_collects_reason_messages_from_summary_and_details(self) -> None:
        trace_module = importlib.import_module("app.services.media.pilot_readout_trace")

        result = trace_module.reason_trace_lines(
            {
                "why": ["Berlin leads the current viral wave."],
                "guardrail_details": [
                    {
                        "code": "campaign_guardrail_ready",
                        "message": "Spend guardrails are currently satisfied.",
                    }
                ],
                "summary": "Pilot summary line.",
            }
        )

        self.assertEqual(
            result,
            [
                "Berlin leads the current viral wave.",
                "Spend guardrails are currently satisfied.",
                "Pilot summary line.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
