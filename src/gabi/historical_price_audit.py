"""Offline, conservative price-source audit for the 2010-2015 index members.

Run ``python -m gabi.historical_price_audit``. This never copies an archived
price into the operational cache. A series is attributed to a CIK only when
SEC evidence covers its trading life and price level; a return overlap tests
adjustments, not ownership, and never fixes a delisting return.
"""
import argparse
import hashlib
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from . import config, historical_membership, storage
from . import historical_issuer_evidence as issuer_evidence
from .historical_archive import ACCREDITED_IDENTITY_TIERS, IDENTITY_INTERVAL_SOURCE
from .historical_data_audit import connect_readonly
from .historical_identity_audit import QUARTERS
from .historical_price_policy import ADJUSTED, YAHOO_SOURCE, qualify_fallback, record_series, record_terminal
from .historical_price_policy import SCHEMA as PROVENANCE_SCHEMA
from .historical_ticker_corrections import identity_nominations
from .historical_tiingo import SOURCE_ID as TIINGO_SOURCE
from .historical_wiki import SOURCE_ID as WIKI_SOURCE

PRICE_SOURCE = json.loads((Path(__file__).with_name("resources") /
                           "historical_sources_1996_2015.json").read_text(encoding="utf-8"))["price_source_id"]
OUTPUT = config.BASE_DIR / "docs" / "historical-prices-2010-2015.csv"
SUMMARY = config.BASE_DIR / "docs" / "historical-prices-2010-2015.json"
QUARTERLY_OUTPUT = config.BASE_DIR / "docs" / "historical-prices-quarterly-2010-2015.csv"
QUARTERLY_SUMMARY = config.BASE_DIR / "docs" / "historical-prices-quarterly-2010-2015.json"
PRODUCER = "historical_price_audit:v2"
MIN_OVERLAP = 60
MAX_P99_RETURN_DIFFERENCE = 0.005
# One day on which the sources disagree by more than this is an unreconciled
# corporate action (typically a spin-off one source did not adjust); p99 alone
# would hide it inside a year of matching returns.
MAX_EVENT_RETURN_DIFFERENCE = 0.05
# A one-day adjusted move this large in an archive-only window is treated as an
# unexplained distribution unless another source corroborates it.
MAX_UNCORROBORATED_ARCHIVE_RETURN = 0.25
# Further archived sources tried, in order, when neither Yahoo nor FINSABER qualifies.
EXTRA_SOURCES = {"tiingo": TIINGO_SOURCE, "wiki": WIKI_SOURCE}
ACCEPTED_ADJUSTMENTS = {"dividends_reconciled", "no_dividends_consistent"}


def _series(conn: sqlite3.Connection, symbol: str, start: str, end: str,
            *, archive: bool, source_id: str = PRICE_SOURCE) -> pd.DataFrame:
    if archive:
        query = ("SELECT date,close,adj_close FROM historical_prices "
                 "WHERE source_id=? AND symbol=? AND date>=? AND date<=? ORDER BY date")
        args: tuple[str, ...] = (source_id, symbol, start, end)
    else:
        query = ("SELECT date,close,adj_close FROM prices "
                 "WHERE symbol=? AND date>=? AND date<=? ORDER BY date")
        args = (symbol, start, end)
    frame = pd.read_sql_query(query, conn, params=args)
    if frame.empty:
        return pd.DataFrame(columns=["close", "adj_close"],
                            index=pd.DatetimeIndex([], name="date"))
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.set_index("date")


def assess_series(frame: pd.DataFrame, sessions: pd.DatetimeIndex) -> dict:
    """Count real exchange sessions with both nominal and adjusted closes."""
    if frame.empty:
        return {"sessions": 0, "first": None, "last": None, "complete": False,
                "complete_from_first": False}
    valid = frame.reindex(sessions)[["close", "adj_close"]].apply(pd.to_numeric, errors="coerce")
    present = valid.notna().all(axis=1) & np.isfinite(valid).all(axis=1) & valid.gt(0).all(axis=1)
    observed = sessions[present]
    tail = present[present.idxmax():] if present.any() else present
    return {"sessions": len(observed),
            "first": observed[0].date().isoformat() if len(observed) else None,
            "last": observed[-1].date().isoformat() if len(observed) else None,
            "complete": len(observed) == len(sessions),
            # Every session from the first observation to the rebalance date.
            "complete_from_first": bool(len(observed)) and bool(tail.all())}


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


def same_traded_prices(yahoo: pd.DataFrame, archive: pd.DataFrame, sessions: pd.DatetimeIndex) -> bool:
    """Unadjusted close returns agree on nearly every common day.

    Yahoo closes are split-adjusted and archive closes as traded, so returns
    (not levels) are compared; split days are the only allowed differences.
    """
    common = yahoo[["close"]].join(archive[["close"]], how="inner", lsuffix="_y", rsuffix="_a").astype(float)
    returns = _adjacent_returns(common[(common > 0).all(axis=1)], sessions)
    if len(returns) < MIN_OVERLAP:
        return False
    return bool(((returns["close_y"] - returns["close_a"]).abs() < 1e-3).mean() >= 0.98)


