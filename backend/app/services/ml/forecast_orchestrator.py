from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.ml.benchmarking.registry import ForecastRegistry


class ForecastOrchestrator:
    """Thin coordinator for registry, rollout, and revision policy decisions."""

    def __init__(self, registry_root: Path | None = None) -> None:
        self.settings = get_settings()
        self.registry = ForecastRegistry(registry_root=registry_root)

    @staticmethod
    def resolve_revision_policy(
        *,
        metadata: dict[str, Any] | None,
        requested_policy: str | None = None,
    ) -> str:
        supported = {"raw", "adjusted", "adaptive"}
        if requested_policy in supported:
            return str(requested_policy)
        revision_meta = (metadata or {}).get("revision_policy_metadata") or {}
        default_policy = str(revision_meta.get("default_policy") or "").strip().lower()
        if default_policy in supported:
            return default_policy
        return "raw"

    def registry_scope(
        self,
        *,
        virus_typ: str,
        horizon_days: int,
    ) -> dict[str, Any]:
        return self.registry.load_scope(virus_typ=virus_typ, horizon_days=horizon_days)

    @staticmethod
    def fallback_component_metadata(model_family: str) -> tuple[dict[str, float], dict[str, float]]:
        return ({model_family: 1.0}, {"state": 1.0, "cluster": 0.0, "national": 0.0})
