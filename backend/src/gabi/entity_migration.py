"""Offline, additive migration and historical identity coverage audit.

Run with ``python -m gabi.entity_migration --help``. No legacy rows are deleted
or automatically attributed using today's ticker map.
"""
import argparse
import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from . import config, identity, storage
from .historical_ticker_corrections import WLP_END, WLP_SOURCES, WLP_START

# Bounds are trading dates, not corporate-name effective dates. Multiple
# independent sources are retained; open ends express continuity until new evidence.
KNOWN_ALIASES = [
    ("1156039", "WellPoint Inc.", "WLP", WLP_START, "2010-02-16", WLP_SOURCES[0]),
    ("1156039", "WellPoint Inc.", "WLP", "2010-02-16", WLP_END,
     "https://www.sec.gov/Archives/edgar/data/1156039/000119312510031423/dex991.htm | "
     "https://www.miaxglobal.com/alert/2014/12/02/miax-corporate-action-alert-wellpoint-inc-wlp-name-and-symbol-change-anthem"),
    ("1326801", "Meta Platforms", "FB", "2012-05-18", "2022-06-09",
     "https://www.sec.gov/Archives/edgar/data/1326801/000132680114000007/fb-12312013x10k.htm"),
    ("1326801", "Meta Platforms", "META", "2022-06-09", None,
     "https://www.sec.gov/Archives/edgar/data/1326801/000132680123000052/meta-12312022x10kars.htm"),
    ("1156039", "Elevance Health", "ANTM", "2014-12-03", "2022-06-28",
     "https://www.miaxglobal.com/alert/2014/12/02/miax-corporate-action-alert-wellpoint-inc-wlp-name-and-symbol-change-anthem"),
    ("1156039", "Elevance Health", "ELV", "2022-06-28", None,
     "https://www.sec.gov/Archives/edgar/data/1156039/000115603922000081/elv-20220630.htm"),
]


def activate_reviewed_symbol(symbol: str) -> int:
    """Activate one reviewed ticker interval without migrating unrelated symbols."""
    selected = [row for row in KNOWN_ALIASES if identity.normalize_symbol(row[2]) == identity.normalize_symbol(symbol)]
    if not selected:
        raise ValueError(f"No reviewed alias for {symbol}")
    for cik, _name, ticker, start, end, source in selected:
        # Historical labels must not overwrite the issuer's current display name.
        entity = identity.ensure_entity(cik)
        identity.add_alias(entity, ticker, start, end, source=source)
    return len(selected)


def migrate() -> dict:
    """Idempotent DDL + reviewed aliases + dated legacy snapshots, no network."""
    with storage.get_connection() as conn:
        identity.ensure_schema(conn)
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='entity_snapshots'").fetchone()
        rows = conn.execute("SELECT symbol,cik,name,sector,industry,effective_date FROM entity_snapshots").fetchall() if exists else []
        conn.commit()
    imported = 0
    for symbol, cik, name, sector, industry, day in rows:
        if not cik:
            continue
        entity = identity.import_filing_identity(symbol, cik, day, source="legacy-snapshot:observed-date", name=name)
        with storage.get_connection() as conn:
            identity.put_observations(conn, entity, "sector", symbol, [{
                "cik": cik, "name": name, "sector": sector, "industry": industry, "effective_date": day,
            }], "legacy-snapshot:observed-date")
            conn.commit()
        imported += 1
    for symbol in sorted({row[2] for row in KNOWN_ALIASES}):
        activate_reviewed_symbol(symbol)
    return {"snapshots_imported": imported, "reviewed_aliases": len(KNOWN_ALIASES),
            "legacy_financial_rows_attributed": 0}


def attribute_legacy(symbol: str, entity_id: str, dataset: str, *, source: str,
                     start: str | None = None, end: str | None = None) -> int:
    """Explicit operator attestation of ownership, after inspecting provider evidence.

    This is deliberately not inferred from the latest edgar_metrics.cik: old
    rows for the symbol could have been fetched for a different issuer.
    """
    if dataset not in {"prices", "splits", "fundamentals", "edgar_facts"}:
        raise ValueError("Unsupported legacy dataset")
    if not source.strip():
        raise ValueError("Attribution evidence is required")
    if start:
        date.fromisoformat(start)
    if end:
        date.fromisoformat(end)
    if start and end and end <= start:
        raise ValueError("Invalid attribution interval")
    with storage.get_connection() as conn:
        identity.ensure_schema(conn)
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (dataset,)).fetchone()
        if not exists:
            return 0
        frame = pd.read_sql_query(f'SELECT * FROM "{dataset}" WHERE symbol=?', conn, params=(symbol,))
        column = "date" if dataset in {"prices", "splits"} else "filed_date" if dataset == "edgar_facts" else "fetched_at"
        if start:
            frame = frame[frame[column] >= start]
        if end:
            frame = frame[frame[column] < end]
        rows = frame.astype(object).where(frame.notna(), None).to_dict("records")
        identity.put_observations(conn, entity_id, dataset, symbol, rows, source)
        conn.commit()
    return len(rows)


