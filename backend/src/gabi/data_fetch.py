"""Descarga de datos desde yfinance con caché en SQLite y descarga concurrente
moderada para respetar los límites (no oficiales) del nivel gratuito.

Además de descargar, clasifica los fallos por motivo (rate limit, ticker sin
datos, timeout, red, respuesta inválida...) para poder explicarle al usuario
por qué ha fallado cada empresa, en vez de solo decir "ha fallado"."""
import concurrent.futures as cf
import json
import time
from datetime import UTC, datetime

import pandas as pd

from gabi.application.market import cached_data
from gabi.application.market.price_sync import run as run_price_sync
from gabi.domain.market.freshness import last_completed_session
from gabi.domain.market.price_sync import yahoo_symbol
from gabi.domain.market.source_errors import RETRYABLE_CATEGORIES as RETRYABLE
from gabi.domain.market.source_errors import classify
from gabi.infrastructure.providers import yahoo
from gabi.infrastructure.storage.cache_reads import SqliteCacheReads
from gabi.infrastructure.storage.cache_writes import SqliteCacheWrites, statement_json

from . import config, identity

RETRYABLE_CATEGORIES = set(RETRYABLE)
RETRY_BACKOFF_SECONDS = 1.5


def _reads() -> SqliteCacheReads:
    # The compatibility path is captured per operation, never mutated.
    return SqliteCacheReads(config.DB_PATH)


def _writes() -> SqliteCacheWrites:
    return SqliteCacheWrites(config.DB_PATH, lambda: datetime.now(UTC))


class _PriceStore:
    def __init__(self, reads: SqliteCacheReads, writes: SqliteCacheWrites):
        self.reads, self.writes = reads, writes

    def adjusted_span(self, symbol):
        return self.reads.adjusted_span(symbol)

    def prices_from(self, symbol, start):
        return cached_data.prices_from(self.reads, symbol, start)

    def prices(self, symbol):
        return cached_data.prices(self.reads, symbol)

    def write(self, symbol, frame, entity_id):
        self.writes.prices(symbol, frame, entity_id=entity_id)


def sync_prices(symbols: list, *, force: bool = False, full_refresh: bool = False, now=None) -> dict:
    """Incremental Yahoo prices, with overlap and explicit adjustment repair."""
    from . import sync_state as sync

    now = now or datetime.now(UTC)
    return run_price_sync(symbols, store=_PriceStore(_reads(), _writes()),
                          owner=lambda symbol, day: identity.resolve(symbol, day)["entity_id"],
                          attempt=sync.Attempt, checkpoint=sync.get, due=sync.due, retry=sync.retry,
                          download=yahoo.download, classify=lambda exc: classify(str(exc))[1],
                          payload_size=lambda frame: len(frame.to_csv().encode()), now=now,
                          session=last_completed_session(now).isoformat(), force=force, full_refresh=full_refresh)


def normalize_symbol(symbol: str) -> str:
    """Yahoo Finance usa '-' en vez de '.' (ej. BRK.B -> BRK-B)."""
    return yahoo_symbol(symbol)


def _classify_error(exc: Exception, service: str = "Yahoo Finance") -> tuple[str, str]:
    """Devuelve (categoria, mensaje_en_español) a partir de una excepción (regla compartida en dominio)."""
    return classify(str(exc), service)


def fetch_prices_batch(symbols: list, period: str = "2y") -> dict:
    """Descarga precios de varios símbolos en una sola llamada batch y los cachea.
    Devuelve dict[symbol] = motivo de error para los símbolos sin datos."""
    tickers = [normalize_symbol(s) for s in symbols]
    failed = {}
    try:
        data = yahoo.download(
            tickers, period=period, interval="1d", group_by="ticker",
            threads=True, auto_adjust=False, progress=False,
        )
    except Exception as exc:
        _, reason = _classify_error(exc)
        return {orig: reason for orig in symbols}

    for orig, norm in zip(symbols, tickers):
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if norm in data.columns.get_level_values(0):
                    df = data[norm]
                elif norm in data.columns.get_level_values(1):
                    df = data.xs(norm, level=1, axis=1)
                else:
                    df = None
            elif len(tickers) == 1:
                df = data
            else:
                df = None
        except Exception:
            df = None
        if df is not None and not df.empty:
            owner = identity.resolve(orig, datetime.now(UTC).date().isoformat())["entity_id"]
            _writes().prices(orig, df.dropna(how="all"), entity_id=owner)
        else:
            failed[orig] = "Sin datos de precio devueltos por Yahoo Finance (posible ticker incorrecto o deslistado)"
    return failed


def _fetch_splits_one(symbol: str) -> dict:
    splits = yahoo.splits(normalize_symbol(symbol))
    if splits is None or splits.empty:
        return {}
    return {d.strftime("%Y-%m-%d"): float(r) for d, r in splits.items()}


