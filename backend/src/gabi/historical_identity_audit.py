"""Offline identity coverage for the archived S&P 500 universe, per period.

2010-2015 (#27) and 2016-2025 (#34) use the same rules; each period writes
its own interval source (``historical_period``).

Community ticker/CIK rows are candidates. Direct SEC ticker evidence and
retrospective issuer corroboration have separate tiers; an issuer name alone
cannot certify a ticker or activate an operational alias.
"""

import argparse
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import requests

from gabi.application.research import historical_audit_exports as audit_exports
from gabi.application.research import historical_identity_audit as identity_audit
from gabi.application.research import identity_instances as instance_scan
from gabi.domain.research import historical_identity_audit as identity_rules
from gabi.domain.research import identity_instances as instance_rules
from gabi.infrastructure.storage.historical_audit_exports import HistoricalAuditFiles
from gabi.infrastructure.storage.historical_identity_audit import SqliteIdentityAuditReads
from gabi.infrastructure.storage.historical_issuer_evidence import HistoricalIssuerFiles
from gabi.infrastructure.storage.identity_instances import LocalIdentityInstances, SqliteIdentityInstances

from . import config, historical_archive, identity, sec_history, storage
from . import historical_issuer_evidence as issuer_evidence
from .historical_period import P2010, Period
from .historical_period import get as get_period
from .historical_ticker_corrections import identity_nominations

QUARTERS = P2010.quarters
TICKER_RE = instance_rules.TICKER_RE
DEI_NAMESPACES = instance_rules.DEI_NAMESPACES
CANDIDATE_SOURCE = "lawcal:2e59b86998a119d68e377f9f98aa7a816cfc7d5b"
INTERVAL_SOURCE = historical_archive.IDENTITY_INTERVAL_SOURCE
# Quarterly filers report within ~100 days; allow one missed report.
MAX_FIRST_FILING_LAG_DAYS = 200


_date = identity_rules._date


_candidate_map = identity_rules._candidate_map


COMMON_TITLE_RE = instance_rules.COMMON_TITLE_RE
NON_COMMON_RE = instance_rules.NON_COMMON_RE





def extract_sec_instance(path: Path, *, cik: str, common_stock_only: bool = False,
                         multi_class: frozenset[str] = frozenset()) -> dict:
    return LocalIdentityInstances(path.parent).extract(path, cik=cik, common_stock_only=common_stock_only,
                                                       multi_class=multi_class)


def scan_local_sec_instances(period: Period = P2010) -> tuple[list[dict], dict]:
    directory = config.DATA_DIR / 'history_refresh' / 'validation_1996_2015' / 'instances'
    return instance_scan.scan(SqliteIdentityInstances(config.DB_PATH), LocalIdentityInstances(directory),
                              tuple(identity_nominations()), period)


