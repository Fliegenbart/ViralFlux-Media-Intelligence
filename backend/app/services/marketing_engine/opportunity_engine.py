"""MarketingOpportunityEngine — Hauptorchestrator.

Führt alle Detektoren aus, erzeugt Sales Pitches, matcht Produkte,
persistiert Opportunities und liefert CRM-fähiges JSON.
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging

from app.models.database import MarketingOpportunity

from .detectors.resource_scarcity import ResourceScarcityDetector
from .detectors.seasonal_deficiency import SeasonalDeficiencyDetector
from .detectors.predictive_sales_spike import PredictiveSalesSpikeDetector
from .detectors.weather_forecast import WeatherForecastDetector
from .pitch_generator import PitchGenerator
from .product_matcher import ProductMatcher

logger = logging.getLogger(__name__)

SYSTEM_VERSION = "LabPulse-Predictor-v2.1"


class MarketingOpportunityEngine:
    """Orchestriert alle Opportunity-Detektoren und CRM-Output."""

    def __init__(self, db: Session):
        self.db = db
        self.detectors = [
            ResourceScarcityDetector(db),
            SeasonalDeficiencyDetector(db),
            PredictiveSalesSpikeDetector(db),
            WeatherForecastDetector(db),
        ]
        self.pitch_generator = PitchGenerator()
        self.product_matcher = ProductMatcher(db)

    def generate_opportunities(self) -> dict:
        """Alle Detektoren ausführen → Pitches → Products → Persist → JSON."""
        all_opportunities = []

        for detector in self.detectors:
            try:
                raw_opps = detector.detect()
                logger.info(
                    f"{detector.OPPORTUNITY_TYPE}: {len(raw_opps)} Opportunities erkannt"
                )
                for raw in raw_opps:
                    # Sales Pitch generieren
                    raw["sales_pitch"] = self.pitch_generator.generate(
                        raw["type"], raw
                    )
                    # Produkte matchen
                    raw["suggested_products"] = self.product_matcher.match(
                        raw["type"], raw
                    )
                    all_opportunities.append(raw)
            except Exception as e:
                logger.error(f"Detector {detector.OPPORTUNITY_TYPE} fehlgeschlagen: {e}")

        # Nach Urgency sortieren
        all_opportunities.sort(
            key=lambda x: x.get("urgency_score", 0), reverse=True
        )

        # Persistieren (mit Dedup)
        saved = 0
        for opp in all_opportunities:
            if self._save_opportunity(opp):
                saved += 1

        logger.info(
            f"MarketingOpportunityEngine: {len(all_opportunities)} erkannt, "
            f"{saved} neu gespeichert"
        )

        # Interne Felder entfernen für Output
        clean_opps = [self._clean_for_output(o) for o in all_opportunities]

        return {
            "meta": {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "system_version": SYSTEM_VERSION,
                "total_opportunities": len(clean_opps),
                "new_saved": saved,
            },
            "opportunities": clean_opps,
        }

    def get_opportunities(
        self,
        type_filter: str = None,
        status_filter: str = None,
        min_urgency: float = None,
        limit: int = 50,
    ) -> list[dict]:
        """Gespeicherte Opportunities mit Filtern abrufen."""
        query = self.db.query(MarketingOpportunity).order_by(
            MarketingOpportunity.urgency_score.desc()
        )

        if type_filter:
            query = query.filter(MarketingOpportunity.opportunity_type == type_filter)
        if status_filter:
            query = query.filter(MarketingOpportunity.status == status_filter)
        if min_urgency is not None:
            query = query.filter(MarketingOpportunity.urgency_score >= min_urgency)

        results = query.limit(limit).all()
        return [self._model_to_dict(r) for r in results]

    def update_status(self, opportunity_id: str, new_status: str) -> dict:
        """Status einer Opportunity aktualisieren."""
        valid_statuses = {"NEW", "URGENT", "SENT", "CONVERTED", "EXPIRED", "DISMISSED"}
        if new_status not in valid_statuses:
            return {"error": f"Ungültiger Status: {new_status}. Erlaubt: {valid_statuses}"}

        opp = (
            self.db.query(MarketingOpportunity)
            .filter(MarketingOpportunity.opportunity_id == opportunity_id)
            .first()
        )

        if not opp:
            return {"error": f"Opportunity {opportunity_id} nicht gefunden"}

        old_status = opp.status
        opp.status = new_status
        self.db.commit()

        return {
            "opportunity_id": opportunity_id,
            "old_status": old_status,
            "new_status": new_status,
        }

    def export_crm_json(self, opportunity_ids: list[str] = None) -> dict:
        """CRM-Export: Markiert Opportunities als exportiert."""
        query = self.db.query(MarketingOpportunity)

        if opportunity_ids:
            query = query.filter(
                MarketingOpportunity.opportunity_id.in_(opportunity_ids)
            )
        else:
            query = query.filter(
                MarketingOpportunity.status.in_(["NEW", "URGENT"])
            )

        results = query.order_by(
            MarketingOpportunity.urgency_score.desc()
        ).all()

        now = datetime.utcnow()
        for opp in results:
            opp.exported_at = now

        self.db.commit()

        opportunities = [self._model_to_dict(r) for r in results]

        return {
            "meta": {
                "generated_at": now.isoformat() + "Z",
                "system_version": SYSTEM_VERSION,
                "total_opportunities": len(opportunities),
                "exported_at": now.isoformat() + "Z",
            },
            "opportunities": opportunities,
        }

    def get_stats(self) -> dict:
        """Aggregierte Statistiken."""
        total = self.db.query(MarketingOpportunity).count()

        by_type = dict(
            self.db.query(
                MarketingOpportunity.opportunity_type,
                func.count(MarketingOpportunity.id),
            )
            .group_by(MarketingOpportunity.opportunity_type)
            .all()
        )

        by_status = dict(
            self.db.query(
                MarketingOpportunity.status,
                func.count(MarketingOpportunity.id),
            )
            .group_by(MarketingOpportunity.status)
            .all()
        )

        avg_urgency = (
            self.db.query(func.avg(MarketingOpportunity.urgency_score)).scalar()
        )

        recent = (
            self.db.query(MarketingOpportunity)
            .filter(
                MarketingOpportunity.created_at
                >= datetime.utcnow() - timedelta(days=7)
            )
            .count()
        )

        return {
            "total": total,
            "recent_7d": recent,
            "by_type": by_type,
            "by_status": by_status,
            "avg_urgency": round(avg_urgency, 1) if avg_urgency else 0,
        }

    def _save_opportunity(self, opp: dict) -> bool:
        """Opportunity in DB speichern (mit Dedup)."""
        opp_id = opp.get("id", "")

        # Dedup: Gleiche ID am selben Tag?
        existing = (
            self.db.query(MarketingOpportunity)
            .filter(MarketingOpportunity.opportunity_id == opp_id)
            .first()
        )
        if existing:
            # Update urgency + content falls sich was geändert hat
            existing.urgency_score = opp.get("urgency_score", existing.urgency_score)
            existing.sales_pitch = opp.get("sales_pitch", existing.sales_pitch)
            existing.suggested_products = opp.get(
                "suggested_products", existing.suggested_products
            )
            self.db.commit()
            return False

        trigger_ctx = opp.get("trigger_context", {})
        detected_at_str = trigger_ctx.get("detected_at", "")
        try:
            detected_at = datetime.fromisoformat(
                detected_at_str.replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            detected_at = datetime.utcnow()

        entry = MarketingOpportunity(
            opportunity_id=opp_id,
            opportunity_type=opp.get("type", ""),
            status=opp.get("status", "NEW"),
            urgency_score=opp.get("urgency_score", 0),
            region_target=opp.get("region_target"),
            trigger_source=trigger_ctx.get("source"),
            trigger_event=trigger_ctx.get("event"),
            trigger_details=trigger_ctx,
            trigger_detected_at=detected_at,
            target_audience=opp.get("target_audience"),
            sales_pitch=opp.get("sales_pitch"),
            suggested_products=opp.get("suggested_products"),
            expires_at=datetime.utcnow() + timedelta(days=14),
        )
        self.db.add(entry)
        self.db.commit()
        return True

    def _clean_for_output(self, opp: dict) -> dict:
        """Entfernt interne _-Felder für den API-Output."""
        return {k: v for k, v in opp.items() if not k.startswith("_")}

    def _model_to_dict(self, m: MarketingOpportunity) -> dict:
        """Konvertiert DB-Model zu Output-Dict."""
        return {
            "id": m.opportunity_id,
            "type": m.opportunity_type,
            "status": m.status,
            "urgency_score": m.urgency_score,
            "region_target": m.region_target,
            "trigger_context": m.trigger_details or {
                "source": m.trigger_source,
                "event": m.trigger_event,
                "detected_at": (
                    m.trigger_detected_at.isoformat()
                    if m.trigger_detected_at
                    else None
                ),
            },
            "target_audience": m.target_audience,
            "sales_pitch": m.sales_pitch,
            "suggested_products": m.suggested_products,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "expires_at": m.expires_at.isoformat() if m.expires_at else None,
            "exported_at": m.exported_at.isoformat() if m.exported_at else None,
        }
