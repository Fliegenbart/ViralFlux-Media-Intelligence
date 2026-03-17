"""add ingestion fields to media outcome batches

Revision ID: e1f4c7b8a9d2
Revises: 9695cafe1234
Create Date: 2026-03-17 21:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e1f4c7b8a9d2"
down_revision = "9695cafe1234"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media_outcome_import_batches",
        sa.Column("source_system", sa.String(), nullable=True),
    )
    op.add_column(
        "media_outcome_import_batches",
        sa.Column("external_batch_id", sa.String(), nullable=True),
    )
    op.add_column(
        "media_outcome_import_batches",
        sa.Column(
            "ingestion_mode",
            sa.String(),
            nullable=False,
            server_default="manual_backoffice",
        ),
    )
    op.create_index(
        "ix_media_outcome_import_batches_source_system",
        "media_outcome_import_batches",
        ["source_system"],
        unique=False,
    )
    op.create_index(
        "ix_media_outcome_import_batches_external_batch_id",
        "media_outcome_import_batches",
        ["external_batch_id"],
        unique=False,
    )
    op.create_index(
        "ix_media_outcome_import_batches_ingestion_mode",
        "media_outcome_import_batches",
        ["ingestion_mode"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_media_outcome_batch_external",
        "media_outcome_import_batches",
        ["source_system", "external_batch_id"],
    )
    op.alter_column(
        "media_outcome_import_batches",
        "ingestion_mode",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_media_outcome_batch_external",
        "media_outcome_import_batches",
        type_="unique",
    )
    op.drop_index(
        "ix_media_outcome_import_batches_ingestion_mode",
        table_name="media_outcome_import_batches",
    )
    op.drop_index(
        "ix_media_outcome_import_batches_external_batch_id",
        table_name="media_outcome_import_batches",
    )
    op.drop_index(
        "ix_media_outcome_import_batches_source_system",
        table_name="media_outcome_import_batches",
    )
    op.drop_column("media_outcome_import_batches", "ingestion_mode")
    op.drop_column("media_outcome_import_batches", "external_batch_id")
    op.drop_column("media_outcome_import_batches", "source_system")
