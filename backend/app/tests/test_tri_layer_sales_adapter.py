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
                date TEXT,
                region_code TEXT,
                units FLOAT,
                brand TEXT,
                product TEXT,
                channel TEXT,
                budget_isolated BOOLEAN,
                causal_adjusted BOOLEAN,
                stockout FLOAT
            )
            """
        ))
        db.execute(text(
            """
            INSERT INTO otc_sell_out
            (date, region_code, units, brand, product, channel, budget_isolated, causal_adjusted, stockout)
            VALUES ('2026-04-20', 'HH', 120.0, 'gelo', 'GeloMyrtol', 'pharmacy', 1, 0, 0.0)
            """
        ))
        db.commit()

        panel = load_sales_panel(db, brand="gelo", virus_typ="Influenza A", cutoff=date(2026, 4, 30))
    finally:
        db.close()
        engine.dispose()

    assert panel.status.status == "connected"
    assert panel.status.coverage == 1.0
    assert int(panel.rows.iloc[0]["units"]) == 120
    assert panel.rows.iloc[0]["region_code"] == "HH"
    assert panel.budget_isolated is True
    assert panel.causal_adjusted is False
    assert "stockout" in panel.known_confounders


def test_budget_isolated_false_blocks_sales_calibration_gate() -> None:
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

    assert snapshot.gates.sales_calibration == "fail"
    assert snapshot.budget_permission_state == "shadow_only"
    assert snapshot.budget_can_change is False


def test_causal_adjusted_true_can_allow_sales_calibration_gate() -> None:
    snapshot = build_region_snapshot(
        TriLayerRegionEvidence(
            region="Hamburg",
            region_code="HH",
            wastewater=SourceEvidence(status="connected", signal=0.9, intensity=0.8, growth=0.2),
            clinical=SourceEvidence(status="connected", signal=0.88, intensity=0.75, growth=0.15),
            sales=SourceEvidence(status="connected", signal=0.9, budget_isolated=False, causal_adjusted=True),
            budget_isolation=BudgetIsolationEvidence(status="pass"),
        )
    )

    assert snapshot.gates.sales_calibration == "pass"
