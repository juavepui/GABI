"""Explicit SEC quarter and original-instance ingestion with injected downloads, imports and checkpoints."""

from collections.abc import Callable, Iterable
from typing import Protocol

import pandas as pd

from gabi.domain.market.identity import normalize_cik
from gabi.domain.research import sec_bulk as rules
from gabi.domain.research.identity_instances import select_cover_filings


class Checkpoints(Protocol):
    def load(self) -> dict: ...
    def save(self, report: dict) -> None: ...


class IngestSelection(Protocol):
    def candidate_ciks_before(self, day: str) -> set[str]: ...
    def period_candidate_ciks(self, source_id: str, start: str, end_exclusive: str) -> set[str]: ...
    def bulk_ciks_filed(self, start: str, end_exclusive: str) -> set[str]: ...
    def submissions(self, forms: list[str]) -> pd.DataFrame: ...
    def accessions_with_facts(self) -> set: ...
    def period_candidates(self, source_id: str, start: str, end_exclusive: str) -> list[tuple]: ...
    def period_filings(self, start: str, end_exclusive: str) -> list[tuple]: ...
    def intervals(self, source_id: str, statuses: tuple[str, ...]) -> list[tuple]: ...


Log = Callable[..., None]


# The downloaded archive location is opaque here: it is only handed to the importer.
def ingest_quarters[Archive](keys: Iterable[str], ciks: set[str], *, download: Callable[[str, str], Archive],
                    import_quarter: Callable[[Archive, str, set[str], bool], dict],
                    facts: bool = True, report: dict | None = None, checkpoints: Checkpoints | None = None,
                    errors: tuple[type[BaseException], ...] = (), log: Log = lambda *args: None) -> dict:
    """Download and import each quarter in order.

    With ``checkpoints`` completed keys are skipped and each outcome is saved before
    the next key; listed ``errors`` become failed entries. Without them the first
    error stops the run, as an explicit one-off import does.
    """
    report = checkpoints.load() if checkpoints else dict(report or {})
    for key in keys:
        if checkpoints and report.get(key, {}).get("status") == "complete":
            continue
        url = rules.quarter_url(key)
        try:
            counts = import_quarter(download(url, f"{key}.zip"), url, ciks, facts)
            report[key] = {"status": "complete", **counts} if checkpoints else counts
        except errors as exc:
            report[key] = {"status": "failed", "error": str(exc)[:180]}
        if checkpoints:
            checkpoints.save(report)
        log(key, report[key])
    return report


def nominated_missing(selection: IngestSelection, nominated: set[str], *, start: str, end_exclusive: str) -> set[str]:
    return nominated - selection.bulk_ciks_filed(start, end_exclusive)


def period_ciks(selection: IngestSelection, source_id: str, *, start: str, end_exclusive: str,
                nominations: Iterable[dict]) -> set[str]:
    ciks = {normalize_cik(cik) for cik in selection.period_candidate_ciks(source_id, start, end_exclusive)}
    return ciks | {row["cik"] for row in nominations if row["valid_from"] < end_exclusive and row["valid_to"] > start}


def cover_filings(selection: IngestSelection, candidate_source: str, *, start: str, end_exclusive: str,
                  nominated: list[tuple], identity_source: str, prioritize_unresolved: bool) -> tuple[dict, int]:
    """Covers to cache for a period: candidate tenures, reviewed nominations and, optionally,
    every filing inside still-unresolved intervals."""
    candidates = selection.period_candidates(candidate_source, start, end_exclusive) + nominated
    unresolved = [row[1:4] for row in selection.intervals(identity_source, ("unresolved",))] \
        if prioritize_unresolved else []
    return select_cover_filings(candidates, selection.period_filings(start, end_exclusive), unresolved,
                                start=start, end_exclusive=end_exclusive)


def recover_instances(selection: IngestSelection, *, limit: int, quarterly: bool, unmatched: set | None,
                      checkpoints: Checkpoints, fetch: Callable[[str, str], bytes], parse: Callable[..., list[dict]],
                      import_facts: Callable[[str, str, list[dict], str], None],
                      errors: tuple[type[BaseException], ...], log: Log = lambda *args: None) -> dict:
    """Recover exact contexts for filings lacking them, saving each outcome before the next."""
    forms = rules.instance_forms(quarterly=quarterly, unmatched=unmatched is not None)
    submissions = selection.submissions(forms)
    existing = set() if unmatched is not None else selection.accessions_with_facts()
    report = checkpoints.load()
    for row in rules.missing_instances(submissions, existing, unmatched).head(limit).itertuples(index=False):
        if report.get(row.accn, {}).get("status") == "complete" and unmatched is None:
            continue
        url = rules.instance_url(row.cik, row.accn, row.instance)
        try:
            rows = parse(fetch(url, f"instances/{row.accn}.xml"), cik=row.cik, accn=row.accn, filed_date=row.filed_date,
                         form=row.form, fp=row.fp, fy=row.fy)
            import_facts(f"CIK{row.cik}", row.cik, rows, url)
            report[row.accn] = {"status": "complete", "cik": row.cik, "rows": len(rows), "url": url}
        except errors as exc:
            report[row.accn] = {"status": "failed", "error": str(exc)[:180], "url": url}
        checkpoints.save(report)
        log(row.accn, report[row.accn]["status"])
    return report


def ingest_companyfacts(ciks: Iterable[str], *, fetch: Callable[[str, str], dict],
                        rows_for: Callable[[dict, str], list], save: Callable[[str, list, str], None],
                        errors: tuple[type[BaseException], ...], with_url: bool,
                        checkpoints: Checkpoints | None = None, log: Log = lambda *args: None) -> dict:
    """Company Facts by CIK only, under a ``CIK##########`` placeholder symbol, never a ticker.

    With ``checkpoints`` the whole report is saved after every issuer (it is not resumed).
    """
    report: dict = {}
    for cik in ciks:
        url = rules.companyfacts_url(cik)
        try:
            rows = rows_for(fetch(url, f"companyfacts/CIK{cik}.json"), cik)
            save(cik, rows, url)
            report[cik] = {"status": "complete", "rows": len(rows), **({"url": url} if with_url else {})}
        except errors as exc:
            report[cik] = {"status": "failed", "error": str(exc)[:180], **({"url": url} if with_url else {})}
        if checkpoints:
            checkpoints.save(report)
            log(cik, report[cik]["status"])
    return report
