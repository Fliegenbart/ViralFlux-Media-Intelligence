"""Experimental county/cluster shadow path for finer geo signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from app.core.time import utc_now
from app.services.ml.experimental_geo_contracts import (
    EXPERIMENTAL_ACTIVATION_POLICY,
    EXPERIMENTAL_GEO_LEVEL,
    EXPERIMENTAL_MODEL_FAMILY,
    EXPERIMENTAL_ROLLOUT_MODE,
    experimental_geo_contract,
)
from app.services.ml.forecast_horizon_utils import SUPPORTED_FORECAST_HORIZONS, ensure_supported_horizon
from app.services.ml.models.geo_hierarchy import GeoHierarchyHelper
from app.services.ml.regional_features import RegionalFeatureBuilder
from app.services.ml.regional_panel_utils import BUNDESLAND_NAMES, seasonal_baseline_and_mad


@dataclass(frozen=True)
class _ExperimentalGeoSummary:
    unit_count: int
    eligible_unit_count: int
    cluster_count: int
    latest_week_start: str | None
    latest_available_date: str | None
    coverage_ratio: float


class ExperimentalGeoForecastService:
    """Experimental county/cluster ranking path that never promotes to production."""

    def __init__(self, db) -> None:
        self.db = db
        self.feature_builder = RegionalFeatureBuilder(db)

    def predict_clusters(
        self,
        *,
        virus_typ: str = "Influenza A",
        horizon_days: int = 7,
        geo_level: str = EXPERIMENTAL_GEO_LEVEL,
        as_of_date: datetime | None = None,
        cluster_count: int = 6,
    ) -> dict[str, Any]:
        horizon = ensure_supported_horizon(horizon_days)
        contract = experimental_geo_contract()
        requested_geo_level = str(geo_level or "").strip().lower()
        if requested_geo_level != EXPERIMENTAL_GEO_LEVEL:
            return self._empty_response(
                virus_typ=virus_typ,
                horizon_days=horizon,
                status="unsupported_public_scope",
                message=(
                    "Der experimentelle Geo-Pfad ist öffentlich nur auf Cluster-Ebene verfügbar. "
                    "Landkreis- oder Stadt-Sicht wird nicht als Forecast-Endpunkt freigegeben."
                ),
                geo_level=requested_geo_level or EXPERIMENTAL_GEO_LEVEL,
                summary=None,
            )

        start_date = pd.Timestamp(as_of_date or utc_now()).normalize() - pd.Timedelta(days=540)
        truth = self.feature_builder.load_landkreis_truth_series(
            virus_typ=virus_typ,
            start_date=start_date,
        )
        if truth.empty:
            return self._empty_response(
                virus_typ=virus_typ,
                horizon_days=horizon,
                status="insufficient_geo_truth",
                message=(
                    "Keine belastbare Landkreis-Truth für den experimentellen Geo-Pfad verfügbar."
                ),
                geo_level=EXPERIMENTAL_GEO_LEVEL,
                summary=None,
            )

        resolved_as_of = self._resolve_as_of_date(truth, requested_as_of=as_of_date)
        visible_truth = truth.loc[truth["available_date"] <= resolved_as_of].copy()
        if visible_truth.empty:
            return self._empty_response(
                virus_typ=virus_typ,
                horizon_days=horizon,
                status="insufficient_geo_truth",
                message=(
                    "Zum angefragten Datenstand ist noch keine sichtbare Landkreis-Truth für den "
                    "experimentellen Geo-Pfad verfügbar."
                ),
                geo_level=EXPERIMENTAL_GEO_LEVEL,
                summary=None,
            )

        eligible_truth = self._eligible_truth_frame(visible_truth)
        summary = self._coverage_summary(visible_truth=visible_truth, eligible_truth=eligible_truth)
        if eligible_truth["geo_unit_id"].nunique() < 2:
            return self._empty_response(
                virus_typ=virus_typ,
                horizon_days=horizon,
                status="insufficient_geo_truth",
                message=(
                    "Die Landkreis-Abdeckung reicht noch nicht für einen experimentellen Cluster-Shadow-Run."
                ),
                geo_level=EXPERIMENTAL_GEO_LEVEL,
                summary=summary,
            )

        cluster_target = min(max(int(cluster_count), 2), int(eligible_truth["geo_unit_id"].nunique()))
        cluster_assignments = self._build_cluster_assignments(
            eligible_truth=eligible_truth,
            cluster_count=cluster_target,
        )
        if not cluster_assignments:
            return self._empty_response(
                virus_typ=virus_typ,
                horizon_days=horizon,
                status="no_model",
                message=(
                    "Die historische Landkreis-Truth ist sichtbar, aber noch nicht stabil genug für "
                    "einen experimentellen Cluster-Schattenpfad."
                ),
                geo_level=EXPERIMENTAL_GEO_LEVEL,
                summary=summary,
            )

        cluster_payload = self._build_cluster_payload(
            virus_typ=virus_typ,
            horizon_days=horizon,
            as_of_date=resolved_as_of,
            eligible_truth=eligible_truth,
            cluster_assignments=cluster_assignments,
        )
        state_reconciliation = self._build_state_reconciliation(
            eligible_truth=eligible_truth,
            cluster_assignments=cluster_assignments,
        )

        return {
            "status": "success",
            "virus_typ": virus_typ,
            "as_of_date": str(resolved_as_of.date()),
            "horizon_days": horizon,
            "supported_horizon_days": list(SUPPORTED_FORECAST_HORIZONS),
            "target_week_start": str(self.feature_builder._target_week_start(resolved_as_of, horizon).date()),
            "model_family": EXPERIMENTAL_MODEL_FAMILY,
            "signal_semantics": "ranking_signal_shadow_v1",
            "context_feature_resolution": "none",
            "shadow_mode_reason": (
                "Nur echte Landkreis-Truth und clusterbasierte Shadow-Rankings. "
                "Keine Produktion, keine Budgetfreigabe, keine Stadt-Claims."
            ),
            "coverage_summary": {
                **summary.__dict__,
                "cluster_count": len(cluster_payload),
                "latest_week_start": summary.latest_week_start,
                "latest_available_date": summary.latest_available_date,
            },
            "total_clusters": len(cluster_payload),
            "clusters": cluster_payload,
            "top_clusters": cluster_payload[:5],
            "state_reconciliation": state_reconciliation,
            "cluster_assignments": {
                geo_unit_id: cluster_id
                for geo_unit_id, cluster_id in sorted(cluster_assignments.items())
            },
            "generated_at": utc_now().isoformat(),
            **contract,
        }

    def _empty_response(
        self,
        *,
        virus_typ: str,
        horizon_days: int,
        status: str,
        message: str,
        geo_level: str,
        summary: _ExperimentalGeoSummary | None,
    ) -> dict[str, Any]:
        payload = {
            "status": status,
            "virus_typ": virus_typ,
            "horizon_days": int(horizon_days),
            "supported_horizon_days": list(SUPPORTED_FORECAST_HORIZONS),
            "model_family": EXPERIMENTAL_MODEL_FAMILY,
            "signal_semantics": "ranking_signal_shadow_v1",
            "message": message,
            "clusters": [],
            "top_clusters": [],
            "state_reconciliation": [],
            "cluster_assignments": {},
            "coverage_summary": (
                {
                    **summary.__dict__,
                    "latest_week_start": summary.latest_week_start,
                    "latest_available_date": summary.latest_available_date,
                }
                if summary is not None
                else {}
            ),
            "generated_at": utc_now().isoformat(),
            **experimental_geo_contract(),
        }
        payload["geo_level"] = geo_level
        return payload

    @staticmethod
    def _resolve_as_of_date(
        truth: pd.DataFrame,
        *,
        requested_as_of: datetime | None,
    ) -> pd.Timestamp:
        latest_available = pd.Timestamp(truth["available_date"].max()).normalize()
        if requested_as_of is None:
            return latest_available
        requested = pd.Timestamp(requested_as_of).normalize()
        return min(requested, latest_available)

    @staticmethod
    def _eligible_truth_frame(visible_truth: pd.DataFrame) -> pd.DataFrame:
        history_lengths = (
            visible_truth.groupby("geo_unit_id")["week_start"]
            .nunique()
            .rename("history_weeks")
            .reset_index()
        )
        eligible_units = set(
            history_lengths.loc[history_lengths["history_weeks"] >= 8, "geo_unit_id"].astype(str).tolist()
        )
        return (
            visible_truth.loc[visible_truth["geo_unit_id"].astype(str).isin(eligible_units)]
            .sort_values(["geo_unit_id", "week_start"])
            .reset_index(drop=True)
        )

    @staticmethod
    def _coverage_summary(
        *,
        visible_truth: pd.DataFrame,
        eligible_truth: pd.DataFrame,
    ) -> _ExperimentalGeoSummary:
        visible_units = int(visible_truth["geo_unit_id"].nunique()) if not visible_truth.empty else 0
        eligible_units = int(eligible_truth["geo_unit_id"].nunique()) if not eligible_truth.empty else 0
        latest_week_start = (
            str(pd.Timestamp(visible_truth["week_start"].max()).date())
            if not visible_truth.empty
            else None
        )
        latest_available_date = (
            str(pd.Timestamp(visible_truth["available_date"].max()).date())
            if not visible_truth.empty
            else None
        )
        coverage_ratio = round(float(eligible_units / max(visible_units, 1)), 4) if visible_units else 0.0
        return _ExperimentalGeoSummary(
            unit_count=visible_units,
            eligible_unit_count=eligible_units,
            cluster_count=0,
            latest_week_start=latest_week_start,
            latest_available_date=latest_available_date,
            coverage_ratio=coverage_ratio,
        )

    @staticmethod
    def _build_cluster_assignments(
        *,
        eligible_truth: pd.DataFrame,
        cluster_count: int,
    ) -> dict[str, str]:
        clustering_panel = eligible_truth.rename(
            columns={
                "geo_unit_id": "geo_unit_id",
                "week_start": "as_of_date",
                "incidence": "current_known_incidence",
            }
        )[["geo_unit_id", "as_of_date", "current_known_incidence"]].copy()
        return GeoHierarchyHelper.build_dynamic_clusters(
            clustering_panel,
            state_col="geo_unit_id",
            value_col="current_known_incidence",
            date_col="as_of_date",
            trailing_days=56,
            n_clusters=cluster_count,
        )

    def _build_cluster_payload(
        self,
        *,
        virus_typ: str,
        horizon_days: int,
        as_of_date: pd.Timestamp,
        eligible_truth: pd.DataFrame,
        cluster_assignments: dict[str, str],
    ) -> list[dict[str, Any]]:
        assigned = eligible_truth.assign(
            cluster_id=eligible_truth["geo_unit_id"].map(cluster_assignments)
        ).dropna(subset=["cluster_id"]).copy()
        if assigned.empty:
            return []

        cluster_history = self._cluster_history(assigned)
        target_week_start = self.feature_builder._target_week_start(as_of_date, horizon_days)
        latest_week = pd.Timestamp(assigned["week_start"].max()).normalize()
        latest_rows = (
            assigned.loc[assigned["week_start"] == latest_week]
            .sort_values(["cluster_id", "geo_unit_name"])
            .reset_index(drop=True)
        )

        payload: list[dict[str, Any]] = []
        for cluster_id, cluster_frame in cluster_history.groupby("cluster_id"):
            cluster_frame = cluster_frame.sort_values("week_start").reset_index(drop=True)
            latest_cluster = cluster_frame.iloc[-1]
            current_incidence = float(latest_cluster["incidence"])
            lag1 = self._lag_value(cluster_frame, lag_weeks=1)
            lag2 = self._lag_value(cluster_frame, lag_weeks=2)
            baseline, mad = seasonal_baseline_and_mad(
                cluster_frame[["week_start", "incidence"]].copy(),
                target_week_start,
            )
            momentum_1w = self._relative_change(current_incidence, lag1)
            prior_momentum = self._relative_change(lag1, lag2)
            acceleration = float(momentum_1w - prior_momentum)
            baseline_zscore = float((current_incidence - baseline) / max(mad, 1.0))
            members = latest_rows.loc[latest_rows["cluster_id"] == cluster_id].copy()
            member_states = sorted(
                {
                    str(value)
                    for value in members["parent_bundesland"].dropna().astype(str).tolist()
                    if str(value)
                }
            )
            dominant_state = (
                members.groupby("parent_bundesland")["population"].sum().sort_values(ascending=False).index[0]
                if not members.empty
                else None
            )
            ranking_signal = self._ranking_signal(
                baseline_zscore=baseline_zscore,
                momentum_1w=momentum_1w,
                acceleration=acceleration,
            )
            signal_confidence = round(
                min(
                    1.0,
                    0.45
                    + 0.25 * min(len(cluster_frame), 16) / 16.0
                    + 0.30 * min(len(members), 8) / 8.0,
                ),
                4,
            )
            payload.append(
                {
                    "cluster_id": str(cluster_id),
                    "cluster_label": str(cluster_id).replace("_", " ").title(),
                    "virus_typ": virus_typ,
                    "geo_level": EXPERIMENTAL_GEO_LEVEL,
                    "truth_resolution": "landkreis",
                    "feature_resolution": "landkreis_truth_only",
                    "current_known_incidence": round(current_incidence, 2),
                    "seasonal_baseline": round(float(baseline), 2),
                    "seasonal_mad": round(float(mad), 2),
                    "baseline_gap": round(float(current_incidence - baseline), 2),
                    "baseline_zscore": round(float(baseline_zscore), 4),
                    "momentum_1w": round(float(momentum_1w), 4),
                    "acceleration_1w": round(float(acceleration), 4),
                    "ranking_signal": round(float(ranking_signal), 4),
                    "signal_score": round(float(ranking_signal), 4),
                    "signal_confidence": float(signal_confidence),
                    "signal_direction": self._direction_label(momentum_1w=momentum_1w, baseline_zscore=baseline_zscore),
                    "member_count": int(members["geo_unit_id"].nunique()),
                    "member_states": member_states,
                    "dominant_bundesland": str(dominant_state) if dominant_state is not None else None,
                    "dominant_bundesland_name": (
                        BUNDESLAND_NAMES.get(str(dominant_state), str(dominant_state))
                        if dominant_state is not None
                        else None
                    ),
                    "member_geo_units": [
                        {
                            "geo_unit_id": str(row.geo_unit_id),
                            "geo_unit_name": str(row.geo_unit_name),
                            "parent_bundesland": str(row.parent_bundesland),
                            "parent_bundesland_name": BUNDESLAND_NAMES.get(str(row.parent_bundesland), str(row.parent_bundesland)),
                        }
                        for row in members.head(8).itertuples()
                    ],
                    "latest_visible_week_start": str(pd.Timestamp(latest_cluster["week_start"]).date()),
                    "target_week_start": str(target_week_start.date()),
                    "status": "shadow_signal",
                    "rollout_mode": EXPERIMENTAL_ROLLOUT_MODE,
                    "activation_policy": EXPERIMENTAL_ACTIVATION_POLICY,
                    "experimental": True,
                    "production_ready": False,
                    "promotion_allowed": False,
                    "claim_scope": "experimental_cluster_level_only",
                    "claim_guardrail_message": experimental_geo_contract()["claim_guardrail_message"],
                }
            )

        payload.sort(key=lambda item: float(item["ranking_signal"]), reverse=True)
        for rank, item in enumerate(payload, start=1):
            item["rank"] = rank
        return payload

    @staticmethod
    def _cluster_history(assigned_truth: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for (cluster_id, week_start), frame in assigned_truth.groupby(["cluster_id", "week_start"], dropna=False):
            weights = pd.to_numeric(frame["population"], errors="coerce").fillna(0.0)
            incidences = pd.to_numeric(frame["incidence"], errors="coerce").fillna(0.0)
            total_weight = float(weights.sum())
            if total_weight <= 0.0:
                continue
            rows.append(
                {
                    "cluster_id": str(cluster_id),
                    "week_start": pd.Timestamp(week_start).normalize(),
                    "incidence": float(np.average(incidences, weights=weights)),
                }
            )
        return pd.DataFrame(rows).sort_values(["cluster_id", "week_start"]).reset_index(drop=True)

    @staticmethod
    def _lag_value(cluster_frame: pd.DataFrame, *, lag_weeks: int) -> float:
        if len(cluster_frame) <= lag_weeks:
            return float(cluster_frame["incidence"].iloc[0])
        return float(cluster_frame["incidence"].iloc[-(lag_weeks + 1)])

    @staticmethod
    def _relative_change(current: float, previous: float) -> float:
        return float((current - previous) / max(abs(previous), 1.0))

    @staticmethod
    def _ranking_signal(
        *,
        baseline_zscore: float,
        momentum_1w: float,
        acceleration: float,
    ) -> float:
        baseline_component = np.clip((baseline_zscore + 2.0) / 6.0, 0.0, 1.0)
        momentum_component = np.clip((momentum_1w + 1.0) / 2.0, 0.0, 1.0)
        acceleration_component = np.clip((acceleration + 1.0) / 2.0, 0.0, 1.0)
        return float(
            (0.50 * baseline_component)
            + (0.35 * momentum_component)
            + (0.15 * acceleration_component)
        )

    @staticmethod
    def _direction_label(*, momentum_1w: float, baseline_zscore: float) -> str:
        if momentum_1w >= 0.15 and baseline_zscore >= 1.0:
            return "rising"
        if momentum_1w <= -0.15 and baseline_zscore <= 0.0:
            return "cooling"
        return "stable"

    @staticmethod
    def _build_state_reconciliation(
        *,
        eligible_truth: pd.DataFrame,
        cluster_assignments: dict[str, str],
    ) -> list[dict[str, Any]]:
        assigned = eligible_truth.assign(
            cluster_id=eligible_truth["geo_unit_id"].map(cluster_assignments)
        ).dropna(subset=["cluster_id"]).copy()
        if assigned.empty:
            return []

        latest_week = pd.Timestamp(assigned["week_start"].max()).normalize()
        latest_rows = assigned.loc[assigned["week_start"] == latest_week].copy()
        payload: list[dict[str, Any]] = []
        for state_code, frame in latest_rows.groupby("parent_bundesland", dropna=False):
            weights = pd.to_numeric(frame["population"], errors="coerce").fillna(0.0)
            incidences = pd.to_numeric(frame["incidence"], errors="coerce").fillna(0.0)
            total_weight = float(weights.sum())
            if total_weight <= 0.0:
                continue
            payload.append(
                {
                    "bundesland": str(state_code),
                    "bundesland_name": BUNDESLAND_NAMES.get(str(state_code), str(state_code)),
                    "current_known_incidence": round(float(np.average(incidences, weights=weights)), 2),
                    "cluster_ids": sorted({str(value) for value in frame["cluster_id"].dropna().astype(str).tolist()}),
                    "geo_unit_count": int(frame["geo_unit_id"].nunique()),
                    "experimental": True,
                    "production_ready": False,
                }
            )
        payload.sort(key=lambda item: item["bundesland"])
        return payload