def archive_adjustment(window: pd.DataFrame, facts: dict[str, list[dict]], start: str, end: str,
                       yahoo: pd.DataFrame, sessions: pd.DatetimeIndex) -> tuple[str, list[dict]]:
    """Reconcile an archive window's implied splits and cash events with SEC."""
    events = issuer_evidence.implied_events(window)
    if not events.empty and events.kind.eq("unexplained").any():
        return "unexplained_adjustment", [{"kind": "adjustment", "dates": [
            day.date().isoformat() for day in events[events.kind == "unexplained"].date]}]
    splits_ok, split_refs = issuer_evidence.verify_splits(events, facts)
    if not splits_ok:
        return "split_unverified", split_refs
    returns = _adjacent_returns(window[["adj_close"]].astype(float), sessions)["adj_close"]
    jumps = returns[returns.abs() > MAX_UNCORROBORATED_ARCHIVE_RETURN]
    if not jumps.empty:
        confirmed = yahoo["adj_close"].astype(float).pct_change(fill_method=None).reindex(jumps.index)
        if confirmed.isna().any() or (confirmed - jumps).abs().gt(MAX_EVENT_RETURN_DIFFERENCE).any():
            return "unexplained_jump", [{"kind": "adjustment", "dates": [
                day.date().isoformat() for day in jumps.index]}]
    status, detail = issuer_evidence.reconcile_dividends(events, facts, start, end)
    refs = [{"kind": "adjustment", "method": "split_dividend_reconciliation", "status": status,
             "source_url": issuer_evidence.FRAME_URL.format(
                 taxonomy="us-gaap", tag="CommonStockDividendsPerShareDeclared",
                 unit="USD-per-shares", period="CY{year}Q{quarter}"),
             **detail}, *split_refs]
    return status, refs


def choose_source(identity_tier: str | None, recycled: bool, yahoo: dict,
                  archive: dict, overlap: str, *, issuer: dict | None = None,
                  fallback_proof: dict | None = None, archive_name: str = "finsaber") -> tuple[str | None, str]:
    """Select one full window with identity, SEC listing life and series identity.

    ``issuer`` holds the per-source SEC checks: ``listing`` (failure reason or
    None), ``yahoo_level``/``archive_level`` (``passed``, or ``fingerprint``
    when no level check exists but cash events match the CIK's SEC dividends)
    and ``yahoo_adjustment``/``archive_adjustment``. Yahoo is preferred, but a
    disagreeing archive blocks it unless SEC dividends show Yahoo is right and
    the archive is not (the archive then lacks dividend adjustments).
    """
    if recycled:
        return None, "multiple_ciks_in_window"
    if not identity_tier:
        return None, "identity_unresolved"
    if not yahoo["complete"] and not archive["complete"]:
        return None, "incomplete_prices"
    if issuer is None:
        return None, "issuer_evidence_missing"
    if issuer["listing"]:
        return None, issuer["listing"]
    identified = {"passed", "fingerprint"}
    if overlap in {"divergent_overlap", "divergent_event"}:
        # Only when both sources quote the same traded prices (the difference is
        # purely in adjustments) can SEC dividends decide which one is right.
        resolved = (yahoo["complete"] and issuer["yahoo_level"] in identified and
                    issuer.get("same_traded_prices", False) and
                    issuer.get("yahoo_adjustment") in ACCEPTED_ADJUSTMENTS and
                    issuer.get("archive_adjustment") not in ACCEPTED_ADJUSTMENTS | {"not_assessed"})
        return ("yahoo", "complete_divergence_resolved_by_sec") if resolved else (None, f"sources_{overlap}")
    if yahoo["complete"] and issuer["yahoo_level"] in identified:
        return "yahoo", "complete"
    if archive["complete"]:
        if issuer["archive_level"] not in identified:
            return None, f"price_level_{issuer['archive_level']}"
        if issuer["archive_adjustment"] not in ACCEPTED_ADJUSTMENTS:
            return None, f"archive_{issuer['archive_adjustment']}"
        accepted, reason = qualify_fallback(identity_tier=identity_tier, recycled=recycled,
                                            archive=archive, overlap=overlap, proof=fallback_proof)
        return (archive_name if accepted else None), reason
    return None, f"price_level_{issuer['yahoo_level']}"


def series_identity(checks: list[dict], adjustment: str, refs: list[dict]) -> str:
    """``passed`` level check, else a dividend ``fingerprint``, else the level status."""
    status = issuer_evidence.level_status(checks)
    if status == "missing" and adjustment == "dividends_reconciled" and refs and refs[0].get("fingerprint"):
        return "fingerprint"
    return status


def _nominated_price_symbol(label: str, cik: str | None, as_of: str, source: str) -> str:
    for row in identity_nominations():
        if (row["label"] == label and row["cik"] == cik and
                row["valid_from"] <= as_of < row["valid_to"] and source in row.get("price_symbols", {})):
            return row["price_symbols"][source]
    return label


