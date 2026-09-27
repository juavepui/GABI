"""#42: O'Brien-Fleming boundaries spend exactly alpha."""

import numpy as np
from scipy.stats import norm

from gabi import prospective_plan as pp


def test_single_look_is_the_fixed_test_and_boundaries_decrease():
    assert np.isclose(pp.boundaries([1.0])[0], norm.ppf(0.95), atol=1e-6)
    bounds = pp.boundaries([0.3, 0.6, 1.0])
    assert bounds[0] > bounds[1] > bounds[2] > norm.ppf(0.95) - 0.1
    assert np.isclose(pp.obrien_fleming_spending(1.0), 0.05)
