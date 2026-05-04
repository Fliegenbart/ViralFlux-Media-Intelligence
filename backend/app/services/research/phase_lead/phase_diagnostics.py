"""Diagnostic-only phase-lead inversion.

Option B uses the raw delayed-convolution likelihood for fitting. The phase
diagnostic in this file must not be added to the posterior objective; it is
for initialization, identifiability checks, warnings, and model introspection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
from scipy.optimize import minimize

from app.services.research.phase_lead.kernels import ObservationKernel


@dataclass
class PhaseDiagnosticResult:
    region_id: str
    pathogen: str
    date: date
    q_phase: float
    c_phase: float
    x_profiled: float
    covariance: np.ndarray
    identifiability_q: float
    identifiability_qc: float
    used_sources: list[str]
    warnings: list[str]


def _projection_matrix(weights: np.ndarray) -> np.ndarray:
    w = np.diag(weights)
    ones = np.ones((weights.size, 1), dtype=float)
    denom = float((ones.T @ w @ ones).item())
    if denom <= 0.0:
        raise ValueError("source weights must contain positive mass")
    return w - (w @ ones @ ones.T @ w) / denom


def _profile_x(z: np.ndarray, f: np.ndarray, weights: np.ndarray) -> float:
    return float(np.sum(weights * (z - f)) / np.sum(weights))


def estimate_phase_diagnostic(
    *,
    region_id: str,
    pathogen: str,
    date: date,
    z_by_source: dict[str, float],
    kernels: dict[str, ObservationKernel],
    source_variance: dict[str, float] | None = None,
    lambda_q: float = 1.0e-4,
    lambda_c: float = 1.0e-3,
    delta_q: float = 1.0e-5,
    delta_qc: float = 1.0e-5,
    bounds: tuple[tuple[float, float], tuple[float, float]] = ((-1.0, 1.0), (-0.5, 0.5)),
) -> PhaseDiagnosticResult:
    sources = [source for source in z_by_source if source in kernels]
    if len(sources) < 2:
        raise ValueError("phase diagnostic requires at least two sources with kernels")
    z = np.array([float(z_by_source[source]) for source in sources], dtype=float)
    variances = source_variance or {}
    weights = np.array([1.0 / max(float(variances.get(source, 1.0)), 1.0e-12) for source in sources])
    projection = _projection_matrix(weights)

    def f_vec(q: float, c: float) -> np.ndarray:
        return np.array([kernels[source].log_phase_transform(q, c) for source in sources], dtype=float)

    def objective(params: np.ndarray) -> float:
        q, c = float(params[0]), float(params[1])
        f = f_vec(q, c)
        residual = z - f
        return float(residual.T @ projection @ residual + lambda_q * q * q + lambda_c * c * c)

    result = minimize(
        objective,
        x0=np.array([0.0, 0.0], dtype=float),
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 200, "ftol": 1.0e-10},
    )
    q_hat, c_hat = [float(value) for value in result.x]
    f_hat = f_vec(q_hat, c_hat)
    x_profiled = _profile_x(z, f_hat, weights)

    jacobian_rows = []
    for source in sources:
        moments = kernels[source].tilted_moments(q_hat, c_hat)
        jacobian_rows.append([-moments["mean_a"], 0.5 * moments["mean_a_a_minus_1"]])
    jacobian = np.asarray(jacobian_rows, dtype=float)
    unregularized_info = jacobian.T @ projection @ jacobian
    regularized_info = unregularized_info + np.diag([lambda_q, lambda_c])
    covariance = np.linalg.pinv(regularized_info)
    identifiability_q = float(jacobian[:, 0].T @ projection @ jacobian[:, 0])
    identifiability_qc = float(np.min(np.linalg.eigvalsh(unregularized_info)))

    warnings: list[str] = []
    if identifiability_q < delta_q:
        warnings.append("local growth is not identifiable from phase geometry")
    if identifiability_qc < delta_qc:
        warnings.append("local acceleration is not identifiable from phase geometry")
    if not result.success:
        warnings.append(f"phase diagnostic optimizer warning: {result.message}")

    return PhaseDiagnosticResult(
        region_id=region_id,
        pathogen=pathogen,
        date=date,
        q_phase=q_hat,
        c_phase=c_hat,
        x_profiled=x_profiled,
        covariance=covariance,
        identifiability_q=identifiability_q,
        identifiability_qc=identifiability_qc,
        used_sources=sources,
        warnings=warnings,
    )
