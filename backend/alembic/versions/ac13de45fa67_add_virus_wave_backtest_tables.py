"""Add virus wave backtest tables.

Revision ID: ac13de45fa67
Revises: ab12cd34ef56
Create Date: 2026-04-30 10:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "ac13de45fa67"
down_revision = "ab12cd34ef56"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in set(inspect(op.get_bind()).get_table_names())


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return index_name in {item["name"] for item in inspector.get_indexes(table_name)}


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], *, unique: bool = False) -> None:
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    if not _table_exists("virus_wave_backtest_runs"):
        op.create_table(
            "virus_wave_backtest_runs",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("run_key", sa.String(), nullable=False),
            sa.Column("algorithm_version", sa.String(), nullable=False),
            sa.Column("backtest_version", sa.String(), nullable=False),
            sa.Column("mode", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="success"),
            sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("pathogens", sa.JSON(), nullable=True),
            sa.Column("regions", sa.JSON(), nullable=True),
            sa.Column("seasons", sa.JSON(), nullable=True),
            sa.Column("baseline_models", sa.JSON(), nullable=True),
            sa.Column("candidate_models", sa.JSON(), nullable=True),
            sa.Column("parameters_json", sa.JSON(), nullable=True),
            sa.Column("summary_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.UniqueConstraint("run_key", name="uq_virus_wave_backtest_runs_run_key"),
        )
    for index_name, columns in {
        "ix_virus_wave_backtest_runs_id": ["id"],
        "ix_virus_wave_backtest_runs_run_key": ["run_key"],
        "ix_virus_wave_backtest_runs_algorithm_version": ["algorithm_version"],
        "ix_virus_wave_backtest_runs_backtest_version": ["backtest_version"],
        "ix_virus_wave_backtest_runs_mode": ["mode"],
        "ix_virus_wave_backtest_runs_status": ["status"],
        "ix_virus_wave_backtest_runs_started_at": ["started_at"],
        "ix_virus_wave_backtest_runs_finished_at": ["finished_at"],
        "ix_virus_wave_backtest_runs_created_at": ["created_at"],
        "idx_virus_wave_backtest_run_mode_finished": ["mode", "finished_at"],
        "idx_virus_wave_backtest_run_version": ["backtest_version", "algorithm_version"],
    }.items():
        _create_index_if_missing(
            index_name,
            "virus_wave_backtest_runs",
            columns,
            unique=index_name == "ix_virus_wave_backtest_runs_run_key",
        )

    if not _table_exists("virus_wave_backtest_results"):
        op.create_table(
            "virus_wave_backtest_results",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("virus_wave_backtest_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("pathogen", sa.String(), nullable=False),
            sa.Column("canonical_pathogen", sa.String(), nullable=False),
            sa.Column("pathogen_variant", sa.String(), nullable=True),
            sa.Column("region_code", sa.String(), nullable=False, server_default="DE"),
            sa.Column("season", sa.String(), nullable=True),
            sa.Column("model_name", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="ok"),
            sa.Column("onset_detection_gain_days", sa.Float(), nullable=True),
            sa.Column("peak_detection_gain_days", sa.Float(), nullable=True),
            sa.Column("phase_accuracy", sa.Float(), nullable=True),
            sa.Column("false_early_warning_rate", sa.Float(), nullable=True),
            sa.Column("missed_wave_rate", sa.Float(), nullable=True),
            sa.Column("false_post_peak_rate", sa.Float(), nullable=True),
            sa.Column("lead_lag_stability", sa.Float(), nullable=True),
            sa.Column("mean_alignment_score", sa.Float(), nullable=True),
            sa.Column("mean_divergence_score", sa.Float(), nullable=True),
            sa.Column("confidence_brier_score", sa.Float(), nullable=True),
            sa.Column("summary_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.UniqueConstraint("run_id", "pathogen", "region_code", "model_name", name="uq_virus_wave_backtest_result_model"),
        )
    for index_name, columns in {
        "ix_virus_wave_backtest_results_id": ["id"],
        "ix_virus_wave_backtest_results_run_id": ["run_id"],
        "ix_virus_wave_backtest_results_pathogen": ["pathogen"],
        "ix_virus_wave_backtest_results_canonical_pathogen": ["canonical_pathogen"],
        "ix_virus_wave_backtest_results_pathogen_variant": ["pathogen_variant"],
        "ix_virus_wave_backtest_results_region_code": ["region_code"],
        "ix_virus_wave_backtest_results_season": ["season"],
        "ix_virus_wave_backtest_results_model_name": ["model_name"],
        "ix_virus_wave_backtest_results_status": ["status"],
        "idx_virus_wave_backtest_result_scope": ["canonical_pathogen", "region_code", "season"],
    }.items():
        _create_index_if_missing(index_name, "virus_wave_backtest_results", columns)

    if not _table_exists("virus_wave_backtest_events"):
        op.create_table(
            "virus_wave_backtest_events",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("virus_wave_backtest_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("pathogen", sa.String(), nullable=False),
            sa.Column("canonical_pathogen", sa.String(), nullable=False),
            sa.Column("pathogen_variant", sa.String(), nullable=True),
            sa.Column("region_code", sa.String(), nullable=False, server_default="DE"),
            sa.Column("season", sa.String(), nullable=True),
            sa.Column("event_type", sa.String(), nullable=False),
            sa.Column("event_date", sa.DateTime(), nullable=True),
            sa.Column("model_name", sa.String(), nullable=False),
            sa.Column("survstat_phase", sa.String(), nullable=True),
            sa.Column("amelag_phase", sa.String(), nullable=True),
            sa.Column("predicted_phase", sa.String(), nullable=True),
            sa.Column("observed_phase", sa.String(), nullable=True),
            sa.Column("lead_lag_days", sa.Integer(), nullable=True),
            sa.Column("confidence_score", sa.Float(), nullable=True),
            sa.Column("details_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        )
    for index_name, columns in {
        "ix_virus_wave_backtest_events_id": ["id"],
        "ix_virus_wave_backtest_events_run_id": ["run_id"],
        "ix_virus_wave_backtest_events_pathogen": ["pathogen"],
        "ix_virus_wave_backtest_events_canonical_pathogen": ["canonical_pathogen"],
        "ix_virus_wave_backtest_events_pathogen_variant": ["pathogen_variant"],
        "ix_virus_wave_backtest_events_region_code": ["region_code"],
        "ix_virus_wave_backtest_events_season": ["season"],
        "ix_virus_wave_backtest_events_event_type": ["event_type"],
        "ix_virus_wave_backtest_events_event_date": ["event_date"],
        "ix_virus_wave_backtest_events_model_name": ["model_name"],
        "idx_virus_wave_backtest_event_scope": ["canonical_pathogen", "region_code", "event_type"],
        "idx_virus_wave_backtest_event_model": ["model_name", "event_date"],
    }.items():
        _create_index_if_missing(index_name, "virus_wave_backtest_events", columns)


def downgrade() -> None:
    for table_name in (
        "virus_wave_backtest_events",
        "virus_wave_backtest_results",
        "virus_wave_backtest_runs",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)
