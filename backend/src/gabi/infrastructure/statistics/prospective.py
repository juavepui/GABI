"""Original SciPy multivariate integration, outside the deterministic plan rules."""

import numpy as np
from scipy.stats import multivariate_normal


class ScipyNormalCDF:
    def __init__(self, rng: np.random.Generator | None = None):
        self.rng = rng

    def __call__(self, values: np.ndarray, covariance: np.ndarray) -> float:
        distribution = multivariate_normal(mean=np.zeros(len(values)), cov=covariance)
        if self.rng is None:
            return float(distribution.cdf(values))
        return float(distribution.cdf(values, rng=self.rng))