def fetch_splits_batch(symbols: list, max_workers: int = 6) -> dict:
    """Descarga y cachea el historial de splits (desdoblamientos de acciones)
    de cada símbolo. yfinance devuelve el precio siempre ajustado por splits
    (haya o no auto_adjust) — sin este historial, calcular la capitalización
    de una fecha anterior a un split posterior con el nº de acciones real de
    esa fecha (SEC EDGAR, sin ajustar) sale sistemáticamente mal (comprobado:
    salía ~4 veces por debajo en un caso real con Apple)."""
    failed = {}
    if not symbols:
        return failed
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch_splits_one, s): s for s in symbols}
        for fut in cf.as_completed(futures):
            sym = futures[fut]
            try:
                owner = identity.resolve(sym, datetime.now(UTC).date().isoformat())["entity_id"]
                _writes().splits(sym, fut.result(), entity_id=owner)
            except Exception as exc:
                _, reason = _classify_error(exc)
                failed[sym] = reason
    return failed


def ensure_price_history_asof(symbols: list, as_of_date: str, progress_cb=None) -> dict:
    """Se asegura de que el histórico de precios llegue al menos hasta
    as_of_date para los símbolos dados. El refresco normal (ensure_universe_data)
    solo pide 2 años porque es lo que necesitan momentum/riesgo del screener en
    vivo; para reconstruir una fecha antigua (screener_asof) hace falta mucho
    más — aquí se pide 'max' (todo el histórico que dé yfinance), pero SOLO
    para los símbolos que no lleguen ya tan atrás, no para todos: pedir 'max'
    a las ~500 empresas en cada refresco normal sería mucho más lento y
    pesado de almacenar para un caso de uso (consultar el pasado) que se usa
    ocasionalmente, no en cada sesión."""
    failed = {}
    download_for = {}
    already_covered = 0
    for symbol in symbols:
        if symbol == config.BENCHMARK_SYMBOL:
            if cached_data.has_verified_price_as_of(_reads(), symbol, as_of_date):
                already_covered += 1
            else:
                download_for[symbol] = symbol
            continue
        history = identity.price_history(symbol, as_of_date)
        if not history.empty and history.loc[history.index <= pd.Timestamp(as_of_date), "adj_close"].notna().any():
            already_covered += 1
            continue
        download_symbol = identity.price_download_symbol(symbol, as_of_date)
        if download_symbol:
            download_for[symbol] = download_symbol
        else:
            failed[symbol] = "Sin identidad temporal o ticker sucesor acreditado; requiere precios históricos atribuidos"
    need_deep_fetch = sorted(set(download_for.values()))
    if not need_deep_fetch:
        return {"deep_fetched": 0, "already_covered": already_covered, "failed": failed}

    download_failed = {}
    batch_size = 50  # la descarga con 'period=max' es más pesado; lotes moderados
    for i in range(0, len(need_deep_fetch), batch_size):
        batch = need_deep_fetch[i:i + batch_size]
        download_failed.update(fetch_prices_batch(batch, period="max"))
        if progress_cb:
            progress_cb(min(i + batch_size, len(need_deep_fetch)), len(need_deep_fetch), batch[-1])

    # Splits: necesarios para poder calcular capitalización/múltiplos de esta
    # fecha correctamente (ver fetch_splits_batch). No se cuentan como fallo
    # aparte porque son secundarios al precio en sí — si fallan, el precio
    # sigue estando disponible, solo la capitalización quedará sin corregir.
    fetch_splits_batch([s for s in need_deep_fetch if s not in download_failed])
    for original, downloaded in download_for.items():
        if downloaded in download_failed:
            failed[original] = download_failed[downloaded]
            continue
        history = (cached_data.prices(_reads(), original) if original == config.BENCHMARK_SYMBOL
                   else identity.price_history(original, as_of_date))
        if history.empty or not history.loc[history.index <= pd.Timestamp(as_of_date), "adj_close"].notna().any():
            failed[original] = "La descarga no aportó precios ajustados atribuidos para esta fecha"

    return {
        "deep_fetched": sum(s not in failed for s in download_for),
        "already_covered": already_covered,
        "failed": failed,
    }


