"""Composed media API router."""

from typing import Any

from fastapi import APIRouter

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


def _to_card_response(opp: dict[str, Any], include_preview: bool = True) -> dict[str, Any]:
    return contract_to_card_response(opp, include_preview=include_preview)


# Keep the old import path stable for tests and any legacy patch targets.
__all__ = ["MarketingOpportunityEngine", "_to_card_response", "router"]
