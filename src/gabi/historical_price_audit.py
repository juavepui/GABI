"""Offline, conservative price-source audit for the 2010-2015 index members.

Run ``python -m gabi.historical_price_audit``. This never promotes an archived
price to the operational cache: an overlap check tests returns, not ownership
or the correctness of a delisting return.
"""
import argparse
import json
import sqlite3
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from . import config, historical_membership
from .historical_archive import IDENTITY_INTERVAL_SOURCE
from .historical_data_audit import connect_readonly

PRICE_SOURCE = json.loads((Path(__file__).with_name("resources") /
                           "historical_sources_1996_2015.json").read_text(encoding="utf-8"))["price_source_id"]
OUTPUT = config.BASE_DIR / "docs" / "historical-prices-2010-2015.csv"
SUMMARY = config.BASE_DIR / "docs" / "historical-prices-2010-2015.json"
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


def overlap_status(yahoo: pd.DataFrame, archive: pd.DataFrame) -> tuple[str, int, float | None]:
    """Compare daily adjusted returns on actual common observations only."""
    common = yahoo[["adj_close"]].join(archive[["adj_close"]], how="inner", lsuffix="_y", rsuffix="_a")
    common = common.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    common = common[(common > 0).all(axis=1)]
    if len(common) < MIN_OVERLAP + 1:
        return "insufficient_overlap", max(0, len(common) - 1), None
    returns = common.pct_change(fill_method=None).dropna()
    # A gap in both sources must not become a fabricated daily return.
    adjacent = common.index.to_series().diff().dt.days.iloc[1:] <= 5
    returns = returns[adjacent.to_numpy()]
    if len(returns) < MIN_OVERLAP:
        return "insufficient_overlap", len(returns), None
    p99 = float((returns["adj_close_y"] - returns["adj_close_a"]).abs().quantile(0.99))
    return ("consistent_overlap" if p99 <= MAX_P99_RETURN_DIFFERENCE else "divergent_overlap",
            len(returns), p99)


def choose_source(identity_tier: str | None, recycled: bool, yahoo: dict,
                  archive: dict, overlap: str) -> tuple[str | None, str]:
    """Select only full windows with accredited identity and no known recycling."""
    if recycled:
        return None, "ticker_recycled"
    if not identity_tier:
        return None, "identity_unresolved"
    if yahoo["complete"]:
        return "yahoo", "complete"
    if archive["complete"] and overlap == "consistent_overlap":
        # A derived pre-IPO/pre-merger predecessor must not supply the missing
        # first session of a security (ABBV/KHC/QRVO in the local archive).
        if yahoo["first"] != archive["first"] or yahoo["last"] != archive["last"]:
            return None, "archive_boundary_unverified"
        return "finsaber", "fallback_consistent_overlap"
    if archive["complete"]:
        return None, "archive_adjustment_unverified"
    return None, "incomplete_prices"


def audit(db: Path) -> tuple[pd.DataFrame, dict]:
    calendar = xcals.get_calendar("XNYS", start="2008-01-01", end="2016-01-01")
    rows = []
    with connect_readonly(db) as conn:
        for year in range(2010, 2016):
            as_of = f"{year}-12-31"
            membership = historical_membership.constituents_as_of(
                as_of, source_id=historical_membership.REFERENCE_SOURCE, compare_reference=False)
            sessions = calendar.sessions[calendar.sessions <= pd.Timestamp(as_of)][-253:]
            start, end = sessions[0].date().isoformat(), sessions[-1].date().isoformat()
            for member in [*membership["members"], {"symbol": "SPY", "identity_tier": "benchmark",
                                                      "cik": None}]:
                symbol = member["symbol"]
                yahoo = _series(conn, symbol, start, end, archive=False)
                archive = _series(conn, symbol, start, end, archive=True) if symbol != "SPY" else pd.DataFrame()
                yc, ac = assess_series(yahoo, sessions), assess_series(archive, sessions)
                overlap, count, p99 = overlap_status(yahoo, archive) if symbol != "SPY" else ("not_applicable", 0, None)
                conflicts = conn.execute(
                    "SELECT COUNT(DISTINCT cik) FROM historical_identity_intervals "
                    "WHERE source_id=? AND symbol=? AND valid_from<=? AND valid_to>?",
                    (IDENTITY_INTERVAL_SOURCE, symbol, end, start)).fetchone()[0] if symbol != "SPY" else 0
                source, status = choose_source(member.get("identity_tier"), conflicts > 1, yc, ac, overlap)
                rows.append({"year": year, "as_of": as_of, "symbol": symbol, "cik": member.get("cik"),
                             "identity_tier": member.get("identity_tier"), "expected_sessions": len(sessions),
                             "yahoo_sessions": yc["sessions"], "yahoo_first": yc["first"], "yahoo_last": yc["last"],
                             "finsaber_sessions": ac["sessions"], "finsaber_first": ac["first"],
                             "finsaber_last": ac["last"], "overlap_returns": count,
                             "overlap_status": overlap, "overlap_p99": p99,
                             "known_cik_conflict": conflicts > 1, "selected_source": source,
                             "coverage_status": status,
                             "price_attribution": "benchmark" if symbol == "SPY" else "legacy_symbol_unattributed"})
    result = pd.DataFrame(rows)
    summary = {"database": db.name, "price_source_id": PRICE_SOURCE,
               "session_definition": "last 253 XNYS sessions through December 31",
               "fallback_rule": f">={MIN_OVERLAP} common daily returns, p99 absolute difference <= {MAX_P99_RETURN_DIFFERENCE}",
               "price_attribution": "candidate_only; no archived or legacy price promoted to entity observations",
               "years": []}
    for year, group in result[result.symbol != "SPY"].groupby("year"):
        summary["years"].append({"year": int(year), "members": len(group),
                                 "yahoo_complete": int(group.yahoo_sessions.eq(group.expected_sessions).sum()),
                                 "finsaber_complete": int(group.finsaber_sessions.eq(group.expected_sessions).sum()),
                                 "selected_yahoo": int(group.selected_source.eq("yahoo").sum()),
                                 "selected_finsaber": int(group.selected_source.eq("finsaber").sum()),
                                 "excluded": int(group.selected_source.isna().sum()),
                                 "reasons": group[group.selected_source.isna()].coverage_status.value_counts().to_dict()})
    summary["spy_complete_all_years"] = bool(result[result.symbol == "SPY"].coverage_status.eq("complete").all())
    return result, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--csv", type=Path, default=OUTPUT)
    parser.add_argument("--json", type=Path, default=SUMMARY)
    args = parser.parse_args()
    frame, summary = audit(args.db)
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.csv, index=False)
    args.json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
