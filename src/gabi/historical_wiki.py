"""Nasdaq Data Link WIKI Prices as an archived price source for 2010-2015 (#28).

The community WIKI table was frozen in March 2018 with the tickers in use
then, so it still holds issuers absorbed in 2016-2018 whose symbols were
later reused (EMC, CA, DOW, STI, MON...). It carries as-traded closes, the
ex-dividend amount and split ratio per day. A ticker may still have been
reused *before* 2018 (NSM, SUN...): rows are only candidates, and
``historical_price_audit`` applies the SEC listing, price-level and dividend
checks per CIK before any attribution.

Responses are cached under ``data/history_refresh/nasdaq_wiki`` with their
SHA-256 in ``historical_sources``; the API key is never written to disk there.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import pandas as pd
import requests

from . import config, historical_archive

SOURCE_ID = "nasdaq-wiki:frozen-2018-03-27"
DIRECTORY = config.DATA_DIR / "history_refresh" / "nasdaq_wiki"
URL = "https://data.nasdaq.com/api/v3/datatables/WIKI/PRICES.json"
START, END_EXCLUSIVE = "2008-01-01", "2016-01-01"
COLUMNS = "ticker,date,open,high,low,close,volume,ex-dividend,split_ratio,adj_close"


def _wiki_ticker(symbol: str) -> str:
    return symbol.replace("-", "_").replace(".", "_")


def fetch(symbols: list[str], *, pause: float = 0.5) -> dict:
    """Download each symbol once (resumable); network errors are retried."""
    key = config.load_nasdaq_data_link_key()
    if not key:
        raise ValueError("Nasdaq Data Link API key missing: set it in Configuración")
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    fetched = cached = empty = failed = 0
    for symbol in symbols:
        path = DIRECTORY / f"{symbol}.json"
        if path.exists():
            cached += 1
            continue
        params = {"ticker": _wiki_ticker(symbol), "date.gte": START, "date.lt": END_EXCLUSIVE,
                  "qopts.columns": COLUMNS, "api_key": key}
        payload = None
        for _attempt in range(6):
            try:
                response = requests.get(URL, params=params, timeout=90)
            except requests.RequestException as exc:
                print(f"WIKI {symbol}: network error ({type(exc).__name__}); retrying in 5 min", flush=True)
                time.sleep(300)
                continue
            if response.status_code == 429:
                time.sleep(600)
                continue
            if response.status_code == 200:
                payload = response.json()
            break
        if payload is None:
            failed += 1
            print(f"WIKI {symbol}: failed", flush=True)
            continue
        if payload["meta"].get("next_cursor_id"):
            raise ValueError(f"WIKI {symbol}: paginated response not expected for one ticker")
        # Store data and column names only; the request URL holds the key.
        path.write_text(json.dumps({"columns": [column["name"] for column in payload["datatable"]["columns"]],
                                    "data": payload["datatable"]["data"]}), encoding="utf-8")
        rows = len(payload["datatable"]["data"])
        empty += rows == 0
        fetched += 1
        print(f"WIKI {symbol}: {rows} rows", flush=True)
        time.sleep(pause)
    return {"fetched": fetched, "cached": cached, "empty": empty, "failed": failed}


def import_cached() -> dict:
    """Idempotently import cached responses as an as-traded archive source."""
    files = sorted(DIRECTORY.glob("*.json"))
    digests: dict[str, str] = {}
    frames = []
    for path in files:
        digests[path.stem] = hashlib.sha256(path.read_bytes()).hexdigest()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not payload["data"]:
            continue
        frame = pd.DataFrame(payload["data"], columns=payload["columns"])
        frame["symbol"] = path.stem
        frames.append(frame.rename(columns={"adj_close": "adjusted_close"})[
            ["symbol", "date", "open", "high", "low", "close", "adjusted_close", "volume"]])
    historical_archive.register_source(SOURCE_ID, {
        "name": "Nasdaq Data Link WIKI Prices (community, frozen 2018-03-27)", "url": URL,
        "start": START, "end_exclusive": END_EXCLUSIVE, "quality": "research_archive_unverified_identity",
        "adjustment": "adj_close adjusts splits and cash dividends; ex-dividend and split_ratio kept in raw files",
        "limitation": "tickers as used until 2018; earlier reuse is possible and checked against SEC per CIK",
        "files_sha256": digests})
    if not frames:
        return {"files": len(files), "accepted": 0, "rejected": 0}
    data = pd.concat(frames, ignore_index=True)
    result = historical_archive.import_price_chunk(SOURCE_ID, data, set(data.symbol), START, END_EXCLUSIVE)
    return {"files": len(files), **result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", type=Path, help="Text file with one symbol per line")
    parser.add_argument("--import-cached", action="store_true")
    args = parser.parse_args()
    report = {}
    if args.fetch:
        symbols = [line.strip().upper() for line in args.fetch.read_text().splitlines() if line.strip()]
        report["fetch"] = fetch(symbols)
    if args.import_cached:
        report["import"] = import_cached()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
