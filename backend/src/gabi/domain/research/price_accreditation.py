"""Evidence and return reconciliation for historical prices."""
import json
from datetime import date, timedelta

import numpy as np
import pandas as pd

from gabi.domain.market import identity
from gabi.domain.research.historical_pit import ADJUSTED, YAHOO_SOURCE

UNKNOWN = "unknown"
MIN_OVERLAP = 60
MAX_P99_RETURN_DIFFERENCE = 0.005
MAX_EVENT_RETURN_DIFFERENCE = 0.05

EVENT_TYPES = {"cash_acquisition", "stock_acquisition", "merger", "bankruptcy_liquidation",
               "delisting", "spin_off", "succession"}

def qualify_fallback(*, identity_tier: str | None, recycled: bool, archive: dict,
                     overlap: str, proof: dict | None) -> tuple[bool, str]:
    """Require independent dated boundaries and return-adjustment evidence.

    A Yahoo overlap is useful corroboration, never a universal requirement.
    `proof` is a reviewed record with independently sourced first/last trade
    dates and a reconciliation of splits and dividends for the requested span.
    """
    if recycled:
        return False, "ticker_recycled"
    if not identity_tier:
        return False, "identity_unresolved"
    if not archive["complete"]:
        return False, "incomplete_prices"
    if overlap in {"divergent_overlap", "divergent_event"}:
        return False, "archive_adjustment_divergent"
    if not proof:
        return False, "archive_evidence_missing"
    first, last = proof.get("first_trade"), proof.get("last_trade")
    if not first or not last or not proof.get("boundary_evidence"):
        return False, "archive_boundary_unverified"
    if first > archive["first"] or last < archive["last"]:
        return False, "archive_outside_trading_life"
    if proof.get("adjustment_basis") != ADJUSTED or not proof.get("adjustment_evidence"):
        return False, "archive_adjustment_unverified"
    if overlap != "consistent_overlap" and not proof.get("corporate_action_evidence"):
        return False, "archive_corporate_actions_unverified"
    return True, "fallback_accredited"


def _refs(refs: list[dict]) -> str:
    if not isinstance(refs, list) or not all(isinstance(r, dict) and r.get("source_url") for r in refs):
        raise ValueError("Evidence must contain source URLs")
    return json.dumps(refs, sort_keys=True)


def _producer(evidence_json: str) -> str | None:
    return next((ref.get("producer") for ref in json.loads(evidence_json)
                 if ref.get("kind") == "source" and ref.get("producer")), None)


def terminal_return(event: dict, *, entry_adj_close: float, last_close: float,
                    last_adj_close: float, successor_close: float | None = None) -> float:
    """Translate documented cash/share consideration onto the adjusted basis.

    The last traded close is used only as the conversion factor between the
    nominal consideration and the already-adjusted entry-to-last return.
    """
    if event["status"] != "terminal_return_confirmed":
        raise ValueError("Terminal return is not confirmed")
    if min(entry_adj_close, last_close, last_adj_close) <= 0:
        raise ValueError("Invalid price")
    cash = event.get("cash_per_share") or 0.0
    ratio = event.get("exchange_ratio") or 0.0
    if ratio and (successor_close is None or successor_close <= 0):
        raise ValueError("Stock consideration requires successor closing price")
    consideration = cash + ratio * (successor_close or 0.0)
    return float((last_adj_close / entry_adj_close) * (consideration / last_close) - 1)

def _adjacent_returns(common: pd.DataFrame, sessions: pd.DatetimeIndex | None) -> pd.DataFrame:
    returns = common.pct_change(fill_method=None).dropna()
    # A gap in either source must not become a fabricated daily return.
    if sessions is not None:
        positions = sessions.get_indexer(common.index)
        adjacent = (positions[1:] >= 0) & (positions[:-1] >= 0) & ((positions[1:] - positions[:-1]) == 1)
    else:
        adjacent = (common.index.to_series().diff().dt.days.iloc[1:] <= 5).to_numpy()
    return returns[adjacent]


def overlap_status(yahoo: pd.DataFrame, archive: pd.DataFrame,
                   sessions: pd.DatetimeIndex | None = None) -> tuple[str, int, float | None]:
    """Compare daily adjusted returns on actual common observations only."""
    common = yahoo[["adj_close"]].join(archive[["adj_close"]], how="inner", lsuffix="_y", rsuffix="_a")
    common = common.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    common = common[(common > 0).all(axis=1)]
    if len(common) < MIN_OVERLAP + 1:
        return "insufficient_overlap", max(0, len(common) - 1), None
    returns = _adjacent_returns(common, sessions)
    if len(returns) < MIN_OVERLAP:
        return "insufficient_overlap", len(returns), None
    difference = (returns["adj_close_y"] - returns["adj_close_a"]).abs()
    p99 = float(difference.quantile(0.99))
    if p99 > MAX_P99_RETURN_DIFFERENCE:
        return "divergent_overlap", len(returns), p99
    if float(difference.max()) > MAX_EVENT_RETURN_DIFFERENCE:
        return "divergent_event", len(returns), p99
    return "consistent_overlap", len(returns), p99

