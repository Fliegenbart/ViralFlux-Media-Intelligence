"""Observation kernels and phase transforms."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.special import gammaln, logsumexp


def _as_normalized_kernel(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("kernel values must be a non-empty one-dimensional array")
    if np.any(values < 0) or not np.isfinite(values).all():
        raise ValueError("kernel values must be finite and non-negative")
    total = float(values.sum())
    if total <= 0.0:
        raise ValueError("kernel values must contain positive mass")
    return values / total


@dataclass(frozen=True)
class ObservationKernel:
    """Discrete infection-age observation kernel."""

    name: str
    _values: np.ndarray

    @classmethod
    def from_values(cls, name: str, values: list[float] | np.ndarray) -> "ObservationKernel":
        return cls(name=name, _values=_as_normalized_kernel(np.asarray(values, dtype=float)))

    @classmethod
    def shifted_negative_binomial(
        cls,
        *,
        name: str,
        max_age: int,
        shift: int,
        mean: float,
        dispersion: float,
    ) -> "ObservationKernel":
        if max_age < 0 or shift < 0 or shift > max_age:
            raise ValueError("max_age and shift must define a valid support")
        if mean <= shift:
            raise ValueError("mean must be larger than shift")
        if dispersion <= 0:
            raise ValueError("dispersion must be positive")

        ages = np.arange(max_age + 1, dtype=int)
        values = np.zeros(max_age + 1, dtype=float)
        mean_after_shift = float(mean - shift)
        r = float(dispersion)
        p = r / (r + mean_after_shift)
        for idx, age in enumerate(ages):
            k = age - shift
            if k < 0:
                continue
            values[idx] = math.exp(
                gammaln(k + r)
                - gammaln(r)
                - gammaln(k + 1)
                + r * math.log(p)
                + k * math.log1p(-p)
            )
        return cls.from_values(name, values)

    def values(self) -> np.ndarray:
        return self._values.copy()

    def mean_delay(self) -> float:
        ages = np.arange(self._values.size, dtype=float)
        return float(np.dot(ages, self._values))

    def _log_terms(self, q: float, c: float = 0.0) -> np.ndarray:
        ages = np.arange(self._values.size, dtype=float)
        log_k = np.full_like(self._values, -np.inf, dtype=float)
        positive = self._values > 0
        log_k[positive] = np.log(self._values[positive])
        return log_k - ages * float(q) + 0.5 * ages * (ages - 1.0) * float(c)

    def phase_transform(self, q: float, c: float = 0.0) -> float:
        return float(math.exp(self.log_phase_transform(q, c)))

    def log_phase_transform(self, q: float, c: float = 0.0) -> float:
        return float(logsumexp(self._log_terms(q, c)))

    def tilted_probabilities(self, q: float, c: float = 0.0) -> np.ndarray:
        log_terms = self._log_terms(q, c)
        return np.exp(log_terms - logsumexp(log_terms))

    def tilted_moments(self, q: float, c: float = 0.0) -> dict[str, float]:
        probs = self.tilted_probabilities(q, c)
        ages = np.arange(self._values.size, dtype=float)
        a_a_minus_1 = ages * (ages - 1.0)
        return {
            "mean_a": float(np.dot(probs, ages)),
            "mean_a_a_minus_1": float(np.dot(probs, a_a_minus_1)),
        }
