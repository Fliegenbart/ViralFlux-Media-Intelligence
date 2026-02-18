"""PredictiveSalesSpikeDetector — Sales/Velocity Spike → OTC Aktivierung.

Nutzt den OrderSignalAnalyzer, um Artikel mit stark steigender
Bestellgeschwindigkeit zu identifizieren und die Aktivierung zu priorisieren.
"""

from datetime import datetime
import logging

from .base_detector import OpportunityDetector

logger = logging.getLogger(__name__)

# Artikel-ID → Lesbarer Name + PLZ-Mapping
ARTICLE_DISPLAY = {
    "GeloMyrtol forte": {"short": "GMF", "condition": "bronchitis_husten"},
    "GeloRevoice": {"short": "REV", "condition": "halsschmerz_heiserkeit"},
    "GeloSitin": {"short": "SIT", "condition": "rhinitis_trockene_nase"},
    "GeloVital": {"short": "VIT", "condition": "immun_support"},
    "GeloProsed": {"short": "PRO", "condition": "erkaltung_akut"},
}


def _infer_condition(product_id: str) -> str:
    s = (product_id or "").strip().lower()
    if not s:
        return "erkaltung_akut"
    if "revoice" in s or "t onsil" in s or "tonsil" in s:
        return "halsschmerz_heiserkeit"
    if "sitin" in s or "nase" in s or "rhinitis" in s:
        return "rhinitis_trockene_nase"
    if "myrtol" in s or "muc" in s or "bronch" in s or "husten" in s:
        return "bronchitis_husten"
    if "vital" in s or "immun" in s:
        return "immun_support"
    return "erkaltung_akut"


class PredictiveSalesSpikeDetector(OpportunityDetector):
    """Erkennt bevorstehende Nachfrage-Spitzen aus ERP-Bestelldaten."""

    OPPORTUNITY_TYPE = "PREDICTIVE_SALES_SPIKE"

    def detect(self) -> list[dict]:
        """Prüft Order Velocity für alle Artikel."""
        from app.services.fusion_engine.order_signal_analyzer import OrderSignalAnalyzer

        analyzer = OrderSignalAnalyzer(self.db)
        summary = analyzer.get_summary()

        if not summary or summary.get("total_articles", 0) == 0:
            logger.info("Keine ERP-Bestelldaten — PredictiveSalesSpikeDetector übersprungen")
            return []

        opportunities = []
        articles = summary.get("articles", {})

        for article_id, vel_data in articles.items():
            alert = vel_data.get("alert_level", "green")
            velocity = vel_data.get("velocity", 0.0)

            # Nur red und yellow alerts
            if alert not in ("red", "yellow"):
                continue

            urgency = self.calculate_urgency({
                "velocity": velocity,
                "alert_level": alert,
            })

            display = ARTICLE_DISPLAY.get(article_id, {})
            short_name = display.get("short", article_id[:8])
            condition = display.get("condition") or _infer_condition(article_id)

            current_orders = vel_data.get("current_week_orders", 0)
            previous_orders = vel_data.get("previous_week_orders", 0)

            # PLZ-Cluster aus customer_id ableiten (falls verfügbar)
            plz_cluster = self._extract_plz_cluster(article_id)

            opp = {
                "id": self._generate_id(f"SPIKE-{short_name}"),
                "type": self.OPPORTUNITY_TYPE,
                "status": "URGENT" if alert == "red" else "NEW",
                "urgency_score": urgency,
                "region_target": {
                    "country": "DE",
                    "states": [],
                    "plz_cluster": plz_cluster or "ALL",
                },
                "trigger_context": {
                    "source": "Internal_ERP",
                    "event": "ORDER_VELOCITY_SURGE",
                    "details": (
                        f"Order Velocity für {article_id} ist um "
                        f"{abs(velocity) * 100:.0f}% gestiegen. "
                        f"Diese Woche: {current_orders}, Vorwoche: {previous_orders}."
                    ),
                    "detected_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
                "target_audience": ["Konsumenten (OTC)", "Apotheken-nahe Zielgruppen"],
                "_condition": condition,
                "_article_id": article_id,
                "_velocity": velocity,
                "_current_orders": current_orders,
                "_previous_orders": previous_orders,
            }
            opportunities.append(opp)

        return opportunities

    def _extract_plz_cluster(self, article_id: str) -> str | None:
        """Versucht PLZ-Cluster aus den Bestelldaten abzuleiten."""
        from app.models.database import GanzimmunData
        from datetime import timedelta

        seven_days_ago = datetime.now() - timedelta(days=7)
        recent = (
            self.db.query(GanzimmunData)
            .filter(
                GanzimmunData.test_typ == article_id,
                GanzimmunData.datum >= seven_days_ago,
                GanzimmunData.extra_data.isnot(None),
            )
            .limit(100)
            .all()
        )

        if not recent:
            return None

        # Sammle customer_ids und versuche PLZ-Muster zu erkennen
        customer_ids = [
            str(r.extra_data.get("customer_id", ""))
            for r in recent
            if r.extra_data and r.extra_data.get("customer_id")
        ]

        if not customer_ids:
            return None

        # Versuche PLZ-Prefix zu finden (erste 2 Ziffern)
        plz_prefixes = []
        for cid in customer_ids:
            digits = "".join(c for c in cid if c.isdigit())
            if len(digits) >= 2:
                plz_prefixes.append(digits[:2])

        if plz_prefixes:
            from collections import Counter
            most_common = Counter(plz_prefixes).most_common(1)
            if most_common:
                return f"{most_common[0][0]}xxx"

        return None

    def calculate_urgency(self, context: dict) -> float:
        """Urgency basiert auf Velocity-Anstieg."""
        velocity = abs(context.get("velocity", 0))
        alert = context.get("alert_level", "green")

        if alert == "red":
            return min(100.0, velocity * 100 * 1.4 + 15)
        elif alert == "yellow":
            return min(80.0, velocity * 100 * 1.2 + 10)
        return 0.0
