"""SEC issuer evidence for attributing historical price series (#28, #34).

Three kinds of free, archived SEC evidence are used, each cached with its URL
and SHA-256 through ``download`` (the pinned SEC archive store):

- submissions JSON: listing life of a CIK (first periodic report, holding
  company successions, delisting/deregistration followed by silence);
- XBRL frames for ``dei:EntityPublicFloat`` and share counts: an independent
  price *level* at the float date, which ties a price series to one issuer;
- XBRL frames for dividends per share: the cash events a split/dividend
  adjusted series must contain.

Nothing here decides a tier. ``historical_price_audit`` combines the checks and
fails closed when evidence is missing or contradictory.
"""

import argparse
import json
from pathlib import Path

from gabi.application.research import historical_issuer_evidence as evidence_downloads
from gabi.domain.research import issuer_evidence as issuer_rules
from gabi.domain.research.sec_bulk import instance_url
from gabi.infrastructure.providers import sec_archive
from gabi.infrastructure.storage.historical_issuer_evidence import HistoricalIssuerFiles
from gabi.infrastructure.storage.sec_archive_download import download_pinned

from . import config

DIRECTORY = config.DATA_DIR / "history_refresh" / "validation_1996_2015"
FRAMES_DIR = DIRECTORY / "frames"
SUBMISSIONS_DIR = DIRECTORY / "identity_submissions"


def download(url: str, path: Path) -> Path:
    """Pinned SEC archive download; the path and User-Agent are read per call (ADR 0005)."""
    return download_pinned(url, path, database=config.DB_PATH, user_agent=config.SEC_USER_AGENT)


FRAME_URL = issuer_rules.FRAME_URL
SUBMISSIONS_URL = issuer_rules.SUBMISSIONS_URL
FRAME_SPECS = issuer_rules.FRAME_SPECS
# Frames through 2025 (#34; 2008-2016 for #28). Floats are annual cover
# facts, so the last year's frames are still filling in.
FRAME_YEARS = issuer_rules.FRAME_YEARS
PERIODS = issuer_rules.PERIODS
ANNUAL_PERIODS = issuer_rules.ANNUAL_PERIODS
# SEC filing history read per CIK (submissions pages, 8-K and 10-K lists).
FILINGS_FROM = issuer_rules.FILINGS_FROM
FILINGS_TO = issuer_rules.FILINGS_TO
# A delisting counts as "no later public float" only with a year of frames after it.
FLOATLESS_BEFORE = issuer_rules.FLOATLESS_BEFORE


def _periods(kind: str) -> list[str]:
    return ANNUAL_PERIODS if kind == "dividend_payments" else PERIODS
PERIODIC_FORMS = issuer_rules.PERIODIC_FORMS
SUCCESSION_FORMS = issuer_rules.SUCCESSION_FORMS
DELISTING_FORMS = issuer_rules.DELISTING_FORMS
# Offerings and exchange registrations that can open an equity's trading life.
REGISTRATION_FORMS = issuer_rules.REGISTRATION_FORMS
# A delisting/deregistration only ends the equity's trading life when the
# issuer then stops filing periodic reports; debt or preferred delistings and
# exchange transfers are followed by further 10-Q/10-K reports.
SILENCE_DAYS = issuer_rules.SILENCE_DAYS
# Public float is held by non-affiliates, so float / (shares x close) is below
# one; controlled issuers go lower, and cover share counts are dated months
# after the float. Outside this band the price cannot be the issuer's
# as-traded price at the float date (another security, wrong split basis).
LEVEL_RATIO_LOW = issuer_rules.LEVEL_RATIO_LOW
LEVEL_RATIO_HIGH = issuer_rules.LEVEL_RATIO_HIGH
CLEAN_SPLITS = issuer_rules.CLEAN_SPLITS
# Larger one-day cash factors are spin-offs/special distributions whose value
# is not a verifiable cash dividend; they block an unreconciled window.
MAX_DIVIDEND_YIELD = issuer_rules.MAX_DIVIDEND_YIELD



def reader() -> HistoricalIssuerFiles:
    return HistoricalIssuerFiles(FRAMES_DIR, SUBMISSIONS_DIR, frame_specs=FRAME_SPECS,
                                periods=PERIODS, annual_periods=ANNUAL_PERIODS)


def _frame_path(kind: str, period: str) -> tuple[str, Path]:
    taxonomy, tag, unit, instant = FRAME_SPECS[kind]
    suffix = "I" if instant else ""
    url = FRAME_URL.format(taxonomy=taxonomy, tag=tag, unit=unit, period=period + suffix)
    return url, FRAMES_DIR / f"{taxonomy}_{tag}_{unit}_{period}{suffix}.json"


