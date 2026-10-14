"""Offline identity coverage for the archived S&P 500 universe, per period (``gabi_cli research identity-audit``).

2010-2015 (#27) and 2016-2025 (#34) use the same rules; each period writes
its own interval source (``historical_period``). This bridge composes the
use cases with the archive, SEC history and issuer evidence modules.

Community ticker/CIK rows are candidates. Direct SEC ticker evidence and
retrospective issuer corroboration have separate tiers; an issuer name alone
cannot certify a ticker or activate an operational alias.
"""

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path

from gabi import config, historical_archive, sec_history
from gabi import historical_issuer_evidence as issuer_evidence
from gabi.application.research import historical_audit_exports as audit_exports
from gabi.application.research import historical_identity_audit as identity_audit
from gabi.application.research import identity_instances as instance_scan
from gabi.application.research import sec_cover_downloads as cover_downloads
from gabi.application.research import sec_quarter_ingest as quarter_ingest
from gabi.domain.research import historical_identity_audit as identity_rules
from gabi.domain.research import identity_instances as instance_rules
from gabi.domain.research import sec_bulk as bulk_rules
from gabi.domain.research.periods import P2010, Period
from gabi.domain.research.periods import get as get_period
from gabi.infrastructure.providers import sec_archive
from gabi.infrastructure.storage.historical_audit_exports import HistoricalAuditFiles
from gabi.infrastructure.storage.historical_identity_audit import SqliteIdentityAuditReads
from gabi.infrastructure.storage.historical_issuer_evidence import HistoricalIssuerFiles
from gabi.infrastructure.storage.identity_instances import LocalIdentityInstances, SqliteIdentityInstances
from gabi.infrastructure.storage.reviewed_resources import identity_nominations
from gabi.infrastructure.storage.sec_quarter_ingest import SqliteSecIngestSelection

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
    nominated = identity_rules.nominated_windows(identity_nominations())
    selected, missing_candidates = quarter_ingest.cover_filings(
        _ingest_selection(), CANDIDATE_SOURCE, start=period.start, end_exclusive=period.end_exclusive,
        nominated=nominated, identity_source=period.identity_source, prioritize_unresolved=prioritize_unresolved)
    directory = config.DATA_DIR / "history_refresh" / "validation_1996_2015" / "instances"
    already_cached, pending = cover_downloads.pending_covers(
        selected, limit, cached=lambda accn: (directory / f"{accn}.xml").exists())
    # Pace starts across workers: 4/s, including retries, below SEC's 10/s cap.
    counts = cover_downloads.download_covers(
        pending, download=lambda url, accn: sec_history.download(url, directory / f"{accn}.xml"),
        errors=(sec_archive.REQUEST_ERROR, OSError, ValueError), status=sec_archive.http_status,
        parallel=sec_archive.parallel, clock=time.monotonic, wait=lambda seconds: time.sleep(seconds), log=_log)
    return {"selected_filings": len(selected), "already_cached": already_cached, **counts,
            "candidates_with_fewer_than_two_filings": missing_candidates,
            "prioritize_unresolved": prioritize_unresolved}


def _ingest_selection() -> SqliteSecIngestSelection:
    # The compatibility setting is captured per operation, never mutated.
    return SqliteSecIngestSelection(config.DB_PATH)


def _download_quarter(url: str, name: str) -> Path:
    return sec_history.download(url, sec_history.DIRECTORY / name)


def _import_quarter(path: Path, url: str, ciks: set[str], facts: bool) -> dict:
    return sec_history.import_quarter(path, url, ciks, facts=facts)


def _log(*values) -> None:
    print(*values, flush=True)


def import_nominated_filings(period: Period = P2010) -> dict:
    """Index SEC bulk 10-K/10-Q rows for nominated CIKs from the cached archive.

    The quarterly Financial Statement Data Sets are already archived with
    their URL/SHA-256; this only adds rows for CIKs no candidate selected.
    """
    ciks = {row["cik"] for row in identity_nominations()}
    # Present means indexed for this period's quarters, not for another period.
    first_year = period.years.start - (1 if period is P2010 else 0)
    missing = quarter_ingest.nominated_missing(_ingest_selection(), ciks, start=f"{first_year}-01-01",
                                               end_exclusive=period.end_exclusive)
    report: dict[str, object] = {"nominated_ciks": len(ciks), "missing_before": len(missing)}
    if not missing:
        return report
    return quarter_ingest.ingest_quarters(
        bulk_rules.quarter_keys(range(first_year, period.years.stop)), missing,
        download=_download_quarter, import_quarter=_import_quarter,
        facts=period is P2010, report=report, log=_log)


def import_period_filings(period: Period) -> dict:
    """Index SEC bulk 10-K/10-Q submissions of every candidate CIK of a period.

    For 2010-2015 this was done by ``sec_history.run_bulk`` (#27). Only the
    SUB table is read here (form, filing date, instance, issuer name); facts
    for 2016+ come from Company Facts. Quarters already indexed are skipped.
    """
    ciks = quarter_ingest.period_ciks(_ingest_selection(), CANDIDATE_SOURCE, start=period.start,
                                      end_exclusive=period.end_exclusive, nominations=identity_nominations())
    # Only quarters inside the period: adding rows filed before it would
    # change the evidence of the previous period's intervals.
    return quarter_ingest.ingest_quarters(
        bulk_rules.quarter_keys(period.years), ciks, download=_download_quarter,
        import_quarter=_import_quarter, facts=False, report={"ciks": len(ciks)}, log=_log)


