"""Tiingo (free plan) as a third archived price source (#28 for 2010-2015, #34 for 2016-2025).

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

from gabi.application.research.tiingo_prices import PriceResponse, RawSnapshot
from gabi.application.research.tiingo_prices import fetch as _fetch
from gabi.application.research.tiingo_prices import import_cached as _import_cached
from gabi.domain.research.tiingo_prices import END_EXCLUSIVE as END_EXCLUSIVE
from gabi.domain.research.tiingo_prices import PACE_SECONDS, PRICES_URL, PriceWindow
from gabi.domain.research.tiingo_prices import SOURCE_ID as SOURCE_ID
from gabi.domain.research.tiingo_prices import START as START
from gabi.domain.research.tiingo_prices import TICKERS_URL as TICKERS_URL
from gabi.domain.research.tiingo_prices import WINDOWS as _WINDOWS
from gabi.domain.research.tiingo_prices import current_listings as _current_listings
from gabi.domain.research.tiingo_prices import eligible as eligible

from . import config, historical_archive, storage, sync_state

DIRECTORY = config.DATA_DIR / "history_refresh" / "tiingo"
WINDOWS = dict(_WINDOWS)


def source_id(window: str) -> str:
    return WINDOWS[window][4]


def _window(window: str) -> tuple[str, str, str, Path]:
    first, last, end_exclusive, subdirectory, _source = WINDOWS[window]
    return first, last, end_exclusive, DIRECTORY / subdirectory if subdirectory else DIRECTORY


def _headers() -> dict:
    key = config.load_tiingo_key()
    if not key:
        raise ValueError("Tiingo API key missing: set it in Configuración")
    return {"Authorization": f"Token {key}", "Content-Type": "application/json"}


def current_listings(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        frame = pd.read_csv(archive.open("supported_tickers.csv"))
    return _current_listings(frame)


class _Cache:
    def __init__(self, directory):
        self.directory = directory

    def ensure_directory(self):
        self.directory.mkdir(parents=True, exist_ok=True)

    def contains(self, symbol):
        return (self.directory / f"{symbol}.json").exists()

    def save(self, symbol, body):
        path = self.directory / f"{symbol}.json"
        pending = path.with_suffix(".json.tmp")
        pending.write_bytes(body)
        pending.replace(path)

    def snapshots(self):
        for path in sorted(self.directory.glob("*.json")):
            body = path.read_bytes()
            yield RawSnapshot(path.stem, body, hashlib.sha256(body).hexdigest())


class _Source:
    def request(self, symbol, first, last):
        ticker = symbol.replace(".", "-").lower()
        try:
            response = requests.get(PRICES_URL.format(ticker=ticker, start=first, end=last), headers=_headers(), timeout=60)
        except requests.RequestException as exc:
            return PriceResponse(error_name=type(exc).__name__)
        return PriceResponse(response.status_code, response.content if response.status_code == 200 else b"",
                             response.json() if response.status_code == 200 else None)


class _Archive:
    def pinned(self, source_id):
        with storage.get_connection() as conn:
            conn.executescript(historical_archive.SCHEMA)
            row = conn.execute("SELECT metadata_json FROM historical_sources WHERE source_id=?", (source_id,)).fetchone()
        return json.loads(row[0]).get("files_sha256", {}) if row else {}

    def register(self, source_id, metadata):
        historical_archive.register_source(source_id, metadata)

    def dates(self, source_id, symbol, first, last):
        return historical_archive.get_prices(source_id, symbol, first, last).index

    def import_prices(self, source_id, frame, symbols, first, last):
        return historical_archive.import_price_chunk(source_id, frame, symbols, first, last)


def _attempt(symbol, dataset):
    return sync_state.Attempt("tiingo", symbol, dataset)


def fetch(symbols: list[str], *, pace: float = PACE_SECONDS, window: str = "2010-2015") -> dict:
    spec = PriceWindow(window, *WINDOWS[window])
    return _fetch(symbols, spec, _Cache(_window(window)[3]), _Source(), attempt_factory=_attempt,
                  wait=time.sleep, progress=lambda message: print(message, flush=True), pace=pace)


def import_cached(window: str = "2010-2015") -> dict:
    return _import_cached(PriceWindow(window, *WINDOWS[window]), _Cache(_window(window)[3]), _Archive(), sync_state,
                          attempt_factory=_attempt)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", type=Path, help="Text file with one symbol per line")
    parser.add_argument("--import-cached", action="store_true")
    parser.add_argument("--window", default="2010-2015", choices=sorted(WINDOWS))
    args = parser.parse_args()
    report = {}
    if args.fetch:
        symbols = [line.strip().upper() for line in args.fetch.read_text().splitlines() if line.strip()]
        report["fetch"] = fetch(symbols, window=args.window)
    if args.import_cached:
        report["import"] = import_cached(args.window)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
