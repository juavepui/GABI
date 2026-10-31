"""Self-financing backtest V3 (#249): explicit cash, execution prices, liquidity and corporate actions.

Version ``backtest-v3``. It does not replace V1/V2, which keep reproducing their
published results; V3 inherits none of their evidence.

- A signal known at a session's close executes at the next session's open, at
  the nominal price (never the research-adjusted series) plus half the spread
  and the slippage, within a share of that day's dollar volume.
- Targets apply to the net asset value minus a cash reserve for costs; sales go
  first and purchases are scaled so cash never goes negative. Leverage exists
  only when declared, and is off by default.
- Corporate actions apply before the open: splits change shares and price,
  dividends pay cash net of withholding, cash mergers and delistings pay out,
  stock mergers convert shares and a bankruptcy pays its recovery (zero if none).
- No price is invented: a missing bar is ``absent`` and a declared halt is
  ``suspended``; neither trades, and the position is valued at its last close and
  reported as stale. Nothing is filled backwards from the future.
"""

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

VERSION = "backtest-v3"
EVENT_KINDS = ("split", "dividend", "cash_merger", "stock_merger", "delisting", "bankruptcy")


@dataclass(frozen=True)
class Bar:
    open: float
    close: float
    volume: float  # Shares traded in the session.
    suspended: bool = False


@dataclass(frozen=True)
class Event:
    kind: str
    symbol: str
    day: date
    ratio: float = 1.0  # split: new shares per old; stock_merger: target shares per share.
    cash: float = 0.0  # Per share: dividend, merger or delisting payout, bankruptcy recovery.
    target: str | None = None  # stock_merger: the acquirer.

    def __post_init__(self) -> None:
        if self.kind not in EVENT_KINDS:
            raise ValueError(f"Evento desconocido: {self.kind}")
        if self.kind == "stock_merger" and not self.target:
            raise ValueError("Una fusión por acciones necesita la empresa absorbente.")


@dataclass(frozen=True)
class Costs:
    commission_fixed: float = 0.0
    commission_pct: float = 0.0
    spread_bps: float = 0.0  # Full spread: each side pays half.
    slippage_bps: float = 0.0
    participation: float = 0.10  # Largest share of the day's dollar volume one order may take.
    min_order: float = 0.0
    dividend_withholding: float = 0.0
    cost_reserve: float = 0.002  # Share of the net asset value kept in cash for costs.
    leverage: bool = False

    def commission(self, notional: float) -> float:
        return self.commission_fixed + notional * self.commission_pct


# Declared scenarios: base for liquid large caps, stress for wide spreads and thin markets.
BASE = Costs(commission_fixed=1.0, spread_bps=5.0, slippage_bps=5.0, participation=0.10)
STRESS = Costs(commission_fixed=1.0, spread_bps=30.0, slippage_bps=25.0, participation=0.02)


@dataclass(frozen=True)
class Rebalance:
    signal_day: date
    weights: dict[str, float]


@dataclass
class _State:
    cash: float
    shares: dict[str, float] = field(default_factory=dict)
    last_close: dict[str, float] = field(default_factory=dict)


def _apply_event(state: _State, event: Event, withholding: float) -> dict | None:
    held = state.shares.get(event.symbol, 0.0)
    if held <= 0:
        return None
    record = {"day": event.day.isoformat(), "kind": event.kind, "symbol": event.symbol, "shares": held}
    if event.kind == "split":
        state.shares[event.symbol] = held * event.ratio
        if event.symbol in state.last_close:
            state.last_close[event.symbol] /= event.ratio
        return record
    if event.kind == "dividend":
        paid = held * event.cash * (1 - withholding)
        state.cash += paid
        return record | {"cash": paid}
    payout = held * event.cash
    state.cash += payout
    del state.shares[event.symbol]
    state.last_close.pop(event.symbol, None)
    if event.kind == "stock_merger":
        assert event.target is not None
        state.shares[event.target] = state.shares.get(event.target, 0.0) + held * event.ratio
        record["target"] = event.target
    return record | {"cash": payout}


