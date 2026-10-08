"""Offline issuer queries with explicit repositories and accredited-history ports."""

from collections.abc import Callable
from datetime import date
from typing import Protocol

import pandas as pd

from gabi.domain.market.identity import MIN_CONFIDENCE, aliases_overlap, attributed_prices, normalize_symbol


class IdentityReader(Protocol):
    def resolve_many(self, symbols: list[str], as_of: str) -> dict[str, dict]: ...
    def registered(self, symbols: list[str]) -> set[str]: ...
    def observations(self, entity_id: str, dataset: str) -> pd.DataFrame: ...
    def aliases(self, entity_id: str) -> list[tuple]: ...
    def price_inputs(self, entity_id: str, symbol: str) -> tuple[pd.DataFrame, list[tuple], list[tuple]]: ...
    def filing_dates(self, owners: dict[str, str], legacy: list[str], as_of: str) -> dict[str, str]: ...


class AccreditedHistory(Protocol):
    def covers(self, as_of: str) -> bool: ...
    def has_series(self, entity_id: str | None, day: str) -> bool: ...
    def ranking_series(self, entity_id: str | None, as_of: str) -> pd.DataFrame: ...
    def holding_series(self, entity_id: str | None, day: str) -> pd.DataFrame: ...


def resolve(reader: IdentityReader, symbol: str, as_of: str) -> dict:
    return reader.resolve_many([symbol], as_of)[symbol]


def price_history(reader: IdentityReader, symbol: str, as_of: str, *, entity_id: str | None = None,
                  accredited: Callable[[str], bool], ranking_series: Callable[[str, str], pd.DataFrame]) -> pd.DataFrame:
    resolved = resolve(reader, symbol, as_of)
    owner = entity_id or resolved["entity_id"]
    if not owner or resolved["status"] == "ambiguous" or (resolved["entity_id"] and resolved["entity_id"] != owner):
        return pd.DataFrame()
    if accredited(as_of):
        return ranking_series(owner, as_of)
    requested = normalize_symbol(symbol)
    frame, aliases, conflicts = reader.price_inputs(owner, requested)
    return attributed_prices(frame, requested, aliases, conflicts)


def download_symbol(reader: IdentityReader, symbol: str, as_of: str, *, today: str) -> str | None:
    date.fromisoformat(today)
    owner = resolve(reader, symbol, as_of)["entity_id"]
    if not owner:
        return None
    if resolve(reader, symbol, today)["entity_id"] == owner:
        return symbol
    aliases = reader.aliases(owner)
    current = list(dict.fromkeys(alias for alias, start, end, confidence in aliases
                                if start <= today < (end or "9999-12-31") and confidence >= MIN_CONFIDENCE))
    resolved = reader.resolve_many(current, today)
    candidates = [alias for alias in current if resolved[alias]["entity_id"] == owner]
    if len(candidates) != 1 or aliases_overlap(aliases, normalize_symbol(symbol), candidates[0]):
        return None
    return candidates[0]


def last_filings(reader: IdentityReader, symbols: list[str], as_of: str) -> dict:
    resolved = reader.resolve_many(symbols, as_of)
    owners = {symbol: row["entity_id"] for symbol, row in resolved.items() if row["entity_id"]}
    unowned = [symbol for symbol in symbols if symbol not in owners]
    registered = reader.registered(unowned)
    legacy = [symbol for symbol in unowned if normalize_symbol(symbol) not in registered]
    # This guard uses all attributed versions, never the fact deduplication policy.
    return reader.filing_dates(owners, legacy, as_of)


def backtest_prices(reader: IdentityReader, symbols: list[str], as_of: str, owners: dict | None, *,
                    benchmark: str, history: AccreditedHistory, ticker_prices: Callable[[str], pd.DataFrame],
                    ticker_prices_many: Callable[[list[str]], dict] | None = None) -> dict:
    historical = history.covers(as_of)
    unresolved = [symbol for symbol in symbols if symbol != benchmark and not (owners or {}).get(symbol)]
    resolved = reader.resolve_many(unresolved, as_of) if historical else {}
    registered = reader.registered(unresolved) if not historical else set()
    result = {}
    fallback = []
    for symbol in symbols:
        owner = (owners or {}).get(symbol)
        if symbol != benchmark:
            if historical and not owner:
                owner = resolved[symbol]["entity_id"]
            if history.has_series(owner, as_of):
                result[symbol] = history.holding_series(owner, as_of)
                continue
            if historical:
                result[symbol] = pd.DataFrame()
                continue
        if symbol != benchmark and (owner or normalize_symbol(symbol) in registered):
            result[symbol] = price_history(reader, symbol, as_of, entity_id=owner,
                accredited=history.covers, ranking_series=history.ranking_series)
        else:
            if ticker_prices_many is None:
                result[symbol] = ticker_prices(symbol)
            else:
                fallback.append(symbol)
                result[symbol] = None
    if fallback and ticker_prices_many is not None:
        result.update(ticker_prices_many(fallback))
    return result
