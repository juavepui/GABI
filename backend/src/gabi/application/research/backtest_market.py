"""Explicit inputs of the V1/V2 multifactor backtests (#132).

The backtests read the historical S&P 500 composition, the point-in-time ranking, prices
attributed to an issuer, SEC filing dates, the NYSE calendar and today's date. Each one
is passed in, so the use cases own no data source and no clock.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class BacktestMarket:
    membership: Callable[[str], dict]  # {"symbols", "is_exact", "note"} at a date
    ranking: Callable[[str, list[str]], pd.DataFrame]  # point-in-time ranking table
    quality: Callable[[pd.DataFrame], dict]  # data-quality summary of a ranking
    prices: Callable[..., dict[str, pd.DataFrame]]  # (symbols, as_of, owners=None) -> adjusted histories
    last_filings: Callable[[list[str], str], dict[str, str]]  # (symbols, as_of) -> last SEC filing date
    owner: Callable[[str, str], str | None]  # (symbol, as_of) -> entity that owned the ticker
    exit_value: Callable[[pd.DataFrame, str, pd.Timestamp, pd.Timestamp], dict]  # terminal value of a series
    calendar: Any  # exchange calendar: date_to_session, next_session, sessions_in_range
    today: Callable[[], date]
    risk_free_rate: float
