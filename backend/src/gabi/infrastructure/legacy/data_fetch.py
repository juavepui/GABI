"""Yahoo downloads into the SQLite cache, with moderate concurrency for the free tier's limits.

Classifies each failure (rate limit, unknown ticker, timeout, network, invalid response) so the
user sees why each company failed. The refresh rules live in ``domain.market.yahoo_data`` and the
orchestration in ``application.market.market_downloads``; this bridge composes them with the
temporal identity and ``config`` (read per operation, ADR 0005)."""
import concurrent.futures as cf
import json
import time
from datetime import UTC, datetime

import pandas as pd

from gabi import config, identity
from gabi.application.market import cached_data
from gabi.application.market import market_downloads as downloads
from gabi.application.market.price_sync import run as run_price_sync
from gabi.domain.market import sync_events as sync_rules
from gabi.domain.market import yahoo_data as rules
from gabi.domain.market.freshness import last_completed_session
from gabi.domain.market.price_sync import yahoo_symbol
from gabi.domain.market.source_errors import RETRYABLE_CATEGORIES as RETRYABLE
from gabi.domain.market.source_errors import classify
from gabi.infrastructure.providers import source_retry, yahoo
from gabi.infrastructure.storage.cache_reads import SqliteCacheReads
from gabi.infrastructure.storage.cache_writes import SqliteCacheWrites, statement_json
from gabi.infrastructure.storage.sync_events import OperationSyncEvents, measured_attempt

RETRYABLE_CATEGORIES = set(RETRYABLE)
RETRY_BACKOFF_SECONDS = 1.5


def _reads() -> SqliteCacheReads:
    # The compatibility path is captured per operation, never mutated.
    return SqliteCacheReads(config.DB_PATH)


def _writes() -> SqliteCacheWrites:
    return SqliteCacheWrites(config.DB_PATH, lambda: datetime.now(UTC))


