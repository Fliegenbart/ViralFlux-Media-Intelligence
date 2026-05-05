"""Configuration contracts for the phase-lead graph renewal filter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Literal


LikelihoodName = Literal["negative_binomial", "student_t"]


@dataclass
class SourceConfig:
    source_type: str
    likelihood: LikelihoodName
    kernel: str
    log_alpha: float = 0.0
    phi: float = 20.0
    sigma: float = 0.5
    df: float = 4.0
    bias: float = 0.0


@dataclass
class RenewalConfig:
    generation_interval: list[float]
    eta_import: float = 0.05
    sigma_log_renewal: float = 0.25
    kappa_forecast: float = 30.0
    beta_pi: float = 0.0
    beta_omega: float = 0.0
    min_reproduction: float = 0.2
    max_reproduction: float = 2.5


@dataclass
class OptimizationConfig:
    method: str = "L-BFGS-B"
    max_iter: int = 500
    max_fun: int = 250_000
    tolerance: float = 1.0e-5
    x_lower: float = -30.0
    x_upper: float = 20.0


@dataclass
class ForecastConfig:
    n_samples: int = 500
    seed: int = 123
    state_noise: float = 0.05
    upward_threshold: float = 0.0
    surge_delta: float = 0.15
    front_c_threshold: float = 0.01
    growth_threshold: float = 0.0


@dataclass
class PhaseLeadConfig:
    window_days: int = 70
    horizons: list[int] = field(default_factory=lambda: [3, 5, 7, 10, 14])
    epsilon_incidence: float = 1.0e-6
    epsilon_observation: float = 1.0e-6
    pathogens: list[str] = field(default_factory=lambda: ["SARS-CoV-2"])
    sources: dict[str, SourceConfig] = field(default_factory=dict)
    renewal: RenewalConfig = field(default_factory=lambda: RenewalConfig([0.45, 0.35, 0.20]))
    optimization: OptimizationConfig = field(default_factory=OptimizationConfig)
    forecast: ForecastConfig = field(default_factory=ForecastConfig)
    graph_lambda_x: float = 1.0e-3
    graph_lambda_q: float = 1.0e-3
    graph_lambda_c: float = 1.0e-3
    scale_lambda: float = 1.0e-3

    def stable_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
