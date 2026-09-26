"""Tiingo (free plan) as a third archived price source for 2010-2015 (issue #28).

Tiingo's daily API only serves the security that *currently* uses a ticker,
so only symbols whose present listing already covered 2009-2015 are fetched;
recycled tickers (EMC, CA, STI...) are skipped rather than mis-attributed. The
free plan allows ~50 requests per hour, so downloads are paced and resumable.

Raw JSON responses are cached under ``data/history_refresh/tiingo`` with their
SHA-256 in ``historical_sources``; the API key travels only in the request
header. Imported rows are *candidates*: ``historical_price_audit`` applies the
same SEC listing, price-level and dividend checks as for FINSABER.
"""

import argparse
import hashlib
import json
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

from . import config, historical_archive

SOURCE_ID = "tiingo:daily-2026-09"
DIRECTORY = config.DATA_DIR / "history_refresh" / "tiingo"
PRICES_URL = "https://api.tiingo.com/tiingo/daily/{ticker}/prices?startDate=2008-01-01&endDate=2016-12-31"
TICKERS_URL = "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"
PACE_SECONDS = 80  # ~45 requests/hour, below the free hourly allocation
START, END_EXCLUSIVE = "2008-01-01", "2016-07-01"


def _headers() -> dict:
    key = config.load_tiingo_key()
    if not key:
        raise ValueError("Tiingo API key missing: set it in Configuración")
    return {"Authorization": f"Token {key}", "Content-Type": "application/json"}


def current_listings(path: Path) -> pd.DataFrame:
    """Latest Tiingo listing per ticker: the one its daily API returns."""
    with zipfile.ZipFile(path) as archive:
        frame = pd.read_csv(archive.open("supported_tickers.csv"))
    frame = frame[frame.priceCurrency.eq("USD")].dropna(subset=["ticker", "startDate"])
    frame["ticker"] = frame.ticker.str.upper()
    return frame.sort_values("startDate").groupby("ticker").tail(1).set_index("ticker")


def eligible(listings: pd.DataFrame, symbol: str, first_needed: str, last_needed: str) -> bool:
    """The present listing is a stock that already traded over the whole need."""
    if symbol not in listings.index:
        return False
    row = listings.loc[symbol]
    return bool(row.assetType == "Stock" and row.startDate <= first_needed and
                str(row.endDate) >= last_needed)


def fetch(symbols: list[str], *, pace: float = PACE_SECONDS) -> dict:
    """Download missing symbols one by one; waits out the hourly allocation."""
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    fetched = cached = failed = 0
    for symbol in symbols:
        path = DIRECTORY / f"{symbol}.json"
        if path.exists():
            cached += 1
            continue
        ticker = symbol.replace(".", "-").lower()
        response = None
        for attempt in range(12):
            try:
                response = requests.get(PRICES_URL.format(ticker=ticker), headers=_headers(), timeout=60)
            except requests.RequestException as exc:
                # Connectivity loss: wait and retry; cached files make reruns resume.
                print(f"Tiingo {symbol}: network error ({type(exc).__name__}); retrying in 5 min", flush=True)
                time.sleep(300)
                continue
            if response.status_code == 429 and attempt < 11:
                print(f"Tiingo hourly allocation reached; waiting ({symbol})", flush=True)
                time.sleep(900)
                continue
            break
        if response is None or response.status_code != 200:
            failed += 1
            print(f"Tiingo {symbol}: HTTP {response.status_code if response is not None else 'no response'}", flush=True)
        else:
            path.write_bytes(response.content)
            fetched += 1
            print(f"Tiingo {symbol}: {len(response.json())} rows", flush=True)
        time.sleep(pace)
    return {"fetched": fetched, "cached": cached, "failed": failed}


def import_cached() -> dict:
    """Idempotently import cached responses as an archived as-traded source."""
    files = sorted(DIRECTORY.glob("*.json"))
    digests = {}
    frames = []
    for path in files:
        digests[path.stem] = hashlib.sha256(path.read_bytes()).hexdigest()
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not rows:
            continue
        frame = pd.DataFrame(rows)
        frame["date"] = frame["date"].str[:10]
        frame["symbol"] = path.stem
        frames.append(frame.rename(columns={"adjClose": "adjusted_close"})[
            ["symbol", "date", "open", "high", "low", "close", "adjusted_close", "volume"]])
    historical_archive.register_source(SOURCE_ID, {
        "name": "Tiingo end-of-day prices (free plan)", "url": "https://api.tiingo.com/tiingo/daily/<ticker>/prices",
        "start": START, "end_exclusive": END_EXCLUSIVE, "quality": "research_archive_unverified_identity",
        "adjustment": "adjClose adjusts splits and cash dividends (divCash/splitFactor kept in raw files)",
        "limitation": "only tickers whose current listing covers the period; recycled tickers are not served",
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
