from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

ExogenousFeatureCategory = Literal[
    "observed_as_of_only",
    "issue_time_forecast_allowed",
    "forbidden_for_training_or_inference",
]

EXOGENOUS_FEATURE_SEMANTICS_VERSION = "regional_exogenous_semantics_v1"


@dataclass(frozen=True)
class ExogenousFeatureContract:
    feature_id: str
    category: ExogenousFeatureCategory
    description: str
    issue_time_required: bool = False
    issue_time_columns: tuple[str, ...] = ()


EXOGENOUS_FEATURE_CONTRACTS: dict[str, ExogenousFeatureContract] = {
    "sars_corona_test_trends": ExogenousFeatureContract(
        feature_id="sars_corona_test_trends",
        category="observed_as_of_only",
        description="Observed national search interest is only allowed up to the as-of date.",
    ),
    "pollen_context": ExogenousFeatureContract(
        feature_id="pollen_context",
        category="observed_as_of_only",
        description="Observed pollen context is only allowed up to the as-of date.",
    ),
    "holiday_calendar": ExogenousFeatureContract(
        feature_id="holiday_calendar",
        category="issue_time_forecast_allowed",
        description="School holiday calendars are deterministic and may be used for future target windows.",
        issue_time_required=False,
    ),
    "weather_daily_forecast": ExogenousFeatureContract(
        feature_id="weather_daily_forecast",
        category="issue_time_forecast_allowed",
        description=(
            "Future weather context is only allowed when the forecast rows carry an explicit "
            "issue-time or forecast-run timestamp known by the as-of date."
        ),
        issue_time_required=True,
        issue_time_columns=("issue_time", "forecast_run_time", "issued_at"),
    ),
    "realized_future_exogenous_values": ExogenousFeatureContract(
        feature_id="realized_future_exogenous_values",
        category="forbidden_for_training_or_inference",
        description="Realized future exogenous values must never be used for training or inference.",
    ),
}


def exogenous_feature_semantics_manifest() -> dict[str, Any]:
    return {
        "version": EXOGENOUS_FEATURE_SEMANTICS_VERSION,
        "feature_categories": {
            feature_id: {
                "category": contract.category,
                "issue_time_required": bool(contract.issue_time_required),
            }
            for feature_id, contract in EXOGENOUS_FEATURE_CONTRACTS.items()
        },
    }


def observed_as_of_only_rows(
    frame: pd.DataFrame | None,
    *,
    as_of: pd.Timestamp,
    datum_column: str = "datum",
    available_time_column: str = "available_time",
) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    visible = frame.copy()
    if available_time_column in visible.columns:
        visible = visible.loc[visible[available_time_column] <= as_of].copy()
    if datum_column in visible.columns:
        visible = visible.loc[visible[datum_column] <= as_of].copy()
    return visible.reset_index(drop=True)


def issue_time_forecast_rows(
    frame: pd.DataFrame | None,
    *,
    as_of: pd.Timestamp,
    contract: ExogenousFeatureContract,
    datum_column: str = "datum",
    available_time_column: str = "available_time",
) -> pd.DataFrame:
    if frame is None:
        return pd.DataFrame()
    if frame.empty:
        return frame.iloc[0:0].copy()
    if contract.category != "issue_time_forecast_allowed":
        raise ValueError(
            f"Feature contract {contract.feature_id} does not allow issue-time forecast rows."
        )
    visible = frame.copy()
    if available_time_column in visible.columns:
        visible = visible.loc[visible[available_time_column] <= as_of].copy()
    if datum_column in visible.columns:
        visible = visible.loc[visible[datum_column] > as_of].copy()
    if visible.empty:
        return visible.reset_index(drop=True)
    if not contract.issue_time_required:
        return visible.reset_index(drop=True)
    for issue_time_column in contract.issue_time_columns:
        if issue_time_column not in visible.columns:
            continue
        eligible = visible.loc[
            visible[issue_time_column].notna()
            & (visible[issue_time_column] <= as_of)
        ].copy()
        if not eligible.empty:
            return eligible.reset_index(drop=True)
    return visible.iloc[0:0].copy().reset_index(drop=True)
