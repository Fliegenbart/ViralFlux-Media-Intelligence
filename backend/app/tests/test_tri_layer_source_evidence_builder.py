from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.services.research.tri_layer.source_evidence_builder import (
    aggregate_source_evidence_by_region,
    build_source_evidence_from_panel,
)


def _panel() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source": "wastewater",
                "source_detail": "wastewater_aggregated:national_fallback",
                "virus_typ": "Influenza A",
                "region_code": "DE",
                "region_name": "Deutschland",
                "signal_date": datetime(2024, 1, 1),
                "available_at": datetime(2024, 1, 2),
                "value_raw": 10.0,
                "value_normalized": 0.0,
                "baseline": 10.0,
                "intensity": 0.5,
                "growth_7d": None,
                "acceleration_7d": None,
                "freshness_days": 20.0,
                "coverage": 0.5,
                "revision_risk": 0.05,
                "usable_confidence": 0.35,
                "is_point_in_time_safe": True,
                "point_in_time_note": None,
            },
            {
                "source": "wastewater",
                "source_detail": "wastewater_aggregated:national_fallback",
                "virus_typ": "Influenza A",
                "region_code": "DE",
                "region_name": "Deutschland",
                "signal_date": datetime(2024, 1, 8),
                "available_at": datetime(2024, 1, 9),
                "value_raw": 20.0,
                "value_normalized": 0.646627,
                "baseline": 10.0,
                "intensity": 0.65625,
                "growth_7d": 1.0,
                "acceleration_7d": None,
                "freshness_days": 13.0,
                "coverage": 0.5,
                "revision_risk": 0.05,
                "usable_confidence": 0.45,
                "is_point_in_time_safe": True,
                "point_in_time_note": None,
            },
            {
                "source": "wastewater",
                "source_detail": "wastewater_aggregated:national_fallback",
                "virus_typ": "Influenza A",
                "region_code": "DE",
                "region_name": "Deutschland",
                "signal_date": datetime(2024, 1, 15),
                "available_at": datetime(2024, 1, 16),
                "value_raw": 40.0,
                "value_normalized": 0.71784,
                "baseline": 20.0,
                "intensity": 0.67213,
                "growth_7d": 1.0,
                "acceleration_7d": 0.0,
                "freshness_days": 6.0,
                "coverage": 0.5,
                "revision_risk": 0.05,
                "usable_confidence": 0.55,
                "is_point_in_time_safe": True,
                "point_in_time_note": None,
            },
            {
                "source": "wastewater",
                "source_detail": "wastewater_aggregated:national_fallback",
                "virus_typ": "Influenza A",
                "region_code": "DE",
                "region_name": "Deutschland",
                "signal_date": datetime(2024, 1, 22),
                "available_at": datetime(2024, 1, 23),
                "value_raw": 999.0,
                "value_normalized": 5.0,
                "baseline": 20.0,
                "intensity": 0.99,
                "growth_7d": 24.0,
                "acceleration_7d": 23.0,
                "freshness_days": 0.0,
                "coverage": 0.5,
                "revision_risk": 0.05,
                "usable_confidence": 0.90,
                "is_point_in_time_safe": True,
                "point_in_time_note": None,
            },
        ]
    )


def test_build_source_evidence_from_panel_uses_latest_visible_wastewater_row() -> None:
    evidence = build_source_evidence_from_panel(
        _panel(),
        source="wastewater",
        region_code="DE",
        virus_typ="Influenza A",
        cutoff=datetime(2024, 1, 20),
    )

    assert evidence.status == "connected"
    assert evidence.signal is not None
    assert 0.55 < evidence.signal < 0.80
    assert evidence.intensity == 0.67213
    assert evidence.growth == 1.0
    assert 0.60 < (evidence.freshness or 0.0) < 0.70
    assert evidence.coverage == 0.5
    assert evidence.snr is not None
    assert evidence.baseline_stability is not None
    assert evidence.consistency is not None
    assert evidence.drift == 0.05
    assert evidence.reliability == 0.55


def test_build_source_evidence_from_panel_keeps_missing_wastewater_not_connected() -> None:
    evidence = build_source_evidence_from_panel(
        _panel(),
        source="wastewater",
        region_code="HH",
        virus_typ="Influenza A",
        cutoff=datetime(2024, 1, 20),
    )

    assert evidence.status == "not_connected"
    assert evidence.signal is None
    assert evidence.intensity is None
    assert evidence.growth is None


def test_national_wastewater_fallback_requires_explicit_opt_in() -> None:
    evidence = build_source_evidence_from_panel(
        _panel(),
        source="wastewater",
        region_code="HH",
        virus_typ="Influenza A",
        cutoff=datetime(2024, 1, 20),
        allow_national_fallback=True,
    )

    assert evidence.status == "partial"
    assert evidence.signal is not None
    assert evidence.coverage is not None
    assert evidence.coverage < 1.0


def test_future_wastewater_rows_are_ignored_for_cutoff() -> None:
    evidence = build_source_evidence_from_panel(
        _panel(),
        source="wastewater",
        region_code="DE",
        virus_typ="Influenza A",
        cutoff=datetime(2024, 1, 20),
    )

    assert evidence.signal is not None
    assert evidence.signal < 0.90
    assert evidence.growth == 1.0


def test_aggregate_source_evidence_by_region_groups_sources() -> None:
    aggregate = aggregate_source_evidence_by_region(
        _panel(),
        virus_typ="Influenza A",
        cutoff=datetime(2024, 1, 20),
    )

    assert "DE" in aggregate
    assert aggregate["DE"]["wastewater"].status == "connected"
