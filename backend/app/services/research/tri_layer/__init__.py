"""Research-only Tri-Layer Evidence Fusion v0."""

from app.services.research.tri_layer.schema import (
    BudgetIsolationEvidence,
    SourceEvidence,
    TriLayerRegionEvidence,
    TriLayerRegionSnapshot,
)
from app.services.research.tri_layer.gpu_runtime import resolve_tri_layer_xgboost_config
from app.services.research.tri_layer.sales_adapter import SalesPanel, SalesSourceStatus, load_sales_panel
from app.services.research.tri_layer.service import build_region_snapshot

__all__ = [
    "BudgetIsolationEvidence",
    "SourceEvidence",
    "TriLayerRegionEvidence",
    "TriLayerRegionSnapshot",
    "build_region_snapshot",
    "resolve_tri_layer_xgboost_config",
    "SalesPanel",
    "SalesSourceStatus",
    "load_sales_panel",
]
