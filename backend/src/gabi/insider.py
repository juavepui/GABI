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
import requests

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

from . import config, edgar, storage
from .data_fetch import _classify_error

SCHEMA = """
CREATE TABLE IF NOT EXISTS insider_transactions (
    symbol TEXT NOT NULL,
    cik TEXT NOT NULL,
    accn TEXT NOT NULL,
    line_no INTEGER NOT NULL,
    owner_name TEXT,
    owner_title TEXT,
    is_officer INTEGER,
    is_director INTEGER,
    is_ten_pct_owner INTEGER,
    is_10b5_1_plan INTEGER,
    transaction_date TEXT NOT NULL,
    transaction_code TEXT NOT NULL,
    acquired_disposed TEXT,
    shares REAL,
    price_per_share REAL,
    shares_owned_after REAL,
    filed_date TEXT,
    PRIMARY KEY (symbol, accn, line_no)
);
CREATE INDEX IF NOT EXISTS idx_insider_symbol_date ON insider_transactions (symbol, transaction_date);
CREATE TABLE IF NOT EXISTS insider_fetch_meta (
    symbol TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL
);
"""


class _Documents:
    @staticmethod
    def submissions(cik: str) -> dict:
        return edgar.fetch_submissions(cik)

    @staticmethod
    def xml(url: str) -> str:
        response = requests.get(url, headers={"User-Agent": config.SEC_USER_AGENT}, timeout=20)
        response.raise_for_status()
        return response.text


def fetch_insider_transactions(symbol: str, cik: str, limit_filings: int = 20) -> list:
    return fetch_transactions(symbol, cik, _Documents(), limit_filings)


def upsert_insider_transactions(symbol: str, rows: list):
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        if rows:
            conn.executemany(
                "INSERT OR REPLACE INTO insider_transactions "
                "(symbol, cik, accn, line_no, owner_name, owner_title, is_officer, is_director, "
                "is_ten_pct_owner, is_10b5_1_plan, transaction_date, transaction_code, acquired_disposed, "
                "shares, price_per_share, shares_owned_after, filed_date) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        r["symbol"], r["cik"], r["accn"], r["line_no"], r["owner_name"], r["owner_title"],
                        int(r["is_officer"]), int(r["is_director"]), int(r["is_ten_pct_owner"]),
                        int(r["is_10b5_1_plan"]), r["transaction_date"], r["transaction_code"],
                        r["acquired_disposed"], r["shares"], r["price_per_share"], r["shares_owned_after"],
                        r["filed_date"],
                    )
                    for r in rows
                ],
            )
        conn.execute(
            "INSERT OR REPLACE INTO insider_fetch_meta (symbol, fetched_at) VALUES (?, ?)",
            (symbol, datetime.now(UTC).isoformat()),
        )
        conn.commit()


def get_insider_transactions(symbol: str) -> pd.DataFrame:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        return pd.read_sql_query(
            "SELECT * FROM insider_transactions WHERE symbol = ? ORDER BY transaction_date DESC",
            conn, params=(symbol,),
        )


def get_insider_fetched_at(symbols: list) -> dict:
    if not symbols:
        return {}
    placeholders = ",".join("?" * len(symbols))
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        rows = conn.execute(
            f"SELECT symbol, fetched_at FROM insider_fetch_meta WHERE symbol IN ({placeholders})", symbols,
        ).fetchall()
    result = {}
    for symbol, fetched_at in rows:
        try:
            result[symbol] = datetime.fromisoformat(fetched_at)
        except Exception:
            result[symbol] = None
    return result


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


class _Store:
    @staticmethod
    def fetched_at(symbols):
        return get_insider_fetched_at(symbols)

    @staticmethod
    def save(symbol, rows):
        upsert_insider_transactions(symbol, rows)

    @staticmethod
    def errors(failed):
        storage.record_update_errors("insider_form4", failed)


def ensure_insider_data(symbols: list, max_age_hours: int = None, max_workers: int = 4, progress_cb=None) -> dict:
    return sync_insiders(symbols, _Source(), _Store(), lambda exc: _classify_error(exc, service="SEC EDGAR")[1],
                         now=lambda: datetime.now(UTC), max_age_hours=max_age_hours,
                         max_workers=max_workers, progress_cb=progress_cb)
