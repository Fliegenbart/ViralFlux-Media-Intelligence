"""Add region and horizon_days scope columns to ml_forecasts.

Revision ID: f1a2b3c4d5e6
Revises: a9c4e6f1b2d3
Create Date: 2026-03-16 23:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "a9c4e6f1b2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ml_forecasts",
        sa.Column("region", sa.String(), nullable=False, server_default="DE"),
    )
    op.add_column(
        "ml_forecasts",
        sa.Column("horizon_days", sa.Integer(), nullable=False, server_default="7"),
    )

    op.execute("UPDATE ml_forecasts SET region = 'DE' WHERE region IS NULL")
    op.execute("UPDATE ml_forecasts SET horizon_days = 7 WHERE horizon_days IS NULL")

    op.alter_column("ml_forecasts", "region", server_default=None)
    op.alter_column("ml_forecasts", "horizon_days", server_default=None)

    op.create_index("ix_ml_forecasts_region", "ml_forecasts", ["region"])
    op.create_index("ix_ml_forecasts_horizon_days", "ml_forecasts", ["horizon_days"])
    op.drop_index("idx_forecast_date_virus", table_name="ml_forecasts")
    op.create_index(
        "idx_forecast_scope_date",
        "ml_forecasts",
        ["forecast_date", "virus_typ", "region", "horizon_days"],
    )
    op.create_index(
        "idx_forecast_scope_created",
        "ml_forecasts",
        ["virus_typ", "region", "horizon_days", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_forecast_scope_created", table_name="ml_forecasts")
    op.drop_index("idx_forecast_scope_date", table_name="ml_forecasts")
    op.create_index("idx_forecast_date_virus", "ml_forecasts", ["forecast_date", "virus_typ"])
    op.drop_index("ix_ml_forecasts_horizon_days", table_name="ml_forecasts")
    op.drop_index("ix_ml_forecasts_region", table_name="ml_forecasts")
    op.drop_column("ml_forecasts", "horizon_days")
    op.drop_column("ml_forecasts", "region")
