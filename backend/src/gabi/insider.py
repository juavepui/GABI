"""Operaciones de insiders (consejeros, directivos, accionistas >10%) desde
los Form 4 de SEC EDGAR (Section 16) — gratis, sin API key.

Es la señal de "qué sabe la dirección que el mercado no sabe todavía" que le
faltaba a GABI: ni yfinance ni el resto de fuentes ya integradas la dan. Una
compra en mercado abierto con dinero propio (código P) es mucho más
informativa que una venta rutinaria, un ejercicio de opciones o una
operación dentro de un plan 10b5-1 programado con meses de antelación — por
eso se distinguen explícitamente en vez de mezclarlas todas como "actividad
de insiders" sin más.

De momento es solo informativo (se muestra en la Ficha de empresa): no entra
en el Composite Score. Igual que con el resto de bloques nuevos, primero hay
que ver si la señal aporta algo con datos reales antes de dejar que vote."""
from datetime import UTC, datetime

import pandas as pd

from gabi.application.market.insider_sync import InsiderAttempt, fetch_transactions, sync_insiders
from gabi.domain.market.insiders import (
    SIGNAL_CODES as SIGNAL_CODES,
)
from gabi.domain.market.insiders import (
    TRANSACTION_CODES as TRANSACTION_CODES,
)
from gabi.domain.market.insiders import (
    parse_form4_xml as parse_form4_xml,
)
from gabi.domain.market.insiders import summarize_insider_activity as _summarize
from gabi.domain.market.source_errors import classify
from gabi.infrastructure.providers.form4 import SecForm4Documents
from gabi.infrastructure.storage.insiders import SCHEMA as SCHEMA
from gabi.infrastructure.storage.insiders import SqliteInsiders

from . import config, edgar


class _Documents:
    @staticmethod
    def submissions(cik: str) -> dict:
        return edgar.fetch_submissions(cik)

    @staticmethod
    def xml(url: str) -> str:
        return SecForm4Documents(config.SEC_USER_AGENT).xml(url)


def fetch_insider_transactions(symbol: str, cik: str, limit_filings: int = 20) -> list:
    return fetch_transactions(symbol, cik, _Documents(), limit_filings)


def _store() -> SqliteInsiders:
    # The compatibility path is captured per operation, never mutated.
    return SqliteInsiders(config.DB_PATH.parent, database=config.DB_PATH, now=lambda: datetime.now(UTC))


def upsert_insider_transactions(symbol: str, rows: list):
    _store().save(symbol, rows)


def get_insider_transactions(symbol: str) -> pd.DataFrame:
    return _store().transactions(symbol)


def get_insider_fetched_at(symbols: list) -> dict:
    return _store().fetched_at(symbols)


def summarize_insider_activity(symbol: str, months: int = 6, transactions: pd.DataFrame | None = None) -> dict:
    """Compatibility entry point; modern callers pass their own date and rows."""
    frame = get_insider_transactions(symbol) if transactions is None else transactions
    return _summarize(frame, months, as_of=datetime.now(UTC).date())


class _Source:
    @staticmethod
    def mapping():
        return edgar.get_cik_map()

    @staticmethod
    def resolve(symbol, mapping):
        return edgar.get_cik_for_symbol(symbol, cik_map=mapping)[0]

    @staticmethod
    def attempts(ciks, max_workers):
        import concurrent.futures as cf

        with cf.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_insider_transactions, symbol, cik): symbol for symbol, cik in ciks.items()}
            for future in cf.as_completed(futures):
                symbol = futures[future]
                try:
                    yield InsiderAttempt(symbol, rows=future.result())
                except Exception as exc:
                    yield InsiderAttempt(symbol, error=exc)


def ensure_insider_data(symbols: list, max_age_hours: int = None, max_workers: int = 4, progress_cb=None) -> dict:
    return sync_insiders(symbols, _Source(), _store(), lambda exc: classify(str(exc), "SEC EDGAR")[1],
                         now=lambda: datetime.now(UTC), max_age_hours=max_age_hours,
                         max_workers=max_workers, progress_cb=progress_cb)
