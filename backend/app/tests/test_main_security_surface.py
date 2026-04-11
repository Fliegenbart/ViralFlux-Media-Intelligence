import unittest
import os
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.requests import Request

os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "test-password")

from app import main


class MainSecuritySurfaceTests(unittest.TestCase):
    def test_docs_surface_is_hidden_by_default_in_production(self) -> None:
        urls = main._api_surface_urls(
            SimpleNamespace(EFFECTIVE_API_DOCS_ENABLED=False)
        )

        self.assertEqual(
            urls,
            {
                "docs_url": None,
                "redoc_url": None,
                "openapi_url": None,
            },
        )

    def test_docs_surface_stays_enabled_outside_production(self) -> None:
        urls = main._api_surface_urls(
            SimpleNamespace(EFFECTIVE_API_DOCS_ENABLED=True)
        )

        self.assertEqual(
            urls,
            {
                "docs_url": "/docs",
                "redoc_url": "/redoc",
                "openapi_url": "/openapi.json",
            },
        )

    def test_public_readiness_payload_strips_internal_details(self) -> None:
        snapshot = {
            "status": "warning",
            "checked_at": "2026-04-11T12:00:00Z",
            "blockers": ["db"],
            "warnings": ["source stale"],
            "components": {"db": {"status": "down"}},
            "startup": {"db_summary": {"status": "warning"}},
        }

        payload = main._public_readiness_payload(
            snapshot,
            settings_obj=SimpleNamespace(
                APP_VERSION="1.0.0",
                ENVIRONMENT="production",
            ),
            expose_details=False,
        )

        self.assertEqual(payload["status"], "warning")
        self.assertEqual(payload["blocker_count"], 1)
        self.assertEqual(payload["warning_count"], 1)
        self.assertNotIn("blockers", payload)
        self.assertNotIn("warnings", payload)
        self.assertNotIn("components", payload)
        self.assertNotIn("startup", payload)

    def test_metrics_access_hidden_without_token_in_production(self) -> None:
        request = Request({"type": "http", "headers": []})

        with self.assertRaises(HTTPException) as exc:
            main._enforce_metrics_access(
                request=request,
                current_user=None,
                settings_obj=SimpleNamespace(
                    EFFECTIVE_PUBLIC_METRICS_ENABLED=False,
                    METRICS_AUTH_TOKEN=None,
                ),
            )

        self.assertEqual(exc.exception.status_code, 404)

    def test_metrics_access_accepts_matching_token(self) -> None:
        request = Request(
            {
                "type": "http",
                "headers": [(b"x-metrics-token", b"secret-token")],
            }
        )

        main._enforce_metrics_access(
            request=request,
            current_user=None,
            settings_obj=SimpleNamespace(
                EFFECTIVE_PUBLIC_METRICS_ENABLED=False,
                METRICS_AUTH_TOKEN="secret-token",
            ),
        )


if __name__ == "__main__":
    unittest.main()
