import unittest

from app.services.media.connector_payload_service import ConnectorPayloadService


def _sample_opportunity(status: str = "APPROVED") -> dict:
    return {
        "id": "opp-123",
        "status": status,
        "brand": "gelo",
        "recommended_product": "GeloProsed",
        "region_codes": ["SH", "HH"],
        "campaign_payload": {
            "campaign": {
                "campaign_name": "Nord Wave Push",
                "objective": "Awareness + Abverkauf",
                "status": status,
            },
            "targeting": {
                "region_scope": ["SH", "HH"],
                "audience_segments": ["Familien", "Pendler"],
            },
            "activation_window": {
                "start": "2026-03-09",
                "end": "2026-03-22",
                "flight_days": 14,
            },
            "budget_plan": {
                "weekly_budget_eur": 120000.0,
                "budget_shift_pct": 18.0,
                "budget_shift_value_eur": 21600.0,
                "total_flight_budget_eur": 120000.0,
                "currency": "EUR",
            },
            "channel_plan": [
                {"channel": "search", "share_pct": 40.0, "kpi_primary": "CTR"},
                {"channel": "social", "share_pct": 35.0, "kpi_primary": "Reach"},
                {"channel": "programmatic", "share_pct": 25.0, "kpi_primary": "Viewability"},
            ],
            "message_framework": {
                "hero_message": "Schietwetter? Reichweite jetzt vorbereiten.",
                "support_points": ["Frühzeitig sichtbar sein", "Regionale Relevanz nutzen"],
                "cta": "Mehr erfahren",
                "compliance_note": "Konservativ formulieren.",
            },
            "measurement_plan": {
                "primary_kpi": "Qualified Visits",
                "secondary_kpis": ["CTR", "CPM"],
            },
            "playbook": {
                "key": "WETTER_REFLEX",
                "title": "Wetter-Reflex",
            },
            "trigger_snapshot": {
                "source": "RKI_ARE",
                "event": "INFLUENZA_TREND",
                "details": "Ansteigende Belastung in Norddeutschland",
                "lead_time_days": 10,
            },
            "ai_plan": {
                "creative_angles": ["Nord-Fokus", "Wetter-Trigger", "Vorbereiten statt warten"],
                "keyword_clusters": ["erkaeltung norddeutschland", "husten wetterumschwung"],
                "next_steps": [{"task": "Setup bauen", "owner": "Media Ops", "eta": "T+0"}],
            },
            "guardrail_report": {
                "passed": True,
                "notes": [],
                "applied_fixes": ["Probability wording softened"],
            },
        },
    }


class ConnectorPayloadServiceTests(unittest.TestCase):
    def test_prepare_sync_package_requires_approval(self) -> None:
        preview = ConnectorPayloadService.prepare_sync_package(
            opportunity=_sample_opportunity(status="READY"),
            connector_key="meta_ads",
        )

        self.assertEqual(preview["connector_key"], "meta_ads")
        self.assertFalse(preview["readiness"]["can_sync_now"])
        self.assertEqual(preview["readiness"]["state"], "approval_required")
        self.assertTrue(
            any("freigegeben" in blocker.lower() for blocker in preview["readiness"]["blockers"])
        )

    def test_prepare_sync_package_builds_google_ads_preview(self) -> None:
        preview = ConnectorPayloadService.prepare_sync_package(
            opportunity=_sample_opportunity(status="APPROVED"),
            connector_key="google_ads",
        )

        self.assertEqual(preview["connector_key"], "google_ads")
        self.assertTrue(preview["readiness"]["can_sync_now"])
        self.assertEqual(preview["normalized_package"]["region_codes"], ["HH", "SH"])
        self.assertEqual(preview["connector_payload"]["campaign"]["name"], "Nord Wave Push")
        self.assertGreaterEqual(len(preview["connector_payload"]["ad_groups"]), 2)
        self.assertIn("husten wetterumschwung", preview["connector_payload"]["ad_groups"][0]["keywords"])


if __name__ == "__main__":
    unittest.main()
