"""Conservative brand-level sell-out adapter for Tri-Layer research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import pandas as pd
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


SalesConnectionStatus = Literal["connected", "partial", "not_connected"]

SELL_OUT_TABLE_CANDIDATES = (
    "otc_sell_out",
    "otc_sellout",
    "brand_sell_out",
    "brand_sellout",
    "sell_out",
    "sellout",
)

DATE_COLUMNS = ("date", "week_start", "window_start", "datum")
REGION_COLUMNS = ("region_code", "region", "bundesland")
VALUE_COLUMNS = ("units", "sales_units", "revenue", "revenue_eur")
BRAND_COLUMNS = ("brand", "brand_id", "client")
PRODUCT_COLUMNS = ("product", "product_name", "sku", "gtin")
OPTIONAL_COLUMNS = (
    "price",
    "promo",
    "distribution",
    "stockout",
    "media_spend",
    "media_spend_eur",
    "channel",
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
    known_confounders: list[str]


def _empty_panel(reason: str, status: SalesConnectionStatus = "not_connected") -> SalesPanel:
    return SalesPanel(
        rows=pd.DataFrame(),
        status=SalesSourceStatus(status=status, coverage=None, freshness_days=None, reason=reason),
        budget_isolated=False,
        causal_adjusted=False,
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
    region_col = _find_column(columns, REGION_COLUMNS)
    value_col = _find_column(columns, VALUE_COLUMNS)
    brand_col = _find_column(columns, BRAND_COLUMNS)
    product_col = _find_column(columns, PRODUCT_COLUMNS)
    missing = [
        name
        for name, value in {
            "date": date_col,
            "region or region_code": region_col,
            "units or revenue": value_col,
            "brand/product identifier": brand_col or product_col,
        }.items()
        if value is None
    ]
    if missing:
        return _empty_panel(
            f"Candidate sell-out table '{table_name}' missing required columns: {', '.join(missing)}.",
            status="partial",
        )

    select_columns = [date_col, region_col, value_col]
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
            status="partial",
        )

    normalized = pd.DataFrame()
    normalized["date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    normalized["region_code"] = df[region_col].astype(str).str.upper()
    normalized["units"] = pd.to_numeric(df[value_col], errors="coerce") if value_col in {"units", "sales_units"} else None
    normalized["revenue"] = pd.to_numeric(df[value_col], errors="coerce") if value_col in {"revenue", "revenue_eur"} else None
    normalized["brand"] = df[brand_col].astype(str) if brand_col else str(brand or "")
    normalized["product"] = df[product_col].astype(str) if product_col else None
    for column in OPTIONAL_COLUMNS:
        if column in df.columns:
            normalized[column] = df[column]

    budget_isolated = _bool_column(normalized, "budget_isolated")
    causal_adjusted = _bool_column(normalized, "causal_adjusted")
    known_confounders = [
        column
        for column in ("price", "promo", "distribution", "stockout", "media_spend", "media_spend_eur")
        if column in normalized.columns and normalized[column].notna().any()
    ]
    coverage = round(normalized["region_code"].nunique() / max(normalized["region_code"].nunique(), 1), 4)
    return SalesPanel(
        rows=normalized,
        status=SalesSourceStatus(
            status="connected",
            coverage=coverage,
            freshness_days=_freshness_days(normalized["date"], cutoff),
            reason=f"Loaded brand-level sell-out data from '{table_name}'.",
        ),
        budget_isolated=budget_isolated,
        causal_adjusted=causal_adjusted,
        known_confounders=known_confounders,
    )
