"""Source-to-latent-grid mapping utilities."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import sparse


@dataclass
class SourceMapping:
    """Map latent regional values to source observation units.

    Convention: observed_unit_value[o] = sum_i H[o, i] * latent_region_value[i].
    """

    source: str
    observation_units: list[str]
    latent_regions: list[str]
    H: Any
    row_normalize: bool = False

    def __post_init__(self) -> None:
        matrix = self.H if sparse.issparse(self.H) else np.asarray(self.H, dtype=float)
        expected_shape = (len(self.observation_units), len(self.latent_regions))
        if matrix.shape != expected_shape:
            raise ValueError(f"H shape {matrix.shape} does not match expected shape {expected_shape}")
        if sparse.issparse(matrix):
            matrix = matrix.tocsr()
        if self.row_normalize:
            matrix = self._row_normalized(matrix)
        row_sums = np.asarray(matrix.sum(axis=1)).ravel()
        if np.any(row_sums == 0):
            warnings.warn(f"SourceMapping {self.source} contains zero-sum rows", RuntimeWarning)
        self.H = matrix

    @staticmethod
    def _row_normalized(matrix: Any) -> Any:
        row_sums = np.asarray(matrix.sum(axis=1)).ravel()
        safe = np.where(row_sums > 0.0, row_sums, 1.0)
        if sparse.issparse(matrix):
            return sparse.diags(1.0 / safe) @ matrix
        return matrix / safe[:, None]

    def apply(self, latent_values: np.ndarray) -> np.ndarray:
        values = np.asarray(latent_values, dtype=float)
        if values.shape[0] != len(self.latent_regions):
            raise ValueError("latent_values length must match latent_regions")
        return np.asarray(self.H @ values).ravel()

    def observation_index(self, observation_unit: str) -> int:
        try:
            return self.observation_units.index(observation_unit)
        except ValueError as exc:
            raise KeyError(f"Unknown observation unit {observation_unit!r} for source {self.source}") from exc
