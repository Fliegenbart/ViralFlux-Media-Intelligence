"""Add forecast_accuracy_log table for production monitoring.

Revision ID: e6a1b4c8d2f3
Revises: d5f8a3c2e1b9
Create Date: 2026-02-22 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'e6a1b4c8d2f3'
down_revision = 'd5f8a3c2e1b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'forecast_accuracy_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('computed_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('virus_typ', sa.String(), nullable=False),
        sa.Column('window_days', sa.Integer(), nullable=False, server_default='14'),
        sa.Column('samples', sa.Integer(), nullable=False),
        sa.Column('mae', sa.Float(), nullable=True),
        sa.Column('rmse', sa.Float(), nullable=True),
        sa.Column('mape', sa.Float(), nullable=True),
        sa.Column('correlation', sa.Float(), nullable=True),
        sa.Column('drift_detected', sa.Boolean(), server_default='false'),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_forecast_accuracy_log_id', 'forecast_accuracy_log', ['id'])
    op.create_index('ix_forecast_accuracy_log_computed_at', 'forecast_accuracy_log', ['computed_at'])
    op.create_index('ix_forecast_accuracy_log_virus_typ', 'forecast_accuracy_log', ['virus_typ'])
    op.create_index('idx_accuracy_virus_computed', 'forecast_accuracy_log', ['virus_typ', 'computed_at'])


def downgrade() -> None:
    op.drop_index('idx_accuracy_virus_computed', table_name='forecast_accuracy_log')
    op.drop_index('ix_forecast_accuracy_log_virus_typ', table_name='forecast_accuracy_log')
    op.drop_index('ix_forecast_accuracy_log_computed_at', table_name='forecast_accuracy_log')
    op.drop_index('ix_forecast_accuracy_log_id', table_name='forecast_accuracy_log')
    op.drop_table('forecast_accuracy_log')
