import unittest
from datetime import datetime

from app.services.media.recommendation_contracts import (
    dedupe_group_id,
    derive_lifecycle_state,
    derive_publish_blockers,
    enrich_card_v2,
    to_card_response,
)


def _sample_card(**overrides):
    base = {
        "id": "opp-1",
        "status": "READY",
        "product": "GeloProsed",
        "recommended_product": "GeloProsed",
        "mapping_status": "approved",
        "region_codes": ["SH"],
        "activation_window": {
            "start": "2026-03-09T00:00:00",
            "end": "2026-03-22T00:00:00",
        },
        "campaign_preview": {
            "budget": {
                "weekly_budget_eur": 120000.0,
            },
        },
        "campaign_payload": {
            "message_framework": {
                "hero_message": "Norddeutschland jetzt vorbereiten.",
            },
            "channel_plan": [
                {"channel": "search", "share_pct": 40.0},
            ],
            "guardrail_report": {
                "passed": True,
            },
        },
        "confidence": 0.82,
        "peix_context": {"score": 67},
        "decision_brief": {
            "facts": [
                {"key": "source", "label": "Quelle", "value": "AMELAG"},
                {"key": "context", "label": "Kontext", "value": "SurvStat"},
            ],
        },
        "condition_key": "erkaltung_akut",
    }
    base.update(overrides)
    return base


