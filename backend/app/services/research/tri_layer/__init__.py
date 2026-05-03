"""Research-only Tri-Layer Evidence Fusion v0."""

from app.services.research.tri_layer.schema import (
    BudgetIsolationEvidence,
    SourceEvidence,
    TriLayerRegionEvidence,
    TriLayerRegionSnapshot,
)
from app.services.research.tri_layer.gpu_runtime import resolve_tri_layer_xgboost_config
from app.services.research.tri_layer.sales_adapter import (
    SalesPanel,
    SalesSourceStatus,
    load_sales_panel,
    sales_panel_to_source_evidence,
)
from app.services.research.tri_layer.service import build_region_snapshot
from app.services.research.tri_layer.challenger_models import (
    fit_tri_layer_challenger_models,
    resolve_tri_layer_challenger_xgboost_params,
)

__all__ = [
    "BudgetIsolationEvidence",
    "SourceEvidence",
    "TriLayerRegionEvidence",
    "TriLayerRegionSnapshot",
    "build_region_snapshot",
    "resolve_tri_layer_xgboost_config",
    "resolve_tri_layer_challenger_xgboost_params",
    "fit_tri_layer_challenger_models",
    "SalesPanel",
    "SalesSourceStatus",
    "load_sales_panel",
    "sales_panel_to_source_evidence",
]
