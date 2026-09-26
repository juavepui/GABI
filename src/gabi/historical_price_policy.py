"""Accredited historical price intervals and terminal-event accounting.

The research archive and the operational Yahoo cache remain separate. This
module stores the evidence needed to use a *specific* source/symbol/CIK interval
and fails closed when an adjusted-return series cannot be established.
"""

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import identity, storage
from .historical_archive import SCHEMA as ARCHIVE_SCHEMA

YAHOO_SOURCE = "yahoo:legacy-cache"
ADJUSTED = "split_and_dividend_adjusted"
UNKNOWN = "unknown"
SCHEMA = """
CREATE TABLE IF NOT EXISTS historical_price_provenance (
 entity_id TEXT NOT NULL, cik TEXT NOT NULL, symbol TEXT NOT NULL,
 valid_from TEXT NOT NULL, valid_to TEXT NOT NULL, source_id TEXT NOT NULL,
 adjustment_basis TEXT NOT NULL, status TEXT NOT NULL, evidence_json TEXT NOT NULL,
 PRIMARY KEY(entity_id,symbol,valid_from,valid_to,source_id),
 CHECK(valid_from < valid_to),
 CHECK(status IN ('tier_a','tier_b','excluded'))
);
CREATE INDEX IF NOT EXISTS idx_historical_price_provenance_lookup
 ON historical_price_provenance(symbol,valid_from,valid_to);
CREATE TABLE IF NOT EXISTS historical_terminal_events (
 entity_id TEXT NOT NULL, symbol TEXT NOT NULL, event_date TEXT NOT NULL,
 event_type TEXT NOT NULL, status TEXT NOT NULL,
 cash_per_share REAL, exchange_ratio REAL, successor_symbol TEXT,
 lower_return REAL, upper_return REAL, evidence_json TEXT NOT NULL,
 PRIMARY KEY(entity_id,symbol,event_date),
 CHECK(status IN ('terminal_return_confirmed','terminal_return_bounded','terminal_return_unknown'))
);
"""

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


def record_series(*, cik: str, symbol: str, valid_from: str, valid_to: str,
                  source_id: str, adjustment_basis: str, status: str,
                  evidence: list[dict]) -> None:
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
    entity_id = identity.ensure_entity(cik)
    with storage.get_connection() as conn:
        conn.executescript(ARCHIVE_SCHEMA + SCHEMA)
        if status == "tier_b":
            archived = pd.read_sql_query(
                "SELECT date,adj_close FROM historical_prices WHERE source_id=? AND symbol=? "
                "AND date>=? AND date<? ORDER BY date", conn,
                params=(source_id, symbol, valid_from, valid_to)).set_index("date")
            yahoo = pd.read_sql_query(
                "SELECT date,adj_close FROM prices WHERE symbol=? AND date>=? AND date<? ORDER BY date",
                conn, params=(symbol, valid_from, valid_to)).set_index("date")
            if archived.empty:
                raise ValueError("Fallback source has no prices in the accredited interval")
            if not yahoo.empty:
                from .historical_price_audit import overlap_status
                archived.index = pd.to_datetime(archived.index)
                yahoo.index = pd.to_datetime(yahoo.index)
                overlap, _count, _p99 = overlap_status(yahoo, archived)
                if overlap in {"divergent_overlap", "divergent_event"}:
                    raise ValueError("Fallback adjusted returns diverge from Yahoo")
        historical_conflict = conn.execute(
            "SELECT 1 FROM historical_identity_intervals WHERE symbol=? AND cik<>? "
            "AND valid_from<? AND valid_to>? LIMIT 1",
            (symbol, cik, valid_to, valid_from)).fetchone()
        if historical_conflict:
            raise ValueError("Historical ticker interval has conflicting CIK evidence")
        conflict = conn.execute(
            "SELECT 1 FROM historical_price_provenance WHERE symbol=? AND entity_id<>? "
            "AND valid_from<? AND valid_to>? AND status!='excluded' LIMIT 1",
            (symbol, entity_id, valid_to, valid_from)).fetchone()
        if conflict:
            raise ValueError("Ticker interval belongs to another issuer")
        competing = conn.execute(
            "SELECT source_id,valid_from,valid_to FROM historical_price_provenance WHERE symbol=? AND entity_id=? "
            "AND valid_from<? AND valid_to>? AND status!='excluded' "
            "AND NOT (source_id=? AND valid_from=? AND valid_to=?)",
            (symbol, entity_id, valid_to, valid_from, source_id, valid_from, valid_to)).fetchall()
        for other_source, other_from, other_to in competing:
            # Consecutive trailing windows accredited from different sources
            # overlap. That is allowed only when both sources demonstrably
            # quote the same adjusted returns on the shared span.
            if other_source == source_id or not _sources_agree(
                    conn, symbol, source_id, other_source, max(valid_from, other_from), min(valid_to, other_to)):
                raise ValueError("Overlapping accredited series require explicit reconciliation")
        conn.execute("INSERT INTO historical_price_provenance VALUES (?,?,?,?,?,?,?,?,?) "
                     "ON CONFLICT(entity_id,symbol,valid_from,valid_to,source_id) DO UPDATE SET "
                     "adjustment_basis=excluded.adjustment_basis,status=excluded.status,"
                     "evidence_json=excluded.evidence_json",
                     (entity_id, cik, symbol, valid_from, valid_to, source_id,
                      adjustment_basis, status, refs))
        conn.commit()


