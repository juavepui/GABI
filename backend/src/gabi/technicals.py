"""Legacy compatibility for ``gabi.domain.market.technicals``."""

import pandas as pd

import gabi.domain.market.technicals as _implementation

from . import config

_LEGACY_RSI_PERIOD = config.RSI_PERIOD


def _rsi(series: pd.Series, period: int = _LEGACY_RSI_PERIOD) -> pd.Series:
    return _implementation._rsi(series, period)


def compute_technicals(price_df: pd.DataFrame, benchmark_df: pd.DataFrame = None) -> dict:
    parameters = _implementation.TechnicalParameters(
        config.SMA_SHORT, config.SMA_LONG, _LEGACY_RSI_PERIOD,
        config.MOMENTUM_SHORT_DAYS, config.MOMENTUM_LONG_DAYS,
    )
    return _implementation.compute_technicals(price_df, benchmark_df, parameters=parameters)


_sma = _implementation._sma
_pct_change_n = _implementation._pct_change_n
_same_window = _implementation._same_window
_return_price = _implementation._return_price
EMPTY_RESULT = _implementation.EMPTY_RESULT
