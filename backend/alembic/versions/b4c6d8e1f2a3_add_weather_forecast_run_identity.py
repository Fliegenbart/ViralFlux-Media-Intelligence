"""Add stable weather forecast run identity columns.

Revision ID: b4c6d8e1f2a3
Revises: e1f4c7b8a9d2
Create Date: 2026-03-26 19:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "b4c6d8e1f2a3"
down_revision = "e1f4c7b8a9d2"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in set(inspect(op.get_bind()).get_table_names())


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return column_name in {item["name"] for item in inspector.get_columns(table_name)}


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return index_name in {item["name"] for item in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if not _table_exists("weather_data"):
        raise RuntimeError("weather_data table is missing; cannot add forecast run identity columns.")

    if not _column_exists("weather_data", "forecast_run_timestamp"):
        op.add_column("weather_data", sa.Column("forecast_run_timestamp", sa.DateTime(), nullable=True))
    if not _column_exists("weather_data", "forecast_run_id"):
        op.add_column("weather_data", sa.Column("forecast_run_id", sa.String(), nullable=True))
    if not _column_exists("weather_data", "forecast_run_identity_source"):
        op.add_column("weather_data", sa.Column("forecast_run_identity_source", sa.String(), nullable=True))
    if not _column_exists("weather_data", "forecast_run_identity_quality"):
        op.add_column("weather_data", sa.Column("forecast_run_identity_quality", sa.String(), nullable=True))

    if not _index_exists("weather_data", "ix_weather_data_forecast_run_timestamp"):
        op.create_index(
            "ix_weather_data_forecast_run_timestamp",
            "weather_data",
            ["forecast_run_timestamp"],
        )
    if not _index_exists("weather_data", "ix_weather_data_forecast_run_id"):
        op.create_index(
            "ix_weather_data_forecast_run_id",
            "weather_data",
            ["forecast_run_id"],
        )


def downgrade() -> None:
    if _index_exists("weather_data", "ix_weather_data_forecast_run_id"):
        op.drop_index("ix_weather_data_forecast_run_id", table_name="weather_data")
    if _index_exists("weather_data", "ix_weather_data_forecast_run_timestamp"):
        op.drop_index("ix_weather_data_forecast_run_timestamp", table_name="weather_data")
    if _column_exists("weather_data", "forecast_run_identity_quality"):
        op.drop_column("weather_data", "forecast_run_identity_quality")
    if _column_exists("weather_data", "forecast_run_identity_source"):
        op.drop_column("weather_data", "forecast_run_identity_source")
    if _column_exists("weather_data", "forecast_run_id"):
        op.drop_column("weather_data", "forecast_run_id")
    if _column_exists("weather_data", "forecast_run_timestamp"):
        op.drop_column("weather_data", "forecast_run_timestamp")
