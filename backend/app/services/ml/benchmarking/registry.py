from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.ml.benchmarking.contracts import RegistryEntry
from app.services.ml.forecast_science_contract import (
    champion_scope_reason,
    is_active_h7_champion_scope,
)

DEFAULT_PROMOTION_MIN_SAMPLE_COUNT = 12
DEFAULT_METRIC_SEMANTICS_VERSION = "regional_probabilistic_metrics_v1"
LEGACY_REGIONAL_METRIC_SEMANTICS_VERSION = "legacy_unversioned_regional_probabilistic"
LEGACY_REGIONAL_EVENT_DEFINITION_VERSION = "legacy_unversioned_regional_probabilistic"
LEGACY_REGIONAL_QUANTILE_GRID_VERSION = "legacy_unversioned_regional_probabilistic"
LEGACY_REGIONAL_SCIENCE_CONTRACT_VERSION = "legacy_pre_h7_science_contract"


def _slug(value: str) -> str:
    return str(value).lower().replace(" ", "_").replace("-", "_")


def _metric_value(metrics: dict[str, Any] | None, *keys: str) -> float | None:
    payload = metrics or {}
    for key in keys:
        if key in payload and payload.get(key) is not None:
            try:
                return float(payload.get(key))
            except (TypeError, ValueError):
                return None
    return None


def _sample_count(metadata: dict[str, Any] | None) -> int | None:
    raw_value = (metadata or {}).get("sample_count")
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _metric_semantics_version(metadata: dict[str, Any] | None) -> str | None:
    value = str((metadata or {}).get("metric_semantics_version") or "").strip()
    return value or None


def _metadata_text(metadata: dict[str, Any] | None, key: str) -> str | None:
    value = str((metadata or {}).get(key) or "").strip()
    return value or None


def _metadata_bool(metadata: dict[str, Any] | None, key: str) -> bool | None:
    if key not in (metadata or {}):
        return None
    return bool((metadata or {}).get(key))


def _metadata_int(metadata: dict[str, Any] | None, key: str) -> int | None:
    raw_value = (metadata or {}).get(key)
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _champion_scope_active(metadata: dict[str, Any] | None) -> bool | None:
    explicit = _metadata_bool(metadata, "champion_scope_active")
    if explicit is not None:
        return explicit
    virus_typ = _metadata_text(metadata, "virus_typ")
    horizon_days = _metadata_int(metadata, "horizon_days")
    if virus_typ is None or horizon_days is None:
        return None
    return is_active_h7_champion_scope(virus_typ, horizon_days)


def _metrics_present(metrics: dict[str, Any] | None) -> bool:
    return bool(metrics) and "error" not in (metrics or {})


def _infer_calibration_mode(metadata: dict[str, Any] | None) -> str | None:
    calibration_mode = _metadata_text(metadata, "calibration_mode")
    if calibration_mode:
        return calibration_mode
    calibration_version = _metadata_text(metadata, "calibration_version")
    if calibration_version and ":" in calibration_version:
        return calibration_version.split(":", 1)[0].strip() or None
    return None


def _normalize_entry_metadata(
    *,
    metadata: dict[str, Any] | None,
    virus_typ: str,
    horizon_days: int,
    model_family: str | None,
    status: str | None,
) -> dict[str, Any]:
    normalized = dict(metadata or {})
    if status and not _metadata_text(normalized, "registry_status"):
        normalized["registry_status"] = status

    if str(model_family or "").strip() != "regional_pooled_panel":
        return normalized

    if not _metadata_text(normalized, "metric_semantics_version"):
        normalized["metric_semantics_version"] = LEGACY_REGIONAL_METRIC_SEMANTICS_VERSION
    if not _metadata_text(normalized, "event_definition_version"):
        normalized["event_definition_version"] = LEGACY_REGIONAL_EVENT_DEFINITION_VERSION
    if not _metadata_text(normalized, "quantile_grid_version"):
        normalized["quantile_grid_version"] = LEGACY_REGIONAL_QUANTILE_GRID_VERSION
    if not _metadata_text(normalized, "science_contract_version"):
        normalized["science_contract_version"] = LEGACY_REGIONAL_SCIENCE_CONTRACT_VERSION
    if "champion_scope_active" not in normalized:
        normalized["champion_scope_active"] = is_active_h7_champion_scope(virus_typ, horizon_days)
    if not _metadata_text(normalized, "champion_scope_reason"):
        normalized["champion_scope_reason"] = champion_scope_reason(virus_typ, horizon_days)
    inferred_calibration_mode = _infer_calibration_mode(normalized)
    if inferred_calibration_mode and not _metadata_text(normalized, "calibration_mode"):
        normalized["calibration_mode"] = inferred_calibration_mode
    normalized.setdefault("legacy_metadata_backfill", True)
    return normalized


