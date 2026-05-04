import numpy as np

from app.services.research.phase_lead.convolution import compute_mu
from app.services.research.phase_lead.kernels import ObservationKernel
from app.services.research.phase_lead.mappings import SourceMapping


def test_compute_mu_uses_delayed_convolution_with_earliest_padding() -> None:
    mapping = SourceMapping(
        source="cases",
        observation_units=["r0", "r1"],
        latent_regions=["r0", "r1"],
        H=np.eye(2),
    )
    kernel = ObservationKernel.from_values("two_day", [0.25, 0.75])
    incidence = np.array(
        [
            [[10.0], [20.0]],
            [[30.0], [40.0]],
            [[50.0], [60.0]],
        ]
    )
    x_window = np.log(incidence)

    mu = compute_mu(
        x_window=x_window,
        source_mapping=mapping,
        kernel=kernel,
        log_alpha=0.0,
        pathogen_index=0,
        epsilon=0.0,
    )

    expected_t0 = 0.25 * incidence[0, :, 0] + 0.75 * incidence[0, :, 0]
    expected_t1 = 0.25 * incidence[1, :, 0] + 0.75 * incidence[0, :, 0]

    assert mu.shape == (2, 3)
    np.testing.assert_allclose(mu[:, 0], expected_t0)
    np.testing.assert_allclose(mu[:, 1], expected_t1)
