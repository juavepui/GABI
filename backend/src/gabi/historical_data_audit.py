"""Offline annual inventory of the local historical cache; never fetches data.

Run ``python -m gabi.historical_data_audit``. The pre-2016 metric calculations
come from the existing quarterly audit; regenerate it if the database changes.
"""
import argparse
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import exchange_calendars as xcals
import pandas as pd

from . import config, scoring
from .historical_coverage import availability, finite, metric_row

BLOCKS = scoring.SCORE_METRICS
METRICS = [metric for metrics in BLOCKS.values() for metric in metrics]
ROOT = config.BASE_DIR
OLD_DETAIL = config.DATA_DIR / "history_refresh" / "validation_1996_2015" / "coverage" / "company-quarter.csv"
OUTPUT = ROOT / "docs" / "historical-data-audit.csv"


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def pick_snapshot(frame: pd.DataFrame, as_of: str) -> tuple[str, list[str]]:
    before = frame[frame.date <= as_of]
    if before.empty:
        raise ValueError(f"No membership snapshot on or before {as_of}")
    row = before.iloc[-1]
    return str(row.date), [s.strip() for s in str(row.tickers).split(",") if s.strip()]


def block_counts(rows: list[dict]) -> dict[str, int]:
    result = {metric: sum(finite(row.get(metric)) for row in rows) for metric in METRICS}
    result.update({f"{block}_complete": sum(all(finite(row.get(metric)) for metric in metrics) for row in rows)
                   for block, metrics in BLOCKS.items()})
    result["all_13"] = sum(availability(row)[0] == 13 for row in rows)
    result["ranking_minimum"] = sum(availability(row)[1] for row in rows)
    return result


def old_block_counts(detail: pd.DataFrame, day: str) -> dict[str, int]:
    frame = detail[detail.date == day]
    if frame.empty:
        raise ValueError(f"Missing pre-2016 quarterly audit at {day}; run python -m gabi.historical_coverage")
    rows = []
    for missing in frame.missing_metrics.fillna(""):
        absent = set(missing.split(";"))
        rows.append({metric: None if metric in absent else 1 for metric in METRICS})
    result = block_counts(rows)
    if "prices_253_recent" in frame:
        result["prices_253_recent"] = int(frame.prices_253_recent.sum())
    return result


def annual_metrics(conn: sqlite3.Connection, symbols: list[str], day: str) -> dict[str, int]:
    """Reuse the existing 13 formulas with ticker-cache inputs, tagged approximate."""
    benchmark = pd.read_sql_query("SELECT date,close,adj_close FROM prices WHERE symbol='SPY' AND date<=? ORDER BY date",
                                  conn, params=(day,))
    benchmark["date"] = pd.to_datetime(benchmark.date)
    benchmark = benchmark.set_index("date")
    sessions = xcals.get_calendar("XNYS", start="1994-01-01", end="2027-01-01").sessions
    expected = sessions[sessions <= pd.Timestamp(day)][-253:]
    complete_prices = 0
    rows = []
    for symbol in symbols:
        facts = pd.read_sql_query(
            "SELECT tag,unit,start_date,end_date,val,form,fp,fy,filed_date,accn FROM edgar_facts "
            "WHERE symbol=? AND filed_date<=? AND end_date<=? ORDER BY filed_date,end_date,accn",
            conn, params=(symbol, day, day))
        prices = pd.read_sql_query("SELECT date,close,adj_close FROM prices WHERE symbol=? AND date<=? ORDER BY date",
                                   conn, params=(symbol, day))
        prices["date"] = pd.to_datetime(prices.date)
        prices = prices.set_index("date")
        complete_prices += len(expected) == 253 and expected.difference(prices.index).empty and prices.reindex(expected).adj_close.gt(0).all()
        nominal = float(prices.close.iloc[-1]) if not prices.empty and pd.notna(prices.close.iloc[-1]) else None
        if nominal is not None:
            future_splits = conn.execute("SELECT ratio FROM splits WHERE symbol=? AND date>?", (symbol, day))
            for (ratio,) in future_splits:
                if ratio:
                    nominal *= ratio
        rows.append(metric_row(facts, prices, benchmark, day, nominal_price=nominal))
    result = block_counts(rows)
    result["prices_253_recent"] = int(complete_prices)
    return result


