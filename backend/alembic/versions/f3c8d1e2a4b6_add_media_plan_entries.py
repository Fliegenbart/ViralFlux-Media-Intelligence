"""Add media_plan_entries table for CSV-uploaded weekly budgets.

Revision ID: f3c8d1e2a4b6
Revises: e2b7a9c3d4f1
Create Date: 2026-04-21 17:00:00.000000

Rationale
---------
The cockpit has always rendered ``mediaPlan.connected: false`` because no
real GELO-side budget feed existed. A full API integration is out of scope
for the pitch; instead we open a CSV-upload bridge so a PM can paste a
per-Bundesland/channel weekly budget and the cockpit starts rendering EUR
values on the spot (Hero "Demo-Szene" → "Empfohlener Shift", per-region
``currentSpendEur``/``recommendedShiftEur``, ``primaryRecommendation.amountEur``).

Design notes
------------
* ``upload_id`` groups all rows of one CSV upload so a future "replace
  current plan" action can wipe-and-reinsert atomically.
* ``iso_week_year`` + ``iso_week`` as two ints (not a single ISO-date
  range) because a user-facing CSV is far easier to read as "2026-W17"
  than "week_start 2026-04-20".
* ``bundesland_code`` nullable — null means "national / unallocated".
* ``channel`` is a free-form string so the user can tag TV / Digital /
  Radio / OOH / Print / <whatever> without us gatekeeping the taxonomy.
  The cockpit aggregates by bundesland and ignores channel for the EUR
  math today; channel is persisted for later breakdown views.

Idempotent
----------
Both ``upgrade`` and ``downgrade`` guard the DDL with an inspector lookup.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "f3c8d1e2a4b6"
down_revision = "e2b7a9c3d4f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "media_plan_entries" in inspector.get_table_names():
        return

    op.create_table(
        "media_plan_entries",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("client", sa.String(length=64), nullable=False, index=True),
        sa.Column("iso_week_year", sa.Integer(), nullable=False, index=True),
        sa.Column("iso_week", sa.Integer(), nullable=False, index=True),
        sa.Column("bundesland_code", sa.String(length=4), nullable=True, index=True),
        sa.Column("channel", sa.String(length=40), nullable=True),
        sa.Column("eur_amount", sa.Float(), nullable=False),
        sa.Column("upload_id", sa.String(length=64), nullable=False, index=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("notes", sa.String(length=240), nullable=True),
    )
    op.create_index(
        "idx_media_plan_client_week",
        "media_plan_entries",
        ["client", "iso_week_year", "iso_week"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "media_plan_entries" not in inspector.get_table_names():
        return
    op.drop_index("idx_media_plan_client_week", table_name="media_plan_entries")
    op.drop_table("media_plan_entries")
