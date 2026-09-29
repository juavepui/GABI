"""Shared Streamlit/API calculation, independent of storage and transport."""
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class Calculators:
    fundamentals: Callable[..., dict]
    technicals: Callable[..., dict]
    risk: Callable[..., dict]
    events: Callable[..., list]
    scores: Callable[..., pd.DataFrame]
    confidence: Callable[..., pd.Series]


@dataclass
class MarketBatch:
    universe: pd.DataFrame
    fundamentals: dict
    prices: dict[str, pd.DataFrame]
    sec: dict


class MarketInputs(Protocol):
    benchmark_symbol: str
    benchmark: pd.DataFrame
    risk_free_rate: float

    def batches(self) -> Iterator[MarketBatch]: ...


@dataclass
class MemoryInputs:
    batch: MarketBatch
    benchmark: pd.DataFrame
    benchmark_symbol: str
    risk_free_rate: float

    def batches(self) -> Iterator[MarketBatch]:
        yield self.batch


def price_metadata(prices: pd.DataFrame | None) -> dict:
    if prices is None or prices.empty:
        return {"price_date": None, "close": None, "adj_close": None}
    last = prices.iloc[-1]
    return {"price_date": prices.index[-1].date().isoformat(), "close": last.get("close"),
            "adj_close": last.get("adj_close")}


def build_ranking(inputs: MarketInputs, calculators: Calculators, weights: dict | None = None,
                  *, today: date, total: int, progress_cb: Callable | None = None) -> pd.DataFrame:
    sources = {inputs.benchmark_symbol: price_metadata(inputs.benchmark)}
    rows: list[dict] = []
    for batch in inputs.batches():
        for _, company in batch.universe.iterrows():
            symbol = company["symbol"]
            record = batch.fundamentals.get(symbol)
            prices = batch.prices.get(symbol)
            sec = batch.sec.get(symbol, {})
            row = {"symbol": symbol, "name": company.get("name"), "sector": company.get("sector")}
            row.update(calculators.fundamentals(record) if record else {})
            row.update(calculators.technicals(prices, inputs.benchmark) if prices is not None else {})
            row.update(calculators.risk(prices, inputs.benchmark, risk_free_rate=inputs.risk_free_rate)
                       if prices is not None else {})
            for key in ("roic", "revenue_cagr_3y", "fcf_cagr_3y", "latest_10k_url", "latest_10k_date",
                        "latest_10q_url", "latest_10q_date"):
                row[key] = sec.get(key)
            earnings = [event for event in calculators.events(symbol, record.get("info", {}),
                        record.get("fetched_at", ""), today=today)
                        if event["event_type"] == "earnings" and event["days_until"] >= 0] if record else []
            next_event = earnings[0] if earnings else None
            for column, key in (("next_earnings_date", "event_date"), ("next_earnings_days", "days_until"),
                                ("next_earnings_is_estimate", "is_estimate")):
                row[column] = next_event[key] if next_event else None
            sources[symbol] = {**price_metadata(prices),
                               "fundamentals_fetched_at": record.get("fetched_at") if record else None,
                               "sec_fetched_at": sec.get("fetched_at")}
            rows.append(row)
            if progress_cb and ((len(rows) - 1) % 25 == 0 or len(rows) == total):
                progress_cb(len(rows), total)
    table = pd.DataFrame(rows, columns=None if rows else ["symbol"]).set_index("symbol")
    if table.empty:
        return table
    table = calculators.scores(table, weights=weights)
    table["confidence"] = calculators.confidence(table, weights=weights)
    table.attrs.update(sources=sources, risk_free_rate=inputs.risk_free_rate)
    return table
