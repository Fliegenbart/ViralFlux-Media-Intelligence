"""Joint delayed-convolution MAP model and renewal forecast.

This is Option B from the research spec: the posterior objective is driven by
raw source likelihoods plus process, graph, scale, kernel, and coefficient
priors. The phase-lead inversion is diagnostic-only and is deliberately not
included as a pseudo-observation penalty, because that would double-count the
same evidence already present in the delayed-convolution likelihood.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
from scipy.optimize import minimize

from app.services.research.phase_lead.baseline import ConstantBaseline, SeasonalBaseline
from app.services.research.phase_lead.config import PhaseLeadConfig
from app.services.research.phase_lead.convolution import compute_mu, incidence_from_x
from app.services.research.phase_lead.data_schema import ObservationRow, filter_vintage
from app.services.research.phase_lead.graph import RegionalGraph
from app.services.research.phase_lead.kernels import ObservationKernel
from app.services.research.phase_lead.likelihoods import neg_binom_nll, wastewater_nll
from app.services.research.phase_lead.mappings import SourceMapping
from app.services.research.phase_lead.phase_diagnostics import (
    PhaseDiagnosticResult,
    estimate_phase_diagnostic,
)
from app.services.research.phase_lead.renewal import (
    derive_q_c,
    normalize_distribution,
    phase_log_r,
    renewal_mean_next,
)


@dataclass
class FitResult:
    issue_date: date
    window_start: date
    window_end: date
    regions: list[str]
    pathogens: list[str]
    dates: list[date]
    x_map: np.ndarray
    n_map: np.ndarray
    q_map: np.ndarray
    c_map: np.ndarray
    parameters: dict[str, Any]
    objective_value: float
    objective_components: dict[str, float]
    converged: bool
    optimizer_info: dict[str, Any]
    phase_diagnostics: list[PhaseDiagnosticResult]
    warnings: list[str]
    config_hash: str
    data_vintage_hash: str
    graph: RegionalGraph
    population: np.ndarray


@dataclass
class ForecastResult:
    issue_date: date
    horizons: list[int]
    samples: np.ndarray
    p_up: np.ndarray
    p_surge: np.ndarray
    p_front: np.ndarray
    eeb: np.ndarray
    gegb: np.ndarray
    region_rankings: dict[str, list[dict[str, float | str]]]
    calibration_metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class PhaseLeadGraphRenewalFilter:
    def __init__(
        self,
        config: PhaseLeadConfig,
        kernels: dict[str, ObservationKernel],
        baseline: SeasonalBaseline | None = None,
    ) -> None:
        self.config = config
        self.kernels = kernels
        self.baseline = baseline or ConstantBaseline(log_value=0.0)
        missing = {
            source_config.kernel
            for source_config in self.config.sources.values()
            if source_config.kernel not in self.kernels
        }
        if missing:
            raise ValueError(f"Missing configured kernels: {sorted(missing)}")

    def fit(
        self,
        *,
        observations: list[ObservationRow | dict[str, Any]],
        mappings: dict[str, SourceMapping],
        graph: RegionalGraph,
        population: dict[str, float] | np.ndarray,
        issue_date: date,
        initial_state: np.ndarray | None = None,
    ) -> FitResult:
        vintage = filter_vintage(observations, issue_date)
        if not vintage:
            raise ValueError("No observations are available for the requested issue_date")

        regions = graph.regions
        pathogens = self.config.pathogens
        population_array = self._population_array(population, regions)
        window_end = max(row.event_date for row in vintage if row.event_date <= issue_date)
        window_start = window_end - timedelta(days=self.config.window_days - 1)
        dates = [window_start + timedelta(days=offset) for offset in range(self.config.window_days)]
        date_to_index = {day: idx for idx, day in enumerate(dates)}
        pathogen_to_index = {pathogen: idx for idx, pathogen in enumerate(pathogens)}
        window_rows = [
            row
            for row in vintage
            if row.source in self.config.sources
            and row.source in mappings
            and row.pathogen in pathogen_to_index
            and row.event_date in date_to_index
        ]
        if not window_rows:
            raise ValueError("No configured observations fall inside the fitting window")

        x0 = self._initial_x(window_rows, mappings, regions, pathogens, dates, initial_state)
        initial_objective, initial_components = self._objective_components(
            x0,
            rows=window_rows,
            mappings=mappings,
            graph=graph,
            population=population_array,
            date_to_index=date_to_index,
            pathogen_to_index=pathogen_to_index,
        )

        shape = x0.shape
        bounds = [
            (self.config.optimization.x_lower, self.config.optimization.x_upper)
            for _ in range(int(np.prod(shape)))
        ]

        def objective_flat(flat: np.ndarray) -> float:
            value, _ = self._objective_components(
                flat.reshape(shape),
                rows=window_rows,
                mappings=mappings,
                graph=graph,
                population=population_array,
                date_to_index=date_to_index,
                pathogen_to_index=pathogen_to_index,
            )
            return value

        candidate_x = x0
        final_objective = initial_objective
        final_components = initial_components
        optimizer_success = True
        optimizer_message = "optimization skipped; using deterministic live initialization"
        optimizer_iterations = 0

        if self.config.optimization.max_iter > 0:
            optimizer_options = {
                "maxiter": self.config.optimization.max_iter,
                "ftol": self.config.optimization.tolerance,
            }
            if self.config.optimization.max_fun > 0:
                optimizer_options["maxfun"] = self.config.optimization.max_fun
            result = minimize(
                objective_flat,
                x0.ravel(),
                method=self.config.optimization.method,
                bounds=bounds,
                options=optimizer_options,
            )
            candidate_x = result.x.reshape(shape)
            final_objective, final_components = self._objective_components(
                candidate_x,
                rows=window_rows,
                mappings=mappings,
                graph=graph,
                population=population_array,
                date_to_index=date_to_index,
                pathogen_to_index=pathogen_to_index,
            )
            if final_objective > initial_objective:
                candidate_x = x0
                final_objective = initial_objective
                final_components = initial_components
            optimizer_success = bool(result.success)
            optimizer_message = str(result.message)
            optimizer_iterations = int(getattr(result, "nit", 0))

        q_map, c_map = derive_q_c(candidate_x)
        n_map = incidence_from_x(candidate_x, self.config.epsilon_incidence)
        diagnostics = self._phase_diagnostics(window_rows, mappings, regions, pathogens, window_end)
        warnings = [warning for diagnostic in diagnostics for warning in diagnostic.warnings]
        if not optimizer_success:
            warnings.append(f"optimizer warning: {optimizer_message}")

        return FitResult(
            issue_date=issue_date,
            window_start=window_start,
            window_end=window_end,
            regions=regions,
            pathogens=pathogens,
            dates=dates,
            x_map=candidate_x,
            n_map=n_map,
            q_map=q_map,
            c_map=c_map,
            parameters={
                "sources": {name: vars(source_config) for name, source_config in self.config.sources.items()},
                "renewal": vars(self.config.renewal),
            },
            objective_value=float(final_objective),
            objective_components=final_components,
            converged=optimizer_success,
            optimizer_info={
                "initial_objective": float(initial_objective),
                "message": optimizer_message,
                "iterations": optimizer_iterations,
                "function_evaluations": int(getattr(result, "nfev", 0)) if self.config.optimization.max_iter > 0 else 0,
                "max_fun": int(self.config.optimization.max_fun),
            },
            phase_diagnostics=diagnostics,
            warnings=warnings,
            config_hash=self.config.stable_hash(),
            data_vintage_hash=self._data_hash(window_rows),
            graph=graph,
            population=population_array,
        )

    def forecast(
        self,
        fit_result: FitResult,
        *,
        horizons: list[int] | None = None,
        n_samples: int | None = None,
        seed: int | None = None,
    ) -> ForecastResult:
        horizons = sorted(horizons or self.config.horizons)
        n_samples = int(n_samples or self.config.forecast.n_samples)
        seed = int(seed if seed is not None else self.config.forecast.seed)
        max_horizon = max(horizons)
        rng = np.random.default_rng(seed)
        generation_interval = normalize_distribution(
            self.config.renewal.generation_interval,
            "generation_interval",
        )
        samples = np.zeros(
            (n_samples, max_horizon, len(fit_result.regions), len(fit_result.pathogens)),
            dtype=float,
        )
        q_samples = np.zeros_like(samples)
        for sample_idx in range(n_samples):
            x_history = fit_result.x_map.copy()
            x_history[-1] = x_history[-1] + rng.normal(
                0.0,
                self.config.forecast.state_noise,
                size=x_history[-1].shape,
            )
            n_history = incidence_from_x(x_history, self.config.epsilon_incidence)
            for h_idx in range(max_horizon):
                q_history, c_history = derive_q_c(x_history)
                q_last = q_history[-1]
                c_last = c_history[-1]
                log_r = phase_log_r(q_last, c_last, generation_interval)
                reproduction = np.clip(
                    np.exp(log_r),
                    self.config.renewal.min_reproduction,
                    self.config.renewal.max_reproduction,
                )
                for pathogen_idx in range(len(fit_result.pathogens)):
                    pi = fit_result.graph.incoming_infection_pressure(
                        n_history[-1, :, pathogen_idx],
                        fit_result.population,
                    )
                    omega = fit_result.graph.incoming_growth_pressure(q_last[:, pathogen_idx])
                    reproduction[:, pathogen_idx] *= np.exp(
                        self.config.renewal.beta_pi * pi
                        + self.config.renewal.beta_omega * omega
                    )
                reproduction = np.clip(
                    reproduction,
                    self.config.renewal.min_reproduction,
                    self.config.renewal.max_reproduction,
                )
                mean_next = renewal_mean_next(
                    n_history,
                    graph=fit_result.graph,
                    generation_interval=generation_interval,
                    eta_import=self.config.renewal.eta_import,
                    reproduction=reproduction,
                )
                kappa = max(self.config.renewal.kappa_forecast, 1.0e-6)
                p = kappa / (kappa + mean_next)
                n_next = rng.negative_binomial(kappa, p)
                x_next = np.log(n_next + self.config.epsilon_incidence)
                x_history = np.concatenate([x_history, x_next[None, :, :]], axis=0)
                n_history = np.concatenate([n_history, n_next[None, :, :]], axis=0)
                samples[sample_idx, h_idx] = x_next
                q_samples[sample_idx, h_idx] = x_history[-1] - x_history[-2]

        horizon_indices = [horizon - 1 for horizon in horizons]
        selected = samples[:, horizon_indices, :, :]
        selected_q = q_samples[:, horizon_indices, :, :]
        x_now = fit_result.x_map[-1][None, None, :, :]
        p_up = np.mean(
            selected - x_now > self.config.forecast.upward_threshold,
            axis=0,
        )
        baseline = self._baseline_array(fit_result, horizons)
        p_surge = np.mean(selected > baseline[None, :, :, :] + self.config.forecast.surge_delta, axis=0)
        c_future = np.zeros_like(selected)
        c_future[:, 2:] = selected_q[:, 2:] - selected_q[:, 1:-1]
        p_front = np.mean(
            (np.max(c_future, axis=1) > self.config.forecast.front_c_threshold)
            & (np.max(selected - baseline[None, :, :, :], axis=1) > 0.0),
            axis=0,
        )
        weights = np.ones(len(horizons), dtype=float) / len(horizons)
        excess = np.clip(np.exp(selected) - np.exp(baseline[None, :, :, :]), 0.0, None)
        eeb = np.tensordot(weights, np.mean(excess, axis=0), axes=(0, 0))
        growth_weighted = np.exp(selected) * (
            selected_q > self.config.forecast.growth_threshold
        )
        gegb = np.tensordot(weights, np.mean(growth_weighted, axis=0), axes=(0, 0))
        rankings = self._rank_regions(fit_result, gegb)

        return ForecastResult(
            issue_date=fit_result.issue_date,
            horizons=horizons,
            samples=selected,
            p_up=p_up,
            p_surge=p_surge,
            p_front=p_front,
            eeb=eeb,
            gegb=gegb,
            region_rankings=rankings,
            calibration_metadata={
                "method": "seeded_negative_binomial_renewal_simulation",
                "seed": seed,
                "n_samples": n_samples,
            },
            warnings=list(fit_result.warnings),
        )

    def phase_diagnostics(
        self,
        fit_result: FitResult,
        observations: list[ObservationRow] | None = None,
    ) -> list[PhaseDiagnosticResult]:
        return fit_result.phase_diagnostics

    def _objective_components(
        self,
        x: np.ndarray,
        *,
        rows: list[ObservationRow],
        mappings: dict[str, SourceMapping],
        graph: RegionalGraph,
        population: np.ndarray,
        date_to_index: dict[date, int],
        pathogen_to_index: dict[str, int],
    ) -> tuple[float, dict[str, float]]:
        observation = self._observation_nll(x, rows, mappings, date_to_index, pathogen_to_index)
        renewal = self._renewal_penalty(x, graph)
        graph_penalty = self._graph_penalty(x, graph)
        scale = 0.0
        kernel = 0.0
        coef = 0.0
        # Intentionally no phase diagnostic penalty in Option B.
        components = {
            "observation": observation,
            "renewal": renewal,
            "graph": graph_penalty,
            "scale": scale,
            "kernel": kernel,
            "coef": coef,
        }
        return float(sum(components.values())), components

    def _observation_nll(
        self,
        x: np.ndarray,
        rows: list[ObservationRow],
        mappings: dict[str, SourceMapping],
        date_to_index: dict[date, int],
        pathogen_to_index: dict[str, int],
    ) -> float:
        mu_cache: dict[tuple[str, int], np.ndarray] = {}
        total = 0.0
        for row in rows:
            source_config = self.config.sources[row.source]
            pathogen_idx = pathogen_to_index[row.pathogen]
            cache_key = (row.source, pathogen_idx)
            if cache_key not in mu_cache:
                mu_cache[cache_key] = compute_mu(
                    x_window=x,
                    source_mapping=mappings[row.source],
                    kernel=self.kernels[source_config.kernel],
                    log_alpha=source_config.log_alpha,
                    pathogen_index=pathogen_idx,
                    epsilon=self.config.epsilon_incidence,
                )
            obs_idx = mappings[row.source].observation_index(row.observation_unit)
            date_idx = date_to_index[row.event_date]
            mu = float(mu_cache[cache_key][obs_idx, date_idx])
            if source_config.likelihood == "negative_binomial":
                total += neg_binom_nll(row.value, mu, source_config.phi)
            elif source_config.likelihood == "student_t":
                y_log = (
                    math.log(row.value + self.config.epsilon_observation)
                    if row.source_type == "wastewater_level"
                    else row.value
                )
                total += wastewater_nll(
                    y_log=y_log,
                    mu=mu,
                    bias=source_config.bias,
                    sigma=source_config.sigma,
                    df=source_config.df,
                )
        return float(total)

    def _renewal_penalty(self, x: np.ndarray, graph: RegionalGraph) -> float:
        sigma = max(self.config.renewal.sigma_log_renewal, 1.0e-9)
        generation_interval = normalize_distribution(
            self.config.renewal.generation_interval,
            "generation_interval",
        )
        n = incidence_from_x(x, self.config.epsilon_incidence)
        q, c = derive_q_c(x)
        total = 0.0
        for t_idx in range(1, x.shape[0]):
            log_r = phase_log_r(q[t_idx - 1], c[t_idx - 1], generation_interval)
            reproduction = np.exp(log_r)
            mean = renewal_mean_next(
                n[:t_idx],
                graph=graph,
                generation_interval=generation_interval,
                eta_import=self.config.renewal.eta_import,
                reproduction=reproduction,
            )
            residual = x[t_idx] - np.log(mean + self.config.epsilon_incidence)
            total += float(np.sum((residual * residual) / (2.0 * sigma * sigma)))
        return total

    def _graph_penalty(self, x: np.ndarray, graph: RegionalGraph) -> float:
        L = graph.symmetrized_laplacian()
        q, c = derive_q_c(x)
        total = 0.0
        for pathogen_idx in range(x.shape[2]):
            for t_idx in range(x.shape[0]):
                xv = x[t_idx, :, pathogen_idx]
                qv = q[t_idx, :, pathogen_idx]
                cv = c[t_idx, :, pathogen_idx]
                total += self.config.graph_lambda_x * float(xv.T @ L @ xv)
                total += self.config.graph_lambda_q * float(qv.T @ L @ qv)
                total += self.config.graph_lambda_c * float(cv.T @ L @ cv)
        return float(total)

    def _initial_x(
        self,
        rows: list[ObservationRow],
        mappings: dict[str, SourceMapping],
        regions: list[str],
        pathogens: list[str],
        dates: list[date],
        initial_state: np.ndarray | None,
    ) -> np.ndarray:
        shape = (len(dates), len(regions), len(pathogens))
        if initial_state is not None:
            arr = np.asarray(initial_state, dtype=float)
            if arr.shape != shape:
                raise ValueError(f"initial_state shape {arr.shape} does not match expected {shape}")
            return arr.copy()

        x = np.full(shape, math.log(1.0), dtype=float)
        counts = np.zeros(shape, dtype=float)
        date_to_index = {day: idx for idx, day in enumerate(dates)}
        pathogen_to_index = {pathogen: idx for idx, pathogen in enumerate(pathogens)}
        for row in rows:
            if row.region_id not in regions or row.event_date not in date_to_index:
                continue
            if self.config.sources[row.source].likelihood != "negative_binomial":
                continue
            t_idx = date_to_index[row.event_date]
            r_idx = regions.index(row.region_id)
            p_idx = pathogen_to_index[row.pathogen]
            x[t_idx, r_idx, p_idx] += math.log(max(row.value, 1.0))
            counts[t_idx, r_idx, p_idx] += 1.0
        mask = counts > 0
        x[mask] = x[mask] / (counts[mask] + 1.0)
        return x

    def _phase_diagnostics(
        self,
        rows: list[ObservationRow],
        mappings: dict[str, SourceMapping],
        regions: list[str],
        pathogens: list[str],
        diagnostic_date: date,
    ) -> list[PhaseDiagnosticResult]:
        diagnostics: list[PhaseDiagnosticResult] = []
        by_key: dict[tuple[str, str, str], ObservationRow] = {}
        for row in rows:
            if row.event_date == diagnostic_date:
                by_key[(row.observation_unit, row.pathogen, row.source)] = row

        for region in regions:
            for pathogen in pathogens:
                z_by_source: dict[str, float] = {}
                kernel_by_source: dict[str, ObservationKernel] = {}
                variance_by_source: dict[str, float] = {}
                for source, source_config in self.config.sources.items():
                    row = by_key.get((region, pathogen, source))
                    if row is None:
                        continue
                    if source_config.likelihood == "student_t":
                        z = float(row.value) - source_config.log_alpha
                        variance = source_config.sigma * source_config.sigma
                    else:
                        z = math.log(row.value + self.config.epsilon_observation) - source_config.log_alpha
                        variance = 1.0 / max(row.value, 1.0)
                    z_by_source[source] = z
                    kernel_by_source[source] = self.kernels[source_config.kernel]
                    variance_by_source[source] = variance
                if len(z_by_source) < 2:
                    continue
                try:
                    diagnostics.append(
                        estimate_phase_diagnostic(
                            region_id=region,
                            pathogen=pathogen,
                            date=diagnostic_date,
                            z_by_source=z_by_source,
                            kernels=kernel_by_source,
                            source_variance=variance_by_source,
                        )
                    )
                except ValueError:
                    continue
        return diagnostics

    def _baseline_array(self, fit_result: FitResult, horizons: list[int]) -> np.ndarray:
        arr = np.zeros((len(horizons), len(fit_result.regions), len(fit_result.pathogens)), dtype=float)
        for h_idx, horizon in enumerate(horizons):
            day = fit_result.window_end + timedelta(days=horizon)
            for r_idx, region in enumerate(fit_result.regions):
                for p_idx, pathogen in enumerate(fit_result.pathogens):
                    arr[h_idx, r_idx, p_idx] = self.baseline.value(region, pathogen, day)
        return arr

    @staticmethod
    def _rank_regions(fit_result: FitResult, gegb: np.ndarray) -> dict[str, list[dict[str, float | str]]]:
        rankings: dict[str, list[dict[str, float | str]]] = {}
        for p_idx, pathogen in enumerate(fit_result.pathogens):
            order = np.argsort(-gegb[:, p_idx])
            rankings[pathogen] = [
                {"region_id": fit_result.regions[idx], "gegb": float(gegb[idx, p_idx])}
                for idx in order
            ]
        if len(fit_result.pathogens) > 1:
            aggregate = gegb.sum(axis=1)
            order = np.argsort(-aggregate)
            rankings["all"] = [
                {"region_id": fit_result.regions[idx], "gegb": float(aggregate[idx])}
                for idx in order
            ]
        return rankings

    @staticmethod
    def _population_array(population: dict[str, float] | np.ndarray, regions: list[str]) -> np.ndarray:
        if isinstance(population, dict):
            return np.array([float(population[region]) for region in regions], dtype=float)
        arr = np.asarray(population, dtype=float)
        if arr.shape != (len(regions),):
            raise ValueError("population array must have one value per region")
        return arr

    @staticmethod
    def _data_hash(rows: list[ObservationRow]) -> str:
        payload = json.dumps([row.model_dump(mode="json") for row in rows], sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
