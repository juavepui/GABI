"""Tiingo listing, fixed windows and candidate-price interpretation."""

from dataclasses import dataclass
from types import MappingProxyType

import pandas as pd

SOURCE_ID = "tiingo:daily-2026-09"
PRICES_URL = "https://api.tiingo.com/tiingo/daily/{ticker}/prices?startDate={start}&endDate={end}"
TICKERS_URL = "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"
PACE_SECONDS = 80
START, END_EXCLUSIVE = "2008-01-01", "2016-07-01"
WINDOWS = MappingProxyType({
    "2010-2015": (START, "2016-12-31", END_EXCLUSIVE, "", SOURCE_ID),
    "2016-2025": ("2014-01-01", "2026-06-30", "2026-07-01", "2016_2025", SOURCE_ID + ":2016-2025"),
    "smallmid": ("2009-01-01", "2026-06-30", "2026-07-01", "smallmid", SOURCE_ID + ":smallmid"),
})


@dataclass(frozen=True)
class PriceWindow:
    name: str
    first: str
    last: str
    end_exclusive: str
    subdirectory: str
    source_id: str


def window(name: str) -> PriceWindow:
    return PriceWindow(name, *WINDOWS[name])


def current_listings(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame[frame.priceCurrency.eq("USD")].dropna(subset=["ticker", "startDate"])
    frame["ticker"] = frame.ticker.str.upper()
    return frame.sort_values("startDate").groupby("ticker").tail(1).set_index("ticker")


def eligible(listings: pd.DataFrame, symbol: str, first_needed: str, last_needed: str) -> bool:
    if symbol not in listings.index:
        return False
    row = listings.loc[symbol]
    return bool(row.assetType == "Stock" and row.startDate <= first_needed and
                str(row.endDate) >= last_needed)


def price_frame(symbol: str, rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["date"] = frame["date"].str[:10]
    frame["symbol"] = symbol
    return frame.rename(columns={"adjClose": "adjusted_close"})[
        ["symbol", "date", "open", "high", "low", "close", "adjusted_close", "volume"]]


def new_observations(frame: pd.DataFrame, before: pd.DatetimeIndex, spec: PriceWindow) -> int:
    return int((~pd.to_datetime(frame.date).isin(before) & (frame.date >= spec.first)
                & (frame.date < spec.end_exclusive)).sum())


def source_metadata(spec: PriceWindow, digests: dict) -> dict:
    return {"name": "Tiingo end-of-day prices (free plan)", "url": "https://api.tiingo.com/tiingo/daily/<ticker>/prices",
            "start": spec.first, "end_exclusive": spec.end_exclusive, "quality": "research_archive_unverified_identity",
            "adjustment": "adjClose adjusts splits and cash dividends (divCash/splitFactor kept in raw files)",
            "limitation": "only tickers whose current listing covers the period; recycled tickers are not served",
            "files_sha256": digests}
