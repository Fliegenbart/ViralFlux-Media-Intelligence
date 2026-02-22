"""CompetitorShortageDetector — BfArM-Engpässe × Conquesting Matrix → Bid-Multiplier Opportunities.

Matches active drug shortages (BfArM Lieferengpass-Meldungen) against the
Conquesting Matrix to identify when competitor products are unavailable.
Outputs a bid_multiplier (e.g. 1.5x) that the Opportunity Fusion Engine
uses to amplify programmatic bids for our own OTC products.

Unlike the legacy ResourceScarcityDetector (which emits blocking/scarcity
signals), this detector is *offensive*: it finds specific competitor SKUs
that are in shortage and maps them to our products that can conquest.
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

# Load conquesting matrix at module level (immutable config)
_MATRIX_PATH = Path(__file__).resolve().parent.parent / "conquesting_matrix.json"


def _load_matrix() -> list[dict[str, Any]]:
    """Load and validate conquesting_matrix.json."""
    try:
        with open(_MATRIX_PATH, encoding="utf-8") as f:
            data = json.load(f)
        products = data.get("products", [])
        logger.info("Conquesting matrix loaded: %d products", len(products))
        return products
    except FileNotFoundError:
        logger.warning("conquesting_matrix.json not found at %s", _MATRIX_PATH)
        return []
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("Failed to parse conquesting_matrix.json: %s", exc)
        return []


CONQUESTING_PRODUCTS = _load_matrix()


class CompetitorShortageDetector(OpportunityDetector):
    """Detects conquesting opportunities from BfArM drug shortages.

    For each product in the Conquesting Matrix, checks if any active BfArM
    shortage matches its target_ingredients or target_forms. If so, generates
    an opportunity with the product's bid_multiplier.
    """

    OPPORTUNITY_TYPE = "COMPETITOR_SHORTAGE"

    def detect(self) -> list[dict]:
        """Match BfArM shortages against Conquesting Matrix."""
        _analyzer = None
        try:
            import app.api.drug_shortage as ds_module
            _analyzer = ds_module._analyzer
        except ImportError:
            logger.warning("drug_shortage module not available")

        # If no data in singleton, try auto-pull from BfArM
        if _analyzer is None or _analyzer.df_filtered is None or _analyzer.df_filtered.empty:
            try:
                from app.services.data_ingest.bfarm_service import BfarmIngestionService
                logger.info("BfArM cache miss in detector — triggering auto-pull")
                result = BfarmIngestionService().run_full_import()
                if result.get("success"):
                    import app.api.drug_shortage as ds_module
                    _analyzer = ds_module._analyzer
            except Exception as exc:
                logger.warning("BfArM auto-pull failed: %s", exc)

        if _analyzer is None or _analyzer.df_filtered is None or _analyzer.df_filtered.empty:
            logger.info("No BfArM data loaded — CompetitorShortageDetector skipped")
            return []

        if not CONQUESTING_PRODUCTS:
            logger.info("Conquesting matrix empty — CompetitorShortageDetector skipped")
            return []

        df = _analyzer.df_filtered
        signals = _analyzer.get_infection_signals()
        wave_type = signals.get("wave_type", "None")
        risk_score = signals.get("current_risk_score", 0)
        pediatric_alert = signals.get("pediatric_alert", False)

        opportunities: list[dict] = []

        for product_cfg in CONQUESTING_PRODUCTS:
            conquesting = product_cfg.get("conquesting", {})
            target_ingredients = [_normalize(i) for i in conquesting.get("target_ingredients", [])]
            target_forms = [_normalize(f) for f in conquesting.get("target_forms", [])]
            bid_multiplier = float(conquesting.get("bid_multiplier", 1.5))

            if not target_ingredients and not target_forms:
                continue

            # Find matching shortages: ingredient OR form match on high-demand entries
            matched_drugs: list[str] = []
            matched_count = 0

            for _, row in df.iterrows():
                wirkstoffe = _normalize(str(row.get("Wirkstoffe", "")))
                darreichung = _normalize(str(row.get("Darreichungsform", "")))
                drug_name = str(row.get("Arzneimittlbezeichnung", ""))
                signal_type = str(row.get("signal_type", ""))

                # Only match demand-driven shortages (not pure supply shocks)
                ingredient_hit = any(ing in wirkstoffe for ing in target_ingredients)
                form_hit = any(frm in darreichung for frm in target_forms)

                if ingredient_hit and (form_hit or not target_forms):
                    matched_count += 1
                    if len(matched_drugs) < 5:
                        matched_drugs.append(drug_name)

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
                    "source": "BfArM_Conquesting",
                    "event": f"COMPETITOR_SHORTAGE_{sku}",
                    "details": (
                        f"{matched_count} competitor shortages match {product_cfg.get('name', sku)}. "
                        f"Wave: {wave_type}. "
                        f"Affected: {', '.join(matched_drugs[:3])}"
                    ),
                    "detected_at": datetime.now().strftime("%Y-%m-%d"),
                },
                "target_audience": ["Erwachsene", "Apotheken-nahe Zielgruppen"],
                # Internal fields for downstream fusion
                "_condition": condition,
                "_conquesting_sku": sku,
                "_conquesting_product": product_cfg.get("name", sku),
                "_bid_multiplier": bid_multiplier,
                "_matched_count": matched_count,
                "_matched_drugs": matched_drugs,
                "_wave_type": wave_type,
                "_pediatric_alert": pediatric_alert,
            }

            if pediatric_alert:
                opp["target_audience"].insert(0, "Eltern")

            opportunities.append(opp)
            logger.info(
                "Conquesting opportunity: %s → %d matches, bid_multiplier=%.1fx, urgency=%.0f",
                sku, matched_count, bid_multiplier, urgency,
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
