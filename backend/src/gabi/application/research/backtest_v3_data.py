"""Backtest V3 inputs (#249) from the price histories the backtests already read.

``BacktestMarket.prices`` returns, per ticker, either a series of the Yahoo
cache (today's split basis; directly or as an entity observation) or an
accredited archive series (as traded). Its provenance sets the basis; the Yahoo
splits are read once for every series that needs them. The result is what
``backtest_v3.run`` takes: nominal bars, corporate events and the anomalies left
out of them.

A series that ends before the last session gets its exit as an explicit event
(``backtest_v3_inputs.terminal``), with V2's terminal semantics: the confirmed
consideration when the archive accredits one, and otherwise the last close,
reported as not strict. No price after the last bar is invented.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import pandas as pd

from gabi.domain.portfolio import backtest_v3_inputs as inputs
from gabi.domain.portfolio.backtest_v3 import Bar, Event
from gabi.domain.research.historical_pit import YAHOO_SOURCE


@dataclass(frozen=True)
class V3Data:
    bars: dict[str, dict[date, Bar]]
    events: list[Event]
    anomalies: list[dict]
    missing: list[str]  # Tickers without any usable series in the window.
    bases: dict[str, str]
    exits: list[dict]  # One per series ending before the last session; ``strict`` False if unconfirmed.

    @property
    def strict(self) -> bool:
        return all(exit_["strict"] for exit_ in self.exits)


def basis(symbol: str, frame: pd.DataFrame) -> tuple[str, str | None]:
    """The price basis of a series and, on today's split basis, the ticker whose splits undo it."""
    source = frame.attrs.get("source_id")
    if source is None or source == YAHOO_SOURCE:
        return inputs.TODAY_SPLITS, str(frame.attrs.get("source_symbol") or symbol)
    return inputs.AS_TRADED, None


def load(frames: dict[str, pd.DataFrame | None], splits: Callable[[list[str]], dict[str, pd.Series]], *,
         start: date, end: date, sessions: list[date] | None = None,
         terminal_event: Callable[[str, pd.DataFrame], dict | None] = lambda symbol, frame: None) -> V3Data:
    """``sessions`` (the backtest calendar) enables exits; ``terminal_event`` reads the accredited event."""
    usable = {symbol: frame for symbol, frame in frames.items() if frame is not None and not frame.empty}
    kinds = {symbol: basis(symbol, frame) for symbol, frame in usable.items()}
    wanted = sorted({source for kind, source in kinds.values() if kind == inputs.TODAY_SPLITS and source})
    ratios = splits(wanted) if wanted else {}
    bars, events, anomalies, missing, exits = {}, [], [], [], []
    for symbol in sorted(frames):
        if symbol not in usable:
            missing.append(symbol)
            continue
        kind, source = kinds[symbol]
        series = inputs.series_inputs(symbol, usable[symbol], basis=kind,
                                      splits=ratios.get(source) if source else None, start=start, end=end)
        if not series.bars:
            missing.append(symbol)
        bars[symbol] = series.bars
        events += series.events
        anomalies += series.anomalies
        if sessions and series.bars and max(series.bars) < max(sessions):
            event, record = inputs.terminal(symbol, series.bars, sessions, terminal_event(symbol, usable[symbol]))
            if event is not None and record is not None:
                events.append(event)
                exits.append(record)
    return V3Data(bars, events, anomalies, missing, {symbol: kind for symbol, (kind, _) in kinds.items()}, exits)
