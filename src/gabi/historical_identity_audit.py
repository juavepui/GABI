"""Offline identity coverage for the archived 2010-2015 S&P 500 universe.

Community ticker/CIK rows are candidates. Only date-valid reviewed aliases
count as resolved identities; a SEC issuer name alone cannot certify a ticker.
"""

import argparse
import hashlib
import json
import re
from bisect import bisect_right
from datetime import date
from pathlib import Path

import pandas as pd
from lxml import etree

from . import config, historical_archive, historical_membership, identity, storage
from .historical_ticker_corrections import correct_symbols

QUARTERS = [date(year, month, day).isoformat()
            for year in range(2010, 2016)
            for month, day in ((3, 31), (6, 30), (9, 30), (12, 31))]
TICKER_RE = re.compile(r"[A-Z][A-Z0-9-]{0,11}\Z")
CANDIDATE_SOURCE = "lawcal:2e59b86998a119d68e377f9f98aa7a816cfc7d5b"


def _date(value: str | None) -> str | None:
    """lawcal marks inferred effective dates with an asterisk."""
    if not value:
        return None
    cleaned = value.strip().rstrip("*")
    return date.fromisoformat(cleaned).isoformat()


def _candidate_map(rows: list[tuple], as_of: str) -> dict[str, dict]:
    candidates: dict[str, dict[str, set[str]]] = {}
    for symbol, cik, name, added, removed, observed in rows:
        start, end = _date(added), _date(removed)
        if not cik or not start or as_of < start or (end and as_of >= end):
            continue
        symbol = identity.normalize_symbol(symbol)
        item = candidates.setdefault(symbol, {"ciks": set(), "names": set(), "observed_ciks": set()})
        item["ciks"].add(identity.normalize_cik(cik))
        if name:
            item["names"].add(name)
        if observed and (observed_date := _date(observed)) and observed_date <= as_of:
            item["observed_ciks"].add(identity.normalize_cik(cik))
    return {symbol: {"cik": next(iter(data["ciks"])) if len(data["ciks"]) == 1 else None,
                     "candidate_cik_count": len(data["ciks"]),
                     "historical_name_candidate": len(data["ciks"]) == 1 and len(data["names"]) == 1,
                     "row_created_by_date": len(data["observed_ciks"]) == 1 and data["observed_ciks"] == data["ciks"]}
            for symbol, data in candidates.items()}


def extract_sec_instance(path: Path, *, cik: str) -> dict:
    """Read ticker and historical issuer name from an original SEC XBRL filing.

    A filing proves its symbol only on its filing date. It cannot by itself
    establish the complete ticker validity interval or index membership.
    """
    expected = identity.normalize_cik(cik)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    root = etree.parse(str(path), parser)
    identifiers = {str(node.text or "").strip().zfill(10)
                   for node in root.xpath("//*[local-name()='identifier']")}
    if identifiers != {expected}:
        raise ValueError(f"XBRL issuer CIK mismatch: {path.name}")
    raw_symbols = {str(node.text or "").strip() for node in root.xpath(
        "//*[local-name()='TradingSymbol' and contains(namespace-uri(), 'xbrl.sec.gov/dei/')]")}
    symbols = {identity.normalize_symbol(value) for value in raw_symbols if value}
    if len(symbols) != 1 or not TICKER_RE.fullmatch(next(iter(symbols))):
        raise ValueError(f"Missing or ambiguous SEC trading symbol: {path.name}")
    names = {str(node.text or "").strip() for node in root.xpath(
        "//*[local-name()='EntityRegistrantName' and contains(namespace-uri(), 'xbrl.sec.gov/dei/')]")
             if str(node.text or "").strip()}
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"symbol": next(iter(symbols)), "cik": expected,
            "historical_name": next(iter(names)) if len(names) == 1 else None,
            "sha256": digest}


