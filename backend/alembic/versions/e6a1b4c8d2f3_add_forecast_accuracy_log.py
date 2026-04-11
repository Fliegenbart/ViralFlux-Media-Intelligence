"""Add forecast_accuracy_log table for production monitoring.

Revision ID: e6a1b4c8d2f3
Revises: d5f8a3c2e1b9
Create Date: 2026-02-22 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'e6a1b4c8d2f3'
down_revision = 'd5f8a3c2e1b9'
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
    if not _table_exists("forecast_accuracy_log"):
        op.create_table(
            'forecast_accuracy_log',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column(
                'computed_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.text('CURRENT_TIMESTAMP'),
            ),
            sa.Column('virus_typ', sa.String(), nullable=False),
            sa.Column('window_days', sa.Integer(), nullable=False, server_default=sa.text('14')),
            sa.Column('samples', sa.Integer(), nullable=False),
            sa.Column('mae', sa.Float(), nullable=True),
            sa.Column('rmse', sa.Float(), nullable=True),
            sa.Column('mape', sa.Float(), nullable=True),
            sa.Column('correlation', sa.Float(), nullable=True),
            sa.Column('drift_detected', sa.Boolean(), server_default=sa.false()),
            sa.Column('details', sa.JSON(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
    _create_index_if_missing('ix_forecast_accuracy_log_id', 'forecast_accuracy_log', ['id'])
    _create_index_if_missing('ix_forecast_accuracy_log_computed_at', 'forecast_accuracy_log', ['computed_at'])
    _create_index_if_missing('ix_forecast_accuracy_log_virus_typ', 'forecast_accuracy_log', ['virus_typ'])
    _create_index_if_missing('idx_accuracy_virus_computed', 'forecast_accuracy_log', ['virus_typ', 'computed_at'])


def downgrade() -> None:
    op.drop_index('idx_accuracy_virus_computed', table_name='forecast_accuracy_log')
    op.drop_index('ix_forecast_accuracy_log_virus_typ', table_name='forecast_accuracy_log')
    op.drop_index('ix_forecast_accuracy_log_computed_at', table_name='forecast_accuracy_log')
    op.drop_index('ix_forecast_accuracy_log_id', table_name='forecast_accuracy_log')
    op.drop_table('forecast_accuracy_log')
