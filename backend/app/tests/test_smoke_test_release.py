from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "smoke_test_release.py"
SPEC = importlib.util.spec_from_file_location("smoke_test_release", SCRIPT_PATH)
assert SPEC and SPEC.loader
smoke_test_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke_test_release)


class SmokeTestReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        credentials_patcher = patch.object(
            smoke_test_release,
            "_load_backend_container_credentials",
            return_value={},
        )
        self.mock_container_credentials = credentials_patcher.start()
        self.addCleanup(credentials_patcher.stop)

    def test_run_smoke_uses_admin_login_for_protected_core_paths(self) -> None:
        responses = [
            (200, {"status": "alive", "environment": "production", "app_version": "1.0.0"}),
            (200, {"status": "healthy", "components": {}, "blockers": []}),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "quality_gate": {"forecast_readiness": "WATCH"},
                    "predictions": [
                        {
                            "bundesland": "BY",
                            "decision_label": "Prepare",
                            "event_probability": 0.52,
                            "decision_priority_index": 0.71,
                            "priority_score": 0.71,
                            "reason_trace": {"drivers": ["signal"]},
                            "uncertainty_summary": "Moderate uncertainty.",
                        }
                    ],
                },
            ),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "summary": {"activate_regions": 1, "prepare_regions": 2, "watch_regions": 13},
                    "recommendations": [
                        {
                            "bundesland": "BY",
                            "recommended_activation_level": "Prepare",
                            "event_probability": 0.52,
                            "decision_priority_index": 0.71,
                            "suggested_budget_share": 0.0,
                            "suggested_budget_amount": 0.0,
                            "allocation_reason_trace": {
                                "why": [
                                    "Prepare is an early-warning stage. Keep the region visible, but do not release paid budget yet.",
                                ],
                                "budget_drivers": [
                                    "Suggested budget share is 0.00%.",
                                ],
                                "uncertainty": [],
                                "blockers": [
                                    "Prepare is an early-warning stage. Keep the region visible, but do not release paid budget yet.",
                                ],
                            },
                            "allocation_support_score": 0.5,
                            "confidence": 0.66,
                        }
                    ],
                },
            ),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "summary": {
                        "top_region": "BY",
                        "top_product_cluster": "Respiratory Core Demand",
                        "ready_recommendations": 0,
                        "observe_only_recommendations": 1,
                    },
                    "recommendations": [
                        {
                            "region": "BY",
                            "recommended_product_cluster": {"label": "Respiratory Core Demand"},
                            "recommended_keyword_cluster": {"label": "Respiratory Relief Search"},
                            "activation_level": "Prepare",
                            "suggested_budget_amount": 0.0,
                            "allocation_support_score": 0.5,
                            "confidence": 0.66,
                            "evidence_class": "moderate",
                            "recommendation_rationale": {
                                "why": [
                                    "BY is an early-warning Prepare region. Operative preparation is justified, but no paid activation budget is released yet.",
                                ],
                                "budget_notes": [
                                    "Suggested campaign budget is 0.00 EUR until Activate is reached and spend gates open.",
                                ],
                                "guardrails": [
                                    "Recommendation stays preparation-only for now.",
                                ],
                            },
                        }
                    ],
                },
            ),
        ]
        calls: list[dict[str, object]] = []

        def fake_request_json(base_url: str, path: str, timeout: float, **kwargs):
            calls.append({"path": path, "kwargs": kwargs})
            return responses[len(calls) - 1]

        with (
            patch.dict(os.environ, {"SMOKE_ADMIN_EMAIL": "ci@test.de", "SMOKE_ADMIN_PASSWORD": "secret"}, clear=False),
            patch.object(smoke_test_release, "_request_json", side_effect=fake_request_json),
            patch.object(
                smoke_test_release,
                "_request_headers",
                return_value=(
                    200,
                    {"Set-Cookie": "viralflux_session=token-123; HttpOnly; Path=/"},
                    {"authenticated": True, "subject": "ci@test.de", "role": "admin"},
                ),
            ) as request_headers_mock,
        ):
            exit_code, result = smoke_test_release.run_smoke(
                base_url="http://127.0.0.1:8000",
                timeout=5.0,
                virus="Influenza A",
                brand="gelo",
                horizon=7,
                budget_eur=50_000.0,
                top_n=3,
                target_source="RKI_ARE",
                check_cockpit=False,
            )

        self.assertEqual(exit_code, smoke_test_release.EXIT_OK)
        self.assertTrue(result["checks"]["auth_login"]["passed"])
        request_headers_mock.assert_called_once()
        self.assertEqual(request_headers_mock.call_args.args[1], "/api/auth/login")
        self.assertEqual(
            calls[2]["kwargs"]["headers"],
            {"Cookie": "viralflux_session=token-123"},
        )
        self.assertIn("brand=gelo", calls[2]["path"])
        self.assertIn("brand=gelo", calls[3]["path"])
        self.assertIn("brand=gelo", calls[4]["path"])

    def test_run_smoke_accepts_explicit_brand_for_regional_core_paths(self) -> None:
        responses = [
            (200, {"status": "alive", "environment": "production"}),
            (200, {"status": "healthy", "components": {}, "blockers": []}),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "predictions": [
                        {
                            "bundesland": "BY",
                            "decision_label": "Prepare",
                            "event_probability": 0.52,
                            "decision_priority_index": 0.71,
                            "priority_score": 0.71,
                            "reason_trace": {},
                            "uncertainty_summary": "Moderate uncertainty.",
                        }
                    ],
                },
            ),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "summary": {},
                    "recommendations": [
                        {
                            "bundesland": "BY",
                            "recommended_activation_level": "Prepare",
                            "event_probability": 0.52,
                            "decision_priority_index": 0.71,
                            "suggested_budget_share": 0.0,
                            "suggested_budget_amount": 0.0,
                            "allocation_reason_trace": {
                                "why": [],
                                "budget_drivers": [],
                                "uncertainty": [],
                                "blockers": [],
                            },
                            "allocation_support_score": 0.5,
                            "confidence": 0.66,
                        }
                    ],
                },
            ),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "summary": {},
                    "recommendations": [
                        {
                            "region": "BY",
                            "recommended_product_cluster": {"label": "Respiratory Core Demand"},
                            "recommended_keyword_cluster": {"label": "Respiratory Relief Search"},
                            "activation_level": "Prepare",
                            "suggested_budget_amount": 0.0,
                            "allocation_support_score": 0.5,
                            "confidence": 0.66,
                            "evidence_class": "moderate",
                            "recommendation_rationale": {"why": [], "budget_notes": [], "guardrails": []},
                        }
                    ],
                },
            ),
        ]
        calls: list[str] = []

        def fake_request_json(base_url: str, path: str, timeout: float, **kwargs):
            del base_url, timeout, kwargs
            calls.append(path)
            return responses[len(calls) - 1]

        with (
            patch.object(smoke_test_release, "_request_json", side_effect=fake_request_json),
            patch.object(smoke_test_release, "_authenticate_headers", return_value=({}, None)),
        ):
            exit_code, result = smoke_test_release.run_smoke(
                base_url="http://127.0.0.1:8000",
                timeout=5.0,
                virus="Influenza A",
                brand="acme-health",
                horizon=7,
                budget_eur=50_000.0,
                top_n=3,
                target_source="RKI_ARE",
                check_cockpit=False,
            )

        self.assertEqual(exit_code, smoke_test_release.EXIT_OK)
        self.assertEqual(result["status"], "pass")
        self.assertIn("brand=acme-health", calls[2])
        self.assertIn("brand=acme-health", calls[3])
        self.assertIn("brand=acme-health", calls[4])

    def test_run_smoke_passes_on_healthy_core_path(self) -> None:
        responses = [
            (200, {"status": "alive", "environment": "production", "app_version": "1.0.0"}),
            (200, {"status": "healthy", "components": {}, "blockers": []}),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "quality_gate": {"forecast_readiness": "WATCH"},
                    "predictions": [
                        {
                            "bundesland": "BY",
                            "decision_label": "Prepare",
                            "event_probability": 0.52,
                            "decision_priority_index": 0.71,
                            "priority_score": 0.71,
                            "reason_trace": {"drivers": ["signal"]},
                            "uncertainty_summary": "Moderate uncertainty.",
                        }
                    ],
                },
            ),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "summary": {"activate_regions": 1, "prepare_regions": 2, "watch_regions": 13},
                    "recommendations": [
                        {
                            "bundesland": "BY",
                            "recommended_activation_level": "Prepare",
                            "event_probability": 0.52,
                            "decision_priority_index": 0.71,
                            "suggested_budget_share": 0.0,
                            "suggested_budget_amount": 0.0,
                            "allocation_reason_trace": {
                                "why": [
                                    "Prepare is an early-warning stage. Keep the region visible, but do not release paid budget yet.",
                                ],
                                "budget_drivers": [
                                    "Suggested budget share is 0.00%.",
                                ],
                                "uncertainty": [],
                                "blockers": [
                                    "Prepare is an early-warning stage. Keep the region visible, but do not release paid budget yet.",
                                ],
                            },
                            "allocation_support_score": 0.5,
                            "confidence": 0.66,
                        }
                    ],
                },
            ),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "summary": {
                        "top_region": "BY",
                        "top_product_cluster": "Respiratory Core Demand",
                        "ready_recommendations": 0,
                        "observe_only_recommendations": 1,
                    },
                    "recommendations": [
                        {
                            "region": "BY",
                            "recommended_product_cluster": {"label": "Respiratory Core Demand"},
                            "recommended_keyword_cluster": {"label": "Respiratory Relief Search"},
                            "activation_level": "Prepare",
                            "suggested_budget_amount": 0.0,
                            "allocation_support_score": 0.5,
                            "confidence": 0.66,
                            "evidence_class": "moderate",
                            "recommendation_rationale": {
                                "why": [
                                    "BY is an early-warning Prepare region. Operative preparation is justified, but no paid activation budget is released yet.",
                                ],
                                "budget_notes": [
                                    "Suggested campaign budget is 0.00 EUR until Activate is reached and spend gates open.",
                                ],
                                "guardrails": [
                                    "Recommendation stays preparation-only for now.",
                                ],
                            },
                        }
                    ],
                },
            ),
        ]

        with (
            patch.object(smoke_test_release, "_request_json", side_effect=responses),
            patch.object(smoke_test_release, "_authenticate_headers", return_value=({}, None)),
        ):
            exit_code, result = smoke_test_release.run_smoke(
                base_url="http://127.0.0.1:8000",
                timeout=5.0,
                virus="Influenza A",
                brand="gelo",
                horizon=7,
                budget_eur=50_000.0,
                top_n=3,
                target_source="RKI_ARE",
                check_cockpit=False,
            )

        self.assertEqual(exit_code, smoke_test_release.EXIT_OK)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["failure_level"], "none")
        self.assertTrue(result["checks"]["regional_forecast"]["passed"])
        self.assertTrue(result["checks"]["regional_allocation"]["passed"])
        self.assertTrue(result["checks"]["regional_campaign_recommendations"]["passed"])
        self.assertEqual(result["checks"]["regional_campaign_recommendations"]["summary"]["ready_recommendations"], 0)

    def test_run_smoke_flags_ready_blocked_without_business_failure(self) -> None:
        responses = [
            (200, {"status": "alive", "environment": "production"}),
            (503, {"status": "unhealthy", "components": {}, "blockers": [{"component": "regional_operational"}]}),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "predictions": [
                        {
                            "bundesland": "BY",
                            "decision_label": "Prepare",
                            "event_probability": 0.52,
                            "decision_priority_index": 0.71,
                            "priority_score": 0.71,
                            "reason_trace": {},
                            "uncertainty_summary": "Moderate uncertainty.",
                        }
                    ],
                },
            ),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "summary": {},
                    "recommendations": [
                        {
                            "bundesland": "BY",
                            "recommended_activation_level": "Prepare",
                            "event_probability": 0.52,
                            "decision_priority_index": 0.71,
                            "suggested_budget_share": 0.0,
                            "suggested_budget_amount": 0.0,
                            "allocation_reason_trace": {
                                "why": [
                                    "Prepare is an early-warning stage. Keep the region visible, but do not release paid budget yet.",
                                ],
                                "budget_drivers": [
                                    "Suggested budget share is 0.00%.",
                                ],
                                "uncertainty": [],
                                "blockers": [
                                    "Prepare is an early-warning stage. Keep the region visible, but do not release paid budget yet.",
                                ],
                            },
                            "allocation_support_score": 0.5,
                            "confidence": 0.66,
                        }
                    ],
                },
            ),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "summary": {},
                    "recommendations": [
                        {
                            "region": "BY",
                            "recommended_product_cluster": {"label": "Respiratory Core Demand"},
                            "recommended_keyword_cluster": {"label": "Respiratory Relief Search"},
                            "activation_level": "Prepare",
                            "suggested_budget_amount": 0.0,
                            "allocation_support_score": 0.5,
                            "confidence": 0.66,
                            "evidence_class": "moderate",
                            "recommendation_rationale": {
                                "why": [
                                    "BY is an early-warning Prepare region. Operative preparation is justified, but no paid activation budget is released yet.",
                                ],
                                "budget_notes": [
                                    "Suggested campaign budget is 0.00 EUR until Activate is reached and spend gates open.",
                                ],
                                "guardrails": [
                                    "Recommendation stays preparation-only for now.",
                                ],
                            },
                        }
                    ],
                },
            ),
        ]

        with (
            patch.object(smoke_test_release, "_request_json", side_effect=responses),
            patch.object(smoke_test_release, "_authenticate_headers", return_value=({}, None)),
        ):
            exit_code, result = smoke_test_release.run_smoke(
                base_url="http://127.0.0.1:8000",
                timeout=5.0,
                virus="Influenza A",
                brand="gelo",
                horizon=7,
                budget_eur=50_000.0,
                top_n=3,
                target_source="RKI_ARE",
                check_cockpit=False,
            )

        self.assertEqual(exit_code, smoke_test_release.EXIT_READY_BLOCKED)
        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["failure_level"], "ready_blocked")
        self.assertTrue(result["checks"]["health_ready"]["blocked"])

    def test_run_smoke_fails_when_business_core_breaks(self) -> None:
        responses = [
            (200, {"status": "alive", "environment": "production"}),
            (200, {"status": "healthy", "components": {}, "blockers": []}),
            (500, {"detail": "server exploded"}),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "summary": {},
                    "recommendations": [
                        {
                            "bundesland": "BY",
                            "recommended_activation_level": "Prepare",
                            "suggested_budget_share": 0.0,
                            "suggested_budget_amount": 0.0,
                            "allocation_reason_trace": {
                                "why": [
                                    "Prepare is an early-warning stage. Keep the region visible, but do not release paid budget yet.",
                                ],
                                "budget_drivers": [
                                    "Suggested budget share is 0.00%.",
                                ],
                                "uncertainty": [],
                                "blockers": [
                                    "Prepare is an early-warning stage. Keep the region visible, but do not release paid budget yet.",
                                ],
                            },
                            "confidence": 0.66,
                        }
                    ],
                },
            ),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "summary": {},
                    "recommendations": [
                        {
                            "region": "BY",
                            "recommended_product_cluster": {"label": "Respiratory Core Demand"},
                            "recommended_keyword_cluster": {"label": "Respiratory Relief Search"},
                            "activation_level": "Prepare",
                            "suggested_budget_amount": 0.0,
                            "confidence": 0.66,
                            "evidence_class": "moderate",
                            "recommendation_rationale": {
                                "why": [
                                    "BY is an early-warning Prepare region. Operative preparation is justified, but no paid activation budget is released yet.",
                                ],
                                "budget_notes": [
                                    "Suggested campaign budget is 0.00 EUR until Activate is reached and spend gates open.",
                                ],
                                "guardrails": [
                                    "Recommendation stays preparation-only for now.",
                                ],
                            },
                        }
                    ],
                },
            ),
        ]

        with (
            patch.object(smoke_test_release, "_request_json", side_effect=responses),
            patch.object(smoke_test_release, "_authenticate_headers", return_value=({}, None)),
        ):
            exit_code, result = smoke_test_release.run_smoke(
                base_url="http://127.0.0.1:8000",
                timeout=5.0,
                virus="Influenza A",
                brand="gelo",
                horizon=7,
                budget_eur=50_000.0,
                top_n=3,
                target_source="RKI_ARE",
                check_cockpit=False,
            )

        self.assertEqual(exit_code, smoke_test_release.EXIT_BUSINESS_SMOKE_FAILED)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["failure_level"], "business_smoke_failed")
        self.assertFalse(result["checks"]["regional_forecast"]["passed"])

    def test_run_smoke_uses_backend_container_credentials_when_env_missing(self) -> None:
        responses = [
            (200, {"status": "alive", "environment": "production", "app_version": "1.0.0"}),
            (200, {"status": "healthy", "components": {}, "blockers": []}),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "quality_gate": {"forecast_readiness": "WATCH"},
                    "predictions": [
                        {
                            "bundesland": "BY",
                            "decision_label": "Prepare",
                            "event_probability": 0.52,
                            "decision_priority_index": 0.71,
                            "priority_score": 0.71,
                            "reason_trace": {"drivers": ["signal"]},
                            "uncertainty_summary": "Moderate uncertainty.",
                        }
                    ],
                },
            ),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "summary": {"activate_regions": 1, "prepare_regions": 2, "watch_regions": 13},
                    "recommendations": [
                        {
                            "bundesland": "BY",
                            "recommended_activation_level": "Prepare",
                            "event_probability": 0.52,
                            "decision_priority_index": 0.71,
                            "suggested_budget_share": 0.0,
                            "suggested_budget_amount": 0.0,
                            "allocation_reason_trace": {
                                "why": [
                                    "Prepare is an early-warning stage. Keep the region visible, but do not release paid budget yet.",
                                ],
                                "budget_drivers": [
                                    "Suggested budget share is 0.00%.",
                                ],
                                "uncertainty": [],
                                "blockers": [
                                    "Prepare is an early-warning stage. Keep the region visible, but do not release paid budget yet.",
                                ],
                            },
                            "allocation_support_score": 0.5,
                            "confidence": 0.66,
                        }
                    ],
                },
            ),
            (
                200,
                {
                    "virus_typ": "Influenza A",
                    "horizon_days": 7,
                    "summary": {
                        "top_region": "BY",
                        "top_product_cluster": "Respiratory Core Demand",
                        "ready_recommendations": 0,
                        "observe_only_recommendations": 1,
                    },
                    "recommendations": [
                        {
                            "region": "BY",
                            "recommended_product_cluster": {"label": "Respiratory Core Demand"},
                            "recommended_keyword_cluster": {"label": "Respiratory Relief Search"},
                            "activation_level": "Prepare",
                            "suggested_budget_amount": 0.0,
                            "allocation_support_score": 0.5,
                            "confidence": 0.66,
                            "evidence_class": "moderate",
                            "recommendation_rationale": {
                                "why": [
                                    "BY is an early-warning Prepare region. Operative preparation is justified, but no paid activation budget is released yet.",
                                ],
                                "budget_notes": [
                                    "Suggested campaign budget is 0.00 EUR until Activate is reached and spend gates open.",
                                ],
                                "guardrails": [
                                    "Recommendation stays preparation-only for now.",
                                ],
                            },
                        }
                    ],
                },
            ),
        ]
        calls: list[dict[str, object]] = []

        def fake_request_json(base_url: str, path: str, timeout: float, **kwargs):
            calls.append({"path": path, "kwargs": kwargs})
            return responses[len(calls) - 1]

        self.mock_container_credentials.return_value = {
            "ADMIN_EMAIL": "container@test.de",
            "ADMIN_PASSWORD": "container-secret",
        }

        with (
            patch.dict(
                os.environ,
                {
                    "SMOKE_ADMIN_EMAIL": "",
                    "SMOKE_ADMIN_PASSWORD": "",
                    "ADMIN_EMAIL": "",
                    "ADMIN_PASSWORD": "",
                },
                clear=False,
            ),
            patch.object(smoke_test_release, "_request_json", side_effect=fake_request_json),
            patch.object(
                smoke_test_release,
                "_request_headers",
                return_value=(
                    200,
                    {"Set-Cookie": "viralflux_session=token-from-container; HttpOnly; Path=/"},
                    {"authenticated": True, "subject": "container@test.de", "role": "admin"},
                ),
            ) as request_headers_mock,
        ):
            exit_code, result = smoke_test_release.run_smoke(
                base_url="http://127.0.0.1:8000",
                timeout=5.0,
                virus="Influenza A",
                brand="gelo",
                horizon=7,
                budget_eur=50_000.0,
                top_n=3,
                target_source="RKI_ARE",
                check_cockpit=False,
            )

        self.assertEqual(exit_code, smoke_test_release.EXIT_OK)
        self.assertTrue(result["checks"]["auth_login"]["passed"])
        self.assertEqual(result["checks"]["auth_login"]["summary"]["auth_source"], "password_login")
        request_headers_mock.assert_called_once()
        self.assertEqual(request_headers_mock.call_args.args[1], "/api/auth/login")
        self.assertEqual(
            request_headers_mock.call_args.kwargs["data"],
            b"username=container%40test.de&password=container-secret",
        )

    def test_run_smoke_adds_auth_hint_when_protected_endpoints_return_401(self) -> None:
        responses = [
            (200, {"status": "alive", "environment": "production"}),
            (200, {"status": "healthy", "components": {}, "blockers": []}),
            (401, {"detail": "Could not validate credentials"}),
            (401, {"detail": "Could not validate credentials"}),
            (401, {"detail": "Could not validate credentials"}),
        ]

        with (
            patch.object(smoke_test_release, "_request_json", side_effect=responses),
            patch.object(smoke_test_release, "_authenticate_headers", return_value=({}, None)),
        ):
            exit_code, result = smoke_test_release.run_smoke(
                base_url="http://127.0.0.1:8000",
                timeout=5.0,
                virus="Influenza A",
                brand="gelo",
                horizon=7,
                budget_eur=50_000.0,
                top_n=3,
                target_source="RKI_ARE",
                check_cockpit=False,
            )

        self.assertEqual(exit_code, smoke_test_release.EXIT_BUSINESS_SMOKE_FAILED)
        self.assertIn("Protected endpoint returned 401.", result["checks"]["regional_forecast"]["errors"][-1])
        self.assertIn("Protected endpoint returned 401.", result["checks"]["regional_allocation"]["errors"][-1])
        self.assertIn(
            "Protected endpoint returned 401.",
            result["checks"]["regional_campaign_recommendations"]["errors"][-1],
        )


if __name__ == "__main__":
    unittest.main()
