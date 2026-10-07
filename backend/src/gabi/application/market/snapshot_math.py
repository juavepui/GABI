"""Read the original seven-day price windows, then calculate ranking returns."""

from collections.abc import Callable
from datetime import date

import pandas as pd

from gabi.domain.portfolio import evaluation

PriceAt = Callable[..., float | None]


class SnapshotCalculations:
    @staticmethod
    def progress(symbols: list[str], as_of_date: str, *, data_as_of, price_at: PriceAt,
                 today: date, cost_bps: float = 0) -> dict:
        start, end = pd.Timestamp(as_of_date), pd.Timestamp(today)
        prices = {}
        for symbol in [*symbols, "SPY"]:
            prices[symbol, "start"] = price_at(symbol, start)
            prices[symbol, "end"] = price_at(symbol, end)
        return evaluation.progress_for(symbols, as_of_date, data_as_of=data_as_of,
                                       prices=prices, today=today, cost_bps=cost_bps)

    @staticmethod
    def curve(symbols: list[str], as_of_date: str, histories: dict) -> pd.DataFrame:
        return evaluation.price_curve_for(symbols, as_of_date, histories)

    @staticmethod
    def evaluate(symbols: list[str], as_of_date: str, months: int, *, price_at: PriceAt,
                 today: date, cost_bps: float = 0) -> dict:
        start = pd.Timestamp(as_of_date)
        end = start + pd.DateOffset(months=months)
        prices = {}
        if end <= pd.Timestamp(today):
            for symbol in [*dict.fromkeys(symbols), "SPY"]:
                prices[symbol, "start"] = price_at(symbol, start)
                prices[symbol, "end"] = price_at(symbol, end, after=True)
        return evaluation.evaluate(symbols, as_of_date, months, cost_bps, prices=prices, today=today)
