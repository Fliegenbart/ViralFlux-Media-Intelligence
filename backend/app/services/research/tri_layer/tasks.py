"""Celery tasks for research-only Tri-Layer Evidence Fusion backtests."""

from __future__ import annotations

import logging

from app.core.celery_app import celery_app
from app.services.research.tri_layer.backtest import (
    TriLayerBacktestConfig,
    run_empty_tri_layer_backtest,
)

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="run_tri_layer_backtest_task")
def run_tri_layer_backtest_task(
    self,
    *,
    virus_typ: str = "Influenza A",
    brand: str = "gelo",
    horizon_days: int = 7,
    start_date: str = "2024-10-01",
    end_date: str = "2026-04-30",
    mode: str = "historical_cutoff",
    include_sales: bool = False,
):
    """Run a research-only TLEF-BICG historical-cutoff backtest.

    v0 intentionally does not trigger training or mutate production state.
    Until a full point-in-time regional panel loader is connected, missing
    source data is represented as an empty blocked report.
    """
    logger.info(
        "Starting Tri-Layer research backtest virus=%s brand=%s horizon=%s include_sales=%s",
        virus_typ,
        brand,
        horizon_days,
        include_sales,
    )
    if include_sales:
        logger.info("Tri-Layer backtest requested include_sales=true; no real sales PIT loader is connected in v0.")
    return run_empty_tri_layer_backtest(
        TriLayerBacktestConfig(
            virus_typ=virus_typ,
            brand=brand,
            horizon_days=int(horizon_days),
            start_date=start_date,
            end_date=end_date,
            mode=mode,
            include_sales=bool(include_sales),
        )
    )