def ensure_decision_prices(symbols: list, progress_cb=None) -> dict:
    """Migra el caché de precios antiguo y refresca los símbolos desactualizados, para las decisiones de cartera."""
    symbols = list(dict.fromkeys(symbols))
    coverage = cached_data.price_coverage(_reads(), symbols)
    today = datetime.now(UTC).date()
    need = []
    for symbol in symbols:
        item = coverage.get(symbol, {})
        latest = item.get("latest_adjusted_date")
        stale = latest is None or (today - datetime.fromisoformat(latest).date()).days > 7
        if item.get("adjusted_count", 0) < 126 or stale:
            need.append(symbol)
    failed = {}
    for i in range(0, len(need), 40):
        batch = need[i:i + 40]
        failed.update(fetch_prices_batch(batch, period="2y"))
        if progress_cb:
            progress_cb(min(i + 40, len(need)), len(need))
    updated = cached_data.price_coverage(_reads(), need)
    for symbol in need:
        if symbol in failed:
            continue
        item = updated.get(symbol, {})
        latest = item.get("latest_adjusted_date")
        if (item.get("adjusted_count", 0) < 126 or latest is None
                or (today - datetime.fromisoformat(latest).date()).days > 7):
            failed[symbol] = "La descarga no aportó 126 cierres ajustados recientes"
    return {"requested": len(need), "already_ready": len(symbols) - len(need), "failed": failed}


def _fetch_fundamentals_attempt(symbol: str):
    t = yahoo.ticker(normalize_symbol(symbol))
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
    from . import sync_state as sync
    previous = cached_data.fundamentals(_reads(), symbols)

    def sync_one(sym):
        owner = identity.resolve(sym, datetime.now(UTC).date().isoformat())["entity_id"]
        attempt = sync.Attempt("yahoo", owner or f"ticker:{sym}", f"fundamentals:{sym}")
        try:
            info, qi, qcf = sync.retry(lambda: _fetch_fundamentals_attempt(sym), attempt)
            payload = {"info": info, "quarterly_income": json.loads(statement_json(qi)),
                       "quarterly_cashflow": json.loads(statement_json(qcf))}
            attempt.payload(payload)
            digest = sync.fingerprint(payload)
            old = previous.get(sym)
            status = "new" if not old else "unchanged" if digest == sync.fingerprint(
                {k: v for k, v in old.items() if k != "fetched_at"}) else "revised"
            # Refresh the snapshot timestamp even when values agree; no historical reprocessing.
            _writes().fundamentals(sym, info, qi, qcf, entity_id=owner)
            attempt.finish(status, state={"fingerprint": digest, "watermark": datetime.now(UTC).isoformat()},
                           new=int(status == "new"), revised=int(status == "revised"), unchanged=int(status == "unchanged"),
                           reason="snapshot Yahoo: proveedor sin endpoint incremental para fundamentales")
        except Exception as exc:
            attempt.finish("failed", reason=str(exc))
            raise

    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(sync_one, s): s for s in symbols}
        done = 0
        for fut in cf.as_completed(futures):
            sym = futures[fut]
            done += 1
            try:
                fut.result()
            except Exception as exc:
                _, reason = _classify_error(exc)
                failed[sym] = reason
            if progress_cb:
                progress_cb(done, total, sym)
    return failed


def _is_stale_trading_day(latest_date) -> bool:
    return (datetime.now(UTC).date() - latest_date).days >= 1


def ensure_universe_data(symbols: list, force: bool = False, max_age_hours: int = None, progress_cb=None,
                         *, full_refresh: bool = False):
    """Se asegura de que precios y fundamentales estén frescos en la caché local,
    descargando solo lo que falte o esté caducado.

    El resultado incluye 'failed': dict[symbol] -> {"precio": motivo, "fundamentales": motivo}
    para poder mostrarle al usuario, empresa a empresa, por qué no se pudo actualizar.
    """
    max_age_hours = max_age_hours or config.CACHE_MAX_AGE_HOURS
    symbols = list(dict.fromkeys(symbols))  # dedup preservando orden
    price_symbols = symbols if config.BENCHMARK_SYMBOL in symbols else symbols + [config.BENCHMARK_SYMBOL]

    price_result = sync_prices(price_symbols, force=force, full_refresh=full_refresh)
    needs_price_refresh = any(not e["skipped"] for e in price_result["events"])
    price_failed = price_result["failed"]

    fetched_at = cached_data.fundamentals_fetched_at(_reads(), symbols)
    now = datetime.now(UTC)
    from . import sync_state
    failed_fundamentals = {dataset.removeprefix("fundamentals:") for _, dataset in sync_state.failed_datasets("yahoo")
                           if dataset.startswith("fundamentals:")}
    stale = [
        s for s in symbols
        if force or full_refresh or s in failed_fundamentals or fetched_at.get(s) is None
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

    _writes().update_errors("yahoo_precio", {s: r["precio"] for s, r in failed.items() if "precio" in r})
    _writes().update_errors(
        "yahoo_fundamentales", {s: r["fundamentales"] for s, r in failed.items() if "fundamentales" in r})

    return {
        "price_refreshed": needs_price_refresh,
        "fundamentals_refreshed": len(stale) - len(fundamentals_failed),
        "price_sync": price_result,
        "failed": failed,
    }
