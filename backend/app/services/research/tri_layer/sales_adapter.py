"""Conservative brand-level sell-out adapter for Tri-Layer research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import pandas as pd
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.services.research.tri_layer.schema import SourceEvidence

SalesConnectionStatus = Literal["connected", "partial", "not_connected"]

ACCEPTED_SELL_OUT_METRICS = {
    "units",
    "revenue",
    "sell_out_units",
    "sell_out_revenue",
}
SELL_OUT_TABLE_CANDIDATES = (
    "outcome_observations",
    "otc_sell_out",
    "otc_sellout",
    "brand_sell_out",
    "brand_sellout",
    "sell_out",
    "sellout",
)

DATE_COLUMNS = ("window_start", "date", "week_start", "datum")
WINDOW_END_COLUMNS = ("window_end", "date", "week_end")
REGION_COLUMNS = ("region_code", "region", "bundesland")
VALUE_COLUMNS = (
    "metric_value",
    "units",
    "sales_units",
    "sell_out_units",
    "revenue",
    "revenue_eur",
    "sell_out_revenue",
)
METRIC_COLUMNS = ("metric_name",)
SOURCE_COLUMNS = ("source_label", "source", "source_system")
BRAND_COLUMNS = ("brand", "brand_id", "client")
PRODUCT_COLUMNS = ("product", "product_name", "sku", "gtin")
OPTIONAL_COLUMNS = (
    "metric_unit",
    "price",
    "promo",
    "distribution",
    "stockout",
    "media_spend",
    "media_spend_eur",
    "channel",
    "holdout_group",
    "budget_isolated",
    "causal_adjusted",
)


@dataclass(frozen=True)
class SalesSourceStatus:
    status: SalesConnectionStatus
    coverage: float | None
    freshness_days: int | None
    reason: str


@dataclass(frozen=True)
class SalesPanel:
    rows: pd.DataFrame
    status: SalesSourceStatus
    budget_isolated: bool
    causal_adjusted: bool
    holdout_validated: bool
    historical_weeks: int
    region_count: int
    known_confounders: list[str]


def _empty_panel(reason: str, status: SalesConnectionStatus = "not_connected") -> SalesPanel:
    return SalesPanel(
        rows=pd.DataFrame(),
        status=SalesSourceStatus(status=status, coverage=None, freshness_days=None, reason=reason),
        budget_isolated=False,
        causal_adjusted=False,
        holdout_validated=False,
        historical_weeks=0,
        region_count=0,
        known_confounders=[],
    )


def _find_column(columns: set[str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _candidate_table(inspector) -> tuple[str | None, set[str]]:
    table_names = set(inspector.get_table_names())
    for table_name in SELL_OUT_TABLE_CANDIDATES:
        if table_name in table_names:
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            return table_name, columns
    return None, set()


def _freshness_days(values: pd.Series, cutoff: date | None) -> int | None:
    if values.empty:
        return None
    parsed = pd.to_datetime(values, errors="coerce")
    parsed = parsed.dropna()
    if parsed.empty:
        return None
    latest = parsed.max().date()
    reference = cutoff or datetime.utcnow().date()
    return max((reference - latest).days, 0)


def _bool_column(df: pd.DataFrame, column: str) -> bool:
    if column not in df.columns or df.empty:
        return False
    values = df[column].dropna()
    if values.empty:
        return False
    return bool(values.astype(bool).all())


def load_sales_panel(
    db: Session,
    brand: str,
    virus_typ: str,
    cutoff: date | None,
) -> SalesPanel:
    """Load normalized brand-level sell-out rows when a real source exists.

    ``virus_typ`` is accepted for future product/pathogen mapping. v0 only
    filters by brand and cutoff because no stable OTC pathogen mapping exists.
    """
    del virus_typ
    inspector = inspect(db.bind)
    table_name, columns = _candidate_table(inspector)
    if table_name is None:
        return _empty_panel("No brand-level sell-out data source connected.")

    date_col = _find_column(columns, DATE_COLUMNS)
    window_end_col = _find_column(columns, WINDOW_END_COLUMNS)
    region_col = _find_column(columns, REGION_COLUMNS)
    value_col = _find_column(columns, VALUE_COLUMNS)
    metric_col = _find_column(columns, METRIC_COLUMNS)
    source_col = _find_column(columns, SOURCE_COLUMNS)
    brand_col = _find_column(columns, BRAND_COLUMNS)
    product_col = _find_column(columns, PRODUCT_COLUMNS)
    missing = [
        name
        for name, value in {
            "date": date_col,
            "region or region_code": region_col,
            "metric_name": metric_col,
            "metric value, units or revenue": value_col,
            "brand/product identifier": brand_col or product_col,
            "source label": source_col,
        }.items()
        if value is None
    ]
    if missing:
        return _empty_panel(
            f"Candidate sell-out table '{table_name}' missing required columns: {', '.join(missing)}.",
            status="partial",
        )

    select_columns = [date_col, region_col, value_col, metric_col, source_col]
    if window_end_col:
        select_columns.append(window_end_col)
    if brand_col:
        select_columns.append(brand_col)
    if product_col:
        select_columns.append(product_col)
    select_columns.extend(column for column in OPTIONAL_COLUMNS if column in columns)
    quoted = ", ".join(f'"{column}"' for column in dict.fromkeys(select_columns))
    where_parts: list[str] = []
    params: dict[str, object] = {}
    if brand_col:
        where_parts.append(f'lower("{brand_col}") = :brand')
        params["brand"] = str(brand or "").strip().lower()
    if cutoff is not None:
        where_parts.append(f'date("{date_col}") <= date(:cutoff)')
        params["cutoff"] = cutoff.isoformat()
    where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
    query = f'SELECT {quoted} FROM "{table_name}"{where_sql}'
    df = pd.DataFrame([dict(row) for row in db.execute(text(query), params).mappings().all()])
    if df.empty:
        return _empty_panel(
            f"Candidate sell-out table '{table_name}' has no rows for brand/cutoff.",
            status="not_connected",
        )

    df["__metric_name"] = df[metric_col].astype(str).str.strip().str.lower()
    df = df.loc[df["__metric_name"].isin(ACCEPTED_SELL_OUT_METRICS)].copy()
    if df.empty:
        return _empty_panel(
            f"Candidate sell-out table '{table_name}' has no accepted sell-out metrics.",
            status="not_connected",
        )

    normalized = pd.DataFrame()
    normalized["window_start"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    normalized["window_end"] = (
        pd.to_datetime(df[window_end_col], errors="coerce").dt.date
        if window_end_col
        else normalized["window_start"]
    )
    normalized["date"] = normalized["window_start"]
    normalized["region_code"] = df[region_col].astype(str).str.upper()
    metric_values = pd.to_numeric(df[value_col], errors="coerce")
    unit_metrics = df["__metric_name"].isin({"units", "sell_out_units"})
    revenue_metrics = df["__metric_name"].isin({"revenue", "sell_out_revenue"})
    normalized["metric_name"] = df["__metric_name"]
    normalized["metric_value"] = metric_values
    normalized["units"] = metric_values.where(unit_metrics)
    normalized["revenue"] = metric_values.where(revenue_metrics)
    normalized["brand"] = df[brand_col].astype(str) if brand_col else str(brand or "")
    normalized["product"] = df[product_col].astype(str) if product_col else None
    normalized["source_label"] = df[source_col].astype(str)
    for column in OPTIONAL_COLUMNS:
        if column in df.columns:
            normalized[column] = df[column]
    normalized = normalized.dropna(subset=["window_start", "region_code", "metric_value"])
    if normalized.empty:
        return _empty_panel(
            f"Candidate sell-out table '{table_name}' has no usable sell-out values after normalization.",
            status="not_connected",
        )

    budget_isolated = _bool_column(normalized, "budget_isolated")
    causal_adjusted = _bool_column(normalized, "causal_adjusted")
    holdout_validated = "holdout_group" in normalized.columns and normalized["holdout_group"].dropna().nunique() >= 2
    known_confounders = [
        column
        for column in ("price", "promo", "distribution", "stockout", "media_spend", "media_spend_eur")
        if column in normalized.columns and normalized[column].notna().any()
    ]
    region_count = int(normalized["region_code"].nunique())
    historical_weeks = int(
        pd.to_datetime(normalized["window_start"], errors="coerce")
        .dropna()
        .dt.to_period("W")
        .nunique()
    )
    coverage = round(min(region_count / 16.0, 1.0), 4)
    return SalesPanel(
        rows=normalized,
        status=SalesSourceStatus(
            status="connected",
            coverage=coverage,
            freshness_days=_freshness_days(normalized["window_end"], cutoff),
            reason=f"Loaded brand-level sell-out data from '{table_name}'.",
        ),
        budget_isolated=budget_isolated,
        causal_adjusted=causal_adjusted,
        holdout_validated=holdout_validated,
        historical_weeks=historical_weeks,
        region_count=region_count,
        known_confounders=known_confounders,
    )


def sales_panel_to_source_evidence(
    panel: SalesPanel,
    *,
    signal: float | None = None,
    reliability: float | None = None,
    oos_lift_predictiveness: float | None = None,
) -> SourceEvidence:
    """Convert a validated sell-out panel into conservative Sales evidence."""
    if panel.status.status != "connected" or panel.rows.empty:
        return SourceEvidence(status="not_connected")
    return SourceEvidence(
        status="connected",
        freshness=None,
        reliability=reliability,
        coverage=panel.status.coverage,
        signal=signal,
        real_sell_out=True,
        historical_weeks=panel.historical_weeks,
        region_count=panel.region_count,
        holdout_validated=panel.holdout_validated,
        budget_isolated=panel.budget_isolated,
        causal_adjusted=panel.causal_adjusted,
        oos_lift_predictiveness=oos_lift_predictiveness,
    )