def coverage_report(history: pd.DataFrame, current_map: pd.DataFrame) -> dict:
    """Compare lexical legacy lookup with reviewed date-valid identity (different guarantees).

    Count distinct symbol/date membership observations, not duplicate daily rows.
    Also report distinct symbols with any mapping so the legacy ~16% hypothesis
    can be checked against an explicitly stated denominator.
    """
    mapping = {identity.normalize_symbol(s) for s in current_map["symbol"] if isinstance(s, str) and s.strip()}
    pairs = {(str(row.date), identity.normalize_symbol(s)) for row in history.itertuples()
             for s in str(row.tickers).split(",") if s.strip()}
    symbols = {symbol for _, symbol in pairs}
    # Read alias evidence once: the historical file can contain millions of pairs.
    with storage.get_connection() as conn:
        identity.ensure_schema(conn)
        aliases = pd.read_sql_query("SELECT * FROM entity_aliases", conn)
    by_symbol = {s: group.to_dict("records") for s, group in aliases.groupby("symbol")}
    resolved = ambiguous = 0
    newly_resolved_symbols = set()
    for day, symbol in pairs:
        matches = [r for r in by_symbol.get(symbol, [])
                   if r["valid_from"] <= day and (pd.isna(r["valid_to"]) or day < r["valid_to"])]
        owners = {r["entity_id"] for r in matches}
        if len(owners) > 1:
            ambiguous += 1
        elif len(owners) == 1 and max(r["confidence"] for r in matches) >= identity.MIN_CONFIDENCE:
            resolved += 1
            newly_resolved_symbols.add(symbol)
    legacy_unresolved = symbols - mapping
    augmented = legacy_unresolved - newly_resolved_symbols
    return {
        "history_start": str(history["date"].min()), "history_end": str(history["date"].max()),
        "distinct_symbols": len(symbols), "symbol_date_pairs": len(pairs),
        "before_unmapped_symbols": len(legacy_unresolved),
        "before_unmapped_pct": 100 * len(legacy_unresolved) / len(symbols) if symbols else 0,
        "after_unmapped_symbols": len(augmented),
        "after_unmapped_pct": 100 * len(augmented) / len(symbols) if symbols else 0,
        "recovered_symbols": sorted(legacy_unresolved - augmented),
        "verified_symbol_date_pairs": resolved, "ambiguous_symbol_date_pairs": ambiguous,
        "unverified_symbol_date_pct": 100 * (len(pairs) - resolved) / len(pairs) if pairs else 0,
        "warning": "Current-map matches are candidates, NOT verified historical identity or usable data coverage.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--activate-reviewed-symbol", help="Activate only a specifically reviewed ticker interval")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--history", type=Path, default=config.DATA_DIR / "sp500_historical_membership.csv")
    parser.add_argument("--cik-map", type=Path, default=config.DATA_DIR / "sec_cik_map.csv")
    parser.add_argument("--attribute-symbol")
    parser.add_argument("--entity-id")
    parser.add_argument("--dataset", choices=["prices", "splits", "fundamentals", "edgar_facts"])
    parser.add_argument("--source")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--submissions-json", type=Path)
    parser.add_argument("--candidate-symbol")
    parser.add_argument("--historical-name")
    args = parser.parse_args()
    if args.attribute_symbol and not all((args.entity_id, args.dataset, args.source)):
        parser.error("Attribution requires --entity-id, --dataset and --source evidence")
    if args.submissions_json and not all((args.candidate_symbol, args.historical_name, args.source)):
        parser.error("Candidate import requires --candidate-symbol, --historical-name and --source")
    config.DB_PATH = args.db
    config.DATA_DIR = args.db.parent
    if (args.migrate or args.activate_reviewed_symbol or args.attribute_symbol or args.submissions_json) and args.db.exists():
        backup = args.db.with_name(args.db.name + ".before-identity.bak")
        if not backup.exists():
            with sqlite3.connect(args.db) as original, sqlite3.connect(backup) as destination:
                original.backup(destination)
    if args.migrate:
        print(json.dumps(migrate(), indent=2))
    if args.activate_reviewed_symbol:
        print(json.dumps({"activated": activate_reviewed_symbol(args.activate_reviewed_symbol),
                          "symbol": identity.normalize_symbol(args.activate_reviewed_symbol)}))
    if args.attribute_symbol:
        print(attribute_legacy(args.attribute_symbol, args.entity_id, args.dataset, source=args.source,
                               start=args.start, end=args.end))
    if args.submissions_json:
        print(identity.import_submissions_candidates(args.candidate_symbol, args.historical_name,
              json.loads(args.submissions_json.read_text(encoding="utf-8")), source=args.source))
    if args.report:
        report = coverage_report(pd.read_csv(args.history, keep_default_na=False),
                                 pd.read_csv(args.cik_map, dtype={"cik": str}, keep_default_na=False))
        report["history_sha256"] = hashlib.sha256(args.history.read_bytes()).hexdigest()
        report["cik_map_sha256"] = hashlib.sha256(args.cik_map.read_bytes()).hexdigest()
        history = pd.read_csv(args.history, keep_default_na=False)
        recent = history[history["date"] >= "2016-01-01"]
        if not recent.empty:
            report["since_2016"] = coverage_report(recent, pd.read_csv(args.cik_map, keep_default_na=False))
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