def fetch_candidate_instances(limit: int, *, prioritize_unresolved: bool = False,
                              period: Period = P2010) -> dict:
    """Cache selected original SEC covers for historic CIK candidates.

    Three filings spread over each candidate's dated tenure give more useful
    checks than downloading every report. Candidate CIKs select *what to check*;
    only a ticker explicitly present in the SEC instance becomes proof.
    Reruns skip existing files and keep the archive's URL/SHA-256 provenance.
    """
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    with storage.get_connection() as conn:
        candidates = conn.execute(
            "SELECT DISTINCT symbol,cik,date_added,date_removed FROM historical_issuer_candidates "
            "WHERE source_id=? AND date_added<? "
            "AND (date_removed IS NULL OR date_removed='' OR date_removed>=?)",
            (CANDIDATE_SOURCE, period.end_exclusive, period.start)).fetchall()
        filings = conn.execute(
            "SELECT accn,cik,filed_date,instance FROM sec_bulk_submissions "
            "WHERE filed_date>=? AND filed_date<? "
            "AND form IN ('10-K','10-Q') AND instance IS NOT NULL ORDER BY filed_date,accn",
            (period.start, period.end_exclusive)).fetchall()
        candidates += [(row["label"], row["cik"],
                        (date.fromisoformat(row["valid_from"]) - timedelta(days=row["evidence_window_days"])).isoformat(),
                        (date.fromisoformat(row["valid_to"]) + timedelta(days=row["evidence_window_days"])).isoformat())
                       for row in identity_nominations()]
        unresolved = conn.execute(
            "SELECT cik,valid_from,valid_to FROM historical_identity_intervals "
            "WHERE source_id=? AND status='unresolved'",
            (period.identity_source,)).fetchall() if prioritize_unresolved else []
    by_cik: dict[str, list[tuple]] = {}
    for row in filings:
        by_cik.setdefault(identity.normalize_cik(row[1]), []).append(row)
    selected: dict[str, tuple] = {}
    missing_candidates = 0
    for _symbol, cik, added, removed in candidates:
        start = max(_date(added) or period.start, period.start)
        end = min(_date(removed) or period.end_exclusive, period.end_exclusive)
        eligible = [row for row in by_cik.get(identity.normalize_cik(cik), [])
                    if start <= row[2] < end]
        if len(eligible) < 2:
            missing_candidates += 1
            continue
        for index in {0, len(eligible) // 2, len(eligible) - 1}:
            row = eligible[index]
            selected[row[0]] = row
    # The ordinary three-per-candidate sample is already cached. For a second
    # pass, inspect remaining filings only inside still-unresolved intervals;
    # never broaden an ambiguous ticker/CIK association automatically.
    for cik, start, end in unresolved:
        for row in by_cik.get(identity.normalize_cik(cik), []):
            if start <= row[2] < end:
                selected[row[0]] = row
    directory = config.DATA_DIR / "history_refresh" / "validation_1996_2015" / "instances"
    already_cached = 0
    pending: list[tuple[str, str, Path]] = []
    for accn, cik, _filed, instance in sorted(selected.values(), key=lambda row: (row[2], row[0])):
        path = directory / f"{accn}.xml"
        if path.exists():
            already_cached += 1
            continue
        if len(pending) >= limit:
            continue
        url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
               f"{accn.replace('-', '')}/{instance}")
        pending.append((accn, url, path))
    # Pace starts across workers: 4/s, including retries, below SEC's 10/s cap.
    pace_lock = threading.Lock()
    next_start = time.monotonic()

    def paced_download(url: str, path: Path) -> None:
        nonlocal next_start
        with pace_lock:
            now = time.monotonic()
            delay = max(0, next_start - now)
            next_start = max(now, next_start) + 0.25
        if delay:
            time.sleep(delay)
        sec_history.download(url, path)

    def fetch_one(accn: str, url: str, path: Path) -> tuple[str, str | None]:
        for attempt in range(3):
            try:
                paced_download(url, path)
                return accn, None
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                return accn, str(exc)
            except (requests.RequestException, OSError, ValueError) as exc:
                return accn, str(exc)
        return accn, "retries exhausted"

    fetched = failures = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch_one, *item) for item in pending]
        for future in as_completed(futures):
            accn, error = future.result()
            if error:
                failures += 1
                print(f"SEC identity download failed {accn}: {error}", flush=True)
            else:
                fetched += 1
            if (fetched + failures) % 50 == 0:
                print(f"SEC identity covers attempted: {fetched + failures}", flush=True)
    return {"selected_filings": len(selected), "already_cached": already_cached,
            "fetched": fetched, "failed": failures,
            "candidates_with_fewer_than_two_filings": missing_candidates,
            "prioritize_unresolved": prioritize_unresolved}