class RecommendationContractsV2Tests(unittest.TestCase):
    def test_publish_blockers_flag_placeholder_product(self) -> None:
        card = _sample_card(recommended_product="Atemwegslinie", product="Atemwegslinie")

        blockers = derive_publish_blockers(card, now=datetime(2026, 3, 6, 12, 0, 0))

        self.assertTrue(any("Produktfreigabe" in blocker for blocker in blockers))

    def test_expired_flights_switch_to_expired_lifecycle(self) -> None:
        card = _sample_card(
            activation_window={
                "start": "2026-02-01T00:00:00",
                "end": "2026-02-10T00:00:00",
            }
        )

        lifecycle_state = derive_lifecycle_state(card, now=datetime(2026, 3, 6, 12, 0, 0))

        self.assertEqual(lifecycle_state, "EXPIRED")

    def test_draft_package_without_content_blockers_enters_review(self) -> None:
        enriched = enrich_card_v2(
            _sample_card(status="DRAFT"),
            now=datetime(2026, 3, 6, 12, 0, 0),
        )

        self.assertEqual(enriched["lifecycle_state"], "REVIEW")
        self.assertFalse(enriched["is_publishable"])
        self.assertIn("Paket ist noch nicht in Prüfung.", enriched["publish_blockers"])

    def test_enrich_card_marks_sync_ready_package_as_publishable(self) -> None:
        enriched = enrich_card_v2(
            _sample_card(status="APPROVED"),
            now=datetime(2026, 3, 6, 12, 0, 0),
        )

        self.assertEqual(enriched["lifecycle_state"], "SYNC_READY")
        self.assertTrue(enriched["is_publishable"])
        self.assertEqual(enriched["evidence_strength"], "hoch")

    def test_placeholder_title_adds_product_release_blocker(self) -> None:
        card = _sample_card(
            display_title="Produktfreigabe ausstehend: Resource Scarcity",
            recommended_product="GeloMyrto forte",
            product="GeloMyrto forte",
        )

        blockers = derive_publish_blockers(card, now=datetime(2026, 3, 6, 12, 0, 0))

        self.assertTrue(any("Produktfreigabe" in blocker for blocker in blockers))

    def test_dedupe_group_id_uses_condition_product_region_and_window(self) -> None:
        card = _sample_card()

        group_id = dedupe_group_id(card)

        self.assertIn("erkaltung_akut", group_id)
        self.assertIn("geloprosed", group_id)
        self.assertIn("SH", group_id)
        self.assertIn("2026-03-09", group_id)

    def test_to_card_response_humanizes_nested_trigger_fields(self) -> None:
        response = to_card_response(
            _sample_card(
                id="opp-2",
                playbook_key="SUPPLY_SHOCK_ATTACK",
                playbook_title="Supply-Shock Attack",
                campaign_preview={
                    "campaign_name": "gelo | GeloMyrto forte | Brandenburg | Supply-Shock Attack",
                    "budget": {"weekly_budget_eur": 120000.0},
                },
                trigger_context={
                    "event": "SUPPLY_SHOCK_WINDOW",
                    "source": "BfArM_API",
                    "details": "SUPPLY_SHOCK_WINDOW in Brandenburg",
                },
                peix_context={
                    "score": 67,
                    "trigger_event": "SUPPLY_SHOCK_WINDOW",
                },
                campaign_payload={
                    "trigger_snapshot": {
                        "event": "SUPPLY_SHOCK_WINDOW",
                        "source": "BfArM_API",
                        "details": "SUPPLY_SHOCK_WINDOW in Brandenburg",
                    },
                    "trigger_evidence": {
                        "event": "SUPPLY_SHOCK_WINDOW",
                        "source": "BfArM_API",
                    },
                    "peix_context": {
                        "score": 67,
                        "trigger_event": "SUPPLY_SHOCK_WINDOW",
                    },
                    "campaign": {
                        "campaign_name": "gelo | GeloMyrto forte | Brandenburg | Supply-Shock Attack",
                    },
                    "playbook": {
                        "key": "SUPPLY_SHOCK_ATTACK",
                        "title": "Supply-Shock Attack",
                    },
                    "ai_plan": {
                        "campaign_name": "gelo | GeloMyrto forte | Brandenburg | Supply-Shock Attack",
                    },
                    "message_framework": {
                        "hero_message": "Norddeutschland jetzt vorbereiten.",
                    },
                    "channel_plan": [
                        {"channel": "search", "share_pct": 40.0},
                    ],
                    "guardrail_report": {
                        "passed": True,
                    },
                },
            ),
            include_preview=True,
        )

        self.assertEqual(response["trigger_context"]["event"], "Verfügbarkeitsfenster im Wettbewerb")
        self.assertEqual(response["trigger_snapshot"]["source"], "BfArM Engpassmonitor")
        self.assertEqual(response["peix_context"]["trigger_event"], "Verfügbarkeitsfenster im Wettbewerb")
        self.assertEqual(
            response["campaign_payload"]["trigger_snapshot"]["event"],
            "Verfügbarkeitsfenster im Wettbewerb",
        )
        self.assertEqual(response["campaign_name"], "GeloMyrto forte: Verfügbarkeitsfenster nutzen")
        self.assertEqual(response["campaign_preview"]["campaign_name"], "GeloMyrto forte: Verfügbarkeitsfenster nutzen")
        self.assertEqual(
            response["campaign_payload"]["campaign"]["campaign_name"],
            "GeloMyrto forte: Verfügbarkeitsfenster nutzen",
        )
        self.assertEqual(response["campaign_payload"]["playbook"]["title"], "Verfügbarkeitsfenster nutzen")
        self.assertEqual(
            response["campaign_payload"]["ai_plan"]["campaign_name"],
            "GeloMyrto forte: Verfügbarkeitsfenster nutzen",
        )

    def test_to_card_response_exposes_semantic_contracts_and_no_urgency_confidence_fallback(self) -> None:
        response = to_card_response(
            _sample_card(
                confidence=None,
                urgency_score=92.0,
                decision_brief={
                    "expectation": {
                        "signal_score": 67.0,
                        "signal_confidence_pct": None,
                    },
                },
                campaign_payload={
                    "message_framework": {
                        "hero_message": "Norddeutschland jetzt vorbereiten.",
                    },
                    "channel_plan": [
                        {"channel": "search", "share_pct": 40.0},
                    ],
                    "guardrail_report": {
                        "passed": True,
                    },
                },
            ),
            include_preview=True,
        )

        self.assertIsNone(response["confidence"])
        self.assertEqual(response["signal_score"], 67.0)
        self.assertEqual(response["priority_score"], 92.0)
        self.assertEqual(response["field_contracts"]["signal_score"]["semantics"], "ranking_signal")
        self.assertEqual(response["field_contracts"]["priority_score"]["semantics"], "activation_priority")

    def test_to_card_response_exposes_neutral_ranking_signal_aliases(self) -> None:
        response = to_card_response(
            _sample_card(
                peix_context={
                    "score": 67.0,
                    "signal_score": 69.0,
                    "impact_probability": 71.0,
                },
                campaign_payload={
                    "peix_context": {
                        "score": 67.0,
                        "signal_score": 69.0,
                        "impact_probability": 71.0,
                    },
                    "message_framework": {
                        "hero_message": "Norddeutschland jetzt vorbereiten.",
                    },
                    "channel_plan": [
                        {"channel": "search", "share_pct": 40.0},
                    ],
                    "guardrail_report": {
                        "passed": True,
                    },
                },
            ),
            include_preview=True,
        )

        self.assertEqual(response["ranking_signal_context"], response["peix_context"])
        self.assertEqual(
            response["campaign_payload"]["ranking_signal_context"],
            response["campaign_payload"]["peix_context"],
        )
        self.assertEqual(
            response["campaign_preview"]["ranking_signal_context"],
            response["campaign_preview"]["peix_context"],
        )
        self.assertEqual(response["field_contracts"]["signal_score"]["source"], "RankingSignal")
        self.assertEqual(response["field_contracts"]["impact_probability"]["source"], "RankingSignal")

    def test_to_card_response_uses_neutral_partner_brand_fallback(self) -> None:
        response = to_card_response(
            _sample_card(
                brand=None,
            ),
            include_preview=True,
        )

        self.assertEqual(response["brand"], "Partner Brand")


if __name__ == "__main__":
    unittest.main()
