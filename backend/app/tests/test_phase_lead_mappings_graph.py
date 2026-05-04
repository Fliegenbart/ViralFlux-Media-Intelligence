import numpy as np
import pytest

from app.services.research.phase_lead.graph import RegionalGraph
from app.services.research.phase_lead.mappings import SourceMapping


def test_source_mapping_aggregates_latent_regions_to_observation_units() -> None:
    mapping = SourceMapping(
        source="wastewater",
        observation_units=["catchment-a", "catchment-b"],
        latent_regions=["DE-BE", "DE-BB"],
        H=np.array([[1.0, 0.0], [0.25, 0.75]]),
    )

    observed = mapping.apply(np.array([10.0, 20.0]))

    np.testing.assert_allclose(observed, np.array([10.0, 17.5]))


def test_source_mapping_rejects_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="shape"):
        SourceMapping(
            source="bad",
            observation_units=["a"],
            latent_regions=["r1", "r2"],
            H=np.array([[1.0, 0.0], [0.0, 1.0]]),
        )


def test_regional_graph_normalizes_source_to_target_rows_and_computes_pressures() -> None:
    graph = RegionalGraph(
        regions=["r0", "r1", "r2"],
        T=np.array(
            [
                [0.0, 2.0, 0.0],
                [0.0, 0.0, 3.0],
                [1.0, 0.0, 0.0],
            ]
        ),
    )
    n = np.array([100.0, 20.0, 10.0])
    q = np.array([0.12, 0.01, -0.02])
    population = np.array([1000.0, 1000.0, 1000.0])

    np.testing.assert_allclose(graph.T.sum(axis=1), np.ones(3))
    pi = graph.incoming_infection_pressure(n, population)
    omega = graph.incoming_growth_pressure(q)

    assert pi.shape == (3,)
    assert omega.shape == (3,)
    assert np.isfinite(pi).all()
    assert np.isfinite(omega).all()
    assert omega[1] > 0.0
