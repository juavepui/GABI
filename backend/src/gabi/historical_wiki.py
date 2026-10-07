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

import requests

from gabi.application.research.wiki_prices import CachedResponse, FetchResponse
from gabi.application.research.wiki_prices import fetch as _fetch
from gabi.application.research.wiki_prices import import_cached as _import_cached
from gabi.domain.research.wiki_prices import COLUMNS, END_EXCLUSIVE, START, URL
from gabi.domain.research.wiki_prices import SOURCE_ID as SOURCE_ID
from gabi.domain.research.wiki_prices import wiki_ticker as _wiki_ticker

from . import config, historical_archive

DIRECTORY = config.DATA_DIR / "history_refresh" / "nasdaq_wiki"


class _Cache:
    # Compatibility for existing callers overriding DIRECTORY. Modern composition
    # uses the bounded, atomic FileWikiCache; no configuration mutation per job.
    def ensure_directory(self):
        DIRECTORY.mkdir(parents=True, exist_ok=True)

    def contains(self, symbol):
        return (DIRECTORY / f"{symbol}.json").exists()

    def save(self, symbol, payload):
        (DIRECTORY / f"{symbol}.json").write_text(json.dumps(payload), encoding="utf-8")

    def records(self):
        for path in sorted(DIRECTORY.glob("*.json")):
            data = path.read_bytes()
            yield CachedResponse(path.stem, json.loads(data.decode("utf8")), hashlib.sha256(data).hexdigest())


class _Source:
    def request(self, symbol, api_key):
        params = {"ticker": _wiki_ticker(symbol), "date.gte": START, "date.lt": END_EXCLUSIVE,
                  "qopts.columns": COLUMNS, "api_key": api_key}
        try:
            response = requests.get(URL, params=params, timeout=90)
        except requests.RequestException as exc:
            return FetchResponse(error_name=type(exc).__name__)
        return FetchResponse(response.status_code, response.json() if response.status_code == 200 else None)


class _Archive:
    def register(self, source_id, metadata):
        historical_archive.register_source(source_id, metadata)

    def import_prices(self, source_id, frame, symbols, start, end):
        return historical_archive.import_price_chunk(source_id, frame, symbols, start, end)


def fetch(symbols: list[str], *, pause: float = 0.5) -> dict:
    return _fetch(symbols, _Cache(), _Source(), api_key=config.load_nasdaq_data_link_key(),
                  wait=time.sleep, progress=lambda message: print(message, flush=True), pause=pause)


def import_cached() -> dict:
    return _import_cached(_Cache(), _Archive())


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
