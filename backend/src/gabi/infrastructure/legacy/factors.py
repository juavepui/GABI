"""Single bridge to the existing Factor Lab engine."""

from pathlib import Path


def run_factors(start: str, end: str, *, months: int, mode: str,
                max_symbols: int | None, data_dir: Path) -> dict:
    from gabi import factor_lab
    from gabi.infrastructure.storage.factor_prices import SqliteFactorPrices

    return factor_lab.run_factor_analysis(start, end, months=months,
                                          mode=mode, max_symbols=max_symbols,
                                          price_loader=SqliteFactorPrices(data_dir))
