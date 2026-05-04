import math

import numpy as np

from app.services.research.phase_lead.kernels import ObservationKernel


def test_fixed_kernel_normalizes_values_and_computes_phase_transform() -> None:
    kernel = ObservationKernel.from_values("early", [2.0, 3.0, 5.0])

    values = kernel.values()
    q = 0.07
    c = 0.02
    ages = np.arange(3, dtype=float)
    manual = np.sum(values * np.exp(-ages * q + 0.5 * ages * (ages - 1.0) * c))

    assert math.isclose(float(values.sum()), 1.0)
    assert math.isclose(kernel.phase_transform(q, c), float(manual), rel_tol=1e-12)
    assert math.isclose(kernel.log_phase_transform(q, c), math.log(float(manual)), rel_tol=1e-12)


def test_kernel_derivative_identities_match_finite_differences() -> None:
    kernel = ObservationKernel.from_values("late", [0.05, 0.15, 0.30, 0.35, 0.15])
    q = 0.04
    c = 0.01
    eps = 1.0e-5

    moments = kernel.tilted_moments(q, c)
    dq_fd = (
        kernel.log_phase_transform(q + eps, c) - kernel.log_phase_transform(q - eps, c)
    ) / (2.0 * eps)
    dc_fd = (
        kernel.log_phase_transform(q, c + eps) - kernel.log_phase_transform(q, c - eps)
    ) / (2.0 * eps)

    assert math.isclose(dq_fd, -moments["mean_a"], rel_tol=1e-5, abs_tol=1e-5)
    assert math.isclose(
        dc_fd,
        0.5 * moments["mean_a_a_minus_1"],
        rel_tol=1e-5,
        abs_tol=1e-5,
    )


def test_shifted_negative_binomial_kernel_is_finite_and_normalized() -> None:
    kernel = ObservationKernel.shifted_negative_binomial(
        name="case_report",
        max_age=12,
        shift=2,
        mean=5.0,
        dispersion=4.0,
    )

    values = kernel.values()

    assert values.shape == (13,)
    assert math.isclose(float(values.sum()), 1.0)
    assert kernel.mean_delay() > 2.0
