"""Add outcome_record_id FK on llm_recommendations for the outcome-loop.

Revision ID: e2b7a9c3d4f1
Revises: d9e8f7a6b5c4
Create Date: 2026-04-20 12:00:00.000000

Rationale
---------
Before this migration, ``media_outcome_records`` and ``llm_recommendations``
coexisted without any structural link — the cockpit could render both, but
no downstream query could answer "did this recommendation match its outcome".
The new nullable FK opens that join without changing existing behaviour:
old rows stay NULL, matcher services (see outcome_ingestion_service and
truth_layer_service) can populate it as confident matches are found.

Design notes
------------
* Nullable FK — populating it is a separate service-layer concern, and we
  must not block recommendation inserts while the matcher is still
  deliberately heuristic.
* ``ON DELETE SET NULL`` — if an outcome record is rebuilt/replaced, the
  recommendation survives with a dangling reference cleared, not deleted.
* Index on the FK column — expected query pattern is "find all recs for
  this outcome" for the reconciliation-loop, not the other direction.

Idempotent
----------
Both ``upgrade`` and ``downgrade`` guard each DDL with a dynamic inspector
lookup so re-applying on a partially migrated DB is safe.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e2b7a9c3d4f1"
down_revision = "d9e8f7a6b5c4"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return index_name in {item["name"] for item in inspector.get_indexes(table_name)}


def _fk_exists(table_name: str, fk_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return fk_name in {fk.get("name") for fk in inspector.get_foreign_keys(table_name)}


def upgrade() -> None:
    if not _column_exists("llm_recommendations", "outcome_record_id"):
        op.add_column(
            "llm_recommendations",
            sa.Column("outcome_record_id", sa.Integer(), nullable=True),
        )
    if not _fk_exists("llm_recommendations", "llm_recommendations_outcome_record_id_fkey"):
        op.create_foreign_key(
            "llm_recommendations_outcome_record_id_fkey",
            "llm_recommendations",
            "media_outcome_records",
            ["outcome_record_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if not _index_exists("llm_recommendations", "ix_llm_recommendations_outcome_record_id"):
        op.create_index(
            "ix_llm_recommendations_outcome_record_id",
            "llm_recommendations",
            ["outcome_record_id"],
        )


def downgrade() -> None:
    if _index_exists("llm_recommendations", "ix_llm_recommendations_outcome_record_id"):
        op.drop_index(
            "ix_llm_recommendations_outcome_record_id",
            table_name="llm_recommendations",
        )
    if _fk_exists("llm_recommendations", "llm_recommendations_outcome_record_id_fkey"):
        op.drop_constraint(
            "llm_recommendations_outcome_record_id_fkey",
            "llm_recommendations",
            type_="foreignkey",
        )
    if _column_exists("llm_recommendations", "outcome_record_id"):
        op.drop_column("llm_recommendations", "outcome_record_id")
