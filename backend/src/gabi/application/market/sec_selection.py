"""Bounded SEC refresh selection and batch coordination with explicit ports."""

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Protocol

import pandas as pd

from gabi.domain.market.sec_cik import lookup
from gabi.domain.market.sec_selection import MISSING_CIK, MISSING_HISTORICAL_CIK, stale_symbols


class SelectionStore(Protocol):
    def current(self, symbols: list[str]) -> tuple[dict, set[str], dict[str, set[str]]]: ...
    def historical(self, symbols: list[str], as_of: str) -> dict[str, dict]: ...
    def covered_entities(self, entities: list[str]) -> set[str]: ...
    def errors(self, failed: dict) -> None: ...


class Resolutions(Protocol):
    def cached_many(self, symbols: list[str]) -> dict[str, tuple]: ...
    def remember_many(self, values: dict[str, tuple]) -> None: ...


def resolve_many(symbols: list[str], mapping: pd.DataFrame | None, resolutions: Resolutions,
                 cached: dict[str, tuple]) -> dict[str, str]:
    remembered: dict[str, tuple] = {}
    result = {}
    for symbol in symbols:
        row = lookup(symbol, mapping) if mapping is not None else None
        if row is not None:
            remembered[symbol] = row
        cik = (row or cached.get(symbol, (None, None)))[0]
        if cik:
            result[symbol] = cik
    if remembered:
        resolutions.remember_many(remembered)
    return result


def batch(symbols: list[str], ciks: dict, *, operation: Callable, runner: Callable[..., Iterable],
          classify_error: Callable[[Exception], str], progress_cb: Callable | None = None) -> dict:
    failed = {symbol: MISSING_CIK for symbol in symbols if not ciks.get(symbol)}
    tasks = [(symbol, ciks[symbol]) for symbol in symbols if ciks.get(symbol)]
    for done, (symbol, error) in enumerate(runner(tasks, operation), start=1):
        if error is not None:
            failed[symbol] = classify_error(error)
        if progress_cb:
            progress_cb(done, len(symbols), symbol)
    return failed


def refresh(symbols: list[str], *, store: SelectionStore, mapping: Callable[..., pd.DataFrame],
            resolutions: Resolutions, download_batch: Callable, classify_error: Callable[[Exception], str],
            now: Callable[[], datetime], default_max_age_hours: int, max_symbols: int = 1000,
            force: bool = False, max_age_hours: int | None = None, progress_cb: Callable | None = None,
            as_of: str | None = None, full_refresh: bool = False) -> dict:
    if len(set(symbols)) > max_symbols:
        raise ValueError("El universo SEC supera el límite de símbolos.")
    if as_of:
        resolved = store.historical(symbols, as_of)
        ciks = {symbol: row["cik"] for symbol, row in resolved.items() if row["cik"]}
        failed: dict = {symbol: MISSING_HISTORICAL_CIK for symbol in symbols if symbol not in ciks}
        covered = store.covered_entities([resolved[symbol]["entity_id"] for symbol in ciks])
        needed = [symbol for symbol in ciks if force or resolved[symbol]["entity_id"] not in covered]
        failed.update(download_batch(needed, ciks, progress_cb=progress_cb, incremental=False))
        store.errors(failed)
        return {"edgar_refreshed": len(needed) - sum(symbol in failed for symbol in needed), "failed": failed}
    symbols = list(dict.fromkeys(symbols))
    live_map_error: str | None = None
    try:
        frame = mapping(force_refresh=True) if full_refresh else mapping()
    except Exception as exc:
        frame, live_map_error = None, classify_error(exc)
    else:
        live_map_error = None
    fetched_at, covered, failures = store.current(symbols)
    cached = resolutions.cached_many(symbols)
    live = dict(zip(frame["symbol"], frame["cik"])) if frame is not None else {}
    failed_symbols = set()
    for symbol, entities in failures.items():
        cik = live.get(symbol) or cached.get(symbol, (None, None))[0]
        if cik and f"cik:{str(cik).zfill(10)}" in entities:
            failed_symbols.add(symbol)
    stale = stale_symbols(symbols, fetched_at, covered, failed_symbols, now(),
                          max_age_hours or default_max_age_hours, force=force, full_refresh=full_refresh)
    ciks = resolve_many(stale, frame, resolutions, cached)
    if frame is None and not ciks:
        failed = {symbol: live_map_error for symbol in symbols}
        store.errors(failed)
        return {"edgar_refreshed": 0, "failed": failed}
    extra = {"full_refresh": True} if full_refresh else {}
    failed = download_batch(stale, ciks, progress_cb=progress_cb, **extra) if stale else {}
    store.errors(failed)
    return {"edgar_refreshed": len(stale) - len(failed), "failed": failed}
