"""Legacy compatibility for ``gabi.domain.portfolio.metrics``."""

import pandas as pd

import gabi.domain.portfolio.metrics as _implementation

from . import config


def rolling_sharpe(returns: pd.Series, window: int = 252,
                   risk_free_rate: float = None) -> pd.Series:
    rate = config.RISK_FREE_RATE if risk_free_rate is None else risk_free_rate
    return _implementation.rolling_sharpe(returns, window, rate)


_finite_returns = _implementation._finite_returns
historical_tail_risk = _implementation.historical_tail_risk
historical_var = _implementation.historical_var
expected_shortfall = _implementation.expected_shortfall
return_distribution = _implementation.return_distribution
tail_risk_metrics = _implementation.tail_risk_metrics
returns_from_nav = _implementation.returns_from_nav
calmar_ratio = _implementation.calmar_ratio
recovery_time = _implementation.recovery_time
beta_vs_benchmark = _implementation.beta_vs_benchmark
tracking_error = _implementation.tracking_error
information_ratio = _implementation.information_ratio
capture_ratios = _implementation.capture_ratios
TRADING_DAYS_PER_YEAR = _implementation.TRADING_DAYS_PER_YEAR
