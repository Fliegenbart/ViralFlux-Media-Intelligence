"""Add trend_momentum_7d and outbreak_risk_score to ml_forecasts

Revision ID: b2a7c3d1e5f8
Revises: fa614f5efb4a
Create Date: 2026-02-21 12:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2a7c3d1e5f8'
down_revision = 'fa614f5efb4a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('ml_forecasts', sa.Column('trend_momentum_7d', sa.Float(), nullable=True))
    op.add_column('ml_forecasts', sa.Column('outbreak_risk_score', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('ml_forecasts', 'outbreak_risk_score')
    op.drop_column('ml_forecasts', 'trend_momentum_7d')
