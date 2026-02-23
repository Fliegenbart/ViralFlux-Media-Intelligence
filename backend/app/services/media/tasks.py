import logging

from app.core.celery_app import celery_app
from app.db.session import get_db_context
from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="refine_recommendation_ai_task")
def refine_recommendation_ai_task(self, opportunity_id: str):
    """Refine a generated recommendation card via AI in the background."""
    logger.info("Starting AI refinement for recommendation %s", opportunity_id)

    try:
        with get_db_context() as db:
            engine = MarketingOpportunityEngine(db)
            result = engine.regenerate_ai_plan(opportunity_id)

            if "error" in result:
                raise RuntimeError(str(result["error"]))

            return {
                "opportunity_id": opportunity_id,
                "success": True,
                "ai_generation_status": result.get("ai_generation_status"),
                "updated_at": result.get("updated_at"),
            }
    except Exception as exc:
        logger.exception("AI refinement failed for recommendation %s", opportunity_id)
        raise RuntimeError(f"AI refinement failed for {opportunity_id}: {exc}") from exc


@celery_app.task(bind=True, name="generate_weekly_brief_task")
def generate_weekly_brief_task(self):
    """Generiert den woechentlichen Gelo Media Action Brief (PDF).

    Laeuft montags 08:30 via Celery Beat.
    """
    logger.info("Starting weekly brief generation")

    try:
        with get_db_context() as db:
            from app.services.media.weekly_brief_service import WeeklyBriefService

            service = WeeklyBriefService(db)
            result = service.generate()

            logger.info(
                "Weekly brief generated: %s, %d pages",
                result["calendar_week"], result["pages"],
            )
            return {
                "success": True,
                "calendar_week": result["calendar_week"],
                "pages": result["pages"],
            }
    except Exception as exc:
        logger.exception("Weekly brief generation failed")
        raise RuntimeError(f"Weekly brief generation failed: {exc}") from exc


@celery_app.task(bind=True, name="generate_marketing_opportunities_task")
def generate_marketing_opportunities_task(self):
    """Alle Detektoren ausfuehren und Marketing-Opportunities generieren.

    Laeuft taeglich nach der Daten-Ingestion (Celery Beat 06:30),
    damit frische Signale in Opportunities umgewandelt werden.
    """
    logger.info("Starting scheduled marketing opportunity generation")

    try:
        with get_db_context() as db:
            engine = MarketingOpportunityEngine(db)
            result = engine.generate_opportunities()

            new_count = result.get("new_opportunities", 0)
            total = result.get("total", 0)
            logger.info(
                "Marketing opportunity generation complete: %d new, %d total",
                new_count, total,
            )

            return {
                "success": True,
                "new_opportunities": new_count,
                "total": total,
            }
    except Exception as exc:
        logger.exception("Marketing opportunity generation failed")
        raise RuntimeError(f"Marketing opportunity generation failed: {exc}") from exc