def _normalize_entry(entry: dict[str, Any] | None, *, virus_typ: str, horizon_days: int) -> dict[str, Any] | None:
    if not entry:
        return entry
    normalized = dict(entry)
    normalized["metadata"] = _normalize_entry_metadata(
        metadata=entry.get("metadata"),
        virus_typ=virus_typ,
        horizon_days=horizon_days,
        model_family=entry.get("model_family"),
        status=entry.get("status"),
    )
    return normalized


class ForecastRegistry:
    """Filesystem-backed champion/challenger registry for forecast scopes."""

    def __init__(self, registry_root: Path | None = None) -> None:
        self.registry_root = registry_root or (
            Path(__file__).resolve().parent.parent.parent.parent / "ml_models" / "forecast_registry"
        )

    def scope_dir(self, *, virus_typ: str, horizon_days: int) -> Path:
        return self.registry_root / _slug(virus_typ) / f"horizon_{int(horizon_days)}"

    def registry_path(self, *, virus_typ: str, horizon_days: int) -> Path:
        return self.scope_dir(virus_typ=virus_typ, horizon_days=horizon_days) / "registry.json"

    def load_scope(self, *, virus_typ: str, horizon_days: int) -> dict[str, Any]:
        path = self.registry_path(virus_typ=virus_typ, horizon_days=horizon_days)
        if not path.exists():
            return {
                "virus_typ": virus_typ,
                "horizon_days": int(horizon_days),
                "champion": None,
                "history": [],
            }
        payload = json.loads(path.read_text())
        payload["champion"] = _normalize_entry(
            payload.get("champion"),
            virus_typ=virus_typ,
            horizon_days=int(horizon_days),
        )
        payload["history"] = [
            _normalize_entry(entry, virus_typ=virus_typ, horizon_days=int(horizon_days))
            for entry in list(payload.get("history") or [])
        ]
        if payload.get("rollback_candidate"):
            payload["rollback_candidate"] = _normalize_entry(
                payload.get("rollback_candidate"),
                virus_typ=virus_typ,
                horizon_days=int(horizon_days),
            )
        return payload

    def save_scope(self, *, virus_typ: str, horizon_days: int, payload: dict[str, Any]) -> None:
        path = self.registry_path(virus_typ=virus_typ, horizon_days=horizon_days)
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized_payload = {
            **payload,
            "champion": _normalize_entry(
                payload.get("champion"),
                virus_typ=virus_typ,
                horizon_days=int(horizon_days),
            ),
            "history": [
                _normalize_entry(entry, virus_typ=virus_typ, horizon_days=int(horizon_days))
                for entry in list(payload.get("history") or [])
            ],
        }
        if payload.get("rollback_candidate"):
            normalized_payload["rollback_candidate"] = _normalize_entry(
                payload.get("rollback_candidate"),
                virus_typ=virus_typ,
                horizon_days=int(horizon_days),
            )
        path.write_text(json.dumps(normalized_payload, indent=2, default=str))

    def _metric_only_promotion_decision(
        self,
        *,
        candidate_metrics: dict[str, Any] | None,
        champion_metrics: dict[str, Any] | None,
    ) -> bool:
        return self._metric_gate_blockers(
            candidate_metrics=candidate_metrics,
            champion_metrics=champion_metrics,
        ) == []

    def _metric_gate_blockers(
        self,
        *,
        candidate_metrics: dict[str, Any] | None,
        champion_metrics: dict[str, Any] | None,
    ) -> list[str]:
        if not candidate_metrics:
            return ["candidate_metrics_missing"]
        if not champion_metrics:
            return []

        candidate_wis = float(candidate_metrics.get("relative_wis") or candidate_metrics.get("wis") or 9999.0)
        champion_wis = float(champion_metrics.get("relative_wis") or champion_metrics.get("wis") or 9999.0)
        if candidate_wis > champion_wis * 0.99:
            return ["wis_not_better_than_champion"]

        if "crps" in candidate_metrics and "crps" in champion_metrics:
            if float(candidate_metrics["crps"]) > float(champion_metrics["crps"]) * 1.01:
                return ["crps_regressed"]

        for metric_name in ("coverage_95",):
            if metric_name in candidate_metrics and metric_name in champion_metrics:
                if float(candidate_metrics[metric_name]) + 1e-9 < float(champion_metrics[metric_name]) - 0.02:
                    return ["coverage_regressed"]

        for metric_name in ("brier_score", "ece"):
            if metric_name in candidate_metrics and metric_name in champion_metrics:
                if float(candidate_metrics[metric_name]) > float(champion_metrics[metric_name]) * 1.05:
                    return ["event_calibration_regressed"]

        if "decision_utility" in candidate_metrics and "decision_utility" in champion_metrics:
            if float(candidate_metrics["decision_utility"]) + 1e-9 < float(champion_metrics["decision_utility"]) - 0.01:
                return ["operational_utility_regressed"]

        return []

    def evaluate_promotion(
        self,
        *,
        candidate_metrics: dict[str, Any] | None,
        champion_metrics: dict[str, Any] | None,
        candidate_metadata: dict[str, Any] | None = None,
        champion_metadata: dict[str, Any] | None = None,
        minimum_sample_count: int | None = None,
    ) -> dict[str, Any]:
        champion_exists = bool(champion_metrics or champion_metadata)
        candidate_metrics_present = _metrics_present(candidate_metrics)
        champion_metrics_present = _metrics_present(champion_metrics)
        quality_gate_overall_passed = bool((candidate_metadata or {}).get("quality_gate_overall_passed"))
        metric_semantics_version = _metric_semantics_version(candidate_metadata)
        champion_metric_semantics_version = _metric_semantics_version(champion_metadata)
        event_definition_version = _metadata_text(candidate_metadata, "event_definition_version")
        champion_event_definition_version = _metadata_text(champion_metadata, "event_definition_version")
        quantile_grid_version = _metadata_text(candidate_metadata, "quantile_grid_version")
        champion_quantile_grid_version = _metadata_text(champion_metadata, "quantile_grid_version")
        calibration_mode = _metadata_text(candidate_metadata, "calibration_mode")
        champion_scope_active = _champion_scope_active(candidate_metadata)
        weather_vintage_discipline_passed = _metadata_bool(
            candidate_metadata,
            "weather_vintage_discipline_passed",
        )
        oof_calibration_only = _metadata_bool(candidate_metadata, "oof_calibration_only")
        quantile_monotonicity_passed = _metadata_bool(
            candidate_metadata,
            "quantile_monotonicity_passed",
        )
        metric_semantics_compatible = (
            True
            if not champion_exists
            else bool(
                metric_semantics_version
                and champion_metric_semantics_version
                and metric_semantics_version == champion_metric_semantics_version
            )
        )
        event_definition_compatible = (
            True
            if not champion_exists
            else bool(
                event_definition_version
                and champion_event_definition_version
                and event_definition_version == champion_event_definition_version
            )
        )
        quantile_grid_compatible = (
            True
            if not champion_exists
            else bool(
                quantile_grid_version
                and champion_quantile_grid_version
                and quantile_grid_version == champion_quantile_grid_version
            )
        )
        effective_minimum_sample_count = int(minimum_sample_count or DEFAULT_PROMOTION_MIN_SAMPLE_COUNT)
        candidate_sample_count = _sample_count(candidate_metadata)
        champion_sample_count = _sample_count(champion_metadata)
        candidate_primary_metric = _metric_value(candidate_metrics, "relative_wis", "wis")
        champion_primary_metric = _metric_value(champion_metrics, "relative_wis", "wis")

        blockers: list[str] = []
        if not candidate_metrics_present:
            blockers.append("candidate_metrics_missing")
        if not quality_gate_overall_passed:
            blockers.append("quality_gate_not_passed")
        if not metric_semantics_version:
            blockers.append("metric_semantics_missing")
        if not event_definition_version:
            blockers.append("event_definition_missing")
        if not quantile_grid_version:
            blockers.append("quantile_grid_version_missing")
        if champion_scope_active is None:
            blockers.append("champion_scope_missing")
        elif not champion_scope_active:
            blockers.append("champion_scope_not_active")
        if weather_vintage_discipline_passed is None:
            blockers.append("vintage_discipline_missing")
        elif not weather_vintage_discipline_passed:
            blockers.append("vintage_discipline_not_passed")
        if oof_calibration_only is None:
            blockers.append("oof_calibration_missing")
        elif not oof_calibration_only:
            blockers.append("oof_calibration_not_passed")
        if quantile_monotonicity_passed is None:
            blockers.append("quantile_monotonicity_missing")
        elif not quantile_monotonicity_passed:
            blockers.append("quantile_monotonicity_not_passed")
        if candidate_sample_count is None:
            blockers.append("candidate_sample_count_missing")
        elif candidate_sample_count < effective_minimum_sample_count:
            blockers.append("minimum_sample_count_not_met")
        if candidate_primary_metric is None:
            blockers.append("candidate_primary_metric_missing")

        if champion_exists:
            if not champion_metrics_present:
                blockers.append("champion_metrics_missing")
            if not champion_metric_semantics_version:
                blockers.append("champion_metric_semantics_missing")
            elif not metric_semantics_compatible:
                blockers.append("metric_semantics_incompatible")
            if not champion_event_definition_version:
                blockers.append("champion_event_definition_missing")
            elif not event_definition_compatible:
                blockers.append("event_definition_incompatible")
            if not champion_quantile_grid_version:
                blockers.append("champion_quantile_grid_version_missing")
            elif not quantile_grid_compatible:
                blockers.append("quantile_grid_incompatible")
            if champion_primary_metric is None:
                blockers.append("champion_primary_metric_missing")

        metric_gate_blockers: list[str] = []
        if not blockers and champion_metrics_present:
            metric_gate_blockers = self._metric_gate_blockers(
                candidate_metrics=candidate_metrics,
                champion_metrics=champion_metrics,
            )
            blockers.extend(metric_gate_blockers)

        promotion_gate_sequence = [
            {
                "name": "champion_scope",
                "passed": champion_scope_active is True,
                "blockers": [
                    blocker for blocker in blockers if blocker in {"champion_scope_missing", "champion_scope_not_active"}
                ],
            },
            {
                "name": "leakage_and_vintage",
                "passed": all(
                    value is True
                    for value in (
                        weather_vintage_discipline_passed,
                        oof_calibration_only,
                        quantile_monotonicity_passed,
                    )
                ),
                "blockers": [
                    blocker
                    for blocker in blockers
                    if blocker
                    in {
                        "vintage_discipline_missing",
                        "vintage_discipline_not_passed",
                        "oof_calibration_missing",
                        "oof_calibration_not_passed",
                        "quantile_monotonicity_missing",
                        "quantile_monotonicity_not_passed",
                    }
                ],
            },
            {
                "name": "wis",
                "passed": not any(
                    blocker in {"wis_not_better_than_champion", "crps_regressed"} for blocker in blockers
                ),
                "blockers": [
                    blocker for blocker in blockers if blocker in {"wis_not_better_than_champion", "crps_regressed"}
                ],
            },
            {
                "name": "coverage",
                "passed": "coverage_regressed" not in blockers,
                "blockers": [blocker for blocker in blockers if blocker == "coverage_regressed"],
            },
            {
                "name": "event_calibration",
                "passed": "event_calibration_regressed" not in blockers,
                "blockers": [blocker for blocker in blockers if blocker == "event_calibration_regressed"],
            },
            {
                "name": "operational_utility",
                "passed": "operational_utility_regressed" not in blockers,
                "blockers": [blocker for blocker in blockers if blocker == "operational_utility_regressed"],
            },
        ]

        return {
            "quality_gate_overall_passed": quality_gate_overall_passed,
            "metric_semantics_version": metric_semantics_version,
            "champion_metric_semantics_version": champion_metric_semantics_version,
            "metric_semantics_compatible": metric_semantics_compatible,
            "event_definition_version": event_definition_version,
            "champion_event_definition_version": champion_event_definition_version,
            "event_definition_compatible": event_definition_compatible,
            "quantile_grid_version": quantile_grid_version,
            "champion_quantile_grid_version": champion_quantile_grid_version,
            "quantile_grid_compatible": quantile_grid_compatible,
            "calibration_mode": calibration_mode,
            "champion_scope_active": champion_scope_active,
            "weather_vintage_discipline_passed": weather_vintage_discipline_passed,
            "oof_calibration_only": oof_calibration_only,
            "quantile_monotonicity_passed": quantile_monotonicity_passed,
            "minimum_sample_count": effective_minimum_sample_count,
            "candidate_sample_count": candidate_sample_count,
            "champion_sample_count": champion_sample_count,
            "candidate_metrics_present": candidate_metrics_present,
            "champion_metrics_present": champion_metrics_present,
            "promotion_allowed": not blockers,
            "promotion_blockers": blockers,
            "promotion_gate_sequence": promotion_gate_sequence,
        }

    def should_promote(
        self,
        *,
        candidate_metrics: dict[str, Any] | None,
        champion_metrics: dict[str, Any] | None,
        candidate_metadata: dict[str, Any] | None = None,
        champion_metadata: dict[str, Any] | None = None,
        minimum_sample_count: int | None = None,
    ) -> bool:
        if (
            candidate_metadata is not None
            or champion_metadata is not None
            or minimum_sample_count is not None
        ):
            return bool(
                self.evaluate_promotion(
                    candidate_metrics=candidate_metrics,
                    champion_metrics=champion_metrics,
                    candidate_metadata=candidate_metadata,
                    champion_metadata=champion_metadata,
                    minimum_sample_count=minimum_sample_count,
                ).get("promotion_allowed")
            )
        return self._metric_only_promotion_decision(
            candidate_metrics=candidate_metrics,
            champion_metrics=champion_metrics,
        )

    def record_evaluation(
        self,
        *,
        virus_typ: str,
        horizon_days: int,
        model_family: str,
        metrics: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        promote: bool = False,
    ) -> dict[str, Any]:
        payload = self.load_scope(virus_typ=virus_typ, horizon_days=horizon_days)
        current_champion = payload.get("champion")
        entry = RegistryEntry(
            model_family=model_family,
            status="champion" if promote else "challenger",
            metrics=metrics,
            metadata=metadata or {},
        ).to_dict()
        history = list(payload.get("history") or [])
        history.append(entry)
        payload["history"] = history
        if promote:
            payload["champion"] = entry
            if current_champion:
                payload["rollback_candidate"] = current_champion
        self.save_scope(virus_typ=virus_typ, horizon_days=horizon_days, payload=payload)
        return payload