def _adjusted(conn, source_id: str, symbol: str, start: str, end: str) -> pd.DataFrame:
    params: tuple[str, ...]
    if source_id == YAHOO_SOURCE:
        query, params = ("SELECT date,adj_close FROM prices WHERE symbol=? AND date>=? AND date<? ORDER BY date",
                         (symbol, start, end))
    else:
        query, params = ("SELECT date,adj_close FROM historical_prices WHERE source_id=? AND symbol=? "
                         "AND date>=? AND date<? ORDER BY date", (source_id, symbol, start, end))
    frame = pd.read_sql_query(query, conn, params=params)
    frame.index = pd.to_datetime(frame.pop("date"))
    return frame


def _sources_agree(conn, symbol: str, left: str, right: str, start: str, end: str) -> bool:
    from .historical_price_audit import overlap_status
    status, _count, _p99 = overlap_status(_adjusted(conn, left, symbol, start, end),
                                          _adjusted(conn, right, symbol, start, end))
    return status == "consistent_overlap"


def terminal_event(*, cik: str, symbol: str, start: str, end: str) -> dict | None:
    """Expose event terms for an explicit terminal-return calculation."""
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        rows = conn.execute(
            "SELECT event_date,event_type,status,cash_per_share,exchange_ratio,successor_symbol,"
            "lower_return,upper_return,evidence_json FROM historical_terminal_events "
            "WHERE entity_id=? AND symbol=? AND event_date>=? AND event_date<? ORDER BY event_date",
            (f"cik:{identity.normalize_cik(cik)}", identity.normalize_symbol(symbol), start, end)).fetchall()
    if len(rows) > 1:
        raise ValueError("Multiple terminal events require explicit review")
    if not rows:
        return None
    keys = ("event_date", "event_type", "status", "cash_per_share", "exchange_ratio",
            "successor_symbol", "lower_return", "upper_return", "evidence")
    result = dict(zip(keys, rows[0], strict=True))
    result["evidence"] = json.loads(result["evidence"])
    return result


def record_terminal(*, cik: str, symbol: str, event_date: str, event_type: str,
                    status: str, evidence: list[dict], cash_per_share: float | None = None,
                    exchange_ratio: float | None = None, successor_symbol: str | None = None,
                    lower_return: float | None = None, upper_return: float | None = None) -> None:
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
    entity_id = identity.ensure_entity(cik)
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO historical_terminal_events VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                     "ON CONFLICT(entity_id,symbol,event_date) DO UPDATE SET "
                     "event_type=excluded.event_type,status=excluded.status,"
                     "cash_per_share=excluded.cash_per_share,exchange_ratio=excluded.exchange_ratio,"
                     "successor_symbol=excluded.successor_symbol,lower_return=excluded.lower_return,"
                     "upper_return=excluded.upper_return,evidence_json=excluded.evidence_json",
                     (entity_id, symbol, event_date, event_type, status, cash_per_share,
                      exchange_ratio, successor_symbol, lower_return, upper_return, refs))
        conn.commit()


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


def price_history(*, cik: str, symbol: str, start: str, end: str,
                  sessions: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Strict attributed read. ``end`` is exclusive; no source stitching or fill."""
    cik = identity.normalize_cik(cik)
    symbol = identity.normalize_symbol(symbol)
    if date.fromisoformat(start) >= date.fromisoformat(end):
        raise ValueError("Empty price request")
    with storage.get_connection() as conn:
        conn.executescript(ARCHIVE_SCHEMA + SCHEMA)
        rows = conn.execute(
            "SELECT source_id,adjustment_basis,status,evidence_json,valid_from,valid_to "
            "FROM historical_price_provenance WHERE entity_id=? AND symbol=? "
            "AND valid_from<=? AND valid_to>=? AND status IN ('tier_a','tier_b')",
            (f"cik:{cik}", symbol, start, end)).fetchall()
        # Overlapping intervals were only accredited when their sources agree;
        # read the operational Yahoo cache first, then archives by source id.
        rows = sorted(rows, key=lambda row: (row[0] != YAHOO_SOURCE, row[0]))
        if not rows or rows[0][1] != ADJUSTED:
            raise ValueError("No unique accredited adjusted price interval")
        source_id, basis, status, refs, valid_from, valid_to = rows[0]
        event = conn.execute(
            "SELECT event_date,status FROM historical_terminal_events "
            "WHERE entity_id=? AND symbol=? AND event_date>=? AND event_date<?",
            (f"cik:{cik}", symbol, start, end)).fetchall()
        if event:
            raise ValueError("Interval crosses a terminal event; calculate its return explicitly")
        if source_id == YAHOO_SOURCE:
            query = "SELECT date,open,high,low,close,volume,adj_close FROM prices WHERE symbol=? AND date>=? AND date<? ORDER BY date"
            params: tuple[str, ...] = (symbol, start, end)
        else:
            query = ("SELECT date,open,high,low,close,volume,adj_close FROM historical_prices "
                     "WHERE source_id=? AND symbol=? AND date>=? AND date<? ORDER BY date")
            params = (source_id, symbol, start, end)
        frame = pd.read_sql_query(query, conn, params=params)
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date")
    if frame.empty or frame["adj_close"].isna().any() or frame["adj_close"].le(0).any():
        raise ValueError("Missing or invalid adjusted price")
    if sessions is not None and not sessions.difference(frame.index).empty:
        raise ValueError("Missing exchange session; no price forward-fill")
    frame.attrs.update(entity_id=f"cik:{cik}", cik=cik, symbol=symbol,
                       valid_from=valid_from, valid_to=valid_to, source_id=source_id,
                       adjustment_basis=basis, price_source_status=status,
                       evidence=json.loads(refs))
    return frame
