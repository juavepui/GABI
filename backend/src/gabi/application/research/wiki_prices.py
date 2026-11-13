"""Explicit, resumable WIKI download and local archive import."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from gabi.domain.research.wiki_prices import (
    END_EXCLUSIVE,
    SOURCE_ID,
    START,
    cache_payload,
    price_frame,
    source_metadata,
)


@dataclass(frozen=True)
class FetchResponse:
    status: int = 0
    payload: dict | None = None
    error_name: str | None = None


@dataclass(frozen=True)
class CachedResponse:
    symbol: str
    payload: dict
    sha256: str


class WikiSource(Protocol):
    def request(self, symbol: str, api_key: str) -> FetchResponse: ...


class WikiCache(Protocol):
    def ensure_directory(self) -> None: ...
    def contains(self, symbol: str) -> bool: ...
    def save(self, symbol: str, payload: dict) -> None: ...
    def records(self) -> Iterator[CachedResponse]: ...


class PriceArchive(Protocol):
    def register(self, source_id: str, metadata: dict) -> None: ...
    def import_prices(self, source_id: str, frame: pd.DataFrame, symbols: set[str], start: str, end: str) -> dict: ...


def fetch(symbols: list[str], cache: WikiCache, source: WikiSource, *, api_key: str | None,
          wait: Callable[[float], None], progress: Callable[[str], None], pause: float = 0.5,
          max_symbols: int = 1000) -> dict:
    if not api_key:
        raise ValueError("Nasdaq Data Link API key missing: set it in Configuración")
    if len(symbols) > max_symbols:
        raise ValueError("WIKI symbol limit exceeded")
    cache.ensure_directory()
    fetched = cached = empty = failed = 0
    for symbol in symbols:
        if cache.contains(symbol):
            cached += 1
            continue
        payload = None
        for _attempt in range(6):
            response = source.request(symbol, api_key)
            if response.error_name:
                progress(f"WIKI {symbol}: network error ({response.error_name}); retrying in 5 min")
                wait(300)
                continue
            if response.status == 429:
                wait(600)
                continue
            if response.status == 200:
                payload = response.payload
            break
        if payload is None:
            failed += 1
            progress(f"WIKI {symbol}: failed")
            continue
        cached_payload = cache_payload(symbol, payload)
        cache.save(symbol, cached_payload)
        rows = len(cached_payload["data"])
        empty += rows == 0
        fetched += 1
        progress(f"WIKI {symbol}: {rows} rows")
        wait(pause)
    return {"fetched": fetched, "cached": cached, "empty": empty, "failed": failed}


def import_cached(cache: WikiCache, archive: PriceArchive, *, max_rows: int = 2_000_000) -> dict:
    digests: dict[str, str] = {}
    frames = []
    rows = 0
    for record in cache.records():
        digests[record.symbol] = record.sha256
        rows += len(record.payload["data"])
        if rows > max_rows:
            raise ValueError("WIKI import row limit exceeded")
        frame = price_frame(record.symbol, record.payload)
        if frame is not None:
            frames.append(frame)
    archive.register(SOURCE_ID, source_metadata(digests))
    if not frames:
        return {"files": len(digests), "accepted": 0, "rejected": 0}
    data = pd.concat(frames, ignore_index=True)
    result = archive.import_prices(SOURCE_ID, data, set(data.symbol), START, END_EXCLUSIVE)
    return {"files": len(digests), **result}
