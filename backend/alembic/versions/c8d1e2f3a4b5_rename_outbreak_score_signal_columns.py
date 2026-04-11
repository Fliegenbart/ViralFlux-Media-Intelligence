"""Rename outbreak score columns to honest signal semantics.

Revision ID: c8d1e2f3a4b5
Revises: b4c6d8e1f2a3
Create Date: 2026-04-11 16:05:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "c8d1e2f3a4b5"
down_revision = "b4c6d8e1f2a3"
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
            "outbreak_scores table is missing; cannot rename signal semantics columns."
        )

    with op.batch_alter_table("outbreak_scores") as batch_op:
        if _column_exists("outbreak_scores", "final_risk_score"):
            batch_op.alter_column(
                "final_risk_score",
                new_column_name="decision_signal_index",
                existing_type=sa.Float(),
                existing_nullable=False,
            )
        if _column_exists("outbreak_scores", "risk_level"):
            batch_op.alter_column(
                "risk_level",
                new_column_name="signal_level",
                existing_type=sa.String(),
                existing_nullable=True,
            )
        if _column_exists("outbreak_scores", "leading_indicator"):
            batch_op.alter_column(
                "leading_indicator",
                new_column_name="signal_source",
                existing_type=sa.String(),
                existing_nullable=True,
            )
        if _column_exists("outbreak_scores", "confidence_level"):
            batch_op.alter_column(
                "confidence_level",
                new_column_name="reliability_label",
                existing_type=sa.String(),
                existing_nullable=True,
            )
        if _column_exists("outbreak_scores", "confidence_numeric"):
            batch_op.alter_column(
                "confidence_numeric",
                new_column_name="reliability_score",
                existing_type=sa.Float(),
                existing_nullable=True,
            )


def downgrade() -> None:
    if not _table_exists("outbreak_scores"):
        raise RuntimeError(
            "outbreak_scores table is missing; cannot restore legacy signal semantics columns."
        )

    with op.batch_alter_table("outbreak_scores") as batch_op:
        if _column_exists("outbreak_scores", "reliability_score"):
            batch_op.alter_column(
                "reliability_score",
                new_column_name="confidence_numeric",
                existing_type=sa.Float(),
                existing_nullable=True,
            )
        if _column_exists("outbreak_scores", "reliability_label"):
            batch_op.alter_column(
                "reliability_label",
                new_column_name="confidence_level",
                existing_type=sa.String(),
                existing_nullable=True,
            )
        if _column_exists("outbreak_scores", "signal_source"):
            batch_op.alter_column(
                "signal_source",
                new_column_name="leading_indicator",
                existing_type=sa.String(),
                existing_nullable=True,
            )
        if _column_exists("outbreak_scores", "signal_level"):
            batch_op.alter_column(
                "signal_level",
                new_column_name="risk_level",
                existing_type=sa.String(),
                existing_nullable=True,
            )
        if _column_exists("outbreak_scores", "decision_signal_index"):
            batch_op.alter_column(
                "decision_signal_index",
                new_column_name="final_risk_score",
                existing_type=sa.Float(),
                existing_nullable=False,
            )
