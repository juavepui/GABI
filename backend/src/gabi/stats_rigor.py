"""Legacy compatibility for ``gabi.domain.research.statistics``."""

import gabi.domain.research.statistics as _implementation

probabilistic_sharpe_ratio = _implementation.probabilistic_sharpe_ratio
probabilistic_sharpe_ratio_annualized = _implementation.probabilistic_sharpe_ratio_annualized
probabilistic_sharpe_ratio_from_returns = _implementation.probabilistic_sharpe_ratio_from_returns
expected_max_sharpe = _implementation.expected_max_sharpe
deflated_sharpe_ratio = _implementation.deflated_sharpe_ratio
bootstrap_sharpe_ci = _implementation.bootstrap_sharpe_ci
_default_metric = _implementation._default_metric
pbo_cscv = _implementation.pbo_cscv
EULER_MASCHERONI = _implementation.EULER_MASCHERONI
