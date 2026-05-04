"""Numerically stable likelihoods for the phase-lead research model."""

from __future__ import annotations

import math

import numpy as np
from scipy.special import gammaln


MIN_POSITIVE = 1.0e-12


def _clip_positive(value: float, name: str) -> float:
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
    return max(float(value), MIN_POSITIVE)


def neg_binom_logpmf(y: float, mu: float, phi: float) -> float:
    if y < 0:
        raise ValueError("negative-binomial observation y must be non-negative")
    mu = _clip_positive(mu, "mu")
    phi = _clip_positive(phi, "phi")
    y = float(y)
    return float(
        gammaln(y + phi)
        - gammaln(phi)
        - gammaln(y + 1.0)
        + phi * math.log(phi / (phi + mu))
        + y * math.log(mu / (phi + mu))
    )


def neg_binom_nll(y: float, mu: float, phi: float) -> float:
    return -neg_binom_logpmf(y, mu, phi)


def student_t_logpdf(y: float, *, loc: float, scale: float, df: float) -> float:
    if scale <= 0 or not math.isfinite(scale):
        raise ValueError("Student-t scale must be positive and finite")
    if df <= 2 or not math.isfinite(df):
        raise ValueError("Student-t df must be > 2 and finite")
    z = (float(y) - float(loc)) / float(scale)
    return float(
        gammaln((df + 1.0) / 2.0)
        - gammaln(df / 2.0)
        - 0.5 * math.log(df * math.pi)
        - math.log(scale)
        - ((df + 1.0) / 2.0) * math.log1p((z * z) / df)
    )


def wastewater_nll(
    *,
    y_log: float,
    mu: float,
    bias: float = 0.0,
    covariates: np.ndarray | None = None,
    gamma: np.ndarray | None = None,
    sigma: float,
    df: float,
) -> float:
    covariate_effect = 0.0
    if covariates is not None or gamma is not None:
        if covariates is None or gamma is None:
            raise ValueError("covariates and gamma must be provided together")
        covariates = np.asarray(covariates, dtype=float)
        gamma = np.asarray(gamma, dtype=float)
        if covariates.shape != gamma.shape:
            raise ValueError("covariates and gamma must have matching shapes")
        covariate_effect = float(np.dot(covariates, gamma))

    loc = math.log(_clip_positive(mu, "mu")) + float(bias) + covariate_effect
    return -student_t_logpdf(float(y_log), loc=loc, scale=sigma, df=df)


def dirichlet_multinomial_logpmf(counts: np.ndarray, pi: np.ndarray, kappa: float) -> float:
    counts = np.asarray(counts, dtype=float)
    pi = np.asarray(pi, dtype=float)
    if counts.ndim != 1 or pi.ndim != 1 or counts.shape != pi.shape:
        raise ValueError("counts and pi must be one-dimensional arrays with the same shape")
    if np.any(counts < 0):
        raise ValueError("Dirichlet-multinomial counts must be non-negative")
    kappa = _clip_positive(kappa, "kappa")
    pi = np.clip(pi, MIN_POSITIVE, None)
    pi = pi / pi.sum()
    alpha = np.clip(kappa * pi, MIN_POSITIVE, None)
    total = float(counts.sum())
    return float(
        gammaln(total + 1.0)
        - np.sum(gammaln(counts + 1.0))
        + gammaln(kappa)
        - gammaln(total + kappa)
        + np.sum(gammaln(counts + alpha) - gammaln(alpha))
    )


def dirichlet_multinomial_nll(counts: np.ndarray, pi: np.ndarray, kappa: float) -> float:
    return -dirichlet_multinomial_logpmf(counts, pi, kappa)
