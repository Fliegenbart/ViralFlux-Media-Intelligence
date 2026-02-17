from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
from typing import Generator
import logging

from app.core.config import get_settings
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

_RUNTIME_SCHEMA_UPDATES = {
    "wastewater_data": {"available_time": "TIMESTAMP"},
    "wastewater_aggregated": {"available_time": "TIMESTAMP"},
    "are_konsultation": {"available_time": "TIMESTAMP"},
    "survstat_weekly_data": {"available_time": "TIMESTAMP"},
    "google_trends_data": {"available_time": "TIMESTAMP"},
    "weather_data": {"available_time": "TIMESTAMP"},
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
}

_RUNTIME_INDEX_UPDATES = {
    "wastewater_data": [("idx_wastewater_available_time", "available_time")],
    "wastewater_aggregated": [("idx_agg_available_time", "available_time")],
    "are_konsultation": [("idx_are_konsult_available_time", "available_time")],
    "survstat_weekly_data": [("idx_survstat_available_time", "available_time")],
    "google_trends_data": [("idx_trends_available_time", "available_time")],
    "weather_data": [("idx_weather_available_time", "available_time")],
    "ganzimmun_data": [("idx_ganzimmun_available_time", "available_time")],
    "marketing_opportunities": [
        ("idx_marketing_opportunities_brand", "brand"),
        ("idx_marketing_opportunities_product", "product"),
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
    """Initialize database - create all tables."""
    logger.info("Creating database tables...")
    try:
        Base.metadata.create_all(bind=engine)
        _ensure_runtime_schema_updates()
        logger.info("Database tables created successfully.")
    except Exception as e:
        if "already exists" in str(e):
            logger.info("Database tables already exist, skipping creation.")
            _ensure_runtime_schema_updates()
        else:
            raise


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
