import logging

from app.core.celery_app import celery_app
from app.core.config import get_settings
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
    """Generiert den wöchentlichen Media Action Brief (PDF).

    Läuft montags 08:30 via Celery Beat.
    """
    brand = get_settings().NORMALIZED_OPERATIONAL_DEFAULT_BRAND
    logger.info("Starting weekly brief generation for brand=%s", brand)

    try:
        with get_db_context() as db:
            from app.services.media.weekly_brief_service import WeeklyBriefService

            service = WeeklyBriefService(db)
            result = service.generate(brand=brand)

            logger.info(
                "Weekly brief generated: %s, %d pages",
                result["calendar_week"], result["pages"],
            )
            return {
                "success": True,
                "brand": brand,
                "calendar_week": result["calendar_week"],
                "pages": result["pages"],
            }
    except Exception as exc:
        logger.exception("Weekly brief generation failed")
        raise RuntimeError(f"Weekly brief generation failed: {exc}") from exc


@celery_app.task(bind=True, name="generate_marketing_opportunities_task")
def generate_marketing_opportunities_task(self):
    """Alle Detektoren ausführen und Marketing-Opportunities generieren.

    Läuft täglich nach der Daten-Ingestion (Celery Beat 06:30),
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


@celery_app.task(bind=True, name="materialize_virus_wave_truth_task")
def materialize_virus_wave_truth_task(
    self,
    virus_types: list[str] | None = None,
    region: str = "DE",
    lookback_weeks: int = 156,
):
    """Manually materialize virusWaveTruth/evidence v1.1 snapshots."""
    logger.info(
        "Starting virus wave truth materialization for region=%s virus_types=%s",
        region,
        virus_types or "default",
    )
    try:
        with get_db_context() as db:
            from app.services.media.cockpit.virus_wave_materialization import materialize_all_virus_wave_truth

            return materialize_all_virus_wave_truth(
                db,
                virus_types=virus_types,
                region=region,
                lookback_weeks=int(lookback_weeks),
            )
    except Exception as exc:
        logger.exception("Virus wave truth materialization failed")
        raise RuntimeError(f"Virus wave truth materialization failed: {exc}") from exc


@celery_app.task(bind=True, name="run_virus_wave_backtest_task")
def run_virus_wave_backtest_task(
    self,
    virus_types: list[str] | None = None,
    region: str = "DE",
    lookback_weeks: int = 156,
    mode: str = "historical_cutoff",
    seasonal_windows: bool = True,
    scope_mode: str = "canonical",
):
    """Manually run research-only virusWaveTruth/evidence v1.7 backtests."""
    logger.info(
        "Starting virus wave backtest for region=%s mode=%s scope_mode=%s virus_types=%s",
        region,
        mode,
        scope_mode,
        virus_types or "default",
    )
    try:
        with get_db_context() as db:
            from app.services.media.cockpit.virus_wave_backtest import run_all_virus_wave_backtests

            return run_all_virus_wave_backtests(
                db,
                virus_types=virus_types,
                region=region,
                lookback_weeks=int(lookback_weeks),
                mode=mode,
                seasonal_windows=bool(seasonal_windows),
                scope_mode=scope_mode,
            )
    except Exception as exc:
        logger.exception("Virus wave backtest failed")
        raise RuntimeError(f"Virus wave backtest failed: {exc}") from exc


@celery_app.task(bind=True, name="generate_virus_wave_backtest_report_task")
def generate_virus_wave_backtest_report_task(
    self,
    mode: str = "historical_cutoff",
    scope_mode: str | None = "canonical",
    output_path: str | None = None,
):
    """Generate the research-only v1.7 backtest evaluation report."""
    logger.info("Starting virus wave backtest evaluation report for mode=%s scope_mode=%s", mode, scope_mode)
    try:
        with get_db_context() as db:
            from app.services.media.cockpit.virus_wave_backtest_report import (
                DEFAULT_REPORT_PATH,
                write_virus_wave_backtest_evaluation_report,
            )

            return write_virus_wave_backtest_evaluation_report(
                db,
                mode=mode,
                scope_mode=scope_mode,
                output_path=output_path or DEFAULT_REPORT_PATH,
            )
    except Exception as exc:
        logger.exception("Virus wave backtest evaluation report failed")
        raise RuntimeError(f"Virus wave backtest evaluation report failed: {exc}") from exc
