"""Historical readers for Factor Lab; calculation is shared application/domain code."""
from datetime import date
from pathlib import Path

from gabi.application.research.factor_engine import run_factor_analysis
from gabi.infrastructure.storage.factor_prices import SqliteFactorPrices


class LegacyFactorInputs:
    def __init__(self, data_dir: Path):
        self.prices = SqliteFactorPrices(data_dir)

    @staticmethod
    def membership(as_of: str) -> dict:
        from gabi import universe

        return universe.get_sp500_constituents_asof(as_of)

    @staticmethod
    def sample(symbols: list, maximum: int | None) -> list:
        from gabi.multifactor_backtest import _sample_symbols

        return _sample_symbols(symbols, maximum)

    @staticmethod
    def ranking(as_of: str, symbols: list):
        from gabi import screener_asof

        return screener_asof.build_ranking_as_of(as_of, symbols=symbols)["table"]


def run_factors(start: str, end: str, *, months: int, mode: str,
                max_symbols: int | None, data_dir: Path, today: date) -> dict:
    return run_factor_analysis(start, end, months=months, mode=mode, max_symbols=max_symbols,
                               inputs=LegacyFactorInputs(data_dir), today=today)