def scan_local_sec_instances() -> tuple[list[dict], dict]:
    """Inspect already downloaded 2010-15 XBRL instances; never fetch files."""
    directory = config.DATA_DIR / "history_refresh" / "validation_1996_2015" / "instances"
    with storage.get_connection() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "sec_bulk_submissions" not in tables:
            raise ValueError("SEC bulk submissions have not been imported")
        filings = {row[0]: row[1:] for row in conn.execute(
            "SELECT accn,cik,filed_date,instance FROM sec_bulk_submissions "
            "WHERE filed_date>='2010-01-01' AND filed_date<'2016-01-01' AND instance IS NOT NULL")}
        candidates = conn.execute("SELECT symbol,cik,name,date_added,date_removed,observed_from "
                                  "FROM historical_issuer_candidates WHERE source_id=?",
                                  (CANDIDATE_SOURCE,)).fetchall() if "historical_issuer_candidates" in tables else []
        snapshots = historical_membership._snapshots(pd.read_sql_query(
            "SELECT date,tickers FROM historical_membership WHERE source_id=? ORDER BY date",
            conn, params=(historical_membership.REFERENCE_SOURCE,))) if "historical_membership" in tables else []
    snapshot_dates = [row[0] for row in snapshots]
    records = []
    failures: dict[str, int] = {}
    for path in sorted(directory.glob("*.xml")):
        metadata = filings.get(path.stem)
        if metadata is None:
            continue
        cik, filed_date, instance = metadata
        try:
            proof = extract_sec_instance(path, cik=cik)
        except (OSError, ValueError, etree.XMLSyntaxError) as exc:
            reason = str(exc).split(":", 1)[0]
            failures[reason] = failures.get(reason, 0) + 1
            continue
        proof.update(accession=path.stem, filed_date=filed_date,
                     source_url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                                f"{path.stem.replace('-', '')}/{instance}")
        candidate = _candidate_map(candidates, filed_date).get(proof["symbol"])
        if candidate is None:
            proof["candidate_status"] = "missing"
        elif candidate["candidate_cik_count"] != 1:
            proof["candidate_status"] = "ambiguous"
        else:
            proof["candidate_status"] = "agrees" if candidate["cik"] == proof["cik"] else "conflicts"
        index = bisect_right(snapshot_dates, filed_date) - 1
        proof["member_in_fja"] = index >= 0 and proof["symbol"] in correct_symbols(snapshots[index][1], filed_date)[0]
        records.append(proof)
    statuses = {status: sum(row["candidate_status"] == status for row in records)
                for status in ("agrees", "conflicts", "ambiguous", "missing")}
    return records, {"filings_with_local_instance": len(records) + sum(failures.values()),
                     "ticker_proofs": len(records), "distinct_ticker_cik_pairs": len({
                         (row["symbol"], row["cik"]) for row in records}),
                     "member_on_filing_date": sum(row["member_in_fja"] for row in records),
                     "historical_names": sum(row["historical_name"] is not None for row in records),
                     "candidate_crosscheck": statuses,
                     "conflict_examples": [{"symbol": row["symbol"], "cik": row["cik"],
                                            "filed_date": row["filed_date"]} for row in records
                                           if row["candidate_status"] in {"conflicts", "ambiguous"}][:20],
                     "rejections": failures}


