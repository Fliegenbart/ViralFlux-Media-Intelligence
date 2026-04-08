"""Contracts for the experimental county/cluster forecast path."""

from __future__ import annotations

from typing import Any


EXPERIMENTAL_GEO_LEVEL = "kreis_cluster"
EXPERIMENTAL_TRUTH_RESOLUTION = "landkreis"
EXPERIMENTAL_FEATURE_RESOLUTION = "landkreis_truth_only"
EXPERIMENTAL_RECONCILIATION_TARGET_LEVEL = "bundesland"
EXPERIMENTAL_CLAIM_SCOPE = "experimental_cluster_level_only"
EXPERIMENTAL_ROLLOUT_MODE = "shadow"
EXPERIMENTAL_ACTIVATION_POLICY = "watch_only"
EXPERIMENTAL_MODEL_FAMILY = "experimental_kreis_cluster_shadow_v1"
EXPERIMENTAL_GUARDRAIL_MESSAGE = (
    "Experimenteller Geo-Pfad auf Cluster-Ebene. Keine Stadt- oder Landkreis-Freigabe für Produktion. "
    "Keine automatische Ableitung aus Bundesland-Forecasts."
)


def experimental_geo_contract() -> dict[str, Any]:
    return {
        "geo_level": EXPERIMENTAL_GEO_LEVEL,
        "truth_resolution": EXPERIMENTAL_TRUTH_RESOLUTION,
        "feature_resolution": EXPERIMENTAL_FEATURE_RESOLUTION,
        "reconciliation_target_level": EXPERIMENTAL_RECONCILIATION_TARGET_LEVEL,
        "experimental": True,
        "production_ready": False,
        "rollout_mode": EXPERIMENTAL_ROLLOUT_MODE,
        "activation_policy": EXPERIMENTAL_ACTIVATION_POLICY,
        "promotion_allowed": False,
        "claim_scope": EXPERIMENTAL_CLAIM_SCOPE,
        "claim_guardrail_message": EXPERIMENTAL_GUARDRAIL_MESSAGE,
    }
