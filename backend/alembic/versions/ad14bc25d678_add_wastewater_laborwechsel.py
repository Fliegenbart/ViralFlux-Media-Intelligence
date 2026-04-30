"""Add AMELAG wastewater laboratory-change quality flag.

Revision ID: ad14bc25d678
Revises: ac13de45fa67
Create Date: 2026-04-30 15:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "ad14bc25d678"
down_revision = "ac13de45fa67"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return column_name in {item["name"] for item in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _column_exists("wastewater_data", "laborwechsel"):
        op.add_column("wastewater_data", sa.Column("laborwechsel", sa.Boolean(), nullable=True))


def downgrade() -> None:
    if _column_exists("wastewater_data", "laborwechsel"):
        op.drop_column("wastewater_data", "laborwechsel")
