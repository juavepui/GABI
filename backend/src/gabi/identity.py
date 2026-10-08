"""Compatibility facade for offline issuer identity and accredited history."""

import uuid
from datetime import date

import pandas as pd

from gabi.application.market import identity as identity_queries
from gabi.domain.market import identity as identity_rules
from gabi.infrastructure.storage import identity_writes
from gabi.infrastructure.storage.identity import SqliteIdentityReads
from gabi.infrastructure.storage.identity_writes import SqliteIdentityWrites
from gabi.infrastructure.storage.ticker_prices import SqliteTickerPrices

from . import config

SCHEMA = identity_writes.SCHEMA
ensure_schema = identity_writes.ensure_schema
put_observations = identity_writes.put_observations
DATA_KEYS = identity_rules.DATA_KEYS
MIN_CONFIDENCE = identity_rules.MIN_CONFIDENCE
normalize_cik = identity_rules.normalize_cik
normalize_symbol = identity_rules.normalize_symbol
_json_value = identity_rules._json_value


def _reader() -> SqliteIdentityReads:
    from . import historical_pit
    return SqliteIdentityReads(config.DB_PATH, periods=historical_pit._active, max_rows=250000, max_bytes=64 * 1024 * 1024)


def _writer() -> SqliteIdentityWrites:
    return SqliteIdentityWrites(config.DB_PATH, date.today, lambda: str(uuid.uuid4()))

def ensure_entity(cik=None, name: str | None = None, *, entity_id: str | None = None) -> str:
    return _writer().ensure_entity(cik, name, entity_id=entity_id)


def add_alias(entity_id: str, symbol: str, valid_from: str, valid_to: str | None = None,
              *, source: str, confidence: float = 1.0):
    return _writer().add_alias(entity_id, symbol, valid_from, valid_to, source=source, confidence=confidence)


def resolve(symbol: str, as_of: str) -> dict:
    return identity_queries.resolve(_reader(), symbol, as_of)


def has_aliases(symbol: str) -> bool:
    return bool(_reader().registered([symbol]))


def observations(entity_id: str, dataset: str) -> pd.DataFrame:
    return _reader().observations(entity_id, dataset)


def price_history(symbol: str, as_of: str, *, entity_id: str | None = None) -> pd.DataFrame:
    from . import historical_pit
    return identity_queries.price_history(_reader(), symbol, as_of, entity_id=entity_id,
                                          accredited=historical_pit.covers, ranking_series=historical_pit.ranking_series)


def diagnostics(symbols: list[str], as_of: str) -> pd.DataFrame:
    found = _reader().resolve_many(sorted(set(symbols)), as_of)
    return pd.DataFrame([{"symbol": symbol, **row} for symbol, row in found.items()])


def price_download_symbol(symbol: str, as_of: str, *, today: str | None = None) -> str | None:
    return identity_queries.download_symbol(_reader(), symbol, as_of, today=today or date.today().isoformat())


def backtest_prices(symbols: list[str], as_of: str, owners: dict | None = None) -> dict:
    """Entity data for registered issuers; legacy adapter for unmigrated callers.

    Strict ranking excludes unresolved issuers before selection. Other legacy
    callers retain their API; they never bypass a registered/conflicting alias.
    SPY remains the explicitly configured benchmark security, not an issuer.
    """
    from . import historical_pit
    ticker_prices = SqliteTickerPrices(config.DB_PATH)
    return identity_queries.backtest_prices(_reader(), symbols, as_of, owners,
        benchmark=config.BENCHMARK_SYMBOL, history=historical_pit,
        ticker_prices=ticker_prices.get, ticker_prices_many=ticker_prices.for_backtest)


def last_filings(symbols: list[str], as_of: str) -> dict:
    return identity_queries.last_filings(_reader(), symbols, as_of)


def import_submissions_candidates(symbol: str, historical_name: str, submissions: dict, *, source: str) -> bool:
    if not identity_rules.name_matches(historical_name, submissions):
        return False
    entity = ensure_entity(submissions["cik"], submissions.get("name"))
    _writer().candidate(symbol, entity, historical_name, source)
    return True


def import_filing_identity(symbol: str, cik: str, filing_date: str, *, source: str,
                           name: str | None = None):
    """A filing cover proves a ticker/CIK on its filing date, not an interval."""
    from datetime import timedelta

    entity = ensure_entity(cik, name)
    end = (date.fromisoformat(filing_date) + timedelta(days=1)).isoformat()
    add_alias(entity, symbol, filing_date, end, source=source)
    return entity


def attributed_fingerprint() -> str:
    return _reader().attributed_fingerprint()