def prepare_series(*, cik: str, symbol: str, valid_from: str, valid_to: str,
                  source_id: str, adjustment_basis: str, status: str,
                  evidence: list[dict]) -> dict:
    """Idempotently attribute an interval; never copy it to the legacy cache."""
    cik = identity.normalize_cik(cik)
    symbol = identity.normalize_symbol(symbol)
    if date.fromisoformat(valid_from) >= date.fromisoformat(valid_to):
        raise ValueError("Empty price interval")
    if status not in {"tier_a", "tier_b", "excluded"}:
        raise ValueError("Invalid price tier")
    if status != "excluded" and adjustment_basis != ADJUSTED:
        raise ValueError("Backtest intervals require split and dividend adjusted returns")
    if status == "tier_a" and source_id != YAHOO_SOURCE:
        raise ValueError("Tier A requires the operational Yahoo source")
    if status == "tier_b" and source_id == YAHOO_SOURCE:
        raise ValueError("Tier B requires a separately accredited fallback")
    kinds = {ref.get("kind") for ref in evidence}
    required = {"identity", "source"} if status == "tier_a" else {
        "identity", "source", "first_trade", "last_trade", "adjustment", "corporate_actions"}
    if status != "excluded" and not required.issubset(kinds):
        raise ValueError("Missing source, identity, boundary or adjustment evidence")
    if status == "tier_b":
        by_kind = {kind: next(ref for ref in evidence if ref.get("kind") == kind)
                   for kind in required}
        first = by_kind["first_trade"].get("date")
        last = by_kind["last_trade"].get("date")
        if not first or not last or date.fromisoformat(first) > date.fromisoformat(valid_from) or \
                date.fromisoformat(last) < date.fromisoformat(valid_to) - timedelta(days=1):
            raise ValueError("Fallback trading boundaries are not documented")
        if by_kind["adjustment"].get("method") != "split_dividend_reconciliation":
            raise ValueError("Fallback adjusted-return convention is not reconciled")
        if by_kind["corporate_actions"].get("valid_from", "9999") > valid_from or \
                by_kind["corporate_actions"].get("valid_to", "0000") < valid_to:
            raise ValueError("Fallback corporate actions do not cover the interval")
    refs = _refs(evidence)
    return dict(cik=cik, symbol=symbol, valid_from=valid_from, valid_to=valid_to,
                source_id=source_id, adjustment_basis=adjustment_basis, status=status, refs=refs)

def prepare_terminal(*, cik: str, symbol: str, event_date: str, event_type: str,
                    status: str, evidence: list[dict], cash_per_share: float | None = None,
                    exchange_ratio: float | None = None, successor_symbol: str | None = None,
                    lower_return: float | None = None, upper_return: float | None = None) -> dict:
    """Record economic treatment separately from the last quoted close."""
    if event_type not in EVENT_TYPES:
        raise ValueError("Unknown terminal event type")
    if status not in {"terminal_return_confirmed", "terminal_return_bounded", "terminal_return_unknown"}:
        raise ValueError("Unknown terminal return status")
    if status == "terminal_return_confirmed":
        cash = cash_per_share is not None and np.isfinite(cash_per_share) and cash_per_share >= 0
        stock = exchange_ratio is not None and np.isfinite(exchange_ratio) and exchange_ratio > 0 and successor_symbol
        if not (cash or stock) or (event_type == "stock_acquisition" and not stock):
            raise ValueError("Confirmed event needs economic consideration")
    if status == "terminal_return_bounded" and (lower_return is None or upper_return is None or
                                                 lower_return > upper_return):
        raise ValueError("Bounded event needs an ordered return interval")
    cik = identity.normalize_cik(cik)
    symbol = identity.normalize_symbol(symbol)
    date.fromisoformat(event_date)
    refs = _refs(evidence)
    return dict(cik=cik, symbol=symbol, event_date=event_date, event_type=event_type,
                status=status, cash_per_share=cash_per_share, exchange_ratio=exchange_ratio,
                successor_symbol=successor_symbol, lower_return=lower_return,
                upper_return=upper_return, refs=refs)
