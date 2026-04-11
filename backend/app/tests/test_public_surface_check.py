import unittest

from backend.scripts.check_public_surface import (
    _extract_main_asset_path,
    _readiness_leaks_internal_details,
    _source_map_check,
)


class PublicSurfaceCheckTests(unittest.TestCase):
    def test_extract_main_asset_path_reads_hashed_main_bundle(self) -> None:
        html = '<script defer src="/static/js/main.a724a176.js"></script>'

        result = _extract_main_asset_path(html)

        self.assertEqual(result, "/static/js/main.a724a176.js")

    def test_extract_main_asset_path_returns_none_when_missing(self) -> None:
        self.assertIsNone(_extract_main_asset_path("<html></html>"))

    def test_readiness_detail_leak_detection_flags_internal_keys(self) -> None:
        self.assertTrue(
            _readiness_leaks_internal_details(
                {"status": "healthy", "components": {"db": {"status": "ok"}}}
            )
        )
        self.assertTrue(
            _readiness_leaks_internal_details(
                {"status": "healthy", "startup": {"db_summary": {"status": "ok"}}}
            )
        )

    def test_readiness_detail_leak_detection_accepts_sanitized_public_shape(self) -> None:
        payload = {
            "status": "healthy",
            "checked_at": "2026-04-11T20:00:00Z",
            "blocker_count": 0,
            "warning_count": 1,
            "environment": "production",
            "app_version": "1.0.0",
        }

        self.assertFalse(_readiness_leaks_internal_details(payload))

    def test_source_map_check_fails_when_map_is_public(self) -> None:
        result = _source_map_check(
            welcome_path="/welcome",
            welcome_status=200,
            welcome_html='<script defer src="/static/js/main.eaf46140.js"></script>',
            source_map_status=200,
            source_map_path="/static/js/main.eaf46140.js.map",
        )

        self.assertFalse(result["passed"])
        self.assertIn("publicly reachable", result["errors"][0])

    def test_source_map_check_passes_when_map_is_hidden(self) -> None:
        result = _source_map_check(
            welcome_path="/welcome",
            welcome_status=200,
            welcome_html='<script defer src="/static/js/main.a724a176.js"></script>',
            source_map_status=404,
            source_map_path="/static/js/main.a724a176.js.map",
        )

        self.assertTrue(result["passed"])


if __name__ == "__main__":
    unittest.main()
