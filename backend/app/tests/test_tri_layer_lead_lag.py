from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from app.services.research.tri_layer.lead_lag import (
    estimate_lead_lag,
    estimate_source_pair_lag_distribution,
)
from app.services.research.tri_layer.schema import SourceEvidence, TriLayerRegionEvidence
from app.services.research.tri_layer.service import build_region_snapshot
from app.services.media.cockpit.tri_layer_evidence import (
    TriLayerSourceStatus,
    TriLayerSourceStatusItem,
    _regions_from_forecast,
)


def _panel_with_lag(*, lag_days: int = 5, include_future: bool = False) -> pd.DataFrame:
    start = datetime(2024, 1, 1)
    wastewater_values = [0.0] * 14 + [float(index + 1) for index in range(16)] + [16.0] * 10
    rows: list[dict[str, object]] = []
    for index, value in enumerate(wastewater_values):
        signal_date = start + timedelta(days=index)
        rows.append(
            {
                "source": "wastewater",
                "source_detail": "synthetic",
                "virus_typ": "Influenza A",
                "region_code": "HH",
                "region_name": "Hamburg",
                "signal_date": signal_date,
                "available_at": signal_date,
                "value_raw": value,
                "value_normalized": value,
                "baseline": 0.0,
                "intensity": None,
                "growth_7d": None,
                "acceleration_7d": None,
                "freshness_days": None,
                "coverage": 1.0,
                "revision_risk": 0.05,
                "usable_confidence": 0.8,
                "is_point_in_time_safe": True,
                "point_in_time_note": None,
            }
        )
        clinical_index = index + lag_days
        clinical_date = start + timedelta(days=clinical_index)
        rows.append(
            {
                "source": "survstat",
                "source_detail": "synthetic",
                "virus_typ": "Influenza A",
                "region_code": "HH",
                "region_name": "Hamburg",
                "signal_date": clinical_date,
                "available_at": clinical_date,
                "value_raw": value,
                "value_normalized": value,
                "baseline": 0.0,
                "intensity": None,
                "growth_7d": None,
                "acceleration_7d": None,
                "freshness_days": None,
                "coverage": 1.0,
                "revision_risk": 0.05,
                "usable_confidence": 0.8,
                "is_point_in_time_safe": True,
                "point_in_time_note": None,
            }
        )
    if include_future:
        future = start + timedelta(days=60)
        rows.extend(
            [
                {
                    "source": "wastewater",
                    "source_detail": "synthetic",
                    "virus_typ": "Influenza A",
                    "region_code": "HH",
                    "region_name": "Hamburg",
                    "signal_date": future,
                    "available_at": future,
                    "value_raw": 999.0,
                    "value_normalized": 999.0,
                    "baseline": 0.0,
                    "intensity": None,
                    "growth_7d": None,
                    "acceleration_7d": None,
                    "freshness_days": None,
                    "coverage": 1.0,
                    "revision_risk": 0.05,
                    "usable_confidence": 0.8,
                    "is_point_in_time_safe": True,
                    "point_in_time_note": None,
                },
                {
                    "source": "survstat",
                    "source_detail": "synthetic",
                    "virus_typ": "Influenza A",
                    "region_code": "HH",
                    "region_name": "Hamburg",
                    "signal_date": future + timedelta(days=21),
                    "available_at": future + timedelta(days=21),
                    "value_raw": 999.0,
                    "value_normalized": 999.0,
                    "baseline": 0.0,
                    "intensity": None,
                    "growth_7d": None,
                    "acceleration_7d": None,
                    "freshness_days": None,
                    "coverage": 1.0,
                    "revision_risk": 0.05,
                    "usable_confidence": 0.8,
                    "is_point_in_time_safe": True,
                    "point_in_time_note": None,
                },
            ]
        )
    return pd.DataFrame(rows)


def test_synthetic_wastewater_leads_clinical_by_five_days() -> None:
    distribution = estimate_source_pair_lag_distribution(
        _panel_with_lag(lag_days=5),
        source_a="wastewater",
        source_b="survstat",
        region_code="HH",
        virus_typ="Influenza A",
        cutoff=datetime(2024, 2, 20),
        max_lag_days=14,
        min_pairs=8,
    )

    assert distribution.status == "estimated"
    assert distribution.mode_days == 5
    assert distribution.mean_days is not None
    assert 4.0 <= distribution.mean_days <= 6.5
    assert distribution.n_pairs >= 8