def audit(db: Path, membership_csv: Path, old_detail: Path) -> pd.DataFrame:
    if not membership_csv.is_file():
        raise FileNotFoundError(membership_csv)
    if not old_detail.is_file():
        raise FileNotFoundError(f"{old_detail}: run python -m gabi.historical_coverage first")
    operational = pd.read_csv(membership_csv, dtype=str).sort_values("date")
    old = pd.read_csv(old_detail, dtype={"date": str, "missing_metrics": str})
    with connect_readonly(db) as conn:
        manifest = json.loads((Path(__file__).with_name("resources") / "historical_sources_1996_2015.json").read_text())
        archive = pd.read_sql_query("SELECT date,tickers FROM historical_membership WHERE source_id=? ORDER BY date",
                                    conn, params=(manifest["membership_source_id"],))
        archive_price_source = manifest["price_source_id"]
        aliases = pd.read_sql_query("SELECT symbol,entity_id,valid_from,valid_to,confidence FROM entity_aliases", conn)
        issuer_entities_by_year = dict(conn.execute(
            "SELECT substr(json_extract(payload_json,'$.filed_date'),1,4),COUNT(DISTINCT entity_id) "
            "FROM entity_observations WHERE dataset='edgar_facts' GROUP BY 1"))
        last_spy = conn.execute("SELECT MAX(date) FROM prices WHERE symbol='SPY' AND adj_close>0").fetchone()[0]
        if last_spy is None:
            raise ValueError("SPY has no adjusted close")
        rows = []
        for year in range(2008, min(2026, date.fromisoformat(last_spy).year) + 1):
            source = archive if year <= 2015 else operational
            day = min(f"{year}-12-31", last_spy, str(source.date.max()))
            snapshot, symbols = pick_snapshot(source, day)
            symbols = list(dict.fromkeys(symbols))
            if year <= 2015:
                metrics = old_block_counts(old, f"{year}-12-31")
                quarter = old[old.date == f"{year}-12-31"]
                if len(quarter) != len(symbols) or set(quarter.symbol) != set(symbols):
                    raise ValueError(f"Historical audit membership changed in {year}; regenerate it")
                metric_source = "issuer_exact_candidate_CIK"
            else:
                metrics = annual_metrics(conn, symbols, day)
                metric_source = "legacy_ticker_approximate"
            latest = dict(conn.execute("SELECT symbol,MAX(filed_date) FROM edgar_facts WHERE filed_date<=? GROUP BY symbol", (day,)))
            fresh_since = (date.fromisoformat(day) - timedelta(days=460)).isoformat()
            adjusted, recent, price_year, price_recent = 0, 0, 0, 0
            price_cutoff = (date.fromisoformat(day) - timedelta(days=10)).isoformat()
            for symbol in symbols:
                filed = latest.get(symbol)
                if filed and filed >= fresh_since:
                    recent += 1
                last = conn.execute("SELECT MAX(date),SUM(CASE WHEN adj_close>0 THEN 1 ELSE 0 END),"
                                    "MAX(CASE WHEN adj_close>0 THEN date END) "
                                    "FROM prices WHERE symbol=? AND date>=? AND date<=?", (symbol, f"{year}-01-01", day)).fetchone()
                if last[0]:
                    price_year += 1
                if last[1]:
                    adjusted += 1
                if last[2] and last[2] >= price_cutoff:
                    price_recent += 1
            owners = 0
            for symbol in symbols:
                claims = aliases[(aliases.symbol == symbol) & (aliases.valid_from <= day)
                                 & (aliases.valid_to.isna() | (aliases.valid_to > day))]
                if len(set(claims.entity_id)) == 1 and not claims.empty and claims.confidence.max() >= 0.9:
                    owners += 1
            split_events = conn.execute("SELECT COUNT(*) FROM splits WHERE date>=? AND date<=?",
                                        (f"{year}-01-01", day)).fetchone()[0]
            archive_prices, archive_adjusted = 0, 0
            if year <= 2015:
                archive_by_symbol = dict(conn.execute(
                    "SELECT symbol,SUM(CASE WHEN adj_close>0 THEN 1 ELSE 0 END) FROM historical_prices "
                    "WHERE source_id=? AND date>=? AND date<=? GROUP BY symbol",
                    (archive_price_source, f"{year}-01-01", day)))
                archive_prices = sum(symbol in archive_by_symbol for symbol in symbols)
                archive_adjusted = sum(bool(archive_by_symbol.get(symbol)) for symbol in symbols)
            archive_ciks = conn.execute("SELECT COUNT(DISTINCT cik) FROM historical_facts WHERE filed_date>=? AND filed_date<=?",
                                        (f"{year}-01-01", day)).fetchone()[0]
            rows.append({"year": year, "as_of": day, "membership_snapshot": snapshot,
                         "membership_source": "fja_archive" if year <= 2015 else "hans_reviewed_extension",
                         "members": len(symbols), "aliases_verified": owners, "prices_year": price_year,
                         "adjusted_prices_year": adjusted, "adjusted_price_recent_10d": price_recent,
                         "archive_prices_year": archive_prices,
                         "archive_adjusted_year": archive_adjusted, "split_events_year": split_events,
                         "legacy_sec_recent": recent, "issuer_entities_filed_year": issuer_entities_by_year.get(str(year), 0),
                         "archive_ciks_filed_year": archive_ciks,
                         "metric_source": metric_source, **metrics})
            print(f"{year}: {len(symbols)} members, {metrics['all_13']} with 13 numeric metrics", flush=True)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--membership", type=Path, default=config.DATA_DIR / "sp500_historical_membership.csv")
    parser.add_argument("--old-detail", type=Path, default=OLD_DETAIL)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = audit(args.db, args.membership, args.old_detail)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(args.output)


if __name__ == "__main__":
    main()
