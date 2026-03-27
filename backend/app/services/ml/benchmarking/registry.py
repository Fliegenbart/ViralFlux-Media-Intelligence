from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.ml.benchmarking.contracts import RegistryEntry

DEFAULT_PROMOTION_MIN_SAMPLE_COUNT = 12
DEFAULT_METRIC_SEMANTICS_VERSION = "regional_probabilistic_metrics_v1"


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


def _metrics_present(metrics: dict[str, Any] | None) -> bool:
    return bool(metrics) and "error" not in (metrics or {})


class ForecastRegistry:
    """Filesystem-backed champion/challenger registry for forecast scopes."""

    def __init__(self, registry_root: Path | None = None) -> None:
        self.registry_root = registry_root or (
            Path(__file__).resolve().parent.parent.parent / "ml_models" / "forecast_registry"
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
        return json.loads(path.read_text())

    def save_scope(self, *, virus_typ: str, horizon_days: int, payload: dict[str, Any]) -> None:
        path = self.registry_path(virus_typ=virus_typ, horizon_days=horizon_days)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=str))

    def _metric_only_promotion_decision(
        self,
        *,
        candidate_metrics: dict[str, Any] | None,
        champion_metrics: dict[str, Any] | None,
    ) -> bool:
        if not candidate_metrics:
            return False
        if not champion_metrics:
            return True

        candidate_wis = float(candidate_metrics.get("relative_wis") or candidate_metrics.get("wis") or 9999.0)
        champion_wis = float(champion_metrics.get("relative_wis") or champion_metrics.get("wis") or 9999.0)
        if candidate_wis > champion_wis * 0.99:
            return False

        if "crps" in candidate_metrics and "crps" in champion_metrics:
            if float(candidate_metrics["crps"]) > float(champion_metrics["crps"]) * 1.01:
                return False

        for metric_name in ("coverage_95",):
            if metric_name in candidate_metrics and metric_name in champion_metrics:
                if float(candidate_metrics[metric_name]) + 1e-9 < float(champion_metrics[metric_name]) - 0.02:
                    return False

        for metric_name in ("brier_score", "ece"):
            if metric_name in candidate_metrics and metric_name in champion_metrics:
                if float(candidate_metrics[metric_name]) > float(champion_metrics[metric_name]) * 1.05:
                    return False

        if "decision_utility" in candidate_metrics and "decision_utility" in champion_metrics:
            if float(candidate_metrics["decision_utility"]) + 1e-9 < float(champion_metrics["decision_utility"]) - 0.01:
                return False

        return True

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
        metric_semantics_compatible = (
            True
            if not champion_exists
            else bool(
                metric_semantics_version
                and champion_metric_semantics_version
                and metric_semantics_version == champion_metric_semantics_version
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
            if champion_primary_metric is None:
                blockers.append("champion_primary_metric_missing")

        if not blockers and champion_metrics_present:
            if not self._metric_only_promotion_decision(
                candidate_metrics=candidate_metrics,
                champion_metrics=champion_metrics,
            ):
                blockers.append("candidate_not_better_than_champion")

        return {
            "quality_gate_overall_passed": quality_gate_overall_passed,
            "metric_semantics_version": metric_semantics_version,
            "champion_metric_semantics_version": champion_metric_semantics_version,
            "metric_semantics_compatible": metric_semantics_compatible,
            "minimum_sample_count": effective_minimum_sample_count,
            "candidate_sample_count": candidate_sample_count,
            "champion_sample_count": champion_sample_count,
            "candidate_metrics_present": candidate_metrics_present,
            "champion_metrics_present": champion_metrics_present,
            "promotion_allowed": not blockers,
            "promotion_blockers": blockers,
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
