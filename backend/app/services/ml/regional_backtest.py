"""Regional backtest reader for pooled panel forecasting."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.services.ml.regional_panel_utils import BUNDESLAND_NAMES
from app.services.ml.regional_trainer import RegionalModelTrainer, _virus_slug

logger = logging.getLogger(__name__)

_ML_MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "ml_models" / "regional_panel"


class RegionalBacktester:
    """Expose persisted pooled panel backtest results."""

    def __init__(self, db, models_dir: Path | None = None):
        self.db = db
        self.models_dir = models_dir or _ML_MODELS_DIR
        self.trainer = RegionalModelTrainer(db, models_dir=self.models_dir)

    def backtest_region(
        self,
        virus_typ: str = "Influenza A",
        bundesland: str = "BY",
        min_train_days: int = 120,
        step_days: int = 7,
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        del min_train_days, step_days, horizon_days
        backtest = self._load_or_compute_backtest(virus_typ=virus_typ)
        details = (backtest.get("details") or {}).get(bundesland.upper())
        if not details:
            return {
                "bundesland": bundesland.upper(),
                "bundesland_name": BUNDESLAND_NAMES.get(bundesland.upper(), bundesland.upper()),
                "error": "No pooled panel backtest available for this Bundesland.",
            }
        return details

    def backtest_all_regions(
        self,
        virus_typ: str = "Influenza A",
        step_days: int = 7,
        horizon_days: int = 7,
    ) -> dict[str, Any]:
        del step_days, horizon_days
        return self._load_or_compute_backtest(virus_typ=virus_typ)

    def _load_or_compute_backtest(self, virus_typ: str) -> dict[str, Any]:
        payload = self.trainer.load_artifacts(virus_typ=virus_typ)
        if payload.get("backtest"):
            return payload["backtest"]

        logger.info("Regional panel backtest missing for %s, computing transiently.", virus_typ)
        result = self.trainer.train_all_regions(virus_typ=virus_typ, persist=False)
        return result.get("backtest") or {
            "virus_typ": virus_typ,
            "total_regions": 0,
            "backtested": 0,
            "failed": 16,
            "error": result.get("error") or "No pooled panel backtest available.",
            "details": {},
        }
