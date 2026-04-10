import hashlib
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
from typing import Any, Generator
import logging

from app.core.config import get_settings
from app.db.schema_contracts import get_required_schema_contract_gaps
from app.models.database import Base

logger = logging.getLogger(__name__)
settings = get_settings()

# Database Engine
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=settings.ENVIRONMENT == "development",
)

# Session Factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
_LAST_INIT_SUMMARY: dict[str, Any] = {}

_RUNTIME_SCHEMA_UPDATES = {
    "wastewater_data": {"available_time": "TIMESTAMP"},
    "wastewater_aggregated": {"available_time": "TIMESTAMP"},
    "are_konsultation": {"available_time": "TIMESTAMP"},
    "survstat_weekly_data": {
        "available_time": "TIMESTAMP",
        "disease_cluster": "VARCHAR",
        "age_group": "VARCHAR",
    },
    "google_trends_data": {"available_time": "TIMESTAMP"},
    "weather_data": {
        "available_time": "TIMESTAMP",
        "forecast_run_timestamp": "TIMESTAMP",
        "forecast_run_id": "VARCHAR",
        "forecast_run_identity_source": "VARCHAR",
        "forecast_run_identity_quality": "VARCHAR",
    },
    "ganzimmun_data": {"available_time": "TIMESTAMP"},
    "marketing_opportunities": {
        "brand": "VARCHAR",
        "product": "VARCHAR",
        "budget_shift_pct": "DOUBLE PRECISION",
        "channel_mix": "JSON",
        "activation_start": "TIMESTAMP",
        "activation_end": "TIMESTAMP",
        "recommendation_reason": "VARCHAR",
        "campaign_payload": "JSON",
        "playbook_key": "VARCHAR",
        "strategy_mode": "VARCHAR",
        "updated_at": "TIMESTAMP",
    },
    "brand_products": {
        "extra_data": "JSON",
        "last_seen_at": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
    },
    "product_condition_mapping": {
        "rule_source": "VARCHAR",
        "fit_score": "DOUBLE PRECISION",
        "mapping_reason": "VARCHAR",
        "is_approved": "BOOLEAN",
        "priority": "INTEGER",
        "notes": "VARCHAR",
        "updated_at": "TIMESTAMP",
    },
    "pollen_data": {
        "available_time": "TIMESTAMP",
        "region_code": "VARCHAR",
        "pollen_type": "VARCHAR",
        "pollen_index": "DOUBLE PRECISION",
        "source": "VARCHAR",
    },
}

_RUNTIME_INDEX_UPDATES = {
    "wastewater_data": [("idx_wastewater_available_time", "available_time")],
    "wastewater_aggregated": [("idx_agg_available_time", "available_time")],
    "are_konsultation": [("idx_are_konsult_available_time", "available_time")],
    "survstat_weekly_data": [
        ("idx_survstat_available_time", "available_time"),
        ("idx_survstat_disease_cluster", "disease_cluster"),
    ],
    "google_trends_data": [("idx_trends_available_time", "available_time")],
    "weather_data": [
        ("idx_weather_available_time", "available_time"),
        ("ix_weather_data_forecast_run_timestamp", "forecast_run_timestamp"),
        ("ix_weather_data_forecast_run_id", "forecast_run_id"),
    ],
    "ganzimmun_data": [("idx_ganzimmun_available_time", "available_time")],
    "marketing_opportunities": [
        ("idx_marketing_opportunities_brand", "brand"),
        ("idx_marketing_opportunities_product", "product"),
        ("idx_marketing_opportunities_playbook_key", "playbook_key"),
        ("idx_marketing_opportunities_strategy_mode", "strategy_mode"),
        ("idx_marketing_opportunities_updated_at", "updated_at"),
    ],
    "brand_products": [
        ("idx_brand_products_brand", "brand"),
        ("idx_brand_products_active", "active"),
        ("idx_brand_products_updated_at", "updated_at"),
    ],
    "product_condition_mapping": [
        ("idx_pcm_brand", "brand"),
        ("idx_pcm_condition_key", "condition_key"),
        ("idx_pcm_rule_source", "rule_source"),
        ("idx_pcm_is_approved", "is_approved"),
        ("idx_pcm_updated_at", "updated_at"),
    ],
    "pollen_data": [
        ("idx_pollen_available_time", "available_time"),
        ("idx_pollen_region_code", "region_code"),
        ("idx_pollen_type", "pollen_type"),
    ],
}


def _set_last_init_summary(summary: dict[str, Any]) -> None:
    global _LAST_INIT_SUMMARY
    _LAST_INIT_SUMMARY = dict(summary)


def get_last_init_summary() -> dict[str, Any]:
    return dict(_LAST_INIT_SUMMARY)