def _execute(state: _State, day: date, weights: dict[str, float], bars: dict[str, Bar | None],
             costs: Costs) -> tuple[list[dict], list[dict]]:
    """Trades at the open toward ``weights``; returns the trades and the orders that could not execute."""
    trades, blocked = [], []
    half = costs.spread_bps / 20000 + costs.slippage_bps / 10000

    def tradable(symbol: str) -> Bar | None:
        bar = bars.get(symbol)
        if bar is None or bar.suspended or bar.open <= 0:
            blocked.append({"day": day.isoformat(), "symbol": symbol,
                            "reason": "suspended" if bar is not None and bar.suspended else "absent"})
            return None
        return bar

    def reference(symbol: str) -> float:
        bar = bars.get(symbol)
        return bar.open if bar is not None and not bar.suspended and bar.open > 0 else state.last_close.get(symbol, 0.0)

    nav = state.cash + sum(quantity * reference(symbol) for symbol, quantity in state.shares.items())
    investable = nav * (1 - costs.cost_reserve)
    targets = {symbol: weight * investable for symbol, weight in weights.items() if weight > 0}
    current = {symbol: quantity * reference(symbol) for symbol, quantity in state.shares.items()}

    def cap(bar: Bar, notional: float) -> tuple[float, bool]:
        limit = costs.participation * bar.volume * bar.open
        return (min(notional, limit), notional > limit + 1e-9)

    for symbol in sorted(set(current) | set(targets)):
        excess = current.get(symbol, 0.0) - targets.get(symbol, 0.0)
        if excess <= 1e-9:
            continue
        bar = tradable(symbol)
        if bar is None:
            continue
        notional, partial = cap(bar, excess)
        if notional < costs.min_order:
            continue
        price = bar.open * (1 - half)
        quantity = min(notional / bar.open, state.shares[symbol])
        proceeds = quantity * price
        commission = costs.commission(proceeds)
        state.cash += proceeds - commission
        state.shares[symbol] -= quantity
        if state.shares[symbol] <= 1e-12:
            del state.shares[symbol]
        trades.append({"day": day.isoformat(), "symbol": symbol, "side": "SELL", "shares": quantity,
                       "price": price, "notional": proceeds, "commission": commission,
                       "execution_cost": quantity * bar.open - proceeds, "partial": partial})

    wanted = []
    for symbol, target in sorted(targets.items()):
        gap = target - current.get(symbol, 0.0)
        if gap <= 1e-9:
            continue
        bar = tradable(symbol)
        if bar is None:
            continue
        notional, partial = cap(bar, gap)
        if notional >= max(costs.min_order, 1e-9):
            wanted.append((symbol, bar, notional, partial))
    budget = state.cash if not costs.leverage else math.inf
    # The notional is the cash paid at the execution price: spread and slippage are already inside it.
    needed = sum(notional + costs.commission(notional) for _, _, notional, _ in wanted)
    scale = min(1.0, budget / needed) if needed > 0 else 1.0
    for symbol, bar, notional, partial in wanted:
        notional *= scale
        if notional < max(costs.min_order, 1e-9):
            continue
        price = bar.open * (1 + half)
        commission = costs.commission(notional)
        if not costs.leverage and notional + commission > state.cash:
            notional = max((state.cash - costs.commission_fixed) / (1 + costs.commission_pct), 0.0)
            commission = costs.commission(notional)
            if notional < max(costs.min_order, 1e-9):
                continue
        quantity = notional / price
        state.cash -= notional + commission
        state.shares[symbol] = state.shares.get(symbol, 0.0) + quantity
        trades.append({"day": day.isoformat(), "symbol": symbol, "side": "BUY", "shares": quantity, "price": price,
                       "notional": notional, "commission": commission,
                       "execution_cost": notional - quantity * bar.open, "partial": partial or scale < 1})
    if not costs.leverage and state.cash < -1e-6:
        raise AssertionError(f"Saldo negativo sin apalancamiento declarado el {day}: {state.cash}")
    return trades, blocked


