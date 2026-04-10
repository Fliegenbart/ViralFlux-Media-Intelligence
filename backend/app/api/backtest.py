"""Backtest API router aggregator."""

from fastapi import APIRouter

from .backtest_routes_core import router as core_router
from .backtest_routes_signals import router as signals_router

router = APIRouter()
router.include_router(core_router)
router.include_router(signals_router)

__all__ = ["router"]
