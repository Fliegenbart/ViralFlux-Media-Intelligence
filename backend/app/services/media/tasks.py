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
