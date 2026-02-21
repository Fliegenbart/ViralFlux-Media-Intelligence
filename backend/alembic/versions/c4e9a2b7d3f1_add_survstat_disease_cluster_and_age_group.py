"""Add disease_cluster and age_group to survstat_weekly_data

Revision ID: c4e9a2b7d3f1
Revises: b2a7c3d1e5f8
Create Date: 2026-02-21 14:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4e9a2b7d3f1'
down_revision = 'b2a7c3d1e5f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('survstat_weekly_data', sa.Column('disease_cluster', sa.String(), nullable=True))
    op.add_column('survstat_weekly_data', sa.Column('age_group', sa.String(), nullable=True))
    op.create_index('idx_survstat_cluster_week', 'survstat_weekly_data', ['disease_cluster', 'week_start'])


def downgrade() -> None:
    op.drop_index('idx_survstat_cluster_week', table_name='survstat_weekly_data')
    op.drop_column('survstat_weekly_data', 'age_group')
    op.drop_column('survstat_weekly_data', 'disease_cluster')
