"""Yahoo Finance through yfinance; the only module that imports it for the compatibility facades.

yfinance owns its HTTP and response sizes, so no byte budget is added here. Calls resolve
``yfinance`` attributes when made, which keeps one replaceable transport for tests and tools.
"""

import socket
from pathlib import Path

import pandas as pd
import yfinance

PRICE_HOST = "query1.finance.yahoo.com"


def reachable(timeout: float = 5.0) -> bool:
    """True when the Yahoo price host resolves and accepts a TCP connection. Without this, a refresh
    started right after the computer wakes up fails for every company with a DNS error."""
    try:
        with socket.create_connection((PRICE_HOST, 443), timeout=timeout):
            return True
    except OSError:
        return False


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
