"""Composed media API router."""

from typing import Any

from fastapi import APIRouter

from app.api.media_routes_cockpit_backtest import router as cockpit_backtest_router
from app.api.media_routes_cockpit_forecast_vintage import router as cockpit_forecast_vintage_router
from app.api.media_routes_cockpit_impact import router as cockpit_impact_router
from app.api.media_routes_cockpit_media_plan import router as cockpit_media_plan_router
from app.api.media_routes_cockpit_media_spending_truth import router as cockpit_media_spending_truth_router
from app.api.media_routes_cockpit_phase_lead import router as cockpit_phase_lead_router
from app.api.media_routes_cockpit_snapshot import router as cockpit_snapshot_router
from app.api.media_routes_cockpit_tri_layer import router as cockpit_tri_layer_router
from app.api.media_routes_cockpit_truth_scoreboard import router as cockpit_truth_scoreboard_router
from app.api.media_routes_outcomes import router as outcomes_router
from app.api.media_routes_recommendations import router as recommendations_router
from app.api.media_routes_weekly_brief import router as weekly_brief_router
from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine
from app.services.media.recommendation_contracts import (
    to_card_response as contract_to_card_response,
)

router = APIRouter()
router.include_router(weekly_brief_router)
router.include_router(outcomes_router)
router.include_router(recommendations_router)
router.include_router(cockpit_snapshot_router)
router.include_router(cockpit_impact_router)
router.include_router(cockpit_backtest_router)
router.include_router(cockpit_truth_scoreboard_router)
router.include_router(cockpit_forecast_vintage_router)
router.include_router(cockpit_media_plan_router)
router.include_router(cockpit_media_spending_truth_router)
router.include_router(cockpit_phase_lead_router)
router.include_router(cockpit_tri_layer_router)


def _to_card_response(opp: dict[str, Any], include_preview: bool = True) -> dict[str, Any]:
    return contract_to_card_response(opp, include_preview=include_preview)


# Keep the old import path stable for tests and any legacy patch targets.
__all__ = ["MarketingOpportunityEngine", "_to_card_response", "router"]
