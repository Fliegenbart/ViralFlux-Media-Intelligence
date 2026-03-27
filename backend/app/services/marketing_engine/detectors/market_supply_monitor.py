"""MarketSupplyMonitor — BfArM supply gaps × Supply-Gap Matrix → priority multipliers.

Watches official BfArM drug shortage notices ("Lieferengpass-Meldungen") and
matches them against a curated mapping of which Gelo OTC products can be
highlighted as *available alternatives* during a supply gap.

The output is a modifier signal (priority_multiplier). Downstream, the
opportunity engine can use it to increase visibility for suitable products
when availability is constrained, without "attack" or "conquest" framing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .base_detector import OpportunityDetector

logger = logging.getLogger(__name__)

_UMLAUT_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _normalize(text: str) -> str:
    """Lowercase + flatten German umlauts for matching."""
    return text.lower().translate(_UMLAUT_MAP)

# Load supply-gap mapping at module level (immutable config)
_MATRIX_PATH = Path(__file__).resolve().parent.parent / "supply_gap_opportunity_matrix.json"


def _load_matrix() -> list[dict[str, Any]]:
    """Load and validate supply_gap_opportunity_matrix.json."""
    try:
        with open(_MATRIX_PATH, encoding="utf-8") as f:
            data = json.load(f)
        products = data.get("products", [])
        logger.info("Supply-gap matrix loaded: %d products", len(products))
        return products
    except FileNotFoundError:
        logger.warning("supply_gap_opportunity_matrix.json not found at %s", _MATRIX_PATH)
        return []
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("Failed to parse supply_gap_opportunity_matrix.json: %s", exc)
        return []


SUPPLY_GAP_PRODUCTS = _load_matrix()


class MarketSupplyMonitor(OpportunityDetector):
    """Detects supply-gap modifier signals from BfArM drug shortages.

    For each product in the supply-gap matrix, checks if any active BfArM
    shortage matches its configured active ingredients or dosage forms.
    If so, generates a modifier opportunity with the product's
    priority_multiplier.
    """

    OPPORTUNITY_TYPE = "MARKET_SUPPLY_GAP"

    def detect(self) -> list[dict]:
        """Match BfArM shortages against the supply-gap matrix."""
        try:
            from app.api.drug_shortage import _ensure_analyzer
            _analyzer = _ensure_analyzer()
        except ImportError:
            logger.warning("drug_shortage module not available")
            _analyzer = None

        if _analyzer is None or _analyzer.df_filtered is None or _analyzer.df_filtered.empty:
            logger.info("No BfArM data loaded — MarketSupplyMonitor skipped")
            return []

        if not SUPPLY_GAP_PRODUCTS:
            logger.info("Supply-gap matrix empty — MarketSupplyMonitor skipped")
            return []

        df = _analyzer.df_filtered
        signals = _analyzer.get_infection_signals()
        wave_type = signals.get("wave_type", "None")
        risk_score = signals.get("current_risk_score", 0)
        pediatric_alert = signals.get("pediatric_alert", False)

        opportunities: list[dict] = []

        for product_cfg in SUPPLY_GAP_PRODUCTS:
            supply_gap = product_cfg.get("supply_gap", {})
            match_active_ingredients = [
                _normalize(i) for i in supply_gap.get("match_active_ingredients", [])
            ]
            match_dosage_forms = [_normalize(f) for f in supply_gap.get("match_dosage_forms", [])]
            priority_multiplier = float(supply_gap.get("priority_multiplier", 1.0))

            if not match_active_ingredients and not match_dosage_forms:
                continue

            # Find matching shortages: ingredient OR form match on high-demand entries
            matched_products: list[str] = []
            matched_count = 0

            for _, row in df.iterrows():
                active_ingredients = _normalize(str(row.get("Wirkstoffe", "")))
                dosage_form = _normalize(str(row.get("Darreichungsform", "")))
                drug_name = str(row.get("Arzneimittlbezeichnung", ""))
                signal_type = str(row.get("signal_type", ""))

                # Only match demand-driven shortages (not pure supply shocks)
                ingredient_hit = any(ing in active_ingredients for ing in match_active_ingredients)
                form_hit = any(frm in dosage_form for frm in match_dosage_forms)

                if ingredient_hit and (form_hit or not match_dosage_forms):
                    matched_count += 1
                    if len(matched_products) < 5:
                        matched_products.append(drug_name)

            if matched_count == 0:
                continue

            # Calculate urgency: base from risk_score, boosted by match density
            urgency = self.calculate_urgency({
                "risk_score": risk_score,
                "matched_count": matched_count,
                "pediatric_alert": pediatric_alert,
                "signal_type": "High_Infection_Signal",
            })

            sku = product_cfg.get("sku", "UNKNOWN")
            condition = product_cfg.get("condition", "erkaltung_akut")

            opp: dict[str, Any] = {
                "id": self._generate_id(f"{sku}-{matched_count}"),
                "type": self.OPPORTUNITY_TYPE,
                "status": "NEW" if urgency < 90 else "URGENT",
                "urgency_score": urgency,
                "region_target": {
                    "country": "DE",
                    "states": [],
                    "plz_cluster": "ALL",
                },
                "trigger_context": {
                    "source": "BFARM_SUPPLY_GAP",
                    "event": f"MARKET_SUPPLY_GAP_{sku}",
                    "details": (
                        f"{matched_count} BfArM shortage notices match {product_cfg.get('name', sku)}. "
                        f"Wave: {wave_type}. "
                        f"Affected: {', '.join(matched_products[:3])}"
                    ),
                    "detected_at": datetime.now().strftime("%Y-%m-%d"),
                },
                "target_audience": ["Erwachsene", "Apotheken-nahe Zielgruppen"],
                # Internal fields for downstream fusion
                "_condition": condition,
                "_supply_gap_sku": sku,
                "_supply_gap_product": product_cfg.get("name", sku),
                "_priority_multiplier": priority_multiplier,
                "_matched_count": matched_count,
                "_matched_products": matched_products,
                "_wave_type": wave_type,
                "_pediatric_alert": pediatric_alert,
            }

            if pediatric_alert:
                opp["target_audience"].insert(0, "Eltern")

            opportunities.append(opp)
            logger.info(
                "Supply-gap signal: %s → %d matches, priority_multiplier=%.2fx, urgency=%.0f",
                sku, matched_count, priority_multiplier, urgency,
            )

        return opportunities

    def calculate_urgency(self, context: dict) -> float:
        """Urgency based on BfArM risk_score + match density + pediatric bonus."""
        base = float(context.get("risk_score", 0))
        matched = context.get("matched_count", 0)

        # More matches → higher urgency (capped)
        if matched >= 10:
            base = min(100, base + 15)
        elif matched >= 5:
            base = min(100, base + 10)
        elif matched >= 2:
            base = min(100, base + 5)

        if context.get("pediatric_alert"):
            base = min(100, base + 10)

        return float(max(0, min(100, base)))