def _as_traded_yahoo(yahoo: pd.DataFrame, splits: pd.DataFrame) -> pd.Series:
    """Yahoo stores closes on today's split basis; known later splits undo it.
    Unknown splits leave the close too low, so the level check fails closed."""
    close = yahoo["close"].astype(float)
    factor = pd.Series(1.0, index=close.index)
    for row in splits.itertuples(index=False):
        factor[factor.index < pd.Timestamp(row.date)] *= float(row.ratio)
    return close * factor


def _split_ratios(frame: pd.DataFrame) -> pd.Series:
    """Split ratios by ex-date implied by an as-traded archive series."""
    if frame.empty:
        return pd.Series(dtype=float)
    events = issuer_evidence.implied_events(frame)
    splits = events[events.kind == "split"] if not events.empty else events
    return pd.Series(splits.ratio.astype(float).to_numpy(), index=pd.DatetimeIndex(splits.date))         if not splits.empty else pd.Series(dtype=float)


def _proof(listing_refs: list[dict], adjustment_refs: list[dict], start: str, end: str) -> dict:
    first = next(ref for ref in listing_refs if ref["kind"] == "first_trade")
    last = next(ref for ref in listing_refs if ref["kind"] == "last_trade")
    return {"first_trade": first["date"], "last_trade": last["date"],
            "boundary_evidence": [first, last], "adjustment_basis": ADJUSTED,
            "adjustment_evidence": adjustment_refs,
            "corporate_action_evidence": [{"kind": "corporate_actions", "valid_from": start,
                                           "valid_to": end, "source_url": last["source_url"]}]}


def _short_history(member: dict, sessions: pd.DatetimeIndex, yahoo: pd.DataFrame, archive: pd.DataFrame,
                   yc: dict, ac: dict, life: dict | None, facts: dict, splits: pd.DataFrame
                   ) -> tuple[str | None, str, dict]:
    """Accredit a series that starts at a SEC-registered listing inside the window."""
    for name, frame, stats in (("yahoo", yahoo, yc), ("finsaber", archive, ac)):
        if not stats["complete_from_first"] or stats["first"] == sessions[0].date().isoformat():
            continue
        start_ref = issuer_evidence.listing_start(life, stats["first"])
        if start_ref is None:
            continue
        end = sessions[-1].date().isoformat()
        reason, refs = issuer_evidence.listing_checks(
            {**life, "first_periodic": stats["first"]} if life else None, stats["first"], end)
        if reason:
            return None, reason, {}
        close = _as_traded_yahoo(frame, splits) if name == "yahoo" else frame["close"].astype(float)
        checks = issuer_evidence.price_level_checks(facts, close, stats["first"], end)
        if issuer_evidence.level_status(checks) == "failed":
            return None, "price_level_failed", {}
        detail = {"listing_refs": [start_ref, *refs[1:]], "level_checks": checks}
        if name == "finsaber":
            status, adj_refs = archive_adjustment(frame.loc[stats["first"]:], facts, stats["first"], end,
                                                  yahoo, sessions[sessions >= pd.Timestamp(stats["first"])])
            if status not in ACCEPTED_ADJUSTMENTS:
                return None, f"archive_{status}", {}
            detail["adjustment_refs"] = adj_refs
        return name, "short_history", detail
    return None, "incomplete_prices", {}


def _next_rebalance(as_of: str) -> str:
    index = QUARTERS.index(as_of) if as_of in QUARTERS else -1
    if 0 <= index < len(QUARTERS) - 1:
        return QUARTERS[index + 1]
    day = date.fromisoformat(as_of)
    return (pd.Timestamp(day) + pd.offsets.QuarterEnd(1)).date().isoformat()


