"""Legacy compatibility for ``gabi.domain.market.risk``."""

import pandas as pd

import gabi.domain.market.risk as _implementation

from . import config


def compute_risk_metrics(price_df: pd.DataFrame, benchmark_df: pd.DataFrame = None,
                         risk_free_rate: float = None) -> dict:
    rate = config.RISK_FREE_RATE if risk_free_rate is None else risk_free_rate
    return _implementation.compute_risk_metrics(price_df, benchmark_df, rate)


_daily_returns = _implementation._daily_returns
_return_price = _implementation._return_price
_annualized_return = _implementation._annualized_return
_annualized_volatility = _implementation._annualized_volatility
_max_drawdown = _implementation._max_drawdown
_beta_vs_benchmark = _implementation._beta_vs_benchmark
_sharpe_ratio = _implementation._sharpe_ratio
_sortino_ratio = _implementation._sortino_ratio
_monthly_win_rate = _implementation._monthly_win_rate
TRADING_DAYS_PER_YEAR = _implementation.TRADING_DAYS_PER_YEAR
EMPTY_RESULT = _implementation.EMPTY_RESULT
