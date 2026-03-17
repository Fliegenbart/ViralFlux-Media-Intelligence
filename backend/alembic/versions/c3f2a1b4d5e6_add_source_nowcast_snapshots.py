"""Add append-only source_nowcast_snapshots table.

Revision ID: c3f2a1b4d5e6
Revises: a9c4e6f1b2d3
Create Date: 2026-03-16 17:15:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "c3f2a1b4d5e6"
down_revision = "a9c4e6f1b2d3"
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
    if not _table_exists("source_nowcast_snapshots"):
        op.create_table(
            "source_nowcast_snapshots",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("source_id", sa.String(), nullable=False),
            sa.Column("signal_id", sa.String(), nullable=False),
            sa.Column("region_code", sa.String(), nullable=True),
            sa.Column("reference_date", sa.DateTime(), nullable=False),
            sa.Column("effective_available_time", sa.DateTime(), nullable=False),
            sa.Column("raw_value", sa.Float(), nullable=False),
            sa.Column("snapshot_captured_at", sa.DateTime(), nullable=False),
            sa.Column("timing_provenance", sa.String(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_source_nowcast_snapshots_id", "source_nowcast_snapshots", ["id"])
    _create_index_if_missing("ix_source_nowcast_snapshots_source_id", "source_nowcast_snapshots", ["source_id"])
    _create_index_if_missing("ix_source_nowcast_snapshots_signal_id", "source_nowcast_snapshots", ["signal_id"])
    _create_index_if_missing("ix_source_nowcast_snapshots_region_code", "source_nowcast_snapshots", ["region_code"])
    _create_index_if_missing("ix_source_nowcast_snapshots_reference_date", "source_nowcast_snapshots", ["reference_date"])
    _create_index_if_missing(
        "ix_source_nowcast_snapshots_effective_available_time",
        "source_nowcast_snapshots",
        ["effective_available_time"],
    )
    _create_index_if_missing(
        "ix_source_nowcast_snapshots_snapshot_captured_at",
        "source_nowcast_snapshots",
        ["snapshot_captured_at"],
    )
    _create_index_if_missing("ix_source_nowcast_snapshots_created_at", "source_nowcast_snapshots", ["created_at"])
    _create_index_if_missing(
        "idx_nowcast_snapshot_source_ref",
        "source_nowcast_snapshots",
        ["source_id", "reference_date"],
    )
    _create_index_if_missing(
        "idx_nowcast_snapshot_signal_region",
        "source_nowcast_snapshots",
        ["signal_id", "region_code"],
    )
    _create_index_if_missing(
        "idx_nowcast_snapshot_capture_source",
        "source_nowcast_snapshots",
        ["snapshot_captured_at", "source_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_nowcast_snapshot_capture_source", table_name="source_nowcast_snapshots")
    op.drop_index("idx_nowcast_snapshot_signal_region", table_name="source_nowcast_snapshots")
    op.drop_index("idx_nowcast_snapshot_source_ref", table_name="source_nowcast_snapshots")
    op.drop_index("ix_source_nowcast_snapshots_created_at", table_name="source_nowcast_snapshots")
    op.drop_index("ix_source_nowcast_snapshots_snapshot_captured_at", table_name="source_nowcast_snapshots")
    op.drop_index(
        "ix_source_nowcast_snapshots_effective_available_time",
        table_name="source_nowcast_snapshots",
    )
    op.drop_index("ix_source_nowcast_snapshots_reference_date", table_name="source_nowcast_snapshots")
    op.drop_index("ix_source_nowcast_snapshots_region_code", table_name="source_nowcast_snapshots")
    op.drop_index("ix_source_nowcast_snapshots_signal_id", table_name="source_nowcast_snapshots")
    op.drop_index("ix_source_nowcast_snapshots_source_id", table_name="source_nowcast_snapshots")
    op.drop_index("ix_source_nowcast_snapshots_id", table_name="source_nowcast_snapshots")
    op.drop_table("source_nowcast_snapshots")
