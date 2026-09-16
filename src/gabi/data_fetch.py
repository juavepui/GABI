"""Descarga de datos desde yfinance con caché en SQLite y descarga concurrente
moderada para respetar los límites (no oficiales) del nivel gratuito."""
import concurrent.futures as cf
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from . import config, storage


def normalize_symbol(symbol: str) -> str:
    """Yahoo Finance usa '-' en vez de '.' (ej. BRK.B -> BRK-B)."""
    return symbol.replace(".", "-")


def fetch_prices_batch(symbols: list, period: str = "2y"):
    """Descarga precios de varios símbolos en una sola llamada batch y los cachea."""
    tickers = [normalize_symbol(s) for s in symbols]
    data = yf.download(
        tickers, period=period, interval="1d", group_by="ticker",
        threads=True, auto_adjust=True, progress=False,
    )
    for orig, norm in zip(symbols, tickers):
        try:
            if len(tickers) == 1:
                df = data
            else:
                df = data[norm] if norm in data.columns.get_level_values(0) else None
        except Exception:
            df = None
        if df is not None and not df.empty:
            storage.upsert_prices(orig, df.dropna(how="all"))


def fetch_fundamentals_one(symbol: str):
    t = yf.Ticker(normalize_symbol(symbol))
    info = t.info or {}
    filtered_info = {k: info.get(k) for k in config.INFO_KEYS}
    qi = getattr(t, "quarterly_income_stmt", None)
    if qi is None or qi.empty:
        qi = getattr(t, "quarterly_financials", pd.DataFrame())
    qcf = getattr(t, "quarterly_cashflow", pd.DataFrame())
    return filtered_info, qi, qcf


def fetch_fundamentals_batch(symbols: list, max_workers: int = 6, progress_cb=None):
    """Descarga fundamentales en paralelo (pool moderado) tolerando fallos individuales."""
    failed = []
    total = len(symbols)
    if total == 0:
        return failed
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fetch_fundamentals_one, s): s for s in symbols}
        done = 0
        for fut in cf.as_completed(futures):
            sym = futures[fut]
            done += 1
            try:
                info, qi, qcf = fut.result()
                storage.upsert_fundamentals(sym, info, qi, qcf)
            except Exception:
                failed.append(sym)
            if progress_cb:
                progress_cb(done, total, sym)
    return failed


def _is_stale_trading_day(latest_date) -> bool:
    return (datetime.now(timezone.utc).date() - latest_date).days >= 1


def ensure_universe_data(symbols: list, force: bool = False, max_age_hours: int = None, progress_cb=None):
    """Se asegura de que precios y fundamentales estén frescos en la caché local,
    descargando solo lo que falte o esté caducado."""
    max_age_hours = max_age_hours or config.CACHE_MAX_AGE_HOURS
    symbols = list(dict.fromkeys(symbols))  # dedup preservando orden
    price_symbols = symbols if config.BENCHMARK_SYMBOL in symbols else symbols + [config.BENCHMARK_SYMBOL]

    latest_price_date = storage.get_latest_price_date()
    needs_price_refresh = force or latest_price_date is None or _is_stale_trading_day(latest_price_date)
    if needs_price_refresh:
        fetch_prices_batch(price_symbols)

    fetched_at = storage.get_fundamentals_fetched_at(symbols)
    now = datetime.now(timezone.utc)
    stale = [
        s for s in symbols
        if force or fetched_at.get(s) is None
        or (now - fetched_at[s]).total_seconds() > max_age_hours * 3600
    ]
    failed = fetch_fundamentals_batch(stale, progress_cb=progress_cb) if stale else []

    return {
        "price_refreshed": needs_price_refresh,
        "fundamentals_refreshed": len(stale) - len(failed),
        "failed": failed,
    }
