"""Determinism (#296): explicit seeds, a fixed integration generator and the ranking fingerprint."""

import numpy as np
import pandas as pd
import pytest

from gabi.domain.research.statistics import bootstrap_sharpe_ci
from gabi.infrastructure.statistics.prospective import ScipyNormalCDF

RETURNS = pd.Series(np.random.default_rng(7).normal(0.0005, 0.01, 300))


def test_the_bootstrap_needs_an_explicit_seed_and_repeats_with_it():
    with pytest.raises(TypeError):
        bootstrap_sharpe_ci(RETURNS, periods_per_year=252, n_boot=50)
    with pytest.raises(TypeError):
        bootstrap_sharpe_ci(RETURNS, periods_per_year=252, n_boot=50, seed=None)
    first = bootstrap_sharpe_ci(RETURNS, periods_per_year=252, n_boot=50, seed=11)
    assert bootstrap_sharpe_ci(RETURNS, periods_per_year=252, n_boot=50, seed=11) == first


def test_the_normal_integration_is_fixed_by_default_and_unseeded_only_on_request():
    covariance = np.array([[1.0, 0.6, 0.3], [0.6, 1.0, 0.6], [0.3, 0.6, 1.0]])
    values = np.array([1.2, 1.5, 1.8])
    # Two fresh default instances give the same number: the generator is fixed, not shared state.
    assert ScipyNormalCDF()(values, covariance) == ScipyNormalCDF()(values, covariance)
    assert ScipyNormalCDF(rng=None).rng is None  # The published-plan commands keep SciPy's own integration.
    seeded = ScipyNormalCDF(rng=np.random.default_rng(3))
    assert 0 < seeded(values, covariance) < 1
