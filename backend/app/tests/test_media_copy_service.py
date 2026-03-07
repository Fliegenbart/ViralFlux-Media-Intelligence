import os
import unittest

# Minimal env bootstrap for app settings during module import.
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("OPENWEATHER_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.api.media import _to_card_response
from app.services.media.copy_service import (
    build_decision_basis_text,
    build_decision_summary_text,
    build_region_outlook_text,
    build_region_recommendation_text,
    public_display_title,
    public_event_label,
    public_reason_text,
    public_source_label,
)


class MediaCopyServiceTests(unittest.TestCase):
    def test_public_display_title_prefers_customer_facing_playbook_title(self) -> None:
        title = public_display_title(
            playbook_key="SUPPLY_SHOCK_ATTACK",
            playbook_title="Supply-Shock Attack",
            campaign_name="gelo | GeloMyrto forte | Brandenburg | Supply-Shock Attack",
            product="GeloMyrto forte",
            trigger_event="SUPPLY_SHOCK_WINDOW",
            condition_label="Bronchitis & Husten",
        )

        self.assertEqual(title, "Verfügbarkeitsfenster nutzen")

    def test_public_reason_text_humanizes_internal_trigger_codes(self) -> None:
        reason = public_reason_text(
            reason="SUPPLY_SHOCK_WINDOW",
            event="SUPPLY_SHOCK_WINDOW",
            details="SUPPLY_SHOCK_WINDOW in Brandenburg",
        )

        self.assertEqual(reason, "Verfügbarkeitsfenster im Wettbewerb")

    def test_build_decision_basis_text_reads_like_customer_copy(self) -> None:
        basis = build_decision_basis_text(
            source_label="BfArM + RKI",
            event="SUPPLY_SHOCK_WINDOW",
            score=86.9,
        )

        self.assertEqual(
            basis,
            "Signalen aus BfArM Engpassmonitor + RKI, dem Muster Verfügbarkeitsfenster im Wettbewerb und einem PeixEpiScore von 86.9",
        )

    def test_public_source_label_humanizes_internal_source_key(self) -> None:
        self.assertEqual(public_source_label("BfArM_API"), "BfArM Engpassmonitor")

    def test_public_event_label_humanizes_respiratory_growth_code(self) -> None:
        self.assertEqual(
            public_event_label("RESPIRATORY_GROWTH_HALSSCHMERZ"),
            "zunehmende Halsschmerz- und Heiserkeitssignale",
        )

    def test_build_region_copy_reads_like_customer_copy(self) -> None:
        outlook = build_region_outlook_text(
            virus_typ="Influenza A",
            trend="fallend",
            change_pct=-12.0,
            vorhersage_delta_pct=9.0,
        )
        recommendation = build_region_recommendation_text(
            region_name="Hamburg",
            outlook_text=outlook,
            product="GeloRevoice",
            reason="Halsbeschwerden und Heiserkeit wahrscheinlicher werden",
        )

        self.assertEqual(
            outlook,
            "aktuell rückläufige Influenza A-Aktivität (-12% WoW), der Forecast zeigt jedoch wieder nach oben",
        )
        self.assertIn("In Hamburg sehen wir für die nächsten 7 bis 14 Tage", recommendation)
        self.assertIn("Deshalb priorisieren wir zunächst GeloRevoice", recommendation)

    def test_build_decision_summary_mentions_review_if_product_needs_confirmation(self) -> None:
        summary = build_decision_summary_text(
            basis_text="Signalen aus RKI SurvStat und dem Muster auffälliger Mykoplasmen-Anstieg",
            condition_text="bronchitis_husten",
            primary_region="Schleswig-Holstein",
            primary_product="Produktfreigabe ausstehend",
            action_required="review_mapping",
        )

        self.assertIn("Bronchitis und Husten", summary)
        self.assertIn("Vor einer Freigabe", summary)

    def test_card_response_exposes_public_titles_and_reason(self) -> None:
        card = _to_card_response(
            {
                "id": "OPP-1",
                "status": "DRAFT",
                "type": "SUPPLY_SHOCK_ATTACK",
                "urgency_score": 91.0,
                "brand": "gelo",
                "recommended_product": "GeloMyrto forte",
                "playbook_key": "SUPPLY_SHOCK_ATTACK",
                "playbook_title": "Supply-Shock Attack",
                "trigger_context": {
                    "event": "SUPPLY_SHOCK_WINDOW",
                    "details": "SUPPLY_SHOCK_WINDOW in Brandenburg",
                },
                "campaign_preview": {
                    "campaign_name": "gelo | GeloMyrto forte | Brandenburg | Supply-Shock Attack",
                },
            }
        )

        self.assertEqual(card["display_title"], "Verfügbarkeitsfenster nutzen")
        self.assertEqual(card["playbook_title"], "Verfügbarkeitsfenster nutzen")
        self.assertEqual(card["reason"], "Verfügbarkeitsfenster im Wettbewerb")


if __name__ == "__main__":
    unittest.main()
