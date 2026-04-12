"""Rename outbreak decision index to decision priority index.

Revision ID: d9e8f7a6b5c4
Revises: c8d1e2f3a4b5
Create Date: 2026-04-12 10:15:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "d9e8f7a6b5c4"
down_revision = "c8d1e2f3a4b5"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in set(inspect(op.get_bind()).get_table_names())


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return column_name in {item["name"] for item in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _table_exists("outbreak_scores"):
        raise RuntimeError(
            "outbreak_scores table is missing; cannot rename decision index column."
        )

    if not _column_exists("outbreak_scores", "decision_signal_index"):
        return

    with op.batch_alter_table("outbreak_scores") as batch_op:
        batch_op.alter_column(
            "decision_signal_index",
            new_column_name="decision_priority_index",
            existing_type=sa.Float(),
            existing_nullable=False,
        )


def downgrade() -> None:
    if not _table_exists("outbreak_scores"):
        raise RuntimeError(
            "outbreak_scores table is missing; cannot restore decision signal index column."
        )

    if not _column_exists("outbreak_scores", "decision_priority_index"):
        return

    with op.batch_alter_table("outbreak_scores") as batch_op:
        batch_op.alter_column(
            "decision_priority_index",
            new_column_name="decision_signal_index",
            existing_type=sa.Float(),
            existing_nullable=False,
        )
