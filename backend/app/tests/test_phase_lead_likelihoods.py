import math

import numpy as np
import pytest

from app.services.research.phase_lead.likelihoods import (
    dirichlet_multinomial_logpmf,
    neg_binom_logpmf,
    neg_binom_nll,
    student_t_logpdf,
    wastewater_nll,
)


def test_negative_binomial_likelihood_is_finite_and_nll_is_negative_logpmf() -> None:
    logp = neg_binom_logpmf(y=4.0, mu=3.2, phi=12.0)

    assert math.isfinite(logp)
    assert math.isclose(neg_binom_nll(4.0, 3.2, 12.0), -logp)


def test_student_t_and_wastewater_likelihood_are_finite() -> None:
    loc = math.log(10.0)
    y_log = loc + 0.1

    assert math.isfinite(student_t_logpdf(y_log, loc=loc, scale=0.5, df=4.0))
    assert math.isfinite(
        wastewater_nll(
            y_log=y_log,
            mu=10.0,
            bias=0.0,
            covariates=np.array([1.0, 2.0]),
            gamma=np.array([0.01, -0.02]),
            sigma=0.5,
            df=4.0,
        )
    )


def test_student_t_rejects_invalid_scale_or_df() -> None:
    with pytest.raises(ValueError):
        student_t_logpdf(1.0, loc=0.0, scale=0.0, df=4.0)
    with pytest.raises(ValueError):
        student_t_logpdf(1.0, loc=0.0, scale=1.0, df=1.0)


def test_dirichlet_multinomial_likelihood_clips_probabilities_and_is_finite() -> None:
    logp = dirichlet_multinomial_logpmf(
        counts=np.array([2, 3, 0]),
        pi=np.array([0.4, 0.6, 0.0]),
        kappa=20.0,
    )

    assert math.isfinite(logp)