def _advisory_lock_key(name: str) -> int:
    digest = hashlib.blake2b(str(name).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


@contextmanager
def try_advisory_lock(name: str) -> Generator[bool, None, None]:
    """Acquire a PostgreSQL advisory lock without blocking forever."""
    lock_name = str(name or "").strip()
    if not lock_name:
        raise ValueError("Advisory lock name must not be empty.")

    lock_key = _advisory_lock_key(lock_name)
    connection = engine.connect()
    acquired = False
    try:
        acquired = bool(
            connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": lock_key},
            ).scalar()
        )
        yield acquired
    finally:
        if acquired:
            try:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": lock_key},
                )
            except Exception as exc:
                logger.warning(
                    "Advisory unlock failed for %s (%s): %s",
                    lock_name,
                    lock_key,
                    exc,
                )
        connection.close()


def _runtime_schema_gaps(existing_tables: set[str] | None = None) -> dict[str, list[str]]:
    try:
        inspector = inspect(engine)
        known_tables = existing_tables or set(inspector.get_table_names())
    except Exception as exc:
        logger.warning(f"Schema-Inspektion fehlgeschlagen, Gaps unbekannt: {exc}")
        return {
            "missing_columns": [],
            "missing_indexes": [],
        }

    missing_columns: list[str] = []
    missing_indexes: list[str] = []

    for table_name, columns in _RUNTIME_SCHEMA_UPDATES.items():
        if table_name not in known_tables:
            continue
        try:
            existing_columns = {
                col["name"] for col in inspector.get_columns(table_name)
            }
        except Exception as exc:
            logger.warning(f"Spalten-Inspektion für {table_name} fehlgeschlagen: {exc}")
            continue
        for col_name in columns:
            if col_name not in existing_columns:
                missing_columns.append(f"{table_name}.{col_name}")

    for table_name, index_defs in _RUNTIME_INDEX_UPDATES.items():
        if table_name not in known_tables:
            continue
        try:
            existing_index_names = {
                item["name"] for item in inspector.get_indexes(table_name)
            }
        except Exception as exc:
            logger.warning(f"Index-Inspektion für {table_name} fehlgeschlagen: {exc}")
            continue
        for index_name, _column_name in index_defs:
            if index_name not in existing_index_names:
                missing_indexes.append(f"{table_name}.{index_name}")

    return {
        "missing_columns": sorted(set(missing_columns)),
        "missing_indexes": sorted(set(missing_indexes)),
    }


def _ensure_runtime_schema_updates():
    """Leichte Runtime-Schema-Updates für fehlende Spalten/Indizes."""
    try:
        existing_tables = set(inspect(engine).get_table_names())
    except Exception as exc:
        logger.warning(f"Schema-Inspektion fehlgeschlagen, Runtime-Updates übersprungen: {exc}")
        return

    failed_columns: list[str] = []

    # Fehlende Spalten ergänzen
    for table_name, columns in _RUNTIME_SCHEMA_UPDATES.items():
        if table_name not in existing_tables:
            continue

        try:
            existing_columns = {
                col["name"] for col in inspect(engine).get_columns(table_name)
            }
        except Exception as exc:
            logger.warning(f"Spalten-Inspektion für {table_name} fehlgeschlagen: {exc}")
            continue

        for col_name, col_type in columns.items():
            if col_name in existing_columns:
                continue
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            f'ALTER TABLE "{table_name}" '
                            f'ADD COLUMN "{col_name}" {col_type}'
                        )
                    )
                logger.info(f"Schema-Update: {table_name}.{col_name} hinzugefügt")
            except Exception as exc:
                msg = str(exc).lower()
                if "already exists" in msg or "duplicate column" in msg:
                    logger.info(
                        f"Schema-Update: {table_name}.{col_name} bereits vorhanden."
                    )
                else:
                    logger.warning(
                        f"Schema-Update fehlgeschlagen für {table_name}.{col_name}: {exc}"
                    )
                    failed_columns.append(f"{table_name}.{col_name}")

            try:
                # Frische Inspektion pro Check, damit keine stale Metadaten verwendet werden.
                refreshed_columns = {
                    col["name"] for col in inspect(engine).get_columns(table_name)
                }
                if col_name not in refreshed_columns:
                    failed_columns.append(f"{table_name}.{col_name}")
            except Exception as exc:
                logger.warning(f"Re-Inspektion für {table_name} fehlgeschlagen: {exc}")
                failed_columns.append(f"{table_name}.{col_name}")

    if failed_columns:
        unique_missing = sorted(set(failed_columns))
        raise RuntimeError(
            "Fehlende DB-Spalten nach Runtime-Update: "
            + ", ".join(unique_missing)
        )

    # Fehlende Indizes ergänzen
    for table_name, index_defs in _RUNTIME_INDEX_UPDATES.items():
        if table_name not in existing_tables:
            continue
        for index_name, column_name in index_defs:
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            f'CREATE INDEX IF NOT EXISTS "{index_name}" '
                            f'ON "{table_name}" ("{column_name}")'
                        )
                    )
            except Exception as exc:
                logger.warning(f"Index-Update fehlgeschlagen für {index_name}: {exc}")


