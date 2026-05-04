from datetime import date

import numpy as np

from app.services.research.phase_lead.kernels import ObservationKernel
from app.services.research.phase_lead.phase_diagnostics import estimate_phase_diagnostic


def test_phase_diagnostic_recovers_growth_when_kernel_geometry_is_separated() -> None:
    q_true = 0.08
    c_true = 0.0
    x_true = 2.3
    kernels = {
        "early": ObservationKernel.from_values("early", [0.65, 0.25, 0.10, 0.00]),
        "middle": ObservationKernel.from_values("middle", [0.10, 0.40, 0.40, 0.10]),
        "late": ObservationKernel.from_values("late", [0.00, 0.10, 0.25, 0.65]),
    }
    z_by_source = {
        name: x_true + kernel.log_phase_transform(q_true, c_true)
        for name, kernel in kernels.items()
    }

    result = estimate_phase_diagnostic(
        region_id="DE-BE",
        pathogen="SARS-CoV-2",
        date=date(2026, 1, 10),
        z_by_source=z_by_source,
        kernels=kernels,
        source_variance={name: 0.01 for name in kernels},
        lambda_q=1.0e-4,
        lambda_c=10.0,
    )

    assert abs(result.q_phase - q_true) < 0.02
    assert result.identifiability_q > 0.0
    assert "growth is not identifiable" not in " ".join(result.warnings)


def test_phase_diagnostic_warns_when_kernels_are_identical() -> None:
    kernel = ObservationKernel.from_values("same", [0.2, 0.6, 0.2])
    result = estimate_phase_diagnostic(
        region_id="DE-BE",
        pathogen="SARS-CoV-2",
        date=date(2026, 1, 10),
        z_by_source={"a": 1.0, "b": 1.0},
        kernels={"a": kernel, "b": kernel},
        source_variance={"a": 0.01, "b": 0.01},
        delta_q=1.0e-6,
        delta_qc=1.0e-6,
    )

    assert result.identifiability_q < 1.0e-6
    assert any("growth is not identifiable" in warning for warning in result.warnings)
    assert np.isfinite(result.covariance).all()