def import_nominated_filings(period: Period = P2010) -> dict:
    """Index SEC bulk 10-K/10-Q rows for nominated CIKs from the cached archive.

    The quarterly Financial Statement Data Sets are already archived with
    their URL/SHA-256; this only adds rows for CIKs no candidate selected.
    """
    ciks = {row["cik"] for row in identity_nominations()}
    with storage.get_connection() as conn:
        sec_history.ensure_schema(conn)
        # Present means indexed for this period's quarters, not for another period.
        first_year = period.years.start - (1 if period is P2010 else 0)
        present = {row[0] for row in conn.execute(
            "SELECT DISTINCT cik FROM sec_bulk_submissions WHERE filed_date>=? AND filed_date<?",
            (f"{first_year}-01-01", period.end_exclusive))}
    missing = ciks - present
    report: dict[str, object] = {"nominated_ciks": len(ciks), "missing_before": len(missing)}
    if not missing:
        return report
    for year in range(period.years.start - (1 if period is P2010 else 0), period.years.stop):
        for quarter in range(1, 5):
            key = f"{year}q{quarter}"
            url = f"https://www.sec.gov/files/dera/data/financial-statement-data-sets/{key}.zip"
            path = sec_history.download(url, sec_history.DIRECTORY / f"{key}.zip")
            report[key] = sec_history.import_quarter(path, url, missing, facts=period is P2010)
            print(key, report[key], flush=True)
    return report


def import_period_filings(period: Period) -> dict:
    """Index SEC bulk 10-K/10-Q submissions of every candidate CIK of a period.

    For 2010-2015 this was done by ``sec_history.run_bulk`` (#27). Only the
    SUB table is read here (form, filing date, instance, issuer name); facts
    for 2016+ come from Company Facts. Quarters already indexed are skipped.
    """
    with storage.get_connection() as conn:
        sec_history.ensure_schema(conn)
        ciks = {identity.normalize_cik(row[0]) for row in conn.execute(
            "SELECT DISTINCT cik FROM historical_issuer_candidates WHERE source_id=? AND cik<>'' "
            "AND replace(date_added,'*','')<? "
            "AND (date_removed IS NULL OR date_removed='' OR replace(date_removed,'*','')>=?)",
            (CANDIDATE_SOURCE, period.end_exclusive, period.start))}
    ciks |= {row["cik"] for row in identity_nominations()
             if row["valid_from"] < period.end_exclusive and row["valid_to"] > period.start}
    report: dict[str, object] = {"ciks": len(ciks)}
    # Only quarters inside the period: adding rows filed before it would
    # change the evidence of the previous period's intervals.
    for year in period.years:
        for quarter in range(1, 5):
            key = f"{year}q{quarter}"
            url = f"https://www.sec.gov/files/dera/data/financial-statement-data-sets/{key}.zip"
            path = sec_history.download(url, sec_history.DIRECTORY / f"{key}.zip")
            report[key] = sec_history.import_quarter(path, url, ciks, facts=False)
            print(key, report[key], flush=True)
    return report


def annual_report_symbol_evidence(limit: int, period: Period = P2010) -> dict:
    """Ticker proofs from 10-K text for intervals the XBRL covers left open.

    Early XBRL covers often omit ``dei:TradingSymbol``. The annual report's
    market section states the symbol; a report naming exactly one symbol is
    stored like a cover proof (URL + SHA-256), otherwise it is ignored.
    """
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    with storage.get_connection() as conn:
        rows = conn.execute(
            "SELECT symbol,cik,valid_from,valid_to,status FROM historical_identity_intervals "
            "WHERE source_id=? AND status IN ('unresolved','corroborated_candidate')",
            (period.identity_source,)).fetchall()
    nominated = {(row["label"], row["cik"]) for row in identity_nominations()}
    # Unresolved intervals, plus nominations still resting on one SEC ticker
    # observation; community-name corroborations are left as they are.
    targets = [row for row in rows if row[4] == "unresolved" or (row[0], row[1]) in nominated]
    downloads = 0
    records = []
    for _symbol, cik, start, end, _status in targets:
        life = issuer_evidence.listing_life(cik)
        if life is None:
            continue
        reports = [row for row in life["annual_reports"] if start <= row["filed"] < end]
        for report in [reports[index] for index in sorted({0, len(reports) - 1})] if reports else []:
            if downloads >= limit:
                break
            url, path = issuer_evidence.fetch_annual_report(cik, report)
            downloads += 1
            extended = period is not P2010
            symbols = issuer_evidence.annual_report_symbols(path.read_text(encoding="utf-8", errors="ignore"),
                                                            extended=extended)
            if extended and len(symbols) > 1:
                # Other companies' symbols (investees, spin-offs) appear in the
                # text; keep the one reviewed ticker of this CIK, if unique.
                reviewed = {ticker for row in identity_nominations() if row["cik"] == cik
                            and row["valid_from"] <= report["filed"] < row["valid_to"] for ticker in row["sec_tickers"]}
                symbols &= reviewed
            if len(symbols) != 1:
                continue
            with path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            records.append({"symbol": next(iter(symbols)), "cik": cik, "accession": report["accession"],
                            "filed_date": report["filed"], "historical_name": life["name"],
                            "historical_name_source": "sec_10k_text", "sha256": digest, "source_url": url})
    imported = historical_archive.import_filing_identity_evidence(records)
    return {"intervals": len(targets), "reports": downloads, "symbol_proofs": imported}


