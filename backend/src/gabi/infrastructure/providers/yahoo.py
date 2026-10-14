"""Yahoo Finance through yfinance; the only module that imports it for the compatibility facades.

yfinance owns its HTTP and response sizes, so no byte budget is added here. Calls resolve
``yfinance`` attributes when made, which keeps one replaceable transport for tests and tools.
"""

from pathlib import Path

import pandas as pd
import yfinance


def download(tickers: list[str], **options) -> pd.DataFrame:
    return yfinance.download(tickers, **options)


def ticker(symbol: str):
    return yfinance.Ticker(symbol)


def splits(symbol: str) -> pd.Series:
    return yfinance.Ticker(symbol).splits


def history(symbol: str, **options) -> pd.DataFrame:
    return yfinance.Ticker(symbol).history(**options)


def use_timezone_cache(directory: Path) -> None:
    """yfinance keeps this location process-wide; callers set it only for explicit refresh actions."""
    yfinance.set_tz_cache_location(str(directory))
