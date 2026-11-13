"""Original SciPy multivariate integration, outside the deterministic plan rules.

The integration is Monte Carlo. New code gets a fixed generator by default (#296), so the
same call returns the same number. ``rng=None`` keeps SciPy's own unseeded integration:
only the commands that regenerate the already published plans pass it, so that their
behaviour stays the one those plans were made with.
"""

import numpy as np
from scipy.stats import multivariate_normal

SEED = 20261104
_FIXED = object()


class ScipyNormalCDF:
    def __init__(self, rng: np.random.Generator | None | object = _FIXED):
        self.rng = np.random.default_rng(SEED) if rng is _FIXED else rng

    def __call__(self, values: np.ndarray, covariance: np.ndarray) -> float:
        distribution = multivariate_normal(mean=np.zeros(len(values)), cov=covariance)
        if self.rng is None:
            return float(distribution.cdf(values))
        return float(distribution.cdf(values, rng=self.rng))