_name_tokens = identity_rules._name_tokens


_name_matches = identity_rules._name_matches


def fetch_issuer_name_histories(limit: int, period: Period = P2010) -> dict:
    """Cache SEC's official name chain for still-unresolved historical CIKs."""
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    with storage.get_connection() as conn:
        ciks = [row[0] for row in conn.execute(
            "SELECT DISTINCT cik FROM historical_identity_intervals "
            "WHERE source_id=? AND status='unresolved' AND cik IN "
            "(SELECT cik FROM sec_bulk_submissions GROUP BY cik HAVING COUNT(*)>=2) ORDER BY cik",
            (period.identity_source,))]
    directory = config.DATA_DIR / "history_refresh" / "validation_1996_2015" / "identity_submissions"
    cached = fetched = failed = 0
    for cik in ciks:
        path = directory / f"CIK{cik}.json"
        if path.exists():
            cached += 1
            continue
        if fetched + failed >= limit:
            break
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        try:
            sec_history.download(url, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            if identity.normalize_cik(payload["cik"]) != cik:
                raise ValueError("SEC submissions issuer CIK mismatch")
            fetched += 1
        except (requests.RequestException, OSError, ValueError, KeyError) as exc:
            failed += 1
            print(f"SEC issuer name history failed {cik}: {exc}", flush=True)
    return {"candidate_ciks": len(ciks), "cached": cached, "fetched": fetched, "failed": failed}


def _official_name_chain(cik: str) -> dict | None:
    return _name_reader().official_name_chain(cik)


def _name_reader():
    directory = config.DATA_DIR / 'history_refresh' / 'validation_1996_2015'
    return HistoricalIssuerFiles(directory / 'frames', directory / 'identity_submissions')


def build_evidence_intervals(period: Period = P2010) -> list[dict]:
    evidence = issuer_evidence.reader()
    return identity_audit.build_evidence_intervals(SqliteIdentityAuditReads(config.DB_PATH),
        _name_reader().official_name_chain, evidence.listing_life, identity_nominations(), period,
        prepare_evidence=evidence.prepare)


def coverage_report(period: Period = P2010) -> dict:
    return identity_audit.coverage_report(SqliteIdentityAuditReads(config.DB_PATH), period)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=P2010.key, help="Historical period (2010-2015 or 2016-2025)")
    parser.add_argument("--output", type=Path, help="Write the offline report as JSON")
    parser.add_argument("--scan-instances", action="store_true", help="Check locally cached original SEC XBRL files")
    parser.add_argument("--fetch-candidate-instances", type=int,
                        help="Download up to N selected SEC XBRL covers of the period for candidate checks")
    parser.add_argument("--fetch-unresolved-instances", type=int,
                        help="Download up to N extra SEC covers only for unresolved dated identity intervals")
    parser.add_argument("--import-period-filings", action="store_true",
                        help="Index SEC bulk 10-K/10-Q submissions of the period's candidate CIKs")
    parser.add_argument("--import-nominated-filings", action="store_true",
                        help="Index cached SEC bulk filings for reviewed CIK nominations")
    parser.add_argument("--annual-report-symbols", type=int,
                        help="Download up to N 10-Ks for open intervals and store stated ticker symbols")
    parser.add_argument("--fetch-issuer-names", type=int,
                        help="Download up to N SEC issuer name histories for unresolved CIKs")
    parser.add_argument("--evidence-csv", type=Path, help="Save accepted SEC filing-day identity evidence")
    parser.add_argument("--import-evidence", action="store_true",
                        help="Idempotently archive SEC filing-day observations; does not create aliases")
    parser.add_argument("--build-intervals", action="store_true",
                        help="Build a separate, retrospective SEC-corroborated identity tier")
    parser.add_argument("--intervals-csv", type=Path,
                        help="Write interval status, dates and SEC provenance for review")
    args = parser.parse_args()
    period = get_period(args.period)
    fetch_summary = None
    if args.import_period_filings:
        print(json.dumps(import_period_filings(period)), flush=True)
    if args.import_nominated_filings:
        print(json.dumps(import_nominated_filings(period)), flush=True)
    if args.annual_report_symbols is not None:
        print(json.dumps(annual_report_symbol_evidence(args.annual_report_symbols, period)), flush=True)
    if args.fetch_candidate_instances is not None and args.fetch_unresolved_instances is not None:
        parser.error("Choose only one SEC instance download mode")
    if args.fetch_candidate_instances is not None or args.fetch_unresolved_instances is not None:
        fetch_summary = fetch_candidate_instances(
            args.fetch_candidate_instances if args.fetch_candidate_instances is not None else args.fetch_unresolved_instances,
            prioritize_unresolved=args.fetch_unresolved_instances is not None, period=period)
        print(json.dumps(fetch_summary), flush=True)
    if args.fetch_issuer_names is not None:
        name_fetch = fetch_issuer_name_histories(args.fetch_issuer_names, period)
        print(json.dumps(name_fetch), flush=True)
    if (args.evidence_csv or args.import_evidence) and not args.scan_instances:
        parser.error("--evidence-csv and --import-evidence require --scan-instances")
    if args.intervals_csv and not args.build_intervals:
        parser.error("--intervals-csv requires --build-intervals")
    evidence_summary = None
    if args.scan_instances:
        records, summary = scan_local_sec_instances(period)
        evidence_summary = summary
        if args.import_evidence:
            summary["imported_observations"] = historical_archive.import_filing_identity_evidence(records)
            summary.update(SqliteIdentityAuditReads(config.DB_PATH).counts())
        if args.evidence_csv:
            audit_exports.export_evidence(HistoricalAuditFiles(), records, str(args.evidence_csv))
    if args.build_intervals:
        intervals = build_evidence_intervals(period)
        historical_archive.replace_identity_intervals(period.identity_source, intervals)
        counts = {status: sum(row["status"] == status for row in intervals)
                  for status in ("confirmed_by_multiple_evidence", "confirmed_historical_ticker",
                                 "corroborated_candidate",
                                 "ambiguous", "unresolved")}
        if args.intervals_csv:
            audit_exports.export_intervals(HistoricalAuditFiles(), intervals, str(args.intervals_csv))
    report = coverage_report(period)
    if fetch_summary:
        report["sec_candidate_download"] = fetch_summary
    if args.fetch_issuer_names is not None:
        report["sec_name_history_download"] = name_fetch
    if evidence_summary:
        report["sec_instance_evidence"] = evidence_summary
    if args.build_intervals:
        report["evidence_intervals"] = {"source_id": period.identity_source, "count": len(intervals),
                                        "statuses": counts,
                                        "note": "Retrospective corroboration, not a reviewed operational alias"}
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        audit_exports.export_report(HistoricalAuditFiles(), report, str(args.output))
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