class _Documents:
    """SEC documents cached by file name with URL/SHA-256 provenance; the directory is read per call."""

    def __init__(self, directory: Path):
        self.directory = directory

    def exists(self, name: str) -> bool:
        return (self.directory / name).exists()

    def download(self, url: str, name: str) -> Path:
        return download(url, self.directory / name)

    def read(self, name: str) -> dict:
        return json.loads((self.directory / name).read_text(encoding="utf-8"))


def fetch_frames() -> dict:
    """Cache every quarterly frame used by the checks (idempotent)."""
    targets = []
    for kind in FRAME_SPECS:
        for period in _periods(kind):
            url, path = _frame_path(kind, period)
            targets.append((url, path.name))
    return evidence_downloads.fetch_frames(targets, _Documents(FRAMES_DIR), missing_error=sec_archive.HTTP_ERROR,
                                           status=sec_archive.http_status)


def fetch_submissions(ciks: set[str]) -> dict:
    """Cache SEC submissions, including older pages that overlap the filing window."""
    return evidence_downloads.fetch_submissions(
        ciks, _Documents(SUBMISSIONS_DIR), errors=(sec_archive.REQUEST_ERROR, OSError, ValueError, KeyError),
        log=lambda message: print(message, flush=True))


def load_frames() -> dict[str, dict[str, list[dict]]]:
    return reader().all_facts()


def issuer_facts(cik: str, frame_year_max: int | None = None) -> dict[str, list[dict]]:
    return reader().issuer_facts(cik, frame_year_max)


def listing_life(cik: str, floatless_before: str = FLOATLESS_BEFORE,
                 frame_year_max: int | None = None) -> dict | None:
    return reader().listing_life(cik, floatless_before, frame_year_max)


listing_checks = issuer_rules.listing_checks


listing_start = issuer_rules.listing_start


_price_on = issuer_rules._price_on


_shares_near = issuer_rules._shares_near


classify_level = issuer_rules.classify_level


level_status = issuer_rules.level_status


level_horizon = issuer_rules.level_horizon


price_level_checks = issuer_rules.price_level_checks


implied_events = issuer_rules.implied_events


verify_splits = issuer_rules.verify_splits


reconcile_dividends = issuer_rules.reconcile_dividends


_reports_no_dividend = issuer_rules._reports_no_dividend


ANNUAL_DIR = DIRECTORY / "annual_reports"
# Item 5 of a 10-K states where and under which symbol the equity trades.
SYMBOL_RE = issuer_rules.SYMBOL_RE


# "Xerox common stock (XRX) is listed on the New York Stock Exchange" (#34).
LISTED_SYMBOL_RE = issuer_rules.LISTED_SYMBOL_RE


annual_report_symbols = issuer_rules.annual_report_symbols


def fetch_annual_report(cik: str, report: dict) -> tuple[str, Path]:
    url = instance_url(cik, report["accession"], report["primary"])
    return url, download(url, ANNUAL_DIR / f"{report['accession']}_{Path(report['primary']).name}")


TERMINAL_DIR = DIRECTORY / "terminal_8k"
TERMINAL_ITEMS = issuer_rules.TERMINAL_ITEMS
RECEIVE_RE = issuer_rules.RECEIVE_RE
CASH_RE = issuer_rules.CASH_RE
STOCK_RE = issuer_rules.STOCK_RE
# Non-cash components next to a cash amount: shares (common or ordinary),
# contingent value rights, elections.
MIXED_RE = issuer_rules.MIXED_RE
ELECTION_RE = issuer_rules.ELECTION_RE


ONE_FOR_ONE_RE = issuer_rules.ONE_FOR_ONE_RE


one_for_one_quote = issuer_rules.one_for_one_quote


completion_reports = issuer_rules.completion_reports


def fetch_report(cik: str, report: dict) -> tuple[str, Path]:
    url = instance_url(cik, report["accession"], report["primary"])
    return url, download(url, TERMINAL_DIR / f"{report['accession']}_{Path(report['primary']).name}")


extract_terms = issuer_rules.extract_terms


classify_terminal = issuer_rules.classify_terminal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-frames", action="store_true")
    parser.add_argument("--fetch-submissions", type=Path,
                        help="Text file with one CIK per line to cache SEC submissions for")
    args = parser.parse_args()
    report = {}
    if args.fetch_frames:
        report["frames"] = fetch_frames()
    if args.fetch_submissions:
        ciks = {line.strip() for line in args.fetch_submissions.read_text().splitlines() if line.strip()}
        report["submissions"] = fetch_submissions(ciks)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
