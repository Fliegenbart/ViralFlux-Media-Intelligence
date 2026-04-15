from __future__ import annotations

from typing import Any

from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session


ML_FORECAST_REGION_SCOPE_MIGRATION = "f1a2b3c4d5e6"
OUTBREAK_SCORE_PRIORITY_INDEX_MIGRATION = "d9e8f7a6b5c4"
MEDIA_OUTCOME_BATCH_INGESTION_FIELDS_MIGRATION = "e1f4c7b8a9d2"

_REQUIRED_SCHEMA_CONTRACTS: dict[str, dict[str, Any]] = {
    "ml_forecasts": {
        "migration_revision": ML_FORECAST_REGION_SCOPE_MIGRATION,
        "columns": ("region", "horizon_days"),
        "indexes": (
            "ix_ml_forecasts_region",
            "ix_ml_forecasts_horizon_days",
            "idx_forecast_scope_date",
            "idx_forecast_scope_created",
        ),
    },
    "outbreak_scores": {
        "migration_revision": OUTBREAK_SCORE_PRIORITY_INDEX_MIGRATION,
        "columns": (
            "decision_priority_index",
            "signal_level",
            "signal_source",
            "reliability_label",
            "reliability_score",
        ),
        "indexes": (
            "idx_outbreak_date_virus",
        ),
    },
    "media_outcome_import_batches": {
        "migration_revision": MEDIA_OUTCOME_BATCH_INGESTION_FIELDS_MIGRATION,
        "columns": (
            "source_system",
            "external_batch_id",
            "ingestion_mode",
        ),
        "indexes": (
            "ix_media_outcome_import_batches_source_system",
            "ix_media_outcome_import_batches_external_batch_id",
            "ix_media_outcome_import_batches_ingestion_mode",
        ),
    },
}

_ML_FORECAST_RUNTIME_COLUMNS: tuple[str, ...] = (
    "trend_momentum_7d",
    "outbreak_risk_score",
)


class SchemaContractMismatchError(RuntimeError):
    """Raised when the live database schema no longer matches the runtime contract."""


class MLForecastSchemaMismatchError(SchemaContractMismatchError):
    """Raised when ml_forecasts misses region/horizon scope fields or indexes."""


class OutbreakScoreSchemaMismatchError(SchemaContractMismatchError):
    """Raised when outbreak_scores is missing the required signal semantics contract."""


def _resolve_bind(bind: Session | Engine | Connection) -> Engine | Connection:
    if isinstance(bind, Session):
        resolved = bind.get_bind()
        if resolved is None:
            raise RuntimeError("Session has no active bind for schema inspection.")
        return resolved
    return bind


def get_required_schema_contract_gaps(
    bind: Session | Engine | Connection,
) -> dict[str, list[str]]:
    inspector = inspect(_resolve_bind(bind))
    existing_tables = set(inspector.get_table_names())

    missing_tables: list[str] = []
    missing_columns: list[str] = []
    missing_indexes: list[str] = []

    for table_name, contract in _REQUIRED_SCHEMA_CONTRACTS.items():
        if table_name not in existing_tables:
            missing_tables.append(table_name)
            continue

        existing_columns = {item["name"] for item in inspector.get_columns(table_name)}
        for column_name in contract.get("columns", ()):
            if column_name not in existing_columns:
                missing_columns.append(f"{table_name}.{column_name}")

        existing_index_names = {item["name"] for item in inspector.get_indexes(table_name)}
        for index_name in contract.get("indexes", ()):
            if index_name not in existing_index_names:
                missing_indexes.append(f"{table_name}.{index_name}")

    return {
        "missing_tables": sorted(set(missing_tables)),
        "missing_columns": sorted(set(missing_columns)),
        "missing_indexes": sorted(set(missing_indexes)),
    }


def get_ml_forecast_schema_gaps(
    bind: Session | Engine | Connection,
) -> dict[str, list[str]]:
    gaps = get_required_schema_contract_gaps(bind)
    inspector = inspect(_resolve_bind(bind))
    existing_tables = set(inspector.get_table_names())
    runtime_missing_columns: list[str] = []
    if "ml_forecasts" in existing_tables:
        existing_columns = {item["name"] for item in inspector.get_columns("ml_forecasts")}
        for column_name in _ML_FORECAST_RUNTIME_COLUMNS:
            if column_name not in existing_columns:
                runtime_missing_columns.append(f"ml_forecasts.{column_name}")
    return {
        "missing_tables": [
            item for item in gaps["missing_tables"] if item == "ml_forecasts"
        ],
        "missing_columns": [
            item for item in gaps["missing_columns"] if item.startswith("ml_forecasts.")
        ] + sorted(set(runtime_missing_columns)),
        "missing_indexes": [
            item for item in gaps["missing_indexes"] if item.startswith("ml_forecasts.")
        ],
    }


def ensure_ml_forecast_schema_aligned(
    bind: Session | Engine | Connection,
) -> None:
    gaps = get_ml_forecast_schema_gaps(bind)
    if not any(gaps.values()):
        return

    parts: list[str] = [
        "MLForecast schema mismatch detected.",
        (
            f"Apply Alembic migration {ML_FORECAST_REGION_SCOPE_MIGRATION} "
            "or upgrade the database to head."
        ),
    ]
    if gaps["missing_tables"]:
        parts.append("Missing tables: " + ", ".join(gaps["missing_tables"]))
    if gaps["missing_columns"]:
        parts.append("Missing columns: " + ", ".join(gaps["missing_columns"]))
    if gaps["missing_indexes"]:
        parts.append("Missing indexes: " + ", ".join(gaps["missing_indexes"]))

    raise MLForecastSchemaMismatchError(" ".join(parts))


def ensure_outbreak_score_schema_aligned(
    bind: Session | Engine | Connection,
) -> None:
    gaps = get_required_schema_contract_gaps(bind)
    outbreak_gaps = {
        "missing_tables": [
            item for item in gaps["missing_tables"] if item == "outbreak_scores"
        ],
        "missing_columns": [
            item for item in gaps["missing_columns"] if item.startswith("outbreak_scores.")
        ],
        "missing_indexes": [
            item for item in gaps["missing_indexes"] if item.startswith("outbreak_scores.")
        ],
    }
    if not any(outbreak_gaps.values()):
        return

    parts: list[str] = [
        "OutbreakScore schema mismatch detected.",
        (
            f"Apply Alembic migration {OUTBREAK_SCORE_PRIORITY_INDEX_MIGRATION} "
            "or upgrade the database to head."
        ),
    ]
    if outbreak_gaps["missing_tables"]:
        parts.append("Missing tables: " + ", ".join(outbreak_gaps["missing_tables"]))
    if outbreak_gaps["missing_columns"]:
        parts.append("Missing columns: " + ", ".join(outbreak_gaps["missing_columns"]))
    if outbreak_gaps["missing_indexes"]:
        parts.append("Missing indexes: " + ", ".join(outbreak_gaps["missing_indexes"]))

    raise OutbreakScoreSchemaMismatchError(" ".join(parts))
