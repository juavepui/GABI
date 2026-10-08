"""SEC issuer evidence for attributing historical price series (#28, #34).

Three kinds of free, archived SEC evidence are used, each cached with its URL
and SHA-256 through ``sec_history.download``:

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

import requests

from gabi.domain.research import issuer_evidence as issuer_rules
from gabi.infrastructure.storage.historical_issuer_evidence import HistoricalIssuerFiles

from . import identity, sec_history

DIRECTORY = sec_history.DIRECTORY
FRAMES_DIR = DIRECTORY / "frames"
SUBMISSIONS_DIR = DIRECTORY / "identity_submissions"
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


def fetch_frames() -> dict:
    """Cache every quarterly frame used by the checks (idempotent)."""
    fetched = cached = missing = 0
    for kind in FRAME_SPECS:
        for period in _periods(kind):
            url, path = _frame_path(kind, period)
            if path.exists():
                cached += 1
                continue
            try:
                sec_history.download(url, path)
                fetched += 1
            except requests.HTTPError as exc:
                # SEC returns 404 for frames without facts; record, never invent.
                if exc.response is not None and exc.response.status_code == 404:
                    missing += 1
                    continue
                raise
    return {"fetched": fetched, "cached": cached, "not_published": missing}


def fetch_submissions(ciks: set[str]) -> dict:
    """Cache SEC submissions, including older pages that overlap the filing window."""
    fetched = cached = failed = 0
    for cik in sorted(identity.normalize_cik(value) for value in ciks):
        path = SUBMISSIONS_DIR / f"CIK{cik}.json"
        try:
            if path.exists():
                cached += 1
            else:
                sec_history.download(SUBMISSIONS_URL.format(name=f"CIK{cik}.json"), path)
                fetched += 1
            payload = json.loads(path.read_text(encoding="utf-8"))
            if identity.normalize_cik(payload["cik"]) != cik:
                raise ValueError("SEC submissions issuer CIK mismatch")
            for page in payload.get("filings", {}).get("files", []):
                if page.get("filingFrom", "9999") > FILINGS_TO or page.get("filingTo", "0000") < FILINGS_FROM:
                    continue
                extra = SUBMISSIONS_DIR / page["name"]
                if not extra.exists():
                    sec_history.download(SUBMISSIONS_URL.format(name=page["name"]), extra)
                    fetched += 1
        except (requests.RequestException, OSError, ValueError, KeyError) as exc:
            failed += 1
            print(f"SEC submissions failed {cik}: {exc}", flush=True)
    return {"ciks": len(ciks), "fetched_files": fetched, "cached": cached, "failed": failed}


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
    url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
           f"{report['accession'].replace('-', '')}/{report['primary']}")
    return url, sec_history.download(url, ANNUAL_DIR / f"{report['accession']}_{Path(report['primary']).name}")


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
    url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
           f"{report['accession'].replace('-', '')}/{report['primary']}")
    return url, sec_history.download(url, TERMINAL_DIR / f"{report['accession']}_{Path(report['primary']).name}")


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
