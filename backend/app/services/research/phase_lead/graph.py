"""Regional graph operations for import and growth pressure."""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np


@dataclass
class RegionalGraph:
    """Directed source-to-target regional graph.

    T[j, i] is the import weight from source region j to destination region i.
    Rows are normalized so each source region distributes one unit of outgoing
    pressure across destinations.
    """

    regions: list[str]
    T: np.ndarray
    normalize: bool = True

    def __post_init__(self) -> None:
        matrix = np.asarray(self.T, dtype=float)
        expected = (len(self.regions), len(self.regions))
        if matrix.shape != expected:
            raise ValueError(f"T shape {matrix.shape} does not match expected shape {expected}")
        if np.any(matrix < 0.0) or not np.isfinite(matrix).all():
            raise ValueError("graph weights must be finite and non-negative")
        if self.normalize:
            matrix = self._normalize_source_rows(matrix)
        self.T = matrix

    @staticmethod
    def _normalize_source_rows(matrix: np.ndarray) -> np.ndarray:
        matrix = np.asarray(matrix, dtype=float).copy()
        row_sums = matrix.sum(axis=1)
        for idx, row_sum in enumerate(row_sums):
            if row_sum <= 0.0:
                warnings.warn(f"RegionalGraph row {idx} has zero mass; adding self-loop", RuntimeWarning)
                matrix[idx, idx] = 1.0
                row_sums[idx] = 1.0
        return matrix / row_sums[:, None]

    def incoming_infection_pressure(
        self,
        n: np.ndarray,
        population: np.ndarray,
        epsilon: float = 1.0e-9,
    ) -> np.ndarray:
        burden = np.asarray(n, dtype=float) / np.asarray(population, dtype=float)
        incoming = self.T.T @ burden
        return np.log(epsilon + incoming) - np.log(epsilon + burden)

    def incoming_growth_pressure(self, q: np.ndarray) -> np.ndarray:
        q = np.asarray(q, dtype=float)
        incoming_weight_sum = self.T.sum(axis=0)
        return (self.T.T @ q) - incoming_weight_sum * q

    def symmetrized_laplacian(self) -> np.ndarray:
        adjacency = 0.5 * (self.T + self.T.T)
        degree = np.diag(adjacency.sum(axis=1))
        return degree - adjacency
