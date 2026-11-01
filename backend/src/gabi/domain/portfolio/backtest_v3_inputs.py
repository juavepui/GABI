"""Nominal bars and corporate events for backtest V3 (#249) from a cached price series.

V3 executes at nominal prices and applies splits and dividends as events, so the
research series cannot be used as stored:

- The Yahoo cache (``today_splits``) keeps open/close on today's split basis and
  volumes multiplied by the later splits. The known later splits undo both;
  each split is an event on its ex-date with the declared ratio.
- An archive series (``as_traded``) already keeps the traded prices; its splits
  are the clean ratios implied by close against adjusted close.

Dividends are the cash implied by the adjusted close on each ex-date
(``issuer_evidence.implied_events``), paid per nominal share. A jump the rules
cannot explain stays out of the events and is reported as an anomaly.

Nothing is invented: a session without a positive open and close is absent, and
a session without volume is a halt (``suspended``), so V3 neither trades nor
values at that bar.
"""

import math
from dataclasses import dataclass
from datetime import date

import pandas as pd

from gabi.domain.portfolio.backtest_v3 import Bar, Event
from gabi.domain.research import issuer_evidence

TODAY_SPLITS = "today_splits"
AS_TRADED = "as_traded"
BASES = (TODAY_SPLITS, AS_TRADED)


@dataclass(frozen=True)
class SeriesInputs:
    bars: dict[date, Bar]
    events: list[Event]
    anomalies: list[dict]


def _split_factor(index: pd.DatetimeIndex, splits: pd.Series) -> pd.Series:
    """Product of the split ratios after each session: the later splits a today-basis price carries."""
    factor = pd.Series(1.0, index=index)
    for day, ratio in splits.items():
        if ratio and math.isfinite(ratio) and ratio > 0:
            factor[factor.index < pd.Timestamp(day)] *= float(ratio)
    return factor


def _number(value) -> float | None:
    number = float(value) if value is not None and not pd.isna(value) else None
    return number if number is not None and math.isfinite(number) else None


def series_inputs(symbol: str, frame: pd.DataFrame, *, basis: str, splits: pd.Series | None = None,
                  start: date | None = None, end: date | None = None) -> SeriesInputs:
    """Bars and events of ``symbol`` between ``start`` and ``end`` (inclusive)."""
    if basis not in BASES:
        raise ValueError(f"Base de precios desconocida: {basis}")
    if frame is None or frame.empty:
        return SeriesInputs({}, [], [])
    data = frame.sort_index()
    data = data[~data.index.duplicated(keep="last")]
    data.index = pd.DatetimeIndex(data.index).normalize()
    splits = (splits if splits is not None else pd.Series(dtype=float)).dropna()
    splits.index = pd.DatetimeIndex(splits.index).normalize()
    factor = _split_factor(data.index, splits) if basis == TODAY_SPLITS else pd.Series(1.0, index=data.index)
    inside = pd.Series(True, index=data.index)
    if start is not None:
        inside &= data.index >= pd.Timestamp(start)
    if end is not None:
        inside &= data.index <= pd.Timestamp(end)

    bars: dict[date, Bar] = {}
    for day, row in data[inside].iterrows():
        open_, close, volume = _number(row.get("open")), _number(row.get("close")), _number(row.get("volume"))
        if not open_ or not close or open_ <= 0 or close <= 0:
            continue  # Absent: no price is invented.
        scale = float(factor[day])
        bars[day.date()] = Bar(open=open_ * scale, close=close * scale, volume=(volume or 0.0) / scale,
                               suspended=not volume or volume <= 0)

    events, anomalies = [], []
    priced = data[["close", "adj_close"]].apply(pd.to_numeric, errors="coerce")
    priced = priced[(priced > 0).all(axis=1)]
    implied = issuer_evidence.implied_events(priced) if len(priced) > 1 else pd.DataFrame()
    for row in implied.itertuples(index=False):
        day = pd.Timestamp(row.date)
        if not inside.get(day, False):
            continue
        if row.kind == "dividend":
            # On today's basis the cash is per adjusted share: the later splits make it nominal.
            amount = float(row.amount) * float(factor.get(day, 1.0))
            events.append(Event("dividend", symbol, day.date(), cash=amount))
        elif row.kind == "split" and basis == AS_TRADED:
            events.append(Event("split", symbol, day.date(), ratio=float(row.ratio)))
        else:
            # On today's basis a split cannot show in close/adj_close: the stored adjustment is inconsistent.
            anomalies.append({"symbol": symbol, "day": day.date().isoformat(), "kind": row.kind,
                              "factor": float(row.factor)})
    if basis == TODAY_SPLITS:
        for day, ratio in splits.items():
            if _within(day, start, end, data):
                events.append(Event("split", symbol, day.date(), ratio=float(ratio)))
    # Splits before dividends on the same day: the dividend is per post-split share.
    order = {"split": 0, "dividend": 1}
    events.sort(key=lambda event: (event.day, order.get(event.kind, 2)))
    return SeriesInputs(bars, events, anomalies)


def _within(day: pd.Timestamp, start: date | None, end: date | None, data: pd.DataFrame) -> bool:
    """A split on a session the series lacks still applies if it falls inside the window and the series."""
    if data.empty or not data.index[0] < day <= data.index[-1]:
        return False
    return (start is None or day >= pd.Timestamp(start)) and (end is None or day <= pd.Timestamp(end))


def terminal(symbol: str, bars: dict[date, Bar], sessions: list[date], event: dict | None
             ) -> tuple[Event | None, dict | None]:
    """The exit of a series that ends before the last session, with V2's terminal semantics.

    The event falls on the first session after the last bar, before its open:

    - a confirmed one-for-one succession pays the last close (V2 liquidates it at that value);
    - a confirmed cash consideration pays it per share; a confirmed liquidation is a
      bankruptcy with that recovery, even when it is zero;
    - anything else pays the last close and is not strict: the result declares it.
    """
    traded = [day for day, bar in bars.items() if not bar.suspended]
    if not traded:
        return None, None
    last_day = max(bars)
    later = [day for day in sessions if day > last_day]
    if not later:
        return None, None
    day, last_close = later[0], bars[max(traded)].close
    status = event.get("status") if event else "series_ended_without_event"
    record = {"symbol": symbol, "last_bar": last_day.isoformat(), "day": day.isoformat(), "status": status,
              "strict": False, "event_type": event.get("event_type") if event else None}
    confirmed = status == "terminal_return_confirmed"
    cash = _number(event.get("cash_per_share")) if event else None
    if confirmed and event and event.get("event_type") == "succession" and event.get("exchange_ratio") == 1.0:
        return (Event("cash_merger", symbol, day, cash=last_close),
                record | {"status": "succession_one_for_one", "strict": True, "cash": last_close})
    if confirmed and event and cash is not None and cash >= 0:
        kind = "bankruptcy" if event.get("event_type") == "bankruptcy_liquidation" else "cash_merger"
        return Event(kind, symbol, day, cash=cash), record | {"strict": True, "cash": cash}
    return Event("delisting", symbol, day, cash=last_close), record | {"cash": last_close}
