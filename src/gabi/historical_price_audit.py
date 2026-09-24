"""Offline, conservative price-source audit for the 2010-2015 index members.

Run ``python -m gabi.historical_price_audit``. This never promotes an archived
price to the operational cache: an overlap check tests returns, not ownership
or the correctness of a delisting return.
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

from . import config, historical_membership
from .historical_archive import IDENTITY_INTERVAL_SOURCE
from .historical_data_audit import connect_readonly
from .historical_identity_audit import QUARTERS
from .historical_price_policy import ADJUSTED, YAHOO_SOURCE, qualify_fallback, record_series

PRICE_SOURCE = json.loads((Path(__file__).with_name("resources") /
                           "historical_sources_1996_2015.json").read_text(encoding="utf-8"))["price_source_id"]
OUTPUT = config.BASE_DIR / "docs" / "historical-prices-2010-2015.csv"
SUMMARY = config.BASE_DIR / "docs" / "historical-prices-2010-2015.json"
QUARTERLY_OUTPUT = config.BASE_DIR / "docs" / "historical-prices-quarterly-2010-2015.csv"
QUARTERLY_SUMMARY = config.BASE_DIR / "docs" / "historical-prices-quarterly-2010-2015.json"
MIN_OVERLAP = 60
MAX_P99_RETURN_DIFFERENCE = 0.005


def _series(conn: sqlite3.Connection, symbol: str, start: str, end: str,
            *, archive: bool) -> pd.DataFrame:
    if archive:
        query = ("SELECT date,close,adj_close FROM historical_prices "
                 "WHERE source_id=? AND symbol=? AND date>=? AND date<=? ORDER BY date")
        args: tuple[str, ...] = (PRICE_SOURCE, symbol, start, end)
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
        return {"sessions": 0, "first": None, "last": None, "complete": False}
    valid = frame.reindex(sessions)[["close", "adj_close"]].apply(pd.to_numeric, errors="coerce")
    present = valid.notna().all(axis=1) & np.isfinite(valid).all(axis=1) & valid.gt(0).all(axis=1)
    observed = sessions[present]
    return {"sessions": len(observed),
            "first": observed[0].date().isoformat() if len(observed) else None,
            "last": observed[-1].date().isoformat() if len(observed) else None,
            "complete": len(observed) == len(sessions)}


def overlap_status(yahoo: pd.DataFrame, archive: pd.DataFrame,
                   sessions: pd.DatetimeIndex | None = None) -> tuple[str, int, float | None]:
    """Compare daily adjusted returns on actual common observations only."""
    common = yahoo[["adj_close"]].join(archive[["adj_close"]], how="inner", lsuffix="_y", rsuffix="_a")
    common = common.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    common = common[(common > 0).all(axis=1)]
    if len(common) < MIN_OVERLAP + 1:
        return "insufficient_overlap", max(0, len(common) - 1), None
    returns = common.pct_change(fill_method=None).dropna()
    # A gap in either source must not become a fabricated daily return.
    if sessions is not None:
        positions = sessions.get_indexer(common.index)
        adjacent = (positions[1:] >= 0) & (positions[:-1] >= 0) & ((positions[1:] - positions[:-1]) == 1)
    else:
        adjacent = (common.index.to_series().diff().dt.days.iloc[1:] <= 5).to_numpy()
    returns = returns[adjacent]
    if len(returns) < MIN_OVERLAP:
        return "insufficient_overlap", len(returns), None
    p99 = float((returns["adj_close_y"] - returns["adj_close_a"]).abs().quantile(0.99))
    return ("consistent_overlap" if p99 <= MAX_P99_RETURN_DIFFERENCE else "divergent_overlap",
            len(returns), p99)


def choose_source(identity_tier: str | None, recycled: bool, yahoo: dict,
                  archive: dict, overlap: str, *, fallback_proof: dict | None = None) -> tuple[str | None, str]:
    """Select only full windows with accredited identity and no known recycling."""
    if recycled:
        return None, "ticker_recycled"
    if not identity_tier:
        return None, "identity_unresolved"
    if yahoo["complete"]:
        return "yahoo", "complete"
    if archive["complete"]:
        accepted, reason = qualify_fallback(identity_tier=identity_tier, recycled=recycled,
                                            archive=archive, overlap=overlap, proof=fallback_proof)
        return ("finsaber" if accepted else None), reason
    return None, "incomplete_prices"


def audit(db: Path, *, dates: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    calendar = xcals.get_calendar("XNYS", start="2008-01-01", end="2016-01-01")
    rows = []
    dates = dates or [f"{year}-12-31" for year in range(2010, 2016)]
    series_cache: dict[tuple[str, bool], pd.DataFrame] = {}
    with connect_readonly(db) as conn:
        has_provenance = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='historical_price_provenance'").fetchone())
        has_events = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='historical_terminal_events'").fetchone())
        for as_of in dates:
            year = int(as_of[:4])
            membership = historical_membership.constituents_as_of(
                as_of, source_id=historical_membership.REFERENCE_SOURCE, compare_reference=False)
            sessions = calendar.sessions[calendar.sessions <= pd.Timestamp(as_of)][-253:]
            start, end = sessions[0].date().isoformat(), sessions[-1].date().isoformat()
            for member in [*membership["members"], {"symbol": "SPY", "identity_tier": "benchmark",
                                                      "cik": None}]:
                symbol = member["symbol"]
                for is_archive in (False, True) if symbol != "SPY" else (False,):
                    key = (symbol, is_archive)
                    if key not in series_cache:
                        series_cache[key] = _series(conn, symbol, "2008-01-01", "2015-12-31",
                                                    archive=is_archive)
                yahoo = series_cache[(symbol, False)].loc[start:end]
                archive = series_cache[(symbol, True)].loc[start:end] if symbol != "SPY" else pd.DataFrame()
                yc, ac = assess_series(yahoo, sessions), assess_series(archive, sessions)
                overlap, count, p99 = overlap_status(yahoo, archive, sessions) if symbol != "SPY" else ("not_applicable", 0, None)
                conflicts = conn.execute(
                    "SELECT COUNT(DISTINCT cik) FROM historical_identity_intervals "
                    "WHERE source_id=? AND symbol=? AND valid_from<=? AND valid_to>?",
                    (IDENTITY_INTERVAL_SOURCE, symbol, end, start)).fetchone()[0] if symbol != "SPY" else 0
                proof_rows = conn.execute(
                    "SELECT adjustment_basis,evidence_json FROM historical_price_provenance "
                    "WHERE entity_id=? AND symbol=? AND source_id=? AND valid_from<=? AND valid_to>=? "
                    "AND status='tier_b'",
                    (member.get("entity_id"), symbol, PRICE_SOURCE, start,
                     (date.fromisoformat(end) + timedelta(days=1)).isoformat())
                ).fetchall() if has_provenance and symbol != "SPY" else []
                fallback_proof = None
                if len(proof_rows) == 1:
                    refs = json.loads(proof_rows[0][1])
                    by_kind = {kind: [ref for ref in refs if ref.get("kind") == kind]
                               for kind in ("first_trade", "last_trade", "adjustment", "corporate_actions")}
                    fallback_proof = {"first_trade": by_kind["first_trade"][0].get("date") if by_kind["first_trade"] else None,
                                      "last_trade": by_kind["last_trade"][0].get("date") if by_kind["last_trade"] else None,
                                      "boundary_evidence": by_kind["first_trade"] + by_kind["last_trade"],
                                      "adjustment_basis": proof_rows[0][0],
                                      "adjustment_evidence": by_kind["adjustment"],
                                      "corporate_action_evidence": by_kind["corporate_actions"]}
                source, status = choose_source(member.get("identity_tier"), conflicts > 1, yc, ac, overlap,
                                               fallback_proof=fallback_proof)
                source_id = YAHOO_SOURCE if source == "yahoo" else PRICE_SOURCE if source == "finsaber" else None
                provenance = conn.execute(
                    "SELECT source_id,adjustment_basis,status,evidence_json FROM historical_price_provenance "
                    "WHERE entity_id=? AND symbol=? AND valid_from<=? AND valid_to>=? "
                    "AND status IN ('tier_a','tier_b')",
                    (member.get("entity_id"), symbol, start,
                     (date.fromisoformat(end) + timedelta(days=1)).isoformat())
                ).fetchall() if has_provenance and source_id else []
                accredited = (len(provenance) == 1 and provenance[0][0] == source_id and
                              provenance[0][1] == ADJUSTED)
                if has_events and symbol != "SPY":
                    events = conn.execute(
                        "SELECT status FROM historical_terminal_events WHERE entity_id=? AND symbol=? "
                        "AND event_date>=? AND event_date<=?",
                        (member.get("entity_id"), symbol, start, end)).fetchall()
                else:
                    events = []
                if events:
                    accredited = False
                sic_row = conn.execute(
                    "SELECT sic FROM sec_bulk_submissions WHERE cik=? AND filed_date<=? "
                    "AND sic IS NOT NULL AND sic!='' ORDER BY filed_date DESC LIMIT 1",
                    (member.get("cik"), as_of)).fetchone() if symbol != "SPY" and member.get("cik") else None
                next_exit = bool(member.get("end_reason") == "exit" and
                                 member.get("valid_to", "9999-12-31") <=
                                 (date.fromisoformat(as_of) + timedelta(days=365)).isoformat())
                rows.append({"year": year, "as_of": as_of, "symbol": symbol, "cik": member.get("cik"),
                             "entity_id": member.get("entity_id"),
                             "identity_tier": member.get("identity_tier"), "expected_sessions": len(sessions),
                             "yahoo_sessions": yc["sessions"], "yahoo_first": yc["first"], "yahoo_last": yc["last"],
                             "finsaber_sessions": ac["sessions"], "finsaber_first": ac["first"],
                             "finsaber_last": ac["last"], "overlap_returns": count,
                             "overlap_status": overlap, "overlap_p99": p99,
                             "known_cik_conflict": conflicts > 1, "selected_source": source,
                             "coverage_status": status,
                             "price_attribution": "benchmark" if symbol == "SPY" else
                             "accredited_entity_interval" if accredited else "legacy_symbol_unattributed",
                             "price_source_status": "benchmark" if symbol == "SPY" else
                             provenance[0][2] if accredited else "candidate_only" if source else "excluded",
                             "terminal_status": ";".join(row[0] for row in events) if events else "none",
                             "identity_valid_from": member.get("valid_from"),
                             "identity_valid_to": member.get("valid_to"),
                             "membership_end_reason": member.get("end_reason"),
                             "sic": sic_row[0] if sic_row else None,
                             "membership_exit_next_365d": next_exit})
    result = pd.DataFrame(rows)
    summary = {"database": db.name, "price_source_id": PRICE_SOURCE,
               "session_definition": "last 253 XNYS sessions through each rebalance date",
               "fallback_rule": "independent trading boundaries, corporate actions and adjustment proof; "
               f"if Yahoo overlap exists, >= {MIN_OVERLAP} returns with p99 difference <= {MAX_P99_RETURN_DIFFERENCE}",
               "price_attribution": "entity intervals stored separately from legacy prices",
               "years": []}
    for year, group in result[result.symbol != "SPY"].groupby("year"):
        summary["years"].append({"year": int(year), "members": len(group),
                                 "yahoo_complete": int(group.yahoo_sessions.eq(group.expected_sessions).sum()),
                                 "finsaber_complete": int(group.finsaber_sessions.eq(group.expected_sessions).sum()),
                                 "selected_yahoo": int(group.selected_source.eq("yahoo").sum()),
                                 "selected_finsaber": int(group.selected_source.eq("finsaber").sum()),
                                 "attributed_usable": int(group.price_attribution.eq("accredited_entity_interval").sum()),
                                 "excluded": int(group.selected_source.isna().sum()),
                                 "reasons": group[group.selected_source.isna()].coverage_status.value_counts().to_dict()})
    summary["rebalances"] = [{"as_of": as_of, "members": len(group),
                               "identity_accredited": int(group.cik.notna().sum()),
                               "price_candidates": int(group.selected_source.notna().sum()),
                               "attributed_usable": int(group.price_attribution.eq("accredited_entity_interval").sum()),
                               "excluded_reasons": group[group.selected_source.isna()].coverage_status.value_counts().to_dict()}
                              for as_of, group in result[result.symbol != "SPY"].groupby("as_of")]
    summary["spy_complete_all_years"] = bool(result[result.symbol == "SPY"].coverage_status.eq("complete").all())
    members = result[result.symbol != "SPY"].copy()
    members["sic_2digit"] = members.sic.fillna("unknown").astype(str).str[:2]
    members["usable"] = members.price_attribution.eq("accredited_entity_interval")
    summary["bias_diagnostics"] = {
        "sic_2digit": [{"sic_2digit": code, "observations": len(group),
                         "usable": int(group.usable.sum())}
                        for code, group in members.groupby("sic_2digit")],
        "membership_exit_next_365d": [{"exit_next_year": bool(flag), "observations": len(group),
                                         "usable": int(group.usable.sum())}
                                        for flag, group in members.groupby("membership_exit_next_365d")],
        "size": "not measured: historical market caps unavailable for many excluded securities",
        "note": "SIC is an issuer-level proxy, not historical GICS; repeated quarterly members are not independent"}
    return result, summary


def promote_tier_a(db: Path, frame: pd.DataFrame) -> dict:
    """Attribute complete Yahoo windows to CIK without touching legacy rows.

    Overlapping quarterly windows for the same security are merged first so a
    strict read has one unambiguous source interval. Only SEC-backed #27/#29
    identity intervals contribute evidence. Reruns upsert the same intervals.
    """
    if db != config.DB_PATH:
        raise ValueError("Promotion only supports the configured local database")
    candidates = frame[(frame.symbol != "SPY") & frame.selected_source.eq("yahoo") &
                       frame.cik.notna() & ~frame.known_cik_conflict]
    intervals: list[dict] = []
    for (symbol, cik), group in candidates.groupby(["symbol", "cik"]):
        for row in group.sort_values("yahoo_first").itertuples(index=False):
            start = row.yahoo_first
            end = (date.fromisoformat(row.yahoo_last) + timedelta(days=1)).isoformat()
            if intervals and intervals[-1]["symbol"] == symbol and intervals[-1]["cik"] == cik and start <= intervals[-1]["end"]:
                intervals[-1]["end"] = max(end, intervals[-1]["end"])
                intervals[-1]["as_of"].append(row.as_of)
            else:
                intervals.append({"symbol": symbol, "cik": cik, "start": start,
                                  "end": end, "as_of": [row.as_of]})
    accepted = 0
    skipped: dict[str, int] = {}
    with connect_readonly(db) as conn:
        for item in intervals:
            symbol, cik = item["symbol"], item["cik"]
            refs: list[dict] = []
            for as_of in item["as_of"]:
                row = conn.execute(
                    "SELECT status,source_refs_json FROM historical_identity_intervals "
                    "WHERE source_id=? AND symbol=? AND cik=? AND valid_from<=? AND valid_to>?",
                    (IDENTITY_INTERVAL_SOURCE, symbol, cik, as_of, as_of)).fetchone()
                if row and row[0] in {"confirmed_by_multiple_evidence", "corroborated_candidate"}:
                    refs.extend({**ref, "kind": "identity", "identity_tier": row[0]}
                                for ref in json.loads(row[1]) if ref.get("source_url"))
            if not refs:
                skipped["missing_sec_identity_reference"] = skipped.get("missing_sec_identity_reference", 0) + 1
                continue
            values = conn.execute(
                "SELECT date,close,adj_close FROM prices WHERE symbol=? AND date>=? AND date<? ORDER BY date",
                (symbol, item["start"], item["end"])).fetchall()
            digest = hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()
            refs.append({"kind": "source", "source_url": f"https://finance.yahoo.com/quote/{symbol}/history/",
                         "local_rows_sha256": digest, "rows": len(values),
                         "note": "legacy Yahoo cache; original per-row download metadata unavailable"})
            try:
                record_series(cik=cik, symbol=symbol, valid_from=item["start"],
                              valid_to=item["end"], source_id=YAHOO_SOURCE,
                              adjustment_basis=ADJUSTED, status="tier_a", evidence=refs)
            except ValueError as exc:
                skipped[str(exc)] = skipped.get(str(exc), 0) + 1
            else:
                accepted += 1
    return {"intervals_promoted": accepted, "skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--csv", type=Path, default=OUTPUT)
    parser.add_argument("--json", type=Path, default=SUMMARY)
    parser.add_argument("--quarterly", action="store_true", help="Audit all 24 quarter ends")
    parser.add_argument("--promote-tier-a", action="store_true", help="Persist SEC-backed complete Yahoo intervals")
    args = parser.parse_args()
    frame, summary = audit(args.db, dates=QUARTERS if args.quarterly else None)
    if args.promote_tier_a:
        summary["promotion"] = promote_tier_a(args.db, frame)
        frame, refreshed = audit(args.db, dates=QUARTERS if args.quarterly else None)
        refreshed["promotion"] = summary["promotion"]
        summary = refreshed
    if args.quarterly and args.csv == OUTPUT:
        args.csv = QUARTERLY_OUTPUT
    if args.quarterly and args.json == SUMMARY:
        args.json = QUARTERLY_SUMMARY
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.csv, index=False)
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
