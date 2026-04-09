"""Composed media API router."""

from fastapi import APIRouter

from app.api.media_routes_outcomes import router as outcomes_router
from app.api.media_routes_recommendations import router as recommendations_router
from app.api.media_routes_weekly_brief import router as weekly_brief_router
from app.services.marketing_engine.opportunity_engine import MarketingOpportunityEngine

router = APIRouter()
router.include_router(weekly_brief_router)
router.include_router(outcomes_router)
router.include_router(recommendations_router)

# Keep the old import path stable for tests and any legacy patch targets.
__all__ = ["MarketingOpportunityEngine", "router"]
