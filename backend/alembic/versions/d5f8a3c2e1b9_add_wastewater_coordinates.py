"""Add latitude and longitude to wastewater_data

Revision ID: d5f8a3c2e1b9
Revises: c4e9a2b7d3f1
Create Date: 2026-02-21 16:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5f8a3c2e1b9'
down_revision = 'c4e9a2b7d3f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('wastewater_data', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('wastewater_data', sa.Column('longitude', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('wastewater_data', 'longitude')
    op.drop_column('wastewater_data', 'latitude')