def run(sessions: list[date], bars: dict[str, dict[date, Bar]], *, rebalances: list[Rebalance],
        costs: Costs, initial_cash: float = 0.0, flows: dict[date, float] | None = None,
        events: list[Event] | None = None) -> dict:
    """Daily simulation over ``sessions``; ``bars[symbol][day]`` holds nominal prices (a missing day is absent)."""
    flows, events = flows or {}, sorted(events or [], key=lambda event: (event.day, event.symbol))
    state = _State(initial_cash)
    pending = sorted(rebalances, key=lambda rebalance: rebalance.signal_day)
    rows: list[dict[str, Any]] = []
    trades, blocked, applied, stale_days = [], [], [], []
    dividends = 0.0
    for day in sessions:
        for event in [event for event in events if event.day == day]:
            record = _apply_event(state, event, costs.dividend_withholding)
            if record:
                applied.append(record)
                if event.kind == "dividend":
                    dividends += record["cash"]
        flow = flows.get(day, 0.0)
        state.cash += flow
        today = {symbol: series.get(day) for symbol, series in bars.items()}
        due = [rebalance for rebalance in pending if rebalance.signal_day < day]
        if due:
            pending = [rebalance for rebalance in pending if rebalance.signal_day >= day]
            done, stuck = _execute(state, day, due[-1].weights, today, costs)
            trades += done
            blocked += stuck
        stale = []
        for symbol in state.shares:
            bar = today.get(symbol)
            if bar is not None and not bar.suspended and bar.close > 0:
                state.last_close[symbol] = bar.close
            else:
                stale.append({"symbol": symbol, "reason": "suspended" if bar is not None else "absent"})
        unpriced = [symbol for symbol in state.shares if symbol not in state.last_close]
        if unpriced:
            raise ValueError(f"Sin ningún precio conocido para {', '.join(unpriced)} el {day}: no se inventa.")
        positions = sum(quantity * state.last_close[symbol] for symbol, quantity in state.shares.items())
        if stale:
            stale_days.append({"day": day.isoformat(), "positions": stale})
        rows.append({"day": day, "cash": state.cash, "positions": positions, "nav": state.cash + positions,
                     "flow": flow, "stale": len(stale)})
    commissions = sum(trade["commission"] for trade in trades)
    execution = sum(trade["execution_cost"] for trade in trades)
    return {"version": VERSION, "daily": rows, "trades": trades, "blocked": blocked, "events": applied,
            "stale": stale_days, "commissions": commissions, "execution_costs": execution,
            "dividends": dividends, "final_shares": dict(state.shares),
            "identity_error": max((abs(row["nav"] - row["cash"] - row["positions"]) for row in rows), default=0.0),
            "min_cash": min((row["cash"] for row in rows), default=initial_cash)}


def benchmark(symbol: str, sessions: list[date], bars: dict[str, dict[date, Bar]], *, costs: Costs,
              initial_cash: float = 0.0, flows: dict[date, float] | None = None,
              events: list[Event] | None = None) -> dict:
    """The same calendar, flows, costs and accounting fully invested in one symbol.

    Each contribution is invested at the next session's open, as a portfolio
    rebalance would be."""
    flows = flows or {}
    signal_days = sorted({sessions[0], *(day for day in flows if day in sessions)})
    rebalances = [Rebalance(day, {symbol: 1.0}) for day in signal_days]
    return run(sessions, {symbol: bars[symbol]}, rebalances=rebalances, costs=costs, initial_cash=initial_cash,
               flows=flows, events=[event for event in events or [] if event.symbol == symbol])
