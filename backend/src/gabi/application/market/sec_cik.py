"""Explicit current SEC map refresh and persistence of successful resolutions."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from gabi.domain.market.sec_cik import lookup, mapping_rows


class CikCache(Protocol):
    def exists(self) -> bool: ...
    def modified_at(self) -> float: ...
    def read(self) -> pd.DataFrame: ...
    def save(self, frame: pd.DataFrame) -> None: ...


class CikResolutions(Protocol):
    def remember(self, symbol: str, cik: str, title: str) -> None: ...
    def cached(self, symbol: str) -> tuple: ...


class CikAttempt(Protocol):
    calls: int
    def payload(self, value) -> None: ...
    def finish(self, status: str, *, state: dict | None = None, new: int = 0, revised: int = 0,
               unchanged: int = 0, reason: str = "", skipped: bool = False) -> dict: ...


def current_map(cache: CikCache, fetch: Callable[[], dict], attempt_factory: Callable[[], CikAttempt],
                retry: Callable, checkpoint: Callable[[], dict], fingerprint: Callable[[object], str],
                timestamp: Callable[[], float], *, force_refresh: bool = False) -> pd.DataFrame:
    if not force_refresh and cache.exists() and timestamp() - cache.modified_at() < 7 * 86400:
        return cache.read()
    attempt = attempt_factory()
    try:
        data = retry(fetch, attempt)
        attempt.payload(data)
    except Exception as exc:
        attempt.finish("failed", reason=str(exc))
        if cache.exists():
            return cache.read()
        raise
    rows = mapping_rows(data)
    frame = pd.DataFrame(rows)
    cache.save(frame)
    cp = checkpoint()
    digest = fingerprint(rows)
    status = "new" if not cp else "unchanged" if cp.get("fingerprint") == digest else "revised"
    attempt.finish(status, state={"fingerprint": digest}, reason="revisión semanal del mapeo ticker/CIK")
    return frame


def resolve(symbol: str, mapping: pd.DataFrame, resolutions: CikResolutions) -> tuple:
    resolved = lookup(symbol, mapping)
    if resolved is None:
        return resolutions.cached(symbol)
    cik, title = resolved
    resolutions.remember(symbol, cik, title)
    return cik, title


@dataclass
class CikResolver:
    cache: CikCache
    resolutions: CikResolutions
    fetch: Callable[[], dict]
    attempt_factory: Callable[[], CikAttempt]
    retry: Callable
    checkpoint: Callable[[], dict]
    fingerprint: Callable[[object], str]
    timestamp: Callable[[], float]

    def mapping(self, force_refresh: bool = False) -> pd.DataFrame:
        return current_map(self.cache, self.fetch, self.attempt_factory, self.retry,
                           self.checkpoint, self.fingerprint, self.timestamp, force_refresh=force_refresh)

    def resolve(self, symbol: str, mapping: pd.DataFrame) -> tuple:
        return resolve(symbol, mapping, self.resolutions)
