from datetime import date, timedelta

import numpy as np

from app.services.research.phase_lead.config import (
    ForecastConfig,
    OptimizationConfig,
    PhaseLeadConfig,
    RenewalConfig,
    SourceConfig,
)
from app.services.research.phase_lead.data_schema import ObservationRow
from app.services.research.phase_lead.graph import RegionalGraph
from app.services.research.phase_lead.joint_model import PhaseLeadGraphRenewalFilter
from app.services.research.phase_lead.kernels import ObservationKernel
from app.services.research.phase_lead.mappings import SourceMapping


def _synthetic_observations(true_x: np.ndarray, start: date) -> list[ObservationRow]:
    observations: list[ObservationRow] = []
    early = ObservationKernel.from_values("wastewater", [0.65, 0.25, 0.10])
    late = ObservationKernel.from_values("cases", [0.05, 0.25, 0.70])
    kernels = {"wastewater": early, "cases": late}
    for source, kernel in kernels.items():
        for t in range(true_x.shape[0]):
            for region_idx, region_id in enumerate(["r0", "r1", "r2"]):
                mu = 0.0
                for age, weight in enumerate(kernel.values()):
                    lag_idx = max(0, t - age)
                    mu += float(weight) * float(np.exp(true_x[lag_idx, region_idx, 0]))
                value = np.log(mu) if source == "wastewater" else round(mu)
                observations.append(
                    ObservationRow(
                        source=source,
                        source_type="wastewater_log" if source == "wastewater" else "count",
                        observation_unit=region_id,
                        region_id=region_id,
                        pathogen="SARS-CoV-2",
                        event_date=start + timedelta(days=t),
                        publication_date=start + timedelta(days=t + 1),
                        revision_date=start + timedelta(days=t + 1),
                        value=float(value),
                    )
                )
    return observations


def test_joint_model_synthetic_fit_forecast_and_no_phase_penalty() -> None:
    rng = np.random.default_rng(123)
    dates = 45
    regions = ["r0", "r1", "r2"]
    start = date(2026, 1, 1)
    t = np.arange(dates)
    true_x = np.zeros((dates, 3, 1), dtype=float)
    true_x[:, 0, 0] = 1.5 + 0.055 * t
    true_x[:, 1, 0] = 1.3 + 0.035 * np.maximum(t - 12, 0)
    true_x[:, 2, 0] = 1.2
    initial_state = true_x + rng.normal(0.0, 0.08, size=true_x.shape)
    observations = _synthetic_observations(true_x, start)

    config = PhaseLeadConfig(
        window_days=dates,
        horizons=[3, 5, 7, 10, 14],
        pathogens=["SARS-CoV-2"],
        sources={
            "wastewater": SourceConfig(
                source_type="wastewater_log",
                likelihood="student_t",
                kernel="wastewater",
                sigma=0.25,
                df=5.0,
            ),
            "cases": SourceConfig(
                source_type="count",
                likelihood="negative_binomial",
                kernel="cases",
                phi=50.0,
            ),
        },
        renewal=RenewalConfig(
            generation_interval=[0.45, 0.35, 0.20],
            eta_import=0.15,
            sigma_log_renewal=2.0,
            kappa_forecast=40.0,
        ),
        optimization=OptimizationConfig(max_iter=20, tolerance=1.0e-5),
        forecast=ForecastConfig(n_samples=80, seed=77),
        graph_lambda_x=0.0,
        graph_lambda_q=0.0,
        graph_lambda_c=0.0,
    )
    mappings = {
        "wastewater": SourceMapping("wastewater", regions, regions, np.eye(3)),
        "cases": SourceMapping("cases", regions, regions, np.eye(3)),
    }
    graph = RegionalGraph(
        regions=regions,
        T=np.array(
            [
                [0.75, 0.25, 0.00],
                [0.00, 1.00, 0.00],
                [0.00, 0.00, 1.00],
            ]
        ),
    )
    kernels = {
        "wastewater": ObservationKernel.from_values("wastewater", [0.65, 0.25, 0.10]),
        "cases": ObservationKernel.from_values("cases", [0.05, 0.25, 0.70]),
    }
    model = PhaseLeadGraphRenewalFilter(config=config, kernels=kernels)

    fit = model.fit(
        observations=observations,
        mappings=mappings,
        graph=graph,
        population={"r0": 1000.0, "r1": 1000.0, "r2": 1000.0},
        issue_date=start + timedelta(days=dates),
        initial_state=initial_state,
    )
    forecast = model.forecast(fit, horizons=[3, 5, 7, 10, 14], n_samples=80, seed=77)

    assert fit.optimizer_info["initial_objective"] > fit.objective_value
    assert np.corrcoef(fit.x_map.ravel(), true_x.ravel())[0, 1] > 0.75
    assert "phase" not in fit.objective_components
    assert fit.phase_diagnostics
    assert forecast.p_up.shape == (5, 3, 1)
    assert forecast.eeb.shape == (3, 1)
    assert forecast.gegb.shape == (3, 1)
    assert forecast.region_rankings["SARS-CoV-2"][0]["region_id"] in {"r0", "r1"}
