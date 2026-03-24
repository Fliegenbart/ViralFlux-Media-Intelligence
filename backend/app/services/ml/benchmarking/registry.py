from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.ml.benchmarking.contracts import RegistryEntry


def _slug(value: str) -> str:
    return str(value).lower().replace(" ", "_").replace("-", "_")


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

    def should_promote(
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
