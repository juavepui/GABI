"""Explicit Yahoo downloads that keep the local cache fresh: universe, historical dates and decisions.

Only what is missing or stale is downloaded; every failure is explained per company.
"""

from collections.abc import Callable, Mapping
from datetime import date, datetime

import pandas as pd

from gabi.domain.market import yahoo_data as rules

DEEP_BATCH = 50  # period="max" downloads are heavier: moderate batches
DECISION_BATCH = 40


def price_history_asof(symbols: list[str], as_of_date: str, *, benchmark: str,
                       benchmark_verified: Callable[[str], bool], history: Callable[[str, str], pd.DataFrame],
                       benchmark_prices: Callable[[], pd.DataFrame], download_symbol: Callable[[str, str], str | None],
                       fetch_prices: Callable[[list[str]], dict], fetch_splits: Callable[[list[str]], dict],
                       progress_cb=None) -> dict:
    """Make the price history reach ``as_of_date``, downloading 'max' only for symbols that do not.

    The live refresh asks for two years; rebuilding an old date needs much more, but only for the
    few symbols without that depth. Splits are fetched too (market cap with the shares of that
    date); a split failure is not a price failure."""
    failed = {}
    download_for = {}
    already_covered = 0
    for symbol in symbols:
        if symbol == benchmark:
            if benchmark_verified(as_of_date):
                already_covered += 1
            else:
                download_for[symbol] = symbol
            continue
        if rules.adjusted_on_or_before(history(symbol, as_of_date), as_of_date):
            already_covered += 1
            continue
        successor = download_symbol(symbol, as_of_date)
        if successor:
            download_for[symbol] = successor
        else:
            failed[symbol] = "Sin identidad temporal o ticker sucesor acreditado; requiere precios históricos atribuidos"
    need_deep_fetch = sorted(set(download_for.values()))
    if not need_deep_fetch:
        return {"deep_fetched": 0, "already_covered": already_covered, "failed": failed}

    download_failed = {}
    for i in range(0, len(need_deep_fetch), DEEP_BATCH):
        batch = need_deep_fetch[i:i + DEEP_BATCH]
        download_failed.update(fetch_prices(batch))
        if progress_cb:
            progress_cb(min(i + DEEP_BATCH, len(need_deep_fetch)), len(need_deep_fetch), batch[-1])
    fetch_splits([s for s in need_deep_fetch if s not in download_failed])
    for original, downloaded in download_for.items():
        if downloaded in download_failed:
            failed[original] = download_failed[downloaded]
            continue
        prices = benchmark_prices() if original == benchmark else history(original, as_of_date)
        if not rules.adjusted_on_or_before(prices, as_of_date):
            failed[original] = "La descarga no aportó precios ajustados atribuidos para esta fecha"
    return {"deep_fetched": sum(s not in failed for s in download_for), "already_covered": already_covered,
            "failed": failed}


def decision_prices(symbols: list[str], *, coverage: Callable[[list[str]], dict], today: date,
                    fetch_prices: Callable[[list[str]], dict], progress_cb=None) -> dict:
    """Refresh the symbols without 126 recent adjusted closes, for portfolio decisions."""
    symbols = list(dict.fromkeys(symbols))
    current = coverage(symbols)
    need = [s for s in symbols if not rules.decision_ready(current.get(s, {}), today)]
    failed = {}
    for i in range(0, len(need), DECISION_BATCH):
        failed.update(fetch_prices(need[i:i + DECISION_BATCH]))
        if progress_cb:
            progress_cb(min(i + DECISION_BATCH, len(need)), len(need))
    updated = coverage(need)
    for symbol in need:
        if symbol not in failed and not rules.decision_ready(updated.get(symbol, {}), today):
            failed[symbol] = "La descarga no aportó 126 cierres ajustados recientes"
    return {"requested": len(need), "already_ready": len(symbols) - len(need), "failed": failed}


def universe_data(symbols: list[str], *, benchmark: str, max_age_hours: float, force: bool, full_refresh: bool,
                  sync_prices: Callable[[list[str]], dict], fundamentals_fetched_at: Callable[[list[str]], Mapping],
                  failed_fundamentals: Callable[[], set[str]], now: Callable[[], datetime],
                  fetch_fundamentals: Callable[[list[str]], dict],
                  record_errors: Callable[[str, dict], None]) -> dict:
    """Fresh prices and fundamentals for the universe, downloading only what is missing or stale.

    ``failed`` maps symbol -> {"precio": reason, "fundamentales": reason}."""
    symbols = list(dict.fromkeys(symbols))
    price_symbols = symbols if benchmark in symbols else symbols + [benchmark]
    price_result = sync_prices(price_symbols)
    fetched_at = fundamentals_fetched_at(symbols)
    stale = rules.stale_fundamentals(symbols, fetched_at, failed_fundamentals(), now(), max_age_hours,
                                     refresh_all=force or full_refresh)
    fundamentals_failed = fetch_fundamentals(stale) if stale else {}
    failed = rules.universe_failures(price_result["failed"], fundamentals_failed, benchmark)
    record_errors("yahoo_precio", {s: r["precio"] for s, r in failed.items() if "precio" in r})
    record_errors("yahoo_fundamentales", {s: r["fundamentales"] for s, r in failed.items() if "fundamentales" in r})
    return {"price_refreshed": any(not e["skipped"] for e in price_result["events"]),
            "fundamentals_refreshed": len(stale) - len(fundamentals_failed),
            "price_sync": price_result, "failed": failed}
