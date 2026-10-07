"""Archived WIKI response interpretation; candidates never establish issuer identity."""

import pandas as pd

SOURCE_ID = "nasdaq-wiki:frozen-2018-03-27"
URL = "https://data.nasdaq.com/api/v3/datatables/WIKI/PRICES.json"
START, END_EXCLUSIVE = "2008-01-01", "2016-07-01"
COLUMNS = "ticker,date,open,high,low,close,volume,ex-dividend,split_ratio,adj_close"


def wiki_ticker(symbol: str) -> str:
    return symbol.replace("-", "_").replace(".", "_")


def cache_payload(symbol: str, payload: dict) -> dict:
    if payload["meta"].get("next_cursor_id"):
        raise ValueError(f"WIKI {symbol}: paginated response not expected for one ticker")
    return {"columns": [column["name"] for column in payload["datatable"]["columns"]],
            "data": payload["datatable"]["data"]}


def price_frame(symbol: str, payload: dict) -> pd.DataFrame | None:
    if not payload["data"]:
        return None
    frame = pd.DataFrame(payload["data"], columns=payload["columns"])
    frame["symbol"] = symbol
    return frame.rename(columns={"adj_close": "adjusted_close"})[
        ["symbol", "date", "open", "high", "low", "close", "adjusted_close", "volume"]]


def source_metadata(digests: dict[str, str]) -> dict:
    return {"name": "Nasdaq Data Link WIKI Prices (community, frozen 2018-03-27)", "url": URL,
            "start": START, "end_exclusive": END_EXCLUSIVE, "quality": "research_archive_unverified_identity",
            "adjustment": "adj_close adjusts splits and cash dividends; ex-dividend and split_ratio kept in raw files",
            "limitation": "tickers as used until 2018; earlier reuse is possible and checked against SEC per CIK",
            "files_sha256": digests}
