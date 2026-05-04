"""Internal service facade for phase-lead research runs."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.services.research.phase_lead.config import PhaseLeadConfig
from app.services.research.phase_lead.data_schema import ObservationRow
from app.services.research.phase_lead.graph import RegionalGraph
from app.services.research.phase_lead.joint_model import (
    FitResult,
    ForecastResult,
    PhaseLeadGraphRenewalFilter,
)
from app.services.research.phase_lead.kernels import ObservationKernel
from app.services.research.phase_lead.mappings import SourceMapping


class PhaseLeadResearchService:
    """Small internal service wrapper matching FluxEngine research conventions."""

    def __init__(self, config: PhaseLeadConfig, kernels: dict[str, ObservationKernel]) -> None:
        self.model = PhaseLeadGraphRenewalFilter(config=config, kernels=kernels)

    def fit(
        self,
        *,
        observations: list[ObservationRow | dict[str, Any]],
        mappings: dict[str, SourceMapping],
        graph: RegionalGraph,
        population: dict[str, float],
        issue_date: date,
        initial_state: Any | None = None,
    ) -> FitResult:
        return self.model.fit(
            observations=observations,
            mappings=mappings,
            graph=graph,
            population=population,
            issue_date=issue_date,
            initial_state=initial_state,
        )

    def forecast(
        self,
        fit_result: FitResult,
        *,
        horizons: list[int] | None = None,
        n_samples: int | None = None,
        seed: int | None = None,
    ) -> ForecastResult:
        return self.model.forecast(
            fit_result,
            horizons=horizons,
            n_samples=n_samples,
            seed=seed,
        )
