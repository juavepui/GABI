"""Annual inventory rules; candidate coverage is never identity accreditation."""
from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd

from gabi.domain.research.coverage import METRICS as METRICS
from gabi.domain.research.coverage import CoverageParameters, availability, finite, metric_row


@dataclass(frozen=True)
class TickerInputs:
    symbol: str
    facts: pd.DataFrame
    prices: pd.DataFrame
    future_splits: tuple[float | None, ...]


def pick_snapshot(frame: pd.DataFrame, as_of: str) -> tuple[str, list[str]]:
    before = frame[frame.date <= as_of]
    if before.empty:
        raise ValueError(f"No membership snapshot on or before {as_of}")
    row = before.iloc[-1]
    return str(row.date), [s.strip() for s in str(row.tickers).split(",") if s.strip()]


def block_counts(rows: list[dict], *, parameters: CoverageParameters = CoverageParameters()) -> dict[str, int]:
    result = {metric: sum(finite(row.get(metric)) for row in rows) for metric in parameters.metrics}
    result.update({f"{block}_complete": sum(all(finite(row.get(metric)) for metric in metrics) for row in rows)
                   for block, metrics in parameters.blocks})
    result["all_13"] = sum(availability(row, parameters=parameters)[0] == 13 for row in rows)
    result["ranking_minimum"] = sum(availability(row, parameters=parameters)[1] for row in rows)
    return result


def old_block_counts(detail: pd.DataFrame, day: str, *, parameters: CoverageParameters = CoverageParameters()) -> dict[str, int]:
    frame = detail[detail.date == day]
    if frame.empty:
        raise ValueError(f"Missing pre-2016 quarterly audit at {day}; run python -m gabi.historical_coverage")
    rows = []
    for missing in frame.missing_metrics.fillna(""):
        absent = set(missing.split(";"))
        rows.append({metric: None if metric in absent else 1 for metric in parameters.metrics})
    result = block_counts(rows, parameters=parameters)
    if "prices_253_recent" in frame:
        result["prices_253_recent"] = int(frame.prices_253_recent.sum())
    return result


def annual_metrics(inputs: Iterable[TickerInputs], benchmark: pd.DataFrame, expected: pd.DatetimeIndex,
                   day: str, *, parameters: CoverageParameters = CoverageParameters()) -> dict[str, int]:
    rows = []
    complete_prices = 0
    for item in inputs:
        prices = item.prices
        complete_prices += len(expected) == 253 and expected.difference(prices.index).empty and prices.reindex(expected).adj_close.gt(0).all()
        nominal = float(prices.close.iloc[-1]) if not prices.empty and pd.notna(prices.close.iloc[-1]) else None
        if nominal is not None:
            for ratio in item.future_splits:
                if ratio:
                    nominal *= ratio
        rows.append(metric_row(item.facts, prices, benchmark, day, nominal_price=nominal, parameters=parameters))
    result = block_counts(rows, parameters=parameters)
    result["prices_253_recent"] = int(complete_prices)
    return result


def verified_owners(aliases: pd.DataFrame, symbols: list[str], day: str) -> int:
    owners = 0
    for symbol in symbols:
        claims = aliases[(aliases.symbol == symbol) & (aliases.valid_from <= day)
                         & (aliases.valid_to.isna() | (aliases.valid_to > day))]
        if len(set(claims.entity_id)) == 1 and not claims.empty and claims.confidence.max() >= 0.9:
            owners += 1
    return owners