def audit(db: Path, *, dates: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    calendar = xcals.get_calendar("XNYS", start="2008-01-01", end="2016-12-31")
    rows = []
    dates = dates or [f"{year}-12-31" for year in range(2010, 2016)]
    series_cache: dict[tuple[str, bool | str], pd.DataFrame] = {}
    with connect_readonly(db) as conn:
        has_events = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='historical_terminal_events'").fetchone())
        has_provenance = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='historical_price_provenance'").fetchone())
        all_splits = pd.read_sql_query("SELECT symbol,date,ratio FROM splits", conn)
        for as_of in dates:
            year = int(as_of[:4])
            membership = historical_membership.constituents_as_of(
                as_of, source_id=historical_membership.REFERENCE_SOURCE, compare_reference=False)
            sessions = calendar.sessions[calendar.sessions <= pd.Timestamp(as_of)][-253:]
            start, end = sessions[0].date().isoformat(), sessions[-1].date().isoformat()
            horizon = _next_rebalance(as_of)
            for member in [*membership["members"], {"symbol": "SPY", "identity_tier": "benchmark",
                                                      "cik": None}]:
                label = member["symbol"]
                cik = member.get("cik")
                symbols = {"yahoo": _nominated_price_symbol(label, cik, as_of, "yahoo"),
                           "finsaber": _nominated_price_symbol(label, cik, as_of, "finsaber"),
                           **{name: _nominated_price_symbol(label, cik, as_of, name) for name in EXTRA_SOURCES}}
                for name, symbol in list(symbols.items())[:2]:
                    key = (symbol, name == "finsaber")
                    if key not in series_cache:
                        series_cache[key] = _series(conn, symbol, "2008-01-01", "2015-12-31",
                                                    archive=name == "finsaber")
                yahoo = series_cache[(symbols["yahoo"], False)].loc[start:end]
                archive = series_cache[(symbols["finsaber"], True)].loc[start:end] if label != "SPY" else \
                    pd.DataFrame(columns=["close", "adj_close"])
                yc, ac = assess_series(yahoo, sessions), assess_series(archive, sessions)
                if label == "SPY":
                    rows.append({"year": year, "as_of": as_of, "symbol": label, "expected_sessions": len(sessions),
                                 "yahoo_sessions": yc["sessions"], "selected_source": "yahoo" if yc["complete"] else None,
                                 "coverage_status": "complete" if yc["complete"] else "incomplete_prices",
                                 "price_attribution": "benchmark", "price_source_status": "benchmark"})
                    continue
                overlap, count, p99 = overlap_status(yahoo, archive, sessions)
                conflicts = conn.execute(
                    "SELECT COUNT(DISTINCT cik) FROM historical_identity_intervals "
                    "WHERE source_id=? AND symbol=? AND valid_from<=? AND valid_to>?",
                    (IDENTITY_INTERVAL_SOURCE, label, end, start)).fetchone()[0]
                issuer = None
                life = issuer_evidence.listing_life(cik) if cik else None
                facts = issuer_evidence.issuer_facts(cik) if cik else {}
                listing_refs: list[dict] = []
                yahoo_checks: list[dict] = []
                archive_checks: list[dict] = []
                adjustment_refs: list[dict] = []
                yahoo_adjustment_refs: list[dict] = []
                if cik:
                    reason, listing_refs = issuer_evidence.listing_checks(life, start, end)
                    until = issuer_evidence.level_horizon(life, end)
                    full_yahoo = series_cache[(symbols["yahoo"], False)].loc[start:until]
                    full_archive = series_cache[(symbols["finsaber"], True)].loc[start:until]
                    splits = all_splits[all_splits.symbol == symbols["yahoo"]]
                    yahoo_close = _as_traded_yahoo(full_yahoo, splits)
                    if overlap == "consistent_overlap":
                        # Same security on both sources: the archive close is as traded.
                        yahoo_close = full_archive["close"].astype(float).reindex(full_yahoo.index).fillna(yahoo_close)
                    archive_splits = _split_ratios(full_archive)
                    yahoo_splits = archive_splits if overlap == "consistent_overlap" else                         pd.Series(splits.ratio.astype(float).to_numpy(), index=pd.to_datetime(splits.date))
                    yahoo_checks = issuer_evidence.price_level_checks(
                        facts, yahoo_close, start, end, until=until, splits=yahoo_splits) if yc["complete"] else []
                    archive_checks = issuer_evidence.price_level_checks(
                        facts, full_archive["close"].astype(float), start, end, until=until,
                        splits=archive_splits) if ac["complete"] else []
                    adjustment = yahoo_adjustment = "not_assessed"
                    if ac["complete"] and (not yc["complete"] or overlap != "consistent_overlap"):
                        adjustment, adjustment_refs = archive_adjustment(archive, facts, start, end, yahoo, sessions)
                    if yc["complete"] and (overlap != "consistent_overlap" or
                                           issuer_evidence.level_status(yahoo_checks) == "missing"):
                        empty = pd.DataFrame(columns=["close", "adj_close"])
                        yahoo_adjustment, yahoo_adjustment_refs = archive_adjustment(
                            yahoo, facts, start, end, empty, sessions)
                    issuer = {"listing": reason,
                              "yahoo_level": series_identity(yahoo_checks, yahoo_adjustment, yahoo_adjustment_refs),
                              "archive_level": series_identity(archive_checks, adjustment, adjustment_refs),
                              "archive_adjustment": adjustment, "yahoo_adjustment": yahoo_adjustment,
                              "same_traded_prices": same_traded_prices(yahoo, archive, sessions)}
                proof = _proof(listing_refs, adjustment_refs, start, end) if listing_refs and \
                    issuer and not issuer["listing"] else None
                source, status = choose_source(member.get("identity_tier"), conflicts > 1, yc, ac, overlap,
                                               issuer=issuer, fallback_proof=proof)
                detail: dict = {}
                if source is None and status in {"incomplete_prices", "listing_starts_after_window"} and \
                        cik and member.get("identity_tier") and conflicts <= 1 and \
                        overlap not in {"divergent_overlap", "divergent_event"}:
                    splits = all_splits[all_splits.symbol == symbols["yahoo"]]
                    short_source, short_status, detail = _short_history(
                        member, sessions, yahoo, archive, yc, ac, life, facts, splits)
                    if short_source:
                        source, status = short_source, short_status
                    elif status == "incomplete_prices":
                        status = short_status
                extra_row: dict = {}
                extra_stats: dict[str, dict] = {}
                for name, extra_source in EXTRA_SOURCES.items():
                    extra_key = (symbols[name], name)
                    if extra_key not in series_cache:
                        series_cache[extra_key] = _series(conn, symbols[name], "2008-01-01", "2015-12-31",
                                                          archive=True, source_id=extra_source)
                    extra = series_cache[extra_key].loc[start:end]
                    stats = assess_series(extra, sessions)
                    extra_stats[name] = stats
                    extra_row.update({f"{name}_sessions": stats["sessions"], f"{name}_first": stats["first"],
                                      f"{name}_last": stats["last"], f"{name}_level": None,
                                      f"{name}_adjustment": None})
                    if source is not None or not stats["complete"] or not cik or not issuer or \
                            issuer["listing"] or not member.get("identity_tier") or conflicts > 1:
                        continue
                    # Extra archived source, same controls as FINSABER. An overlap
                    # only counts against it when that other series is identified.
                    identified = {"passed", "fingerprint"}
                    e_overlap = overlap_status(yahoo, extra, sessions)[0] \
                        if issuer["yahoo_level"] in identified else "insufficient_overlap"
                    if e_overlap == "insufficient_overlap" and issuer["archive_level"] in identified and \
                            issuer["archive_adjustment"] in ACCEPTED_ADJUSTMENTS:
                        e_overlap = overlap_status(archive, extra, sessions)[0]
                    until = issuer_evidence.level_horizon(life, end)
                    full_extra = series_cache[extra_key].loc[start:until]
                    e_checks = issuer_evidence.price_level_checks(
                        facts, full_extra["close"].astype(float), start, end, until=until,
                        splits=_split_ratios(full_extra))
                    e_adjustment, e_refs = archive_adjustment(extra, facts, start, end, yahoo, sessions)
                    e_issuer = {**issuer, "archive_level": series_identity(e_checks, e_adjustment, e_refs),
                                "archive_adjustment": e_adjustment}
                    e_source, e_status = choose_source(
                        member.get("identity_tier"), False, {"complete": False}, stats, e_overlap, issuer=e_issuer,
                        fallback_proof=_proof(listing_refs, e_refs, start, end), archive_name=name)
                    extra_row.update({f"{name}_level": e_issuer["archive_level"], f"{name}_adjustment": e_adjustment})
                    if e_source:
                        source, status = e_source, f"{name}_{e_status}"
                        archive_checks, adjustment_refs = e_checks, e_refs
                        detail = {}
                source_id = {"yahoo": YAHOO_SOURCE, "finsaber": PRICE_SOURCE, **EXTRA_SOURCES}.get(source or "")
                source_symbol = symbols[source] if source else None
                source_stats = {"yahoo": yc, "finsaber": ac, **extra_stats}.get(source or "", ac)
                provenance = conn.execute(
                    "SELECT source_id,adjustment_basis,status FROM historical_price_provenance "
                    "WHERE entity_id=? AND symbol=? AND source_id=? AND valid_from<=? AND valid_to>=? "
                    "AND status IN ('tier_a','tier_b')",
                    (member.get("entity_id"), source_symbol, source_id,
                     source_stats["first"] or start,
                     (date.fromisoformat(end) + timedelta(days=1)).isoformat())
                ).fetchall() if has_provenance and source_id else []
                accredited = len(provenance) == 1 and provenance[0][1] == ADJUSTED
                delisting = (life or {}).get("delisting")
                forward_exit = bool(delisting and as_of < delisting["filed"] <= horizon)
                events = conn.execute(
                    "SELECT status FROM historical_terminal_events WHERE entity_id=? "
                    "AND event_date>? AND event_date<=?",
                    (member.get("entity_id"), as_of, horizon)).fetchall() if has_events and cik else []
                if not forward_exit:
                    forward = "continues_to_next_rebalance" if cik and life else "unknown"
                else:
                    forward = events[0][0] if len(events) == 1 else "terminal_event_missing"
                sic_row = conn.execute(
                    "SELECT sic FROM sec_bulk_submissions WHERE cik=? AND filed_date<=? "
                    "AND sic IS NOT NULL AND sic!='' ORDER BY filed_date DESC LIMIT 1",
                    (cik, as_of)).fetchone() if cik else None
                floats = [row for row in facts.get("public_float", []) if row["end"] <= as_of and row["val"]]
                next_exit = bool(member.get("end_reason") == "exit" and
                                 member.get("valid_to", "9999-12-31") <=
                                 (date.fromisoformat(as_of) + timedelta(days=365)).isoformat())
                level_checks = detail.get("level_checks", yahoo_checks if source == "yahoo" else archive_checks)
                rows.append({"year": year, "as_of": as_of, "symbol": label, "cik": cik,
                             "entity_id": member.get("entity_id"),
                             "identity_tier": member.get("identity_tier"), "expected_sessions": len(sessions),
                             "yahoo_symbol": symbols["yahoo"], "finsaber_symbol": symbols["finsaber"],
                             "yahoo_sessions": yc["sessions"], "yahoo_first": yc["first"], "yahoo_last": yc["last"],
                             "finsaber_sessions": ac["sessions"], "finsaber_first": ac["first"],
                             "finsaber_last": ac["last"], "overlap_returns": count,
                             "overlap_status": overlap, "overlap_p99": p99,
                             "known_cik_conflict": conflicts > 1,
                             "sec_first_periodic": (life or {}).get("first_periodic"),
                             "sec_delisting": delisting["filed"] if delisting else None,
                             "listing_check": issuer["listing"] if issuer else None,
                             "yahoo_level": issuer["yahoo_level"] if issuer else None,
                             "finsaber_level": issuer["archive_level"] if issuer else None,
                             "finsaber_adjustment": issuer["archive_adjustment"] if issuer else None,
                             "yahoo_adjustment": issuer["yahoo_adjustment"] if issuer else None,
                             **extra_row,
                             "level_ratio": json.dumps([round(check["ratio"], 4) for check in level_checks]),
                             "selected_source": source, "source_symbol": source_symbol,
                             "coverage_status": status,
                             "history": "short_history" if status == "short_history" else
                             "full_window" if source else None,
                             "price_attribution": "accredited_entity_interval" if accredited
                             else "legacy_symbol_unattributed",
                             "price_source_status": provenance[0][2] if accredited else
                             "candidate_only" if source else "excluded",
                             "forward_status": forward,
                             "identity_valid_from": member.get("valid_from"),
                             "identity_valid_to": member.get("valid_to"),
                             "membership_end_reason": member.get("end_reason"),
                             "sic": sic_row[0] if sic_row else None,
                             "public_float_usd": floats[-1]["val"] if floats else None,
                             "membership_exit_next_365d": next_exit,
                             "evidence_refs": {"listing": detail.get("listing_refs", listing_refs),
                                           "level": level_checks,
                                           "adjustment": detail.get("adjustment_refs", yahoo_adjustment_refs
                                                                    if source == "yahoo" else adjustment_refs)}})
    result = pd.DataFrame(rows)
    return result, summarize(result, db)


def summarize(result: pd.DataFrame, db: Path) -> dict:
    summary: dict = {"database": db.name, "price_source_id": PRICE_SOURCE,
                     "session_definition": "last 253 XNYS sessions through each rebalance date",
                     "fallback_rule": "SEC listing life, SEC public-float price level and split/dividend "
                     f"reconciliation; any Yahoo overlap needs >= {MIN_OVERLAP} returns, p99 difference <= "
                     f"{MAX_P99_RETURN_DIFFERENCE} and no day above {MAX_EVENT_RETURN_DIFFERENCE}",
                     "price_attribution": "entity intervals stored separately from legacy prices",
                     "years": []}
    members = result[result.symbol != "SPY"].copy()
    members["usable"] = members.price_attribution.eq("accredited_entity_interval")
    members["usable_full"] = members.usable & members.history.eq("full_window")
    for year, group in members.groupby("year"):
        summary["years"].append({"year": int(year), "members": len(group),
                                 "identity_accredited": int(group.cik.notna().sum()),
                                 "yahoo_complete": int(group.yahoo_sessions.eq(group.expected_sessions).sum()),
                                 "finsaber_complete": int(group.finsaber_sessions.eq(group.expected_sessions).sum()),
                                 "tier_a": int((group.usable & group.selected_source.eq("yahoo")).sum()),
                                 "tier_b": int((group.usable & group.selected_source.isin(["finsaber", *EXTRA_SOURCES])).sum()),
                                 "tier_b_by_source": {name: int((group.usable & group.selected_source.eq(name)).sum())
                                                      for name in ("finsaber", *EXTRA_SOURCES)},
                                 "usable_full_window": int(group.usable_full.sum()),
                                 "usable_short_history": int((group.usable & ~group.usable_full).sum()),
                                 "excluded": int((~group.usable).sum()),
                                 "reasons": group[~group.usable].coverage_status.value_counts().to_dict()})
    summary["rebalances"] = [{"as_of": as_of, "members": len(group),
                               "identity_accredited": int(group.cik.notna().sum()),
                               "usable_full_window": int(group.usable_full.sum()),
                               "usable_including_short_history": int(group.usable.sum()),
                               "usable_pct": round(100 * group.usable.mean(), 2),
                               "usable_full_window_pct": round(100 * group.usable_full.mean(), 2),
                               "forward": group.forward_status.value_counts().to_dict(),
                               "excluded_reasons": group[~group.usable].coverage_status.value_counts().to_dict()}
                              for as_of, group in members.groupby("as_of")]
    summary["spy_complete_all_years"] = bool(result[result.symbol == "SPY"].coverage_status.eq("complete").all())
    members["sic_2digit"] = members.sic.fillna("unknown").astype(str).str[:2]
    members["float_quintile"] = members.groupby("as_of").public_float_usd.transform(
        lambda values: pd.qcut(values.rank(method="first"), 5, labels=False) + 1 if values.notna().sum() >= 5 else np.nan)
    summary["bias_diagnostics"] = {
        "sic_2digit": [{"sic_2digit": code, "observations": len(group), "usable": int(group.usable.sum())}
                       for code, group in members.groupby("sic_2digit")],
        "membership_exit_next_365d": [{"exit_next_year": bool(flag), "observations": len(group),
                                       "usable": int(group.usable.sum())}
                                      for flag, group in members.groupby("membership_exit_next_365d")],
        "public_float_quintile": [{"quintile": int(q), "observations": len(group), "usable": int(group.usable.sum())}
                                  for q, group in members.dropna(subset=["float_quintile"]).groupby("float_quintile")],
        "public_float_missing": {"observations": int(members.public_float_usd.isna().sum()),
                                 "usable": int(members[members.public_float_usd.isna()].usable.sum())},
        "note": "SIC is an issuer-level proxy, not historical GICS; public float (SEC dei, latest before the "
                "rebalance) is a size proxy; repeated quarterly members are not independent"}
    return summary


def promote(db: Path, frame: pd.DataFrame) -> dict:
    """Attribute accepted windows to CIK intervals without touching legacy rows.

    Overlapping quarterly windows for the same security and source are merged
    so a strict read has one unambiguous interval. Rows produced by earlier
    runs of this audit are replaced, so a series that no longer qualifies (for
    example a recycled Yahoo symbol) loses its attribution. Reruns are idempotent.
    """
    if db != config.DB_PATH:
        raise ValueError("Promotion only supports the configured local database")
    candidates = frame[(frame.symbol != "SPY") & frame.selected_source.notna() & frame.cik.notna()]
    intervals: list[dict] = []
    ordered = candidates.assign(first=candidates.apply(lambda row: row[f"{row.selected_source}_first"], axis=1),
                                last=candidates.apply(lambda row: row[f"{row.selected_source}_last"], axis=1))
    for (symbol, cik, source), group in ordered.groupby(["source_symbol", "cik", "selected_source"]):
        for row in group.sort_values("first").itertuples(index=False):
            end = (date.fromisoformat(row.last) + timedelta(days=1)).isoformat()
            current = intervals[-1] if intervals else None
            if current and (current["symbol"], current["cik"], current["source"]) == (symbol, cik, source) \
                    and row.first <= current["end"]:
                current["end"] = max(end, current["end"])
                current["rows"].append(row)
            else:
                intervals.append({"symbol": symbol, "cik": cik, "source": source, "start": row.first,
                                  "end": end, "rows": [row]})
    with connect_readonly(db) as conn:
        identity_rows = conn.execute(
            "SELECT symbol,cik,valid_from,valid_to,status,source_refs_json FROM historical_identity_intervals "
            "WHERE source_id=?", (IDENTITY_INTERVAL_SOURCE,)).fetchall()
    with storage.get_connection() as conn:
        conn.executescript(PROVENANCE_SCHEMA)
        removed = conn.execute(
            "DELETE FROM historical_price_provenance WHERE evidence_json LIKE ? OR evidence_json LIKE ?",
            (f'%"producer": "{PRODUCER}"%', '%legacy Yahoo cache; original per-row download metadata unavailable%')
        ).rowcount
        conn.commit()
    accepted = {"tier_a": 0, "tier_b": 0}
    skipped: dict[str, int] = {}
    for item in intervals:
        symbol, cik, label_rows = item["symbol"], item["cik"], item["rows"]
        refs: list[dict] = []
        for row in label_rows:
            for label, icik, valid_from, valid_to, status, source_refs in identity_rows:
                if label == row.symbol and icik == cik and valid_from <= row.as_of < valid_to and \
                        status in ACCREDITED_IDENTITY_TIERS:
                    refs.extend({**ref, "kind": "identity", "identity_tier": status, "index_label": label}
                                for ref in json.loads(source_refs)[:3] if ref.get("source_url"))
            refs.extend(row.evidence_refs["listing"] + row.evidence_refs["adjustment"])
            refs.extend({**check, "kind": "price_level"} for check in row.evidence_refs["level"])
        if not any(ref["kind"] == "identity" for ref in refs):
            skipped["missing_sec_identity_reference"] = skipped.get("missing_sec_identity_reference", 0) + 1
            continue
        table = "prices" if item["source"] == "yahoo" else "historical_prices"
        source_id = {"yahoo": YAHOO_SOURCE, "finsaber": PRICE_SOURCE, **EXTRA_SOURCES}[item["source"]]
        with connect_readonly(db) as conn:
            query = (f"SELECT date,close,adj_close FROM {table} WHERE symbol=? AND date>=? AND date<? "
                     + ("AND source_id=? " if table == "historical_prices" else "") + "ORDER BY date")
            params = (symbol, item["start"], item["end"]) + ((source_id,) if table == "historical_prices" else ())
            values = conn.execute(query, params).fetchall()
        digest = hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()
        refs.append({"kind": "source", "producer": PRODUCER, "local_rows_sha256": digest, "rows": len(values),
                     "source_url": {"yahoo": f"https://finance.yahoo.com/quote/{symbol}/history/",
                                    "finsaber": "https://huggingface.co/datasets/finsaber-team/FINSABER-reproduce",
                                    "tiingo": f"https://api.tiingo.com/tiingo/daily/{symbol.lower()}/prices",
                                    "wiki": "https://data.nasdaq.com/databases/WIKIP"
                                    }[item["source"]],
                     "index_labels": sorted({row.symbol for row in label_rows}),
                     "note": {"yahoo": "legacy Yahoo cache", "finsaber": "FINSABER archived snapshot",
                              "tiingo": "Tiingo free-plan snapshot",
                              "wiki": "Nasdaq Data Link WIKI Prices, frozen 2018"}[item["source"]]})
        if item["source"] != "yahoo":
            refs.append({"kind": "corporate_actions", "valid_from": item["start"], "valid_to": item["end"],
                         "source_url": next(ref["source_url"] for ref in refs if ref["kind"] == "last_trade"),
                         "basis": "SEC listing life, successions and split/dividend reconciliation per window"})
            first_dates = [ref["date"] for ref in refs if ref["kind"] == "first_trade" and ref.get("date")]
            last_dates = [ref["date"] for ref in refs if ref["kind"] == "last_trade" and ref.get("date")]
            refs = [ref for ref in refs if ref["kind"] not in {"first_trade", "last_trade"}] + [
                {**next(ref for ref in refs if ref["kind"] == "first_trade"), "date": min(first_dates)},
                {**next(ref for ref in refs if ref["kind"] == "last_trade"), "date": min(last_dates)}]
        tier = "tier_a" if item["source"] == "yahoo" else "tier_b"
        try:
            record_series(cik=cik, symbol=symbol, valid_from=item["start"], valid_to=item["end"],
                          source_id=source_id, adjustment_basis=ADJUSTED, status=tier, evidence=refs)
        except ValueError as exc:
            skipped[str(exc)] = skipped.get(str(exc), 0) + 1
        else:
            accepted[tier] += 1
    return {"removed_previous": removed, "intervals_promoted": accepted, "skipped": skipped}


def record_terminal_events(frame: pd.DataFrame) -> dict:
    """Record every member delisted before the next rebalance as an explicit event.

    The completion 8-K around the SEC delisting supplies the consideration;
    only a single unconditional cash amount is ``terminal_return_confirmed``.
    Stock, mixed, election, bankruptcy or unreadable cases stay unknown and are
    excluded from a strict backtest instead of using the last traded price.
    """
    members = frame[(frame.symbol != "SPY") & frame.cik.notna() & frame.sec_delisting.notna()]
    exits = members[members.apply(lambda row: row.as_of < row.sec_delisting <= _next_rebalance(row.as_of), axis=1)]
    counts: dict[str, int] = {}
    for (label, cik), _group in exits.groupby(["symbol", "cik"]):
        life = issuer_evidence.listing_life(cik)
        if life is None or life["delisting"] is None:
            continue
        delisting = life["delisting"]
        evidence = [{"kind": "delisting", "source_url": life["source_url"], **delisting}]
        terms = {"cash": [], "stock": [], "election": False, "bankruptcy": False, "quotes": []}
        items: set[str] = set()
        event_date = delisting["filed"]
        for report in issuer_evidence.completion_reports(life, delisting["filed"])[:3]:
            url, path = issuer_evidence.fetch_report(cik, report)
            found = issuer_evidence.extract_terms(path.read_text(encoding="utf-8", errors="ignore"))
            report_items = set(report["items"].split(","))
            if found["cash"] or found["stock"] or "1.03" in report_items:
                terms, items, event_date = found, report_items, report["filed"]
                evidence.append({"kind": "completion_8k", "source_url": url, "filed": report["filed"],
                                 "items": report["items"], "quotes": found["quotes"]})
                break
        event_type, status, economics = issuer_evidence.classify_terminal(items, terms)
        record_terminal(cik=cik, symbol=label, event_date=event_date, event_type=event_type,
                        status=status, evidence=evidence, **economics)
        counts[f"{event_type}:{status}"] = counts.get(f"{event_type}:{status}", 0) + 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--csv", type=Path, default=OUTPUT)
    parser.add_argument("--json", type=Path, default=SUMMARY)
    parser.add_argument("--quarterly", action="store_true", help="Audit all 24 quarter ends")
    parser.add_argument("--promote", "--promote-tier-a", dest="promote", action="store_true",
                        help="Persist SEC-backed Tier A/B intervals (replaces earlier audit rows)")
    parser.add_argument("--terminal-events", action="store_true",
                        help="Record SEC-evidenced terminal events for members delisted before the next rebalance")
    args = parser.parse_args()
    frame, summary = audit(args.db, dates=QUARTERS if args.quarterly else None)
    terminal = record_terminal_events(frame) if args.terminal_events else None
    promotion = promote(args.db, frame) if args.promote else None
    if terminal is not None or promotion is not None:
        frame, summary = audit(args.db, dates=QUARTERS if args.quarterly else None)
    if promotion is not None:
        summary["promotion"] = promotion
    if terminal is not None:
        summary["terminal_events"] = terminal
    if args.quarterly and args.csv == OUTPUT:
        args.csv = QUARTERLY_OUTPUT
    if args.quarterly and args.json == SUMMARY:
        args.json = QUARTERLY_SUMMARY
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    frame.drop(columns=["evidence_refs"], errors="ignore").to_csv(args.csv, index=False)
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("years", "promotion", "terminal_events") if key in summary},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
