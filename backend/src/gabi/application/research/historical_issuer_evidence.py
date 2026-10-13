"""Listing evidence assembled from explicit local submissions and frame facts."""

from collections.abc import Callable, Iterable
from typing import Protocol

from gabi.domain.market.identity import normalize_cik
from gabi.domain.research import issuer_evidence


class IssuerFiles(Protocol):
    def submissions(self, cik: str) -> tuple[dict, list[dict]] | None: ...
    def issuer_facts(self, cik: str, frame_year_max: int | None = None) -> dict: ...


def listing_life(reader: IssuerFiles, cik: str, floatless_before: str,
                 frame_year_max: int | None = None) -> dict | None:
    cik = normalize_cik(cik)
    documents = reader.submissions(cik)
    if documents is None:
        return None
    payload, pages = documents
    return issuer_evidence.listing_life(cik, payload, pages, reader.issuer_facts(cik, frame_year_max),
                                       floatless_before)


class SubmissionFiles(Protocol):
    def exists(self, name: str) -> bool: ...
    def download(self, url: str, name: str) -> object: ...
    def read(self, name: str) -> dict: ...


def fetch_frames(targets: Iterable[tuple[str, str]], files: SubmissionFiles, *, missing_error: type[BaseException],
                 status: Callable[[BaseException], int | None]) -> dict:
    """Cache every (url, name) frame once; SEC answers 404 for frames without facts: recorded, never invented."""
    fetched = cached = missing = 0
    for url, name in targets:
        if files.exists(name):
            cached += 1
            continue
        try:
            files.download(url, name)
            fetched += 1
        except missing_error as exc:
            if status(exc) == 404:
                missing += 1
                continue
            raise
    return {"fetched": fetched, "cached": cached, "not_published": missing}


def fetch_submissions(ciks: set[str], files: SubmissionFiles, *, errors: tuple[type[BaseException], ...],
                      log: Callable[[str], None]) -> dict:
    """Cache SEC submissions, including older pages that overlap the filing window; failures are per CIK."""
    fetched = cached = failed = 0
    for cik in sorted(normalize_cik(value) for value in ciks):
        name = f"CIK{cik}.json"
        try:
            if files.exists(name):
                cached += 1
            else:
                files.download(issuer_evidence.SUBMISSIONS_URL.format(name=name), name)
                fetched += 1
            payload = files.read(name)
            if normalize_cik(payload["cik"]) != cik:
                raise ValueError("SEC submissions issuer CIK mismatch")
            for page in payload.get("filings", {}).get("files", []):
                if page.get("filingFrom", "9999") > issuer_evidence.FILINGS_TO                         or page.get("filingTo", "0000") < issuer_evidence.FILINGS_FROM:
                    continue
                if not files.exists(page["name"]):
                    files.download(issuer_evidence.SUBMISSIONS_URL.format(name=page["name"]), page["name"])
                    fetched += 1
        except errors as exc:
            failed += 1
            log(f"SEC submissions failed {cik}: {exc}")
    return {"ciks": len(ciks), "fetched_files": fetched, "cached": cached, "failed": failed}