def _events() -> OperationSyncEvents:
    return OperationSyncEvents(config.DB_PATH)


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
    now = now or datetime.now(UTC)
    events = _events()
    return run_price_sync(symbols, store=_PriceStore(_reads(), _writes()),
                          owner=lambda symbol, day: identity.resolve(symbol, day)["entity_id"],
                          attempt=lambda *key: measured_attempt(events, *key), checkpoint=events.get,
                          due=sync_rules.due, retry=source_retry.retry,
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
        df = rules.ticker_frame(data, norm, len(tickers))
        if df is not None and not df.empty:
            owner = identity.resolve(orig, datetime.now(UTC).date().isoformat())["entity_id"]
            _writes().prices(orig, df.dropna(how="all"), entity_id=owner)
        else:
            failed[orig] = rules.NO_PRICES
    return failed


def _fetch_splits_one(symbol: str) -> dict:
    return rules.split_ratios(yahoo.splits(normalize_symbol(symbol)))


def fetch_splits_batch(symbols: list, max_workers: int = 6) -> dict:
    """Descarga y cachea el historial de splits (desdoblamientos de acciones)
    de cada símbolo. yfinance devuelve el precio siempre ajustado por splits
    (haya o no auto_adjust) — sin este historial, calcular la capitalización
    de una fecha anterior a un split posterior con el nº de acciones real de
    esa fecha (SEC EDGAR, sin ajustar) sale sistemáticamente mal (comprobado:
    salía ~4 veces por debajo en un caso real con Apple)."""
    failed: dict[str, str] = {}
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
    """Price history reaching ``as_of_date``; 'max' downloads only for symbols that lack it."""
    return downloads.price_history_asof(
        symbols, as_of_date, benchmark=config.BENCHMARK_SYMBOL,
        benchmark_verified=lambda day: cached_data.has_verified_price_as_of(_reads(), config.BENCHMARK_SYMBOL, day),
        history=lambda symbol, day: identity.price_history(symbol, day),
        benchmark_prices=lambda: cached_data.prices(_reads(), config.BENCHMARK_SYMBOL),
        download_symbol=lambda symbol, day: identity.price_download_symbol(symbol, day),
        fetch_prices=lambda batch: fetch_prices_batch(batch, period="max"),
        fetch_splits=lambda batch: fetch_splits_batch(batch), progress_cb=progress_cb)


def ensure_decision_prices(symbols: list, progress_cb=None) -> dict:
    """Refresh symbols without 126 recent adjusted closes, for portfolio decisions."""
    return downloads.decision_prices(symbols, coverage=lambda batch: cached_data.price_coverage(_reads(), batch),
                                     today=datetime.now(UTC).date(),
                                     fetch_prices=lambda batch: fetch_prices_batch(batch, period="2y"),
                                     progress_cb=progress_cb)


def _fetch_fundamentals_attempt(symbol: str):
    t = yahoo.ticker(normalize_symbol(symbol))
    filtered_info = rules.fundamentals_info(t.info, config.INFO_KEYS)
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
    failed: dict[str, str] = {}
    total = len(symbols)
    if total == 0:
        return failed
    events = _events()
    previous = cached_data.fundamentals(_reads(), symbols)

    def sync_one(sym):
        owner = identity.resolve(sym, datetime.now(UTC).date().isoformat())["entity_id"]
        attempt = measured_attempt(events, "yahoo", owner or f"ticker:{sym}", f"fundamentals:{sym}")
        try:
            info, qi, qcf = source_retry.retry(lambda: _fetch_fundamentals_attempt(sym), attempt)
            payload = {"info": info, "quarterly_income": json.loads(statement_json(qi)),
                       "quarterly_cashflow": json.loads(statement_json(qcf))}
            attempt.payload(payload)
            digest = sync_rules.fingerprint(payload)
            status = rules.fundamentals_status(digest, previous.get(sym), sync_rules.fingerprint)
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


def ensure_universe_data(symbols: list, force: bool = False, max_age_hours: int | None = None, progress_cb=None,
                         *, full_refresh: bool = False):
    """Fresh prices and fundamentals in the local cache, downloading only what is missing or stale.

    ``failed`` maps symbol -> {"precio": reason, "fundamentales": reason}, so each company's failure
    can be explained."""
    writes = _writes()
    return downloads.universe_data(
        symbols, benchmark=config.BENCHMARK_SYMBOL, max_age_hours=max_age_hours or config.CACHE_MAX_AGE_HOURS,
        force=force, full_refresh=full_refresh,
        sync_prices=lambda batch: sync_prices(batch, force=force, full_refresh=full_refresh),
        fundamentals_fetched_at=lambda batch: cached_data.fundamentals_fetched_at(_reads(), batch),
        failed_fundamentals=lambda: {dataset.removeprefix("fundamentals:")
                                     for _, dataset in _events().failed_datasets("yahoo")
                                     if dataset.startswith("fundamentals:")},
        now=lambda: datetime.now(UTC),
        fetch_fundamentals=lambda batch: fetch_fundamentals_batch(batch, progress_cb=progress_cb),
        record_errors=writes.update_errors)


def refresh_data(symbols: list, force: bool = False, progress_cb=None, edgar_progress_cb=None,
                 *, full_refresh: bool = False, sec_sync=None) -> dict:
    """Yahoo (prices and fundamentals) and SEC EDGAR, with both sources' failures per company.

    Moved from ``screener`` (F7.30); only worker and periodic adapters call it."""
    from gabi import edgar

    result = ensure_universe_data(symbols, force=force, progress_cb=progress_cb, full_refresh=full_refresh)
    edgar_result = (sec_sync or edgar.ensure_edgar_data)(symbols, force=force, progress_cb=edgar_progress_cb or progress_cb,
                                                         full_refresh=full_refresh)
    for sym, reason in edgar_result["failed"].items():
        result["failed"].setdefault(sym, {})["edgar"] = reason
    result["edgar_refreshed"] = edgar_result["edgar_refreshed"]
    return result
