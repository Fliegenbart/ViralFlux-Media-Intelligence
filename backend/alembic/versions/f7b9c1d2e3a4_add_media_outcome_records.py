"""Add media_outcome_records table for truth layer imports.

Revision ID: f7b9c1d2e3a4
Revises: e6a1b4c8d2f3
Create Date: 2026-03-06 11:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'f7b9c1d2e3a4'
down_revision = 'e6a1b4c8d2f3'
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
    if not _table_exists("media_outcome_records"):
        op.create_table(
            'media_outcome_records',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('week_start', sa.DateTime(), nullable=False),
            sa.Column('brand', sa.String(), nullable=False, server_default='gelo'),
            sa.Column('product', sa.String(), nullable=False),
            sa.Column('region_code', sa.String(), nullable=False),
            sa.Column('media_spend_eur', sa.Float(), nullable=True),
            sa.Column('impressions', sa.Float(), nullable=True),
            sa.Column('clicks', sa.Float(), nullable=True),
            sa.Column('qualified_visits', sa.Float(), nullable=True),
            sa.Column('search_lift_index', sa.Float(), nullable=True),
            sa.Column('sales_units', sa.Float(), nullable=True),
            sa.Column('order_count', sa.Float(), nullable=True),
            sa.Column('revenue_eur', sa.Float(), nullable=True),
            sa.Column('source_label', sa.String(), nullable=False, server_default='manual'),
            sa.Column('import_batch_id', sa.String(), nullable=True),
            sa.Column('extra_data', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint(
                'week_start',
                'brand',
                'product',
                'region_code',
                'source_label',
                name='uq_media_outcome_record',
            ),
        )
    _create_index_if_missing('ix_media_outcome_records_id', 'media_outcome_records', ['id'])
    _create_index_if_missing('ix_media_outcome_records_week_start', 'media_outcome_records', ['week_start'])
    _create_index_if_missing('ix_media_outcome_records_brand', 'media_outcome_records', ['brand'])
    _create_index_if_missing('ix_media_outcome_records_product', 'media_outcome_records', ['product'])
    _create_index_if_missing('ix_media_outcome_records_region_code', 'media_outcome_records', ['region_code'])
    _create_index_if_missing('ix_media_outcome_records_source_label', 'media_outcome_records', ['source_label'])
    _create_index_if_missing('ix_media_outcome_records_import_batch_id', 'media_outcome_records', ['import_batch_id'])
    _create_index_if_missing('ix_media_outcome_records_created_at', 'media_outcome_records', ['created_at'])
    _create_index_if_missing('ix_media_outcome_records_updated_at', 'media_outcome_records', ['updated_at'])
    _create_index_if_missing('idx_media_outcome_brand_week', 'media_outcome_records', ['brand', 'week_start'])
    _create_index_if_missing('idx_media_outcome_product_week', 'media_outcome_records', ['product', 'week_start'])


def downgrade() -> None:
    op.drop_index('idx_media_outcome_product_week', table_name='media_outcome_records')
    op.drop_index('idx_media_outcome_brand_week', table_name='media_outcome_records')
    op.drop_index('ix_media_outcome_records_updated_at', table_name='media_outcome_records')
    op.drop_index('ix_media_outcome_records_created_at', table_name='media_outcome_records')
    op.drop_index('ix_media_outcome_records_import_batch_id', table_name='media_outcome_records')
    op.drop_index('ix_media_outcome_records_source_label', table_name='media_outcome_records')
    op.drop_index('ix_media_outcome_records_region_code', table_name='media_outcome_records')
    op.drop_index('ix_media_outcome_records_product', table_name='media_outcome_records')
    op.drop_index('ix_media_outcome_records_brand', table_name='media_outcome_records')
    op.drop_index('ix_media_outcome_records_week_start', table_name='media_outcome_records')
    op.drop_index('ix_media_outcome_records_id', table_name='media_outcome_records')
    op.drop_table('media_outcome_records')
