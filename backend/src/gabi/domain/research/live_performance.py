"""Prospective paper portfolio from frozen decisions, never overlapping cohorts."""

from collections.abc import Callable
from datetime import datetime

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from gabi.domain.research.live_ledger import fingerprint


def entry_session(timestamp: str) -> str:
    instant = pd.Timestamp(timestamp)
    if instant.tzinfo is None:
        raise ValueError("Timestamp UTC/offset requerido.")
    calendar = xcals.get_calendar("XNYS")
    dates = calendar.sessions_in_range(instant.date(), (instant + pd.Timedelta(days=14)).date())
    return next(d.date().isoformat() for d in dates if calendar.session_open(d) > instant)


def _price(history: pd.DataFrame, date: str, opening: bool) -> float | None:
    if history.empty or pd.Timestamp(date) not in history.index:
        return None
    row = history.loc[pd.Timestamp(date)]
    if isinstance(row, pd.DataFrame):
        return None
    close, adjusted = row.get("close"), row.get("adj_close")
    value = row.get("open") if opening else close
    if any(v is None or not np.isfinite(v) or v <= 0 for v in (close, adjusted, value)):
        return None
    return float(value * adjusted / close)


def report(all_events: list[dict], now: datetime, last_session: str, benchmark_history: pd.DataFrame,
           history: Callable[[str, dict], pd.DataFrame], *, benchmark_symbol: str,
           model_version: str | None = None, as_of: str | None = None) -> dict:
    """Paper portfolio of the frozen LIVE_FORWARD decisions up to ``as_of`` (default: the last closed session).

    ``history(symbol, payload)`` returns the adjusted prices attributed to the decision's issuer
    (empty when a recycled ticker cannot be attributed); ``now`` and ``last_session`` are injected.
    """
    cutoff = as_of or last_session
    if cutoff > last_session:
        raise ValueError("No se evalúan cierres futuros.")
    calendar = xcals.get_calendar("XNYS")
    if not calendar.is_session(cutoff):
        raise ValueError("El corte debe ser una sesión XNYS.")
    decisions = [e for e in all_events if e["payload"].get("kind") == "DECISION"
                 and e["payload"].get("stage") == "LIVE_FORWARD"]
    versions = sorted({e["payload"]["model_version"] for e in decisions})
    if model_version is None:
        if len(versions) > 1:
            raise ValueError("Hay varias versiones: seleccione una; no se combinan modelos.")
        model_version = versions[0] if versions else None
    decisions = [e for e in decisions if e["payload"]["model_version"] == model_version]
    first_by_entry: dict[str, dict] = {}
    for event in decisions:
        date = entry_session(event["payload"]["created_at"])
        if date <= cutoff:
            first_by_entry.setdefault(date, event)
    schedule = sorted(first_by_entry.items())
    nav, complete = 1., True
    drift: dict[str, float] = {}
    intervals, prices_used = [], []
    benchmark_entry = benchmark_last = None
    for i, (date, event) in enumerate(schedule):
        payload = event["payload"]
        end = schedule[i + 1][0] if i + 1 < len(schedule) else cutoff
        end_open = i + 1 < len(schedule)
        picks = payload["top_n"] if payload["status"] == "SIGNAL" else []
        weights = {s: 1 / len(picks) for s in picks}
        gross, ratios, missing = 1. - sum(weights.values()), {}, []
        for symbol, weight in weights.items():
            owner = payload.get("sources", {}).get(symbol, {}).get("entity_id")
            prices = history(symbol, payload)
            start_price, end_price = _price(prices, date, True), _price(prices, end, end_open)
            prices_used.append({"seq": event["seq"], "symbol": symbol, "entry_date": date, "end_date": end,
                                "entry_adjusted_open": start_price, "end_adjusted_price": end_price,
                                "entity_id": owner, "identity_status": "attributed" if owner else "unverified ticker"})
            if start_price is None or end_price is None:
                missing.append(symbol)
            else:
                ratios[symbol] = end_price / start_price
                gross += weight * ratios[symbol]
        turn = sum(abs(weights.get(s, 0) - drift.get(s, 0)) for s in set(weights) | set(drift)) if complete else None
        cost = .001 * turn if turn is not None else None
        if missing:
            complete = False
        if complete:
            assert cost is not None
            factor = (1 - cost) * gross
            nav *= factor
            drift = {s: weights[s] * ratios[s] / gross for s in picks} if gross else {}
        else:
            factor = None
        bench_a, bench_b = _price(benchmark_history, date, True), _price(benchmark_history, end, end_open)
        if benchmark_entry is None and i == 0:
            benchmark_entry = bench_a
        benchmark_last = bench_b
        prices_used.append({"seq": event["seq"], "symbol": benchmark_symbol, "entry_date": date,
                            "end_date": end, "entry_adjusted_open": bench_a, "end_adjusted_price": bench_b})
        intervals.append({"seq": event["seq"], "record_hash": event["record_hash"], "status": payload["status"],
                          "entry": date, "end": end, "end_basis": "open" if end_open else "close",
                          "requested": len(picks), "missing": missing, "gross_return": gross - 1 if not missing else None,
                          "turnover_notional": turn, "cost_fraction": cost, "net_return": factor - 1 if factor is not None else None,
                          "nav": nav if complete else None})
    benchmark = (.999 * benchmark_last / benchmark_entry - 1) if benchmark_entry and benchmark_last else None
    result = {"stage": "LIVE_FORWARD", "model_version": model_version, "available_versions": versions,
              "as_of": cutoff, "generated_at": now.isoformat(), "intervals": intervals,
              "complete": complete and bool(intervals), "cumulative_return": nav - 1 if complete and intervals else None,
              "benchmark_return": benchmark, "prices_used": prices_used,
              "policy": "first decision per next-open session; equal weights; 10 bp/side on traded asset notional; missing blocks accumulation",
              "limitations": ["Paper portfolio, not execution or the frozen quarterly backtest.",
                              "Current revised prices for outcomes; original decision remains frozen.",
                              "A positive cumulative return is not independent predictive confirmation."]}
    result["outcome_data_fingerprint"] = fingerprint(prices_used)
    return result
