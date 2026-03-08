"""Add media outcome import batches and issues tables.

Revision ID: a9c4e6f1b2d3
Revises: f7b9c1d2e3a4
Create Date: 2026-03-08 10:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a9c4e6f1b2d3"
down_revision = "f7b9c1d2e3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_outcome_import_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.String(), nullable=False),
        sa.Column("brand", sa.String(), nullable=False, server_default="gelo"),
        sa.Column("source_label", sa.String(), nullable=False, server_default="manual"),
        sa.Column("file_name", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="validated"),
        sa.Column("rows_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_valid", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_duplicate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("week_min", sa.DateTime(), nullable=True),
        sa.Column("week_max", sa.DateTime(), nullable=True),
        sa.Column("coverage_after_import", sa.JSON(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id"),
    )
    op.create_index("ix_media_outcome_import_batches_id", "media_outcome_import_batches", ["id"])
    op.create_index("ix_media_outcome_import_batches_batch_id", "media_outcome_import_batches", ["batch_id"])
    op.create_index("ix_media_outcome_import_batches_brand", "media_outcome_import_batches", ["brand"])
    op.create_index("ix_media_outcome_import_batches_source_label", "media_outcome_import_batches", ["source_label"])
    op.create_index("ix_media_outcome_import_batches_status", "media_outcome_import_batches", ["status"])
    op.create_index("ix_media_outcome_import_batches_week_min", "media_outcome_import_batches", ["week_min"])
    op.create_index("ix_media_outcome_import_batches_week_max", "media_outcome_import_batches", ["week_max"])
    op.create_index("ix_media_outcome_import_batches_uploaded_at", "media_outcome_import_batches", ["uploaded_at"])
    op.create_index("ix_media_outcome_import_batches_created_at", "media_outcome_import_batches", ["created_at"])
    op.create_index("ix_media_outcome_import_batches_updated_at", "media_outcome_import_batches", ["updated_at"])
    op.create_index("idx_media_outcome_batch_brand_uploaded", "media_outcome_import_batches", ["brand", "uploaded_at"])
    op.create_index("idx_media_outcome_batch_status_uploaded", "media_outcome_import_batches", ["status", "uploaded_at"])

    op.create_table(
        "media_outcome_import_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.String(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("field_name", sa.String(), nullable=True),
        sa.Column("issue_code", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("raw_row", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_media_outcome_import_issues_id", "media_outcome_import_issues", ["id"])
    op.create_index("ix_media_outcome_import_issues_batch_id", "media_outcome_import_issues", ["batch_id"])
    op.create_index("ix_media_outcome_import_issues_row_number", "media_outcome_import_issues", ["row_number"])
    op.create_index("ix_media_outcome_import_issues_field_name", "media_outcome_import_issues", ["field_name"])
    op.create_index("ix_media_outcome_import_issues_issue_code", "media_outcome_import_issues", ["issue_code"])
    op.create_index("ix_media_outcome_import_issues_created_at", "media_outcome_import_issues", ["created_at"])
    op.create_index("idx_media_outcome_issue_batch_row", "media_outcome_import_issues", ["batch_id", "row_number"])
    op.create_index("idx_media_outcome_issue_batch_code", "media_outcome_import_issues", ["batch_id", "issue_code"])


def downgrade() -> None:
    op.drop_index("idx_media_outcome_issue_batch_code", table_name="media_outcome_import_issues")
    op.drop_index("idx_media_outcome_issue_batch_row", table_name="media_outcome_import_issues")
    op.drop_index("ix_media_outcome_import_issues_created_at", table_name="media_outcome_import_issues")
    op.drop_index("ix_media_outcome_import_issues_issue_code", table_name="media_outcome_import_issues")
    op.drop_index("ix_media_outcome_import_issues_field_name", table_name="media_outcome_import_issues")
    op.drop_index("ix_media_outcome_import_issues_row_number", table_name="media_outcome_import_issues")
    op.drop_index("ix_media_outcome_import_issues_batch_id", table_name="media_outcome_import_issues")
    op.drop_index("ix_media_outcome_import_issues_id", table_name="media_outcome_import_issues")
    op.drop_table("media_outcome_import_issues")

    op.drop_index("idx_media_outcome_batch_status_uploaded", table_name="media_outcome_import_batches")
    op.drop_index("idx_media_outcome_batch_brand_uploaded", table_name="media_outcome_import_batches")
    op.drop_index("ix_media_outcome_import_batches_updated_at", table_name="media_outcome_import_batches")
    op.drop_index("ix_media_outcome_import_batches_created_at", table_name="media_outcome_import_batches")
    op.drop_index("ix_media_outcome_import_batches_uploaded_at", table_name="media_outcome_import_batches")
    op.drop_index("ix_media_outcome_import_batches_week_max", table_name="media_outcome_import_batches")
    op.drop_index("ix_media_outcome_import_batches_week_min", table_name="media_outcome_import_batches")
    op.drop_index("ix_media_outcome_import_batches_status", table_name="media_outcome_import_batches")
    op.drop_index("ix_media_outcome_import_batches_source_label", table_name="media_outcome_import_batches")
    op.drop_index("ix_media_outcome_import_batches_brand", table_name="media_outcome_import_batches")
    op.drop_index("ix_media_outcome_import_batches_batch_id", table_name="media_outcome_import_batches")
    op.drop_index("ix_media_outcome_import_batches_id", table_name="media_outcome_import_batches")
    op.drop_table("media_outcome_import_batches")
