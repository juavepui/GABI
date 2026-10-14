"""Canonical blind-validation seals, picks and mark-to-market returns."""

import hashlib
import json
from datetime import date

import pandas as pd

MIN_COVERAGE = .7


def canonical_payload(rebalance_date: str, symbols: list, entry_prices: dict) -> str:
    return json.dumps({
        "rebalance_date": rebalance_date,
        "symbols": sorted(symbols),
        "entry_prices": {s: entry_prices[s] for s in sorted(entry_prices)},
    }, sort_keys=True)


def record_hash(prev_hash: str | None, payload: str) -> str:
    return hashlib.sha256(f"{prev_hash or ''}{payload}".encode()).hexdigest()


def eligible(ranked: pd.DataFrame) -> pd.DataFrame:
    """Scored rows with enough coverage, in ranking order."""
    return ranked[ranked["composite_score"].notna() & (ranked["score_coverage"] >= MIN_COVERAGE)]


def _adjusted_closes(history: pd.DataFrame | None, as_of_ts: pd.Timestamp) -> pd.Series | None:
    history = pd.DataFrame() if history is None else history
    history = history[history.index <= as_of_ts] if not history.empty else history
    if history.empty or "adj_close" not in history or history["adj_close"].dropna().empty:
        return None
    return history["adj_close"].dropna()


def entry_prices(histories: dict, picks: list, as_of_ts: pd.Timestamp) -> tuple[dict, list]:
    """Last adjusted close on or before ``as_of_ts`` per pick, and the picks without one."""
    prices, missing = {}, []
    for symbol in picks:
        closes = _adjusted_closes(histories.get(symbol), as_of_ts)
        if closes is None:
            missing.append(symbol)
            continue
        prices[symbol] = float(closes.iloc[-1])
    return prices, missing


def finite(value) -> float | None:
    return float(value) if value is not None and pd.notna(value) else None


def ranking_snapshot(ranked: pd.DataFrame, eligible_symbols) -> tuple[str, str]:
    """The full universe score of a rebalance, as JSON and its sha256."""
    chosen = set(eligible_symbols)
    ranking = json.dumps({symbol: {"composite_score": finite(row["composite_score"]),
                                   "score_coverage": finite(row["score_coverage"]),
                                   "eligible": symbol in chosen}
                          for symbol, row in ranked.iterrows()}, sort_keys=True)
    return ranking, hashlib.sha256(ranking.encode()).hexdigest()


def last_price_on_or_before(history: pd.DataFrame, as_of_ts: pd.Timestamp) -> float | None:
    if history.empty or "adj_close" not in history:
        return None
    prices = history[history.index <= as_of_ts]["adj_close"].dropna()
    return float(prices.iloc[-1]) if not prices.empty else None


def mark_to_market_return(histories: dict, symbols: list, entry: dict, as_of_ts: pd.Timestamp) -> float | None:
    """Equal-weight return from the entry prices to the last close on or before ``as_of_ts``."""
    returns = []
    for symbol in symbols:
        closes = _adjusted_closes(histories.get(symbol), as_of_ts)
        if closes is not None:
            returns.append(float(closes.iloc[-1]) / entry[symbol] - 1)
    return float(sum(returns) / len(returns)) if returns else None


def is_revealed(validation: dict, today: date) -> bool:
    return validation["status"] == "broken_early" or today.isoformat() >= validation["unlock_date"]


def next_rebalance_due(validation: dict, periods: list[dict]) -> str | None:
    if periods:
        last_date = pd.Timestamp(periods[-1]["rebalance_date"])
        return (last_date + pd.DateOffset(months=validation["rebalance_months"])).date().isoformat()
    return validation["start_date"] or None


def verify_chain(periods: list[dict]) -> dict:
    prev_hash = None
    for period in periods:
        payload = canonical_payload(period["rebalance_date"], json.loads(period["symbols_json"]),
                                    json.loads(period["entry_prices_json"]))
        expected = record_hash(prev_hash, payload)
        if expected != period["record_hash"] or period["prev_hash"] != prev_hash:
            return {"ok": False, "broken_at": period["rebalance_date"], "n_periods": len(periods)}
        prev_hash = period["record_hash"]
    return {"ok": True, "broken_at": None, "n_periods": len(periods)}


def disclosure(status: str, unlock_date: str, looks: list[str] | None, today: str) -> dict:
    """What performance a blind validation may show on `today` (ISO dates).

    Without a preregistered plan, as the Streamlit page: everything once the seal is broken or the
    unlock date arrives. With a plan, only at its reviews: performance is computed up to the last
    review reached, never with later quarters, and nothing before the first review. A seal broken
    before this rule existed stays visible, because hiding it would misstate what was already seen.
    """
    if status == "broken_early":
        return {"revealed": True, "through": None, "next_look": None}
    if not looks:
        return {"revealed": today >= unlock_date, "through": None, "next_look": None}
    reached = [look for look in sorted(looks) if today >= look]
    upcoming = [look for look in sorted(looks) if look > today]
    return {"revealed": bool(reached), "through": reached[-1] if reached else None,
            "next_look": upcoming[0] if upcoming else None}
