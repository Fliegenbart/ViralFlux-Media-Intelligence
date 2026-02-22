"""OTC-relevante Krankheitscluster für SurvStat-Daten.

Definiert die Whitelist der für Pharma-OTC-Marketing relevanten
Krankheiten aus dem RKI SurvStat-System, gruppiert in 4 strategische
Makro-Cluster. Alle Krankheiten, die nicht in dieser Liste stehen,
werden beim Import verworfen.

Verwendung:
- survstat_service.py: Filtering beim Ingest
- ai_campaign_planner.py: Creative Routing (welches Banner?)
- backtester.py: Ground-Truth-Daten für XGBoost-Training
- forecast_service.py: Demografische Kaskaden-Features
"""

from __future__ import annotations

import logging
from typing import Final

import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
#  OTC DISEASE CLUSTERS
# ═══════════════════════════════════════════════════════════════════════

OTC_RELEVANT_DISEASES: Final[dict[str, list[str]]] = {
    "RESPIRATORY": [
        "Influenza, saisonal",
        "COVID-19",
        "RSV (Meldepflicht gemäß IfSG)",
        "RSV (Meldepflicht gemäß Landesmeldeverordnung)",
        "Mycoplasma",
        "Keuchhusten (Meldepflicht gemäß IfSG)",
        "Keuchhusten (Meldepflicht gemäß Landesmeldeverordnung)",
        "Pneumokokken (Meldepflicht gemäß IfSG)",
        "Pneumokokken (Meldepflicht gemäß Landesverordnung)",
        "Adenovirus (andere Form, Meldepflichtig gemäß Landesmeldeverordnung)",
        "Parainfluenza",
    ],
    "GASTROINTESTINAL": [
        "Norovirus-Gastroenteritis",
        "Rotavirus-Gastroenteritis",
        "Campylobacter-Enteritis",
        "Salmonellose",
    ],
    "PEDIATRIC_SKIN": [
        "Hand-Fuß-Mund-Krankheit",
        "Scharlach",
        "Ringelröteln",
        "Windpocken",
        "Windpocken (Meldepflicht gemäß Landesmeldeverordnung)",
    ],
    "PARASITES_VECTORS": [
        "Kopflausbefall",
        "FSME (Frühsommer-Meningoenzephalitis)",
        "Borreliose",
        "Krätzmilbenbefall",
    ],
}

# Flat set for O(1) lookup
ALL_OTC_DISEASES: Final[set[str]] = {
    disease for diseases in OTC_RELEVANT_DISEASES.values() for disease in diseases
}

# Reverse mapping: disease name → cluster
_DISEASE_TO_CLUSTER: Final[dict[str, str]] = {
    disease: cluster
    for cluster, diseases in OTC_RELEVANT_DISEASES.items()
    for disease in diseases
}


def disease_to_cluster(name: str) -> str | None:
    """Map a RKI disease name to its OTC macro-cluster.

    Returns None if the disease is not OTC-relevant (→ should be discarded).
    Handles exact match first, then case-insensitive substring fallback
    for minor RKI naming variations.
    """
    if not name:
        return None

    # Exact match (fast path)
    cluster = _DISEASE_TO_CLUSTER.get(name)
    if cluster:
        return cluster

    # Fuzzy fallback: case-insensitive substring match
    name_lower = name.lower().strip()
    for disease, cluster in _DISEASE_TO_CLUSTER.items():
        if disease.lower() in name_lower or name_lower in disease.lower():
            return cluster

    return None


def is_otc_relevant(disease: str) -> bool:
    """Check if a disease name is in the OTC whitelist."""
    return disease_to_cluster(disease) is not None


# ═══════════════════════════════════════════════════════════════════════
#  ML UTILITIES
# ═══════════════════════════════════════════════════════════════════════


def calculate_trailing_trend(
    db: Session,
    bundesland: str,
    disease_cluster: str,
    weeks_back: int = 3,
) -> float:
    """Calculate percentage momentum of a disease cluster over the last N weeks.

    Used by ai_campaign_planner.py for Creative Routing:
    - If PEDIATRIC_SKIN momentum is +300%, route child-fever creative
    - If RESPIRATORY momentum is +50%, route adult-cough creative

    Returns percentage change (e.g., 0.5 = +50%, -0.3 = -30%).
    Returns 0.0 if insufficient data.
    """
    from app.models.database import SurvstatWeeklyData

    # Get the last N+1 weeks of aggregated incidence for this cluster
    rows = (
        db.query(
            SurvstatWeeklyData.week_label,
            func.sum(SurvstatWeeklyData.incidence).label("total_incidence"),
        )
        .filter(
            SurvstatWeeklyData.disease_cluster == disease_cluster,
            SurvstatWeeklyData.bundesland == bundesland,
        )
        .group_by(SurvstatWeeklyData.week_label)
        .order_by(SurvstatWeeklyData.week_label.desc())
        .limit(weeks_back + 1)
        .all()
    )

    if len(rows) < 2:
        return 0.0

    # rows are DESC-ordered: rows[0] = latest, rows[-1] = oldest
    latest = rows[0].total_incidence or 0.0
    oldest = rows[-1].total_incidence or 0.0

    if oldest == 0:
        return 1.0 if latest > 0 else 0.0

    return (latest - oldest) / oldest


def create_demographic_cascade_feature(
    df: pd.DataFrame,
    shift_days: int = 14,
) -> pd.Series:
    """Create a leading indicator from pediatric disease time series.

    Epidemiological rationale: Respiratory infections in children (0-4 years)
    precede adult infections by 2-3 weeks. Shifting the pediatric time series
    forward by 14 days creates a feature that LEADS the adult target variable.

    Args:
        df: DataFrame with columns 'ds' (datetime) and 'y' (incidence).
            Should be filtered to pediatric age group (0-4 or 0-14).
        shift_days: Number of days to shift forward (default: 14).

    Returns:
        pd.Series: Time-shifted incidence values, aligned to the original
        date index. Use as XGBoost feature alongside wastewater/trends data.
    """
    if df.empty or "ds" not in df.columns or "y" not in df.columns:
        return pd.Series(dtype=float)

    df_sorted = df.sort_values("ds").copy()
    df_sorted["ds"] = pd.to_datetime(df_sorted["ds"])

    # Detect data frequency
    diffs = df_sorted["ds"].diff().dt.days.dropna()
    freq_days = int(diffs.median()) if len(diffs) > 0 else 7
    freq_days = max(1, freq_days)

    # Number of periods to shift
    shift_periods = max(1, shift_days // freq_days)

    shifted = df_sorted["y"].shift(-shift_periods)
    shifted.index = df_sorted.index

    return shifted.rename("pediatric_cascade")