def annual_report_symbol_evidence(limit: int, period: Period = P2010) -> dict:
    """Ticker proofs from 10-K text for intervals the XBRL covers left open (see the use case)."""
    def digest(path: Path) -> str:
        with path.open("rb") as source:
            return hashlib.file_digest(source, "sha256").hexdigest()

    records, targets, downloads = identity_audit.annual_report_symbol_evidence(
        lambda: _ingest_selection().intervals(period.identity_source, ("unresolved", "corroborated_candidate")),
        identity_nominations(), limit, extended=period is not P2010, listing_life=issuer_evidence.listing_life,
        fetch_annual_report=issuer_evidence.fetch_annual_report,
        text=lambda path: path.read_text(encoding="utf-8", errors="ignore"), digest=digest,
        symbols=lambda text, extended: issuer_evidence.annual_report_symbols(text, extended=extended))
    imported = historical_archive.import_filing_identity_evidence(records)
    return {"intervals": targets, "reports": downloads, "symbol_proofs": imported}


_name_tokens = identity_rules._name_tokens


_name_matches = identity_rules._name_matches


def fetch_issuer_name_histories(limit: int, period: Period = P2010) -> dict:
    """Cache SEC's official name chain for still-unresolved historical CIKs."""
    directory = config.DATA_DIR / "history_refresh" / "validation_1996_2015" / "identity_submissions"

    def download(cik: str) -> dict:
        path = directory / f"CIK{cik}.json"
        sec_history.download(f"https://data.sec.gov/submissions/CIK{cik}.json", path)
        return json.loads(path.read_text(encoding="utf-8"))

    return identity_audit.fetch_issuer_name_histories(
        lambda: _ingest_selection().unresolved_ciks_with_filings(period.identity_source), limit,
        cached=lambda cik: (directory / f"CIK{cik}.json").exists(), download=download,
        errors=(sec_archive.REQUEST_ERROR, OSError, ValueError, KeyError), log=_log)


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


def command(period_key: str, *, emit: Callable[[dict], None], output: Path | None = None,
            scan_instances: bool = False, fetch_candidates: int | None = None, fetch_unresolved: int | None = None,
            import_period: bool = False, import_nominated: bool = False, annual_report_symbols: int | None = None,
            fetch_issuer_names: int | None = None, evidence_csv: Path | None = None, import_evidence: bool = False,
            build_intervals: bool = False, intervals_csv: Path | None = None) -> dict | None:
    """The command's steps in their published order; ``emit`` receives each step's summary.

    Returns the coverage report, or None when it was written to ``output``."""
    period = get_period(period_key)
    fetch_summary = None
    if import_period:
        emit(import_period_filings(period))
    if import_nominated:
        emit(import_nominated_filings(period))
    if annual_report_symbols is not None:
        emit(annual_report_symbol_evidence(annual_report_symbols, period))
    cover_limit = fetch_candidates if fetch_candidates is not None else fetch_unresolved
    if cover_limit is not None:
        fetch_summary = fetch_candidate_instances(cover_limit, prioritize_unresolved=fetch_unresolved is not None,
                                                  period=period)
        emit(fetch_summary)
    if fetch_issuer_names is not None:
        name_fetch = fetch_issuer_name_histories(fetch_issuer_names, period)
        emit(name_fetch)
    evidence_summary = None
    if scan_instances:
        records, summary = scan_local_sec_instances(period)
        evidence_summary = summary
        if import_evidence:
            summary["imported_observations"] = historical_archive.import_filing_identity_evidence(records)
            summary.update(SqliteIdentityAuditReads(config.DB_PATH).counts())
        if evidence_csv:
            audit_exports.export_evidence(HistoricalAuditFiles(), records, str(evidence_csv))
    if build_intervals:
        intervals = build_evidence_intervals(period)
        historical_archive.replace_identity_intervals(period.identity_source, intervals)
        counts = {status: sum(row["status"] == status for row in intervals)
                  for status in ("confirmed_by_multiple_evidence", "confirmed_historical_ticker",
                                 "corroborated_candidate",
                                 "ambiguous", "unresolved")}
        if intervals_csv:
            audit_exports.export_intervals(HistoricalAuditFiles(), intervals, str(intervals_csv))
    report = coverage_report(period)
    if fetch_summary:
        report["sec_candidate_download"] = fetch_summary
    if fetch_issuer_names is not None:
        report["sec_name_history_download"] = name_fetch
    if evidence_summary:
        report["sec_instance_evidence"] = evidence_summary
    if build_intervals:
        report["evidence_intervals"] = {"source_id": period.identity_source, "count": len(intervals),
                                        "statuses": counts,
                                        "note": "Retrospective corroboration, not a reviewed operational alias"}
    if output:
        audit_exports.export_report(HistoricalAuditFiles(), report, str(output))
        return None
    return report
