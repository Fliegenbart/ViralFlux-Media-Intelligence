"""Add generic outcome_observations table for optional truth-layer ingestion.

Revision ID: d7e4c9a1b2f3
Revises: c3f2a1b4d5e6
Create Date: 2026-03-16 18:25:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "d7e4c9a1b2f3"
down_revision = "c3f2a1b4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    op.create_index("ix_outcome_observations_id", "outcome_observations", ["id"])
    op.create_index("ix_outcome_observations_brand", "outcome_observations", ["brand"])
    op.create_index("ix_outcome_observations_product", "outcome_observations", ["product"])
    op.create_index("ix_outcome_observations_region_code", "outcome_observations", ["region_code"])
    op.create_index("ix_outcome_observations_window_start", "outcome_observations", ["window_start"])
    op.create_index("ix_outcome_observations_window_end", "outcome_observations", ["window_end"])
    op.create_index("ix_outcome_observations_metric_name", "outcome_observations", ["metric_name"])
    op.create_index("ix_outcome_observations_source_label", "outcome_observations", ["source_label"])
    op.create_index("ix_outcome_observations_channel", "outcome_observations", ["channel"])
    op.create_index("ix_outcome_observations_campaign_id", "outcome_observations", ["campaign_id"])
    op.create_index("ix_outcome_observations_holdout_group", "outcome_observations", ["holdout_group"])
    op.create_index("ix_outcome_observations_created_at", "outcome_observations", ["created_at"])
    op.create_index("ix_outcome_observations_updated_at", "outcome_observations", ["updated_at"])
    op.create_index("idx_outcome_obs_brand_window", "outcome_observations", ["brand", "window_start"])
    op.create_index("idx_outcome_obs_metric_window", "outcome_observations", ["metric_name", "window_start"])
    op.create_index("idx_outcome_obs_region_product", "outcome_observations", ["region_code", "product"])


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
