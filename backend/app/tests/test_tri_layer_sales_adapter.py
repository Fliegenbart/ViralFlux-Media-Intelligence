from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.services.research.tri_layer.sales_adapter import load_sales_panel
from app.services.research.tri_layer.schema import (
    BudgetIsolationEvidence,
    SourceEvidence,
    TriLayerRegionEvidence,
)
from app.services.research.tri_layer.service import build_region_snapshot


def _session():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    return engine, SessionLocal()


def test_missing_sales_tables_returns_not_connected() -> None:
    engine, db = _session()
    try:
        panel = load_sales_panel(db, brand="gelo", virus_typ="Influenza A", cutoff=date(2026, 4, 30))
    finally:
        db.close()
        engine.dispose()

    assert panel.rows.empty
    assert panel.status.status == "not_connected"
    assert panel.status.coverage is None
    assert panel.budget_isolated is False
    assert panel.causal_adjusted is False
    assert panel.status.reason == "No brand-level sell-out data source connected."


def test_connected_candidate_table_missing_required_columns_returns_partial() -> None:
    engine, db = _session()
    try:
        db.execute(text("CREATE TABLE otc_sell_out (week_start TEXT, brand TEXT, product TEXT)"))
        db.commit()

        panel = load_sales_panel(db, brand="gelo", virus_typ="Influenza A", cutoff=date(2026, 4, 30))
    finally:
        db.close()
        engine.dispose()

    assert panel.rows.empty
    assert panel.status.status == "partial"
    assert "missing required columns" in panel.status.reason


def test_connected_candidate_table_with_required_columns_returns_normalized_panel() -> None:
    engine, db = _session()
    try:
        db.execute(text(
            """
            CREATE TABLE otc_sell_out (
                window_start TEXT,
                window_end TEXT,
                region_code TEXT,
                metric_name TEXT,
                metric_value FLOAT,
                brand TEXT,
                product TEXT,
                source_label TEXT,
                channel TEXT,
                holdout_group TEXT,
                budget_isolated BOOLEAN,
                causal_adjusted BOOLEAN,
                stockout FLOAT
            )
            """
        ))
        for offset, region, holdout in (
            (0, "HH", "test"),
            (7, "BE", "control"),
            (14, "BY", "test"),
            (21, "NW", "control"),
            (28, "HH", "test"),
            (35, "BE", "control"),
            (42, "BY", "test"),
            (49, "NW", "control"),
        ):
            db.execute(text(
                """
                INSERT INTO otc_sell_out
                (
                    window_start, window_end, region_code, metric_name, metric_value,
                    brand, product, source_label, channel, holdout_group,
                    budget_isolated, causal_adjusted, stockout
                )
                VALUES (
                    date('2026-02-02', :offset || ' days'),
                    date('2026-02-08', :offset || ' days'),
                    :region,
                    'sell_out_units',
                    120.0,
                    'gelo',
                    'GeloMyrtol',
                    'gelo_pos_panel',
                    'pharmacy',
                    :holdout,
                    1,
                    0,
                    0.0
                )
                """
            ), {"offset": offset, "region": region, "holdout": holdout})
        db.commit()

        panel = load_sales_panel(db, brand="gelo", virus_typ="Influenza A", cutoff=date(2026, 4, 30))
    finally:
        db.close()
        engine.dispose()

    assert panel.status.status == "connected"
    assert panel.status.coverage == 0.25
    assert int(panel.rows.iloc[0]["units"]) == 120
    assert set(panel.rows["region_code"]) == {"HH", "BE", "BY", "NW"}
    assert panel.budget_isolated is True
    assert panel.causal_adjusted is False
    assert panel.holdout_validated is True
    assert panel.historical_weeks >= 8
    assert panel.region_count == 4
    assert "stockout" in panel.known_confounders


def test_connected_sales_without_real_sell_out_metadata_is_not_available() -> None:
    snapshot = build_region_snapshot(
        TriLayerRegionEvidence(
            region="Hamburg",
            region_code="HH",
            wastewater=SourceEvidence(status="connected", signal=0.9, intensity=0.8, growth=0.2),
            clinical=SourceEvidence(status="connected", signal=0.88, intensity=0.75, growth=0.15),
            sales=SourceEvidence(status="connected", signal=0.9, budget_isolated=False, causal_adjusted=False),
            budget_isolation=BudgetIsolationEvidence(status="pass"),
        )
    )

    assert snapshot.commercial_relevance_score is None
    assert snapshot.gates.sales_calibration == "not_available"
    assert snapshot.gates.budget_isolation == "not_available"
    assert snapshot.budget_permission_state in {"shadow_only", "calibration_window"}
    assert snapshot.budget_can_change is False


def test_causal_adjusted_true_can_allow_sales_calibration_gate() -> None:
    snapshot = build_region_snapshot(
        TriLayerRegionEvidence(
            region="Hamburg",
            region_code="HH",
            wastewater=SourceEvidence(status="connected", signal=0.9, intensity=0.8, growth=0.2),
            clinical=SourceEvidence(status="connected", signal=0.88, intensity=0.75, growth=0.15),
            sales=SourceEvidence(
                status="connected",
                signal=0.9,
                budget_isolated=False,
                causal_adjusted=True,
                real_sell_out=True,
                holdout_validated=True,
                historical_weeks=12,
                region_count=4,
                oos_lift_predictiveness=0.12,
            ),
            budget_isolation=BudgetIsolationEvidence(status="pass"),
        )
    )

    assert snapshot.gates.sales_calibration == "pass"
    assert snapshot.budget_permission_state == "limited"
    assert snapshot.budget_can_change is False