def coverage_report() -> dict:
    """Measure quarterly member observations, retaining candidate/verified tiers."""
    with storage.get_connection() as conn:
        required = {"historical_membership", "historical_issuer_candidates", "entity_aliases", "entities"}
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = required - tables
        if missing:
            raise ValueError(f"Missing local identity tables: {sorted(missing)}")
        history = pd.read_sql_query("SELECT date,tickers FROM historical_membership WHERE source_id=? ORDER BY date",
                                    conn, params=(historical_membership.REFERENCE_SOURCE,))
        candidates = conn.execute("SELECT symbol,cik,name,date_added,date_removed,observed_from "
                                  "FROM historical_issuer_candidates WHERE source_id=?",
                                  (CANDIDATE_SOURCE,)).fetchall()
        aliases = conn.execute("SELECT a.symbol,a.entity_id,e.cik,a.valid_from,a.valid_to,a.confidence "
                               "FROM entity_aliases a JOIN entities e USING(entity_id)").fetchall()
        sec_names = conn.execute("SELECT cik,name,filed_date FROM sec_bulk_submissions "
                                 "WHERE name IS NOT NULL AND name<>'' AND filed_date<='2015-12-31'").fetchall() if "sec_bulk_submissions" in tables else []
    snapshots = historical_membership._snapshots(history)
    if not snapshots or snapshots[0][0] > QUARTERS[0] or snapshots[-1][0] > "2015-12-31":
        raise ValueError("Archived fja05680 membership coverage is missing or invalid")
    snapshot_dates = [row[0] for row in snapshots]
    by_year: dict[str, dict] = {}
    ambiguous_examples: set[str] = set()
    for day in QUARTERS:
        index = bisect_right(snapshot_dates, day) - 1
        symbols, _ = correct_symbols(snapshots[index][1], day)
        candidates_by_symbol = _candidate_map(candidates, day)
        annual = by_year.setdefault(day[:4], {"quarter_dates": [], "member_observations": 0,
                                               "resolved_cik": 0, "resolved_entity_id": 0,
                                               "date_valid_alias": 0, "historical_name_sec": 0,
                                               "candidate_unique_cik": 0, "candidate_row_created_by_date": 0,
                                               "candidate_name": 0, "ambiguous_alias": 0,
                                               "ambiguous_candidate_cik": 0})
        annual["quarter_dates"].append(day)
        annual["member_observations"] += len(symbols)
        for symbol in symbols:
            matching = [row for row in aliases if row[0] == symbol and row[3] <= day
                        and (row[4] is None or day < row[4])]
            owners = {row[1] for row in matching}
            valid = len(owners) == 1 and max((row[5] for row in matching), default=0) >= identity.MIN_CONFIDENCE
            if len(owners) > 1:
                annual["ambiguous_alias"] += 1
                ambiguous_examples.add(symbol)
            if valid:
                annual["date_valid_alias"] += 1
                annual["resolved_entity_id"] += 1
                cik = next((row[2] for row in matching if row[1] in owners), None)
                if cik:
                    annual["resolved_cik"] += 1
                    # A historical issuer name must come from a SEC filing
                    # available by that date, not today's entity name.
                    if any(row[0] == cik and row[2] <= day for row in sec_names):
                        annual["historical_name_sec"] += 1
            candidate = candidates_by_symbol.get(symbol)
            if candidate:
                if candidate["cik"]:
                    annual["candidate_unique_cik"] += 1
                    annual["candidate_row_created_by_date"] += candidate["row_created_by_date"]
                elif candidate["candidate_cik_count"] > 1:
                    annual["ambiguous_candidate_cik"] += 1
                    ambiguous_examples.add(symbol)
                annual["candidate_name"] += candidate["historical_name_candidate"]
    for annual in by_year.values():
        denominator = annual["member_observations"]
        annual["percent"] = {key: round(100 * annual[key] / denominator, 3) for key in (
            "resolved_cik", "resolved_entity_id", "date_valid_alias", "historical_name_sec",
            "candidate_unique_cik", "candidate_row_created_by_date", "candidate_name")}
    return {"membership_source_id": historical_membership.REFERENCE_SOURCE,
            "candidate_source_id": CANDIDATE_SOURCE,
            "window": [QUARTERS[0], QUARTERS[-1]], "unit": "quarter-end member observation",
            "candidate_warning": "lawcal CIK/name are reconstructed candidates, not verified ticker aliases; row creation date does not date the manually backfilled CIK",
            "by_year": by_year, "ambiguous_examples": sorted(ambiguous_examples)[:30]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the offline report as JSON")
    parser.add_argument("--scan-instances", action="store_true", help="Check locally cached original SEC XBRL files")
    parser.add_argument("--evidence-csv", type=Path, help="Save accepted SEC filing-day identity evidence")
    parser.add_argument("--import-evidence", action="store_true",
                        help="Idempotently archive SEC filing-day observations; does not create aliases")
    args = parser.parse_args()
    if (args.evidence_csv or args.import_evidence) and not args.scan_instances:
        parser.error("--evidence-csv and --import-evidence require --scan-instances")
    report = coverage_report()
    if args.scan_instances:
        records, summary = scan_local_sec_instances()
        report["sec_instance_evidence"] = summary
        if args.import_evidence:
            summary["imported_observations"] = historical_archive.import_filing_identity_evidence(records)
            with storage.get_connection() as conn:
                summary["stored_observations"] = conn.execute(
                    "SELECT COUNT(*) FROM entity_observations WHERE dataset='filing_identity'").fetchone()[0]
                summary["active_alias_rows"] = conn.execute("SELECT COUNT(*) FROM entity_aliases").fetchone()[0]
        if args.evidence_csv:
            args.evidence_csv.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(records).to_csv(args.evidence_csv, index=False)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
