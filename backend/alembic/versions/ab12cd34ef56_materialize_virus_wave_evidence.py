"""Materialize virus wave evidence v1.1.

Revision ID: ab12cd34ef56
Revises: f3c8d1e2a4b6
Create Date: 2026-04-30 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "ab12cd34ef56"
down_revision = "f3c8d1e2a4b6"
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
    if not _table_exists("virus_wave_feature_runs"):
        op.create_table(
            "virus_wave_feature_runs",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("run_key", sa.String(), nullable=False),
            sa.Column("algorithm_version", sa.String(), nullable=False),
            sa.Column("mode", sa.String(), nullable=False, server_default="materialized"),
            sa.Column("status", sa.String(), nullable=False, server_default="success"),
            sa.Column("pathogen", sa.String(), nullable=False),
            sa.Column("region_code", sa.String(), nullable=False, server_default="DE"),
            sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("pathogens_processed", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("regions_processed", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("input_min_date", sa.DateTime(), nullable=True),
            sa.Column("input_max_date", sa.DateTime(), nullable=True),
            sa.Column("parameters_json", sa.JSON(), nullable=True),
            sa.Column("snapshot_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.UniqueConstraint("run_key", name="uq_virus_wave_feature_runs_run_key"),
        )
    _create_index_if_missing("ix_virus_wave_feature_runs_id", "virus_wave_feature_runs", ["id"])
    _create_index_if_missing("ix_virus_wave_feature_runs_run_key", "virus_wave_feature_runs", ["run_key"], unique=True)
    _create_index_if_missing("ix_virus_wave_feature_runs_algorithm_version", "virus_wave_feature_runs", ["algorithm_version"])
    _create_index_if_missing("ix_virus_wave_feature_runs_status", "virus_wave_feature_runs", ["status"])
    _create_index_if_missing("ix_virus_wave_feature_runs_pathogen", "virus_wave_feature_runs", ["pathogen"])
    _create_index_if_missing("ix_virus_wave_feature_runs_region_code", "virus_wave_feature_runs", ["region_code"])
    _create_index_if_missing("ix_virus_wave_feature_runs_finished_at", "virus_wave_feature_runs", ["finished_at"])
    _create_index_if_missing("ix_virus_wave_feature_runs_input_max_date", "virus_wave_feature_runs", ["input_max_date"])
    _create_index_if_missing("ix_virus_wave_feature_runs_created_at", "virus_wave_feature_runs", ["created_at"])
    _create_index_if_missing("idx_virus_wave_run_scope_finished", "virus_wave_feature_runs", ["pathogen", "region_code", "finished_at"])
    _create_index_if_missing("idx_virus_wave_run_algorithm_status", "virus_wave_feature_runs", ["algorithm_version", "status"])

    if not _table_exists("virus_wave_features"):
        op.create_table(
            "virus_wave_features",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("virus_wave_feature_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source", sa.String(), nullable=False),
            sa.Column("source_role", sa.String(), nullable=False),
            sa.Column("pathogen", sa.String(), nullable=False),
            sa.Column("region_code", sa.String(), nullable=False, server_default="DE"),
            sa.Column("season", sa.String(), nullable=True),
            sa.Column("phase", sa.String(), nullable=True),
            sa.Column("onset_date", sa.DateTime(), nullable=True),
            sa.Column("peak_date", sa.DateTime(), nullable=True),
            sa.Column("end_date", sa.DateTime(), nullable=True),
            sa.Column("wave_strength", sa.Float(), nullable=True),
            sa.Column("peak_value", sa.Float(), nullable=True),
            sa.Column("area_under_curve", sa.Float(), nullable=True),
            sa.Column("growth_rate", sa.Float(), nullable=True),
            sa.Column("decline_rate", sa.Float(), nullable=True),
            sa.Column("wave_points", sa.Integer(), nullable=True),
            sa.Column("latest_observation_date", sa.DateTime(), nullable=True),
            sa.Column("data_freshness_days", sa.Integer(), nullable=True),
            sa.Column("signal_basis", sa.String(), nullable=True),
            sa.Column("quality_flags_json", sa.JSON(), nullable=True),
            sa.Column("confidence_score", sa.Float(), nullable=True),
            sa.Column("feature_payload_json", sa.JSON(), nullable=True),
            sa.Column("algorithm_version", sa.String(), nullable=False),
            sa.Column("computed_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.UniqueConstraint("run_id", "source", "pathogen", "region_code", name="uq_virus_wave_feature_run_source"),
        )
    for index_name, columns in {
        "ix_virus_wave_features_id": ["id"],
        "ix_virus_wave_features_run_id": ["run_id"],
        "ix_virus_wave_features_source": ["source"],
        "ix_virus_wave_features_source_role": ["source_role"],
        "ix_virus_wave_features_pathogen": ["pathogen"],
        "ix_virus_wave_features_region_code": ["region_code"],
        "ix_virus_wave_features_season": ["season"],
        "ix_virus_wave_features_phase": ["phase"],
        "ix_virus_wave_features_onset_date": ["onset_date"],
        "ix_virus_wave_features_peak_date": ["peak_date"],
        "ix_virus_wave_features_latest_observation_date": ["latest_observation_date"],
        "ix_virus_wave_features_algorithm_version": ["algorithm_version"],
        "ix_virus_wave_features_computed_at": ["computed_at"],
        "ix_virus_wave_features_created_at": ["created_at"],
        "idx_virus_wave_feature_scope_source": ["pathogen", "region_code", "source"],
        "idx_virus_wave_feature_algorithm": ["algorithm_version", "computed_at"],
    }.items():
        _create_index_if_missing(index_name, "virus_wave_features", columns)

    if not _table_exists("virus_wave_alignment"):
        op.create_table(
            "virus_wave_alignment",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("virus_wave_feature_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("pathogen", sa.String(), nullable=False),
            sa.Column("region_code", sa.String(), nullable=False, server_default="DE"),
            sa.Column("season", sa.String(), nullable=True),
            sa.Column("early_source", sa.String(), nullable=False, server_default="amelag"),
            sa.Column("confirmed_source", sa.String(), nullable=False, server_default="survstat"),
            sa.Column("early_wave_feature_id", sa.Integer(), sa.ForeignKey("virus_wave_features.id", ondelete="SET NULL"), nullable=True),
            sa.Column("confirmed_wave_feature_id", sa.Integer(), sa.ForeignKey("virus_wave_features.id", ondelete="SET NULL"), nullable=True),
            sa.Column("raw_lead_lag_days", sa.Integer(), nullable=True),
            sa.Column("early_source_lead_days", sa.Integer(), nullable=True),
            sa.Column("alignment_status", sa.String(), nullable=True),
            sa.Column("alignment_score", sa.Float(), nullable=True),
            sa.Column("divergence_score", sa.Float(), nullable=True),
            sa.Column("correlation_score", sa.Float(), nullable=True),
            sa.Column("confidence_score", sa.Float(), nullable=True),
            sa.Column("matched_window_start", sa.DateTime(), nullable=True),
            sa.Column("matched_window_end", sa.DateTime(), nullable=True),
            sa.Column("alignment_payload_json", sa.JSON(), nullable=True),
            sa.Column("algorithm_version", sa.String(), nullable=False),
            sa.Column("computed_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.UniqueConstraint("run_id", "pathogen", "region_code", name="uq_virus_wave_alignment_run_scope"),
        )
    for index_name, columns in {
        "ix_virus_wave_alignment_id": ["id"],
        "ix_virus_wave_alignment_run_id": ["run_id"],
        "ix_virus_wave_alignment_pathogen": ["pathogen"],
        "ix_virus_wave_alignment_region_code": ["region_code"],
        "ix_virus_wave_alignment_season": ["season"],
        "ix_virus_wave_alignment_early_source": ["early_source"],
        "ix_virus_wave_alignment_confirmed_source": ["confirmed_source"],
        "ix_virus_wave_alignment_early_wave_feature_id": ["early_wave_feature_id"],
        "ix_virus_wave_alignment_confirmed_wave_feature_id": ["confirmed_wave_feature_id"],
        "ix_virus_wave_alignment_alignment_status": ["alignment_status"],
        "ix_virus_wave_alignment_algorithm_version": ["algorithm_version"],
        "ix_virus_wave_alignment_computed_at": ["computed_at"],
        "idx_virus_wave_alignment_scope": ["pathogen", "region_code", "alignment_status"],
    }.items():
        _create_index_if_missing(index_name, "virus_wave_alignment", columns)

    if not _table_exists("virus_wave_evidence"):
        op.create_table(
            "virus_wave_evidence",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("virus_wave_feature_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("pathogen", sa.String(), nullable=False),
            sa.Column("region_code", sa.String(), nullable=False, server_default="DE"),
            sa.Column("season", sa.String(), nullable=True),
            sa.Column("profile_name", sa.String(), nullable=False),
            sa.Column("primary_source", sa.String(), nullable=True),
            sa.Column("base_weights_json", sa.JSON(), nullable=True),
            sa.Column("quality_multipliers_json", sa.JSON(), nullable=True),
            sa.Column("effective_weights_json", sa.JSON(), nullable=True),
            sa.Column("source_availability_json", sa.JSON(), nullable=True),
            sa.Column("evidence_coverage", sa.Float(), nullable=True),
            sa.Column("evidence_mode", sa.String(), nullable=False, server_default="diagnostic_only"),
            sa.Column("budget_can_change", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("confidence_score", sa.Float(), nullable=True),
            sa.Column("confidence_method", sa.String(), nullable=True),
            sa.Column("quality_flags_json", sa.JSON(), nullable=True),
            sa.Column("evidence_payload_json", sa.JSON(), nullable=True),
            sa.Column("algorithm_version", sa.String(), nullable=False),
            sa.Column("computed_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.UniqueConstraint("run_id", "pathogen", "region_code", "profile_name", name="uq_virus_wave_evidence_run_profile"),
        )
    for index_name, columns in {
        "ix_virus_wave_evidence_id": ["id"],
        "ix_virus_wave_evidence_run_id": ["run_id"],
        "ix_virus_wave_evidence_pathogen": ["pathogen"],
        "ix_virus_wave_evidence_region_code": ["region_code"],
        "ix_virus_wave_evidence_season": ["season"],
        "ix_virus_wave_evidence_profile_name": ["profile_name"],
        "ix_virus_wave_evidence_primary_source": ["primary_source"],
        "ix_virus_wave_evidence_evidence_mode": ["evidence_mode"],
        "ix_virus_wave_evidence_budget_can_change": ["budget_can_change"],
        "ix_virus_wave_evidence_algorithm_version": ["algorithm_version"],
        "ix_virus_wave_evidence_computed_at": ["computed_at"],
        "idx_virus_wave_evidence_scope_profile": ["pathogen", "region_code", "profile_name"],
        "idx_virus_wave_evidence_algorithm": ["algorithm_version", "computed_at"],
    }.items():
        _create_index_if_missing(index_name, "virus_wave_evidence", columns)


def downgrade() -> None:
    for table_name in (
        "virus_wave_evidence",
        "virus_wave_alignment",
        "virus_wave_features",
        "virus_wave_feature_runs",
    ):
        if _table_exists(table_name):
            op.drop_table(table_name)
