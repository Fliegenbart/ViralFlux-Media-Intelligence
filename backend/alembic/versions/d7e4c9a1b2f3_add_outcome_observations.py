"""Add generic outcome_observations table for optional truth-layer ingestion.

Revision ID: d7e4c9a1b2f3
Revises: c3f2a1b4d5e6
Create Date: 2026-03-16 18:25:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "d7e4c9a1b2f3"
down_revision = "c3f2a1b4d5e6"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in set(inspect(op.get_bind()).get_table_names())


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return index_name in {item["name"] for item in inspector.get_indexes(table_name)}


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    if not _table_exists("outcome_observations"):
        op.create_table(
            "outcome_observations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("brand", sa.String(), nullable=False, server_default="gelo"),
            sa.Column("product", sa.String(), nullable=False),
            sa.Column("region_code", sa.String(), nullable=False),
            sa.Column("window_start", sa.DateTime(), nullable=False),
            sa.Column("window_end", sa.DateTime(), nullable=False),
            sa.Column("metric_name", sa.String(), nullable=False),
            sa.Column("metric_value", sa.Float(), nullable=False),
            sa.Column("metric_unit", sa.String(), nullable=True),
            sa.Column("source_label", sa.String(), nullable=False, server_default="manual"),
            sa.Column("channel", sa.String(), nullable=True),
            sa.Column("campaign_id", sa.String(), nullable=True),
            sa.Column("holdout_group", sa.String(), nullable=True),
            sa.Column("confidence_hint", sa.Float(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "window_start",
                "window_end",
                "brand",
                "product",
                "region_code",
                "metric_name",
                "source_label",
                name="uq_outcome_observation",
            ),
        )
    _create_index_if_missing("ix_outcome_observations_id", "outcome_observations", ["id"])
    _create_index_if_missing("ix_outcome_observations_brand", "outcome_observations", ["brand"])
    _create_index_if_missing("ix_outcome_observations_product", "outcome_observations", ["product"])
    _create_index_if_missing("ix_outcome_observations_region_code", "outcome_observations", ["region_code"])
    _create_index_if_missing("ix_outcome_observations_window_start", "outcome_observations", ["window_start"])
    _create_index_if_missing("ix_outcome_observations_window_end", "outcome_observations", ["window_end"])
    _create_index_if_missing("ix_outcome_observations_metric_name", "outcome_observations", ["metric_name"])
    _create_index_if_missing("ix_outcome_observations_source_label", "outcome_observations", ["source_label"])
    _create_index_if_missing("ix_outcome_observations_channel", "outcome_observations", ["channel"])
    _create_index_if_missing("ix_outcome_observations_campaign_id", "outcome_observations", ["campaign_id"])
    _create_index_if_missing("ix_outcome_observations_holdout_group", "outcome_observations", ["holdout_group"])
    _create_index_if_missing("ix_outcome_observations_created_at", "outcome_observations", ["created_at"])
    _create_index_if_missing("ix_outcome_observations_updated_at", "outcome_observations", ["updated_at"])
    _create_index_if_missing("idx_outcome_obs_brand_window", "outcome_observations", ["brand", "window_start"])
    _create_index_if_missing("idx_outcome_obs_metric_window", "outcome_observations", ["metric_name", "window_start"])
    _create_index_if_missing("idx_outcome_obs_region_product", "outcome_observations", ["region_code", "product"])


def downgrade() -> None:
    op.drop_index("idx_outcome_obs_region_product", table_name="outcome_observations")
    op.drop_index("idx_outcome_obs_metric_window", table_name="outcome_observations")
    op.drop_index("idx_outcome_obs_brand_window", table_name="outcome_observations")
    op.drop_index("ix_outcome_observations_updated_at", table_name="outcome_observations")
    op.drop_index("ix_outcome_observations_created_at", table_name="outcome_observations")
    op.drop_index("ix_outcome_observations_holdout_group", table_name="outcome_observations")
    op.drop_index("ix_outcome_observations_campaign_id", table_name="outcome_observations")
    op.drop_index("ix_outcome_observations_channel", table_name="outcome_observations")
    op.drop_index("ix_outcome_observations_source_label", table_name="outcome_observations")
    op.drop_index("ix_outcome_observations_metric_name", table_name="outcome_observations")
    op.drop_index("ix_outcome_observations_window_end", table_name="outcome_observations")
    op.drop_index("ix_outcome_observations_window_start", table_name="outcome_observations")
    op.drop_index("ix_outcome_observations_region_code", table_name="outcome_observations")
    op.drop_index("ix_outcome_observations_product", table_name="outcome_observations")
    op.drop_index("ix_outcome_observations_brand", table_name="outcome_observations")
    op.drop_index("ix_outcome_observations_id", table_name="outcome_observations")
    op.drop_table("outcome_observations")
