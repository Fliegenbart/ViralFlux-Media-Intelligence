from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, MediaOutcomeRecord
from app.services.research.tri_layer.sales_adapter import load_sales_panel
from app.services.research.tri_layer.schema import (
    SourceEvidence,
    TriLayerRegionEvidence,
)
from app.services.research.tri_layer.service import build_region_snapshot


_BUDGET_RANK = {
    "blocked": 0,
    "calibration_window": 1,
    "shadow_only": 2,
    "limited": 3,
    "approved": 4,
}


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return engine, SessionLocal()


def _snapshot_with_sales(sales: SourceEvidence):
    return build_region_snapshot(
        TriLayerRegionEvidence(
            region="Hamburg",
            region_code="HH",
            wastewater=SourceEvidence(
                status="connected",
                signal=0.92,
                intensity=0.86,
                growth=0.24,
                coverage=0.8,
                reliability=0.8,
            ),
            clinical=SourceEvidence(
                status="connected",
                signal=0.90,
                intensity=0.82,
                growth=0.18,
                coverage=0.9,
                reliability=0.9,
            ),
            sales=sales,
        )
    )


def test_strong_epidemiology_without_sales_cannot_create_commercial_relevance() -> None:
    snapshot = _snapshot_with_sales(SourceEvidence(status="not_connected"))

    assert snapshot.commercial_relevance_score is None
    assert snapshot.gates.sales_calibration == "not_available"
    assert snapshot.gates.budget_isolation in {"not_available", "fail"}
    assert _BUDGET_RANK[snapshot.budget_permission_state] <= _BUDGET_RANK["shadow_only"]
    assert snapshot.budget_can_change is False


def test_media_outcome_spend_only_is_not_sell_out_sales_calibration() -> None:
    engine, db = _session()
    try:
        db.add(
            MediaOutcomeRecord(
                week_start=datetime(2026, 4, 20),
                brand="gelo",
                product="GeloMyrtol",
                region_code="HH",
                media_spend_eur=1200.0,
                impressions=10000.0,
                source_label="media_plan",
            )
        )
        db.commit()

        panel = load_sales_panel(db, brand="gelo", virus_typ="Influenza A", cutoff=datetime(2026, 4, 30).date())
        snapshot = _snapshot_with_sales(SourceEvidence(status=panel.status.status))
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    assert panel.status.status == "not_connected"
    assert snapshot.commercial_relevance_score is None
    assert snapshot.gates.sales_calibration == "not_available"
    assert _BUDGET_RANK[snapshot.budget_permission_state] <= _BUDGET_RANK["shadow_only"]
    assert snapshot.budget_can_change is False


def test_real_sales_without_validation_metadata_cannot_approve_budget() -> None:
    snapshot = _snapshot_with_sales(
        SourceEvidence(
            status="connected",
            signal=0.90,
            reliability=0.9,
            coverage=0.9,
            real_sell_out=True,
        )
    )

    assert snapshot.commercial_relevance_score is None
    assert snapshot.gates.sales_calibration == "fail"
    assert _BUDGET_RANK[snapshot.budget_permission_state] <= _BUDGET_RANK["shadow_only"]
    assert snapshot.budget_can_change is False


def test_real_sales_with_budget_isolated_false_cannot_approve_budget() -> None:
    snapshot = _snapshot_with_sales(
        SourceEvidence(
            status="connected",
            signal=0.90,
            reliability=0.9,
            coverage=0.9,
            real_sell_out=True,
            historical_weeks=12,
            region_count=4,
            holdout_validated=True,
            budget_isolated=False,
            causal_adjusted=False,
            oos_lift_predictiveness=0.15,
        )
    )

    assert snapshot.commercial_relevance_score is None
    assert snapshot.gates.sales_calibration == "fail"
    assert _BUDGET_RANK[snapshot.budget_permission_state] <= _BUDGET_RANK["shadow_only"]
    assert snapshot.budget_can_change is False


def test_real_sales_with_budget_isolation_and_validation_allows_limited_only() -> None:
    snapshot = _snapshot_with_sales(
        SourceEvidence(
            status="connected",
            signal=0.90,
            reliability=0.9,
            coverage=0.9,
            real_sell_out=True,
            historical_weeks=12,
            region_count=4,
            holdout_validated=True,
            budget_isolated=True,
            causal_adjusted=False,
            oos_lift_predictiveness=0.15,
        )
    )

    assert snapshot.commercial_relevance_score is not None
    assert snapshot.gates.sales_calibration == "pass"
    assert snapshot.gates.budget_isolation == "pass"
    assert snapshot.budget_permission_state == "limited"
    assert snapshot.budget_can_change is False