def test_no_panel_data_returns_not_available() -> None:
    distribution = estimate_source_pair_lag_distribution(
        pd.DataFrame(),
        source_a="wastewater",
        source_b="survstat",
        region_code="HH",
        virus_typ="Influenza A",
        cutoff=datetime(2024, 2, 20),
    )

    assert distribution.status == "not_available"
    assert distribution.mean_days is None
    assert distribution.n_pairs == 0


def test_flat_data_returns_flat_correlation_with_high_uncertainty() -> None:
    flat_panel = _panel_with_lag(lag_days=5)
    flat_panel["value_raw"] = 1.0
    flat_panel["value_normalized"] = 1.0

    distribution = estimate_source_pair_lag_distribution(
        flat_panel,
        source_a="wastewater",
        source_b="survstat",
        region_code="HH",
        virus_typ="Influenza A",
        cutoff=datetime(2024, 2, 20),
        max_lag_days=14,
        min_pairs=8,
    )

    assert distribution.status == "flat_correlation"
    assert distribution.uncertainty is not None
    assert distribution.uncertainty >= 0.9


def test_future_rows_after_cutoff_are_ignored() -> None:
    distribution = estimate_source_pair_lag_distribution(
        _panel_with_lag(lag_days=5, include_future=True),
        source_a="wastewater",
        source_b="survstat",
        region_code="HH",
        virus_typ="Influenza A",
        cutoff=datetime(2024, 2, 20),
        max_lag_days=14,
        min_pairs=8,
    )

    assert distribution.status == "estimated"
    assert distribution.mode_days == 5


def test_estimate_lead_lag_does_not_emit_fixed_sales_lag_without_sales_panel() -> None:
    estimate = estimate_lead_lag(
        wastewater=SourceEvidence(status="connected"),
        clinical=SourceEvidence(status="connected"),
        sales=SourceEvidence(status="not_connected"),
        panel=_panel_with_lag(lag_days=5),
        virus_typ="Influenza A",
        region_code="HH",
        cutoff=datetime(2024, 2, 20),
    )

    assert estimate.wastewater_to_clinical_days_mean is not None
    assert 4.0 <= estimate.wastewater_to_clinical_days_mean <= 6.5
    assert estimate.clinical_to_sales_days_mean is None


def test_region_snapshot_uses_panel_for_dynamic_wastewater_clinical_lag() -> None:
    snapshot = build_region_snapshot(
        TriLayerRegionEvidence(
            region="Hamburg",
            region_code="HH",
            wastewater=SourceEvidence(status="connected", signal=0.8, growth=0.2, intensity=0.7),
            clinical=SourceEvidence(status="connected", signal=0.75, growth=0.15, intensity=0.65),
            sales=SourceEvidence(status="not_connected"),
        ),
        observation_panel=_panel_with_lag(lag_days=5),
        virus_typ="Influenza A",
        cutoff=datetime(2024, 2, 20),
    )

    assert snapshot.lead_lag.wastewater_to_clinical_days_mean is not None
    assert 4.0 <= snapshot.lead_lag.wastewater_to_clinical_days_mean <= 6.5
    assert snapshot.lead_lag.clinical_to_sales_days_mean is None


def test_cockpit_region_wiring_exposes_dynamic_lag_from_panel() -> None:
    regions = _regions_from_forecast(
        {
            "virus_typ": "Influenza A",
            "predictions": [
                {
                    "bundesland": "HH",
                    "bundesland_name": "Hamburg",
                    "decision": {},
                    "prediction_interval": {},
                }
            ],
        },
        source_status=TriLayerSourceStatus(
            wastewater=TriLayerSourceStatusItem(status="connected"),
            clinical=TriLayerSourceStatusItem(status="connected"),
            sales=TriLayerSourceStatusItem(status="not_connected"),
        ),
        observation_panel=_panel_with_lag(lag_days=5),
        clinical_evidence_by_region={
            "HH": SourceEvidence(status="connected", signal=0.75, growth=0.15, intensity=0.65)
        },
        cutoff=datetime(2024, 2, 20),
        virus_typ="Influenza A",
    )

    assert len(regions) == 1
    assert regions[0].lead_lag.wastewater_to_clinical_days_mean is not None
    assert 4.0 <= regions[0].lead_lag.wastewater_to_clinical_days_mean <= 6.5
    assert regions[0].lead_lag.clinical_to_sales_days_mean is None