def init_db():
    """Verify startup database state without mutating migration-managed schema."""
    logger.info("Checking database schema bootstrap state...")
    auto_create = settings.EFFECTIVE_DB_AUTO_CREATE_SCHEMA
    allow_runtime_updates = settings.EFFECTIVE_DB_ALLOW_RUNTIME_SCHEMA_UPDATES
    schema_management_mode = "verify_only"
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    expected_tables = set(Base.metadata.tables.keys())
    missing_tables = sorted(expected_tables - existing_tables)
    actions: list[str] = []
    warnings: list[str] = []
    required_schema_gaps = {
        "missing_tables": [],
        "missing_columns": [],
        "missing_indexes": [],
    }

    if allow_runtime_updates:
        warnings.append(
            "DB_ALLOW_RUNTIME_SCHEMA_UPDATES is deprecated and ignored. Startup runs in verify-only mode; apply explicit migrations instead."
        )

    if missing_tables:
        if auto_create:
            Base.metadata.create_all(bind=engine)
            actions.append("create_all")
            existing_tables = set(inspect(engine).get_table_names())
            missing_tables = sorted(expected_tables - existing_tables)
        if missing_tables:
            summary = {
                "status": "critical",
                "message": "Database schema is incomplete and auto-create is disabled.",
                "auto_create_schema": auto_create,
                "runtime_schema_updates_enabled": allow_runtime_updates,
                "schema_management_mode": schema_management_mode,
                "missing_tables": missing_tables,
                "warnings": warnings,
                "actions": actions,
            }
            _set_last_init_summary(summary)
            raise RuntimeError(
                "Fehlende DB-Tabellen ohne Auto-Create: " + ", ".join(missing_tables)
            )

    required_schema_gaps = get_required_schema_contract_gaps(engine)
    if (
        required_schema_gaps["missing_tables"]
        or required_schema_gaps["missing_columns"]
        or required_schema_gaps["missing_indexes"]
    ):
        summary = {
            "status": "critical",
            "message": "Database schema is missing required migration-managed fields.",
            "auto_create_schema": auto_create,
            "runtime_schema_updates_enabled": allow_runtime_updates,
            "schema_management_mode": schema_management_mode,
            "missing_tables": missing_tables,
            "required_schema_gaps": required_schema_gaps,
            "warnings": warnings,
            "actions": actions,
        }
        _set_last_init_summary(summary)
        details = (
            required_schema_gaps["missing_tables"]
            + required_schema_gaps["missing_columns"]
            + required_schema_gaps["missing_indexes"]
        )
        raise RuntimeError(
            "Fehlende Pflicht-Migrationen für DB-Kernschema: " + ", ".join(details)
        )

    gaps = _runtime_schema_gaps(existing_tables)
    if gaps["missing_columns"] or gaps["missing_indexes"]:
        summary = {
            "status": "critical",
            "message": "Database schema has unapplied runtime gaps.",
            "auto_create_schema": auto_create,
            "runtime_schema_updates_enabled": allow_runtime_updates,
            "schema_management_mode": schema_management_mode,
            "missing_tables": missing_tables,
            "required_schema_gaps": required_schema_gaps,
            "runtime_schema_gaps": gaps,
            "warnings": warnings,
            "actions": actions,
        }
        _set_last_init_summary(summary)
        details = gaps["missing_columns"] + gaps["missing_indexes"]
        raise RuntimeError(
            "Fehlende DB-Migrationen/Schema-Gaps: " + ", ".join(details)
        )

    summary = {
        "status": "warning" if warnings else "ok",
        "message": "Database schema verification completed.",
        "auto_create_schema": auto_create,
        "runtime_schema_updates_enabled": allow_runtime_updates,
        "schema_management_mode": schema_management_mode,
        "missing_tables": missing_tables,
        "required_schema_gaps": required_schema_gaps,
        "runtime_schema_gaps": gaps,
        "warnings": warnings,
        "actions": actions,
        "expected_table_count": len(expected_tables),
        "existing_table_count": len(existing_tables),
    }
    _set_last_init_summary(summary)
    logger.info("Database schema verification completed successfully.")
    return summary


def get_db() -> Generator[Session, None, None]:
    """
    Dependency für FastAPI Endpoints.
    
    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """
    Context Manager für Hintergrund-Tasks.
    
    Usage:
        with get_db_context() as db:
            db.query(Model).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        db.close()


async def check_db_connection() -> bool:
    """Check if database connection is healthy."""
    try:
        with get_db_context() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False
