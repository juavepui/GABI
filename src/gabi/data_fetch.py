"""Descarga de datos desde yfinance con caché en SQLite y descarga concurrente
moderada para respetar los límites (no oficiales) del nivel gratuito.

Además de descargar, clasifica los fallos por motivo (rate limit, ticker sin
datos, timeout, red, respuesta inválida...) para poder explicarle al usuario
por qué ha fallado cada empresa, en vez de solo decir "ha fallado"."""
import concurrent.futures as cf
import time
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from . import config, storage

RETRYABLE_CATEGORIES = {"rate_limit", "timeout", "connection"}
RETRY_BACKOFF_SECONDS = 1.5


def normalize_symbol(symbol: str) -> str:
    """Yahoo Finance usa '-' en vez de '.' (ej. BRK.B -> BRK-B)."""
    return symbol.replace(".", "-")


def _classify_error(exc: Exception, service: str = "Yahoo Finance") -> tuple[str, str]:
    """Devuelve (categoria, mensaje_en_español) a partir de una excepción.
    Genérica: la reutiliza también gabi.edgar para clasificar fallos de SEC EDGAR."""
    msg = str(exc)
    lower = msg.lower()
    if "429" in msg or "too many requests" in lower or "rate limit" in lower:
        return "rate_limit", f"Límite de peticiones de {service} alcanzado (rate limit)"
    if "delisted" in lower or "no data found" in lower or "no price data" in lower or "not found" in lower:
        return "not_found", "Sin datos disponibles (ticker posiblemente deslistado, incorrecto o sin cobertura)"
    if "timeout" in lower or "timed out" in lower:
        return "timeout", f"Tiempo de espera agotado al contactar con {service}"
    if "connection" in lower or "connect" in lower or "network" in lower or "resolve" in lower:
        return "connection", f"Error de conexión de red con {service}"
    if "json" in lower or "expecting value" in lower:
        return "invalid_response", "Respuesta inválida o vacía del servidor"
    return "other", (msg[:200] if msg else "Error desconocido")


def fetch_prices_batch(symbols: list, period: str = "2y") -> dict:
    """Descarga precios de varios símbolos en una sola llamada batch y los cachea.
    Devuelve dict[symbol] = motivo de error para los símbolos sin datos."""
    tickers = [normalize_symbol(s) for s in symbols]
    failed = {}
    try:
        data = yf.download(
            tickers, period=period, interval="1d", group_by="ticker",
            threads=True, auto_adjust=True, progress=False,
        )
    except Exception as exc:
        _, reason = _classify_error(exc)
        return {orig: reason for orig in symbols}

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
        else:
            failed[orig] = "Sin datos de precio devueltos por Yahoo Finance (posible ticker incorrecto o deslistado)"
    return failed


def _fetch_fundamentals_attempt(symbol: str):
    t = yf.Ticker(normalize_symbol(symbol))
    info = t.info or {}
    has_signal = any(
        info.get(k) is not None for k in ("regularMarketPrice", "currentPrice", "sector", "marketCap")
    )
    if not has_signal:
        raise ValueError("Yahoo Finance no devolvió datos fundamentales para este ticker")
    filtered_info = {k: info.get(k) for k in config.INFO_KEYS}
    qi = getattr(t, "quarterly_income_stmt", None)
    if qi is None or qi.empty:
        qi = getattr(t, "quarterly_financials", pd.DataFrame())
    qcf = getattr(t, "quarterly_cashflow", pd.DataFrame())
    return filtered_info, qi, qcf


def fetch_fundamentals_one(symbol: str):
    """Descarga fundamentales de un ticker, con un reintento si el fallo
    parece transitorio (rate limit, timeout, red)."""
    try:
        return _fetch_fundamentals_attempt(symbol)
    except Exception as exc:
        category, _ = _classify_error(exc)
        if category in RETRYABLE_CATEGORIES:
            time.sleep(RETRY_BACKOFF_SECONDS)
            return _fetch_fundamentals_attempt(symbol)
        raise


def fetch_fundamentals_batch(symbols: list, max_workers: int = 6, progress_cb=None) -> dict:
    """Descarga fundamentales en paralelo (pool moderado) tolerando fallos individuales.
    Devuelve dict[symbol] = motivo de error en español para los símbolos que fallaron."""
    failed = {}
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
            except Exception as exc:
                _, reason = _classify_error(exc)
                failed[sym] = reason
            if progress_cb:
                progress_cb(done, total, sym)
    return failed


def _is_stale_trading_day(latest_date) -> bool:
    return (datetime.now(timezone.utc).date() - latest_date).days >= 1


def ensure_universe_data(symbols: list, force: bool = False, max_age_hours: int = None, progress_cb=None):
    """Se asegura de que precios y fundamentales estén frescos en la caché local,
    descargando solo lo que falte o esté caducado.

    El resultado incluye 'failed': dict[symbol] -> {"precio": motivo, "fundamentales": motivo}
    para poder mostrarle al usuario, empresa a empresa, por qué no se pudo actualizar.
    """
    max_age_hours = max_age_hours or config.CACHE_MAX_AGE_HOURS
    symbols = list(dict.fromkeys(symbols))  # dedup preservando orden
    price_symbols = symbols if config.BENCHMARK_SYMBOL in symbols else symbols + [config.BENCHMARK_SYMBOL]

    latest_price_date = storage.get_latest_price_date()
    needs_price_refresh = force or latest_price_date is None or _is_stale_trading_day(latest_price_date)
    price_failed = fetch_prices_batch(price_symbols) if needs_price_refresh else {}

    fetched_at = storage.get_fundamentals_fetched_at(symbols)
    now = datetime.now(timezone.utc)
    stale = [
        s for s in symbols
        if force or fetched_at.get(s) is None
        or (now - fetched_at[s]).total_seconds() > max_age_hours * 3600
    ]
    fundamentals_failed = fetch_fundamentals_batch(stale, progress_cb=progress_cb) if stale else {}

    failed = {}
    for sym, reason in price_failed.items():
        if sym == config.BENCHMARK_SYMBOL:
            continue  # SPY es el benchmark interno, no una empresa del universo
        failed.setdefault(sym, {})["precio"] = reason
    for sym, reason in fundamentals_failed.items():
        failed.setdefault(sym, {})["fundamentales"] = reason

    return {
        "price_refreshed": needs_price_refresh,
        "fundamentals_refreshed": len(stale) - len(fundamentals_failed),
        "failed": failed,
    }
