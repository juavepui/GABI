"""Gather local metadata, then calculate coverage and provenance with one clock."""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from gabi.domain.market.data_quality import (
    DEFAULT_RULES,
    ProvenanceInputs,
    QualityRules,
    SummaryInputs,
    symbol_provenance,
    universe_summary,
)


@dataclass(frozen=True)
class QualityReaders:
    price_coverage: Callable[[list], dict]
    fundamentals_fetched: Callable[[list], dict]
    sec_fetched: Callable[[list], dict]
    insider_fetched: Callable[[list], dict]
    sec_facts: Callable[[list], set]
    sector_asof: Callable[[list, str], dict]
    local_ciks: Callable[[list], dict]
    cik_cache_present: bool
    macro_fetched: Callable[[], dict]
    macro_series: tuple[str, ...]
    macro_history: Callable[[str], pd.DataFrame]
    fundamentals: Callable[[list], dict]
    sec_metrics: Callable[[list], dict]


def summary(symbols: list, readers: QualityReaders, *, now: datetime, rules: QualityRules = DEFAULT_RULES) -> dict:
    if not symbols:
        return {"n_symbols": 0, "sources": {}, "cik": None, "macro": None}
    now = now.astimezone(UTC)
    today = pd.Timestamp(now).date().isoformat()
    past = (pd.Timestamp(now) - pd.DateOffset(years=1)).date().isoformat()
    prices = readers.price_coverage(symbols)
    fundamentals = readers.fundamentals_fetched(symbols)
    sec, insider = readers.sec_fetched(symbols), readers.insider_fetched(symbols)
    facts = readers.sec_facts(symbols)
    current_sectors, past_sectors = readers.sector_asof(symbols, today), readers.sector_asof(symbols, past)
    ciks, fetched = readers.local_ciks(symbols), readers.macro_fetched()
    dates = {}
    for series in readers.macro_series:
        history = readers.macro_history(series)
        valid = history.dropna(subset=["value"]) if not history.empty else history
        dates[series] = str(valid.index.max().date()) if not valid.empty else None
    inputs = SummaryInputs(prices, fundamentals, sec, insider, facts, current_sectors, past_sectors,
                           ciks, readers.cik_cache_present, fetched, dates, readers.macro_series)
    return universe_summary(symbols, inputs, now=now, rules=rules)


def provenance(symbol: str, readers: QualityReaders, *, now: datetime, as_of: str | None = None,
               rules: QualityRules = DEFAULT_RULES) -> dict:
    now = now.astimezone(UTC)
    reference = as_of or (pd.Timestamp(now) - pd.DateOffset(years=1)).date().isoformat()
    prices = readers.price_coverage([symbol]).get(symbol, {})
    fundamentals = readers.fundamentals([symbol]).get(symbol)
    sec = readers.sec_fetched([symbol]).get(symbol)
    metrics = readers.sec_metrics([symbol]).get(symbol, {})
    facts = symbol in readers.sec_facts([symbol])
    insider = readers.insider_fetched([symbol]).get(symbol)
    sector = readers.sector_asof([symbol], reference)[symbol]
    cik = readers.local_ciks([symbol])[symbol]
    inputs = ProvenanceInputs(prices, fundamentals, sec, metrics, facts, insider, sector, cik, reference)
    return symbol_provenance(symbol, inputs, now=now, rules=rules)
