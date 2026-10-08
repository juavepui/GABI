"""Offline, conservative price-source audit for historical index members.

Run ``python -m gabi.historical_price_audit [--period 2016-2025]``; the default
period is 2010-2015 (#28), and 2016-2025 (#34) applies the same rules. This never copies an archived
price into the operational cache. A series is attributed to a CIK only when
SEC evidence covers its trading life and price level; a return overlap tests
adjustments, not ownership, and never fixes a delisting return.
"""
import argparse
import json
import sqlite3
from datetime import date
from pathlib import Path

import exchange_calendars as xcals
import pandas as pd

from gabi.application.research import historical_composition as composition
from gabi.application.research import historical_price_audit as price_audit
from gabi.domain.research import historical_price_audit as price_rules
from gabi.domain.research import price_accreditation
from gabi.infrastructure.storage.historical_audit_exports import HistoricalAuditFiles
from gabi.infrastructure.storage.historical_audit_writes import SCHEMA as _PROVENANCE_SCHEMA
from gabi.infrastructure.storage.historical_audit_writes import SqliteHistoricalAuditWrites
from gabi.infrastructure.storage.historical_price_audit import SqlitePriceAuditReads, series_from_connection
from gabi.infrastructure.storage.identity import SqliteIdentityReads

from . import config, historical_membership
from . import historical_issuer_evidence as issuer_evidence
from .historical_period import P2010, Period
from .historical_period import get as get_period
from .historical_price_policy import YAHOO_SOURCE
from .historical_ticker_corrections import identity_nominations
from .historical_tiingo import SOURCE_ID as TIINGO_SOURCE
from .historical_tiingo import source_id as tiingo_source
from .historical_wiki import SOURCE_ID as WIKI_SOURCE

PRICE_SOURCE = json.loads((Path(__file__).with_name("resources") /
                           "historical_sources_1996_2015.json").read_text(encoding="utf-8"))["price_source_id"]
OUTPUT = config.BASE_DIR / "docs" / "historical-prices-2010-2015.csv"
SUMMARY = config.BASE_DIR / "docs" / "historical-prices-2010-2015.json"
QUARTERLY_OUTPUT = config.BASE_DIR / "docs" / "historical-prices-quarterly-2010-2015.csv"
QUARTERLY_SUMMARY = config.BASE_DIR / "docs" / "historical-prices-quarterly-2010-2015.json"
PRODUCER = P2010.price_producer
QUARTERS = price_rules.QUARTERS
PROVENANCE_SCHEMA = _PROVENANCE_SCHEMA
AUDIT_URL = "https://github.com/juavepui/GABI/blob/develop/docs/historical-prices-quarterly-2010-2015.csv"


def outputs(period: Period) -> dict[str, Path | str]:
    """Annual/quarterly CSV and JSON outputs and the audit URL cited as evidence."""
    return {"csv": config.BASE_DIR / "docs" / f"historical-prices-{period.key}.csv",
            "json": config.BASE_DIR / "docs" / f"historical-prices-{period.key}.json",
            "quarterly_csv": config.BASE_DIR / "docs" / f"historical-prices-quarterly-{period.key}.csv",
            "quarterly_json": config.BASE_DIR / "docs" / f"historical-prices-quarterly-{period.key}.json",
            "url": ("https://github.com/juavepui/GABI/blob/develop/docs/"
                    f"historical-prices-quarterly-{period.key}.csv")}

MIN_OVERLAP = 60
MAX_P99_RETURN_DIFFERENCE = 0.005
# One day on which the sources disagree by more than this is an unreconciled
# corporate action (typically a spin-off one source did not adjust); p99 alone
# would hide it inside a year of matching returns.
MAX_EVENT_RETURN_DIFFERENCE = 0.05
# A one-day adjusted move this large in an archive-only window is treated as an
# unexplained distribution unless another source corroborates it.
MAX_UNCORROBORATED_ARCHIVE_RETURN = 0.25
# Further archived sources tried, in order, when neither Yahoo nor FINSABER qualifies.
EXTRA_SOURCES = {"tiingo": TIINGO_SOURCE, "wiki": WIKI_SOURCE}


def source_ids(period: Period) -> dict[str, str]:
    """Source id of each named price source for a period (Tiingo has one per window)."""
    return {"yahoo": YAHOO_SOURCE, "finsaber": PRICE_SOURCE, "tiingo": tiingo_source(period.key),
            "wiki": WIKI_SOURCE}
# Holding period after the last 2015 rebalance runs into 2016.
SERIES_END = P2010.series_end
# A holding bought at a rebalance needs prices until the first session on or
# after the next rebalance date; a week of slack covers holidays/weekends.
FORWARD_SLACK_DAYS = 7
ACCEPTED_ADJUSTMENTS = {"dividends_reconciled", "no_dividends_consistent"}


def _series(conn: sqlite3.Connection, symbol: str, start: str, end: str,
            *, archive: bool, source_id: str = PRICE_SOURCE) -> pd.DataFrame:
    return series_from_connection(conn, symbol, start, end, archive=archive, source_id=source_id)


assess_series = price_rules.assess_series


_adjacent_returns = price_accreditation._adjacent_returns


overlap_status = price_accreditation.overlap_status


same_traded_prices = price_rules.same_traded_prices


archive_adjustment = price_rules.archive_adjustment


choose_source = price_rules.choose_source


series_identity = price_rules.series_identity


def _nominated_price_symbol(label: str, cik: str | None, as_of: str, source: str) -> str:
    return price_rules._nominated_price_symbol(label, cik, as_of, source, identity_nominations())


continued_price_symbols = price_rules.continued_price_symbols


_as_traded_yahoo = price_rules._as_traded_yahoo


_level_checks = price_rules._level_checks


_split_ratios = price_rules._split_ratios


_proof = price_rules._proof


_short_history = price_rules._short_history


forward_coverage = price_rules.forward_coverage


_next_rebalance = price_rules._next_rebalance


def audit(db: Path, *, dates: list[str] | None = None, period: Period = P2010) -> tuple[pd.DataFrame, dict]:
    calendar = xcals.get_calendar("XNYS", start=period.series_start, end=f"{period.series_end[:4]}-12-31")
    evidence = issuer_evidence.reader()
    return price_audit.audit(SqlitePriceAuditReads(db),
        lambda day: composition.constituents_as_of(historical_membership._composition(db), SqliteIdentityReads(db), day, source_id=period.membership_source,
            compare_reference=False, identity_source=period.identity_source), evidence,
        calendar=calendar, source_ids=source_ids(period), nominations=identity_nominations(),
        database_name=db.name, dates=dates, period=period, prepare_evidence=evidence.prepare)


def summarize(result: pd.DataFrame, db: Path) -> dict:
    return price_rules.summarize(result, db.name, PRICE_SOURCE, EXTRA_SOURCES)


def promote(db: Path, frame: pd.DataFrame, period: Period = P2010) -> dict:
    if db != config.DB_PATH:
        raise ValueError("Promotion only supports the configured local database")
    return price_audit.promote(SqlitePriceAuditReads(db), _writer(db), frame, period=period,
                               source_ids=source_ids(period), audit_url=str(outputs(period)['url']))


def record_terminal_events(frame: pd.DataFrame, period: Period = P2010) -> dict:
    return price_audit.record_terminal_events(_writer(config.DB_PATH), issuer_evidence.reader(), _document, frame, period)


def record_succession_events(frame: pd.DataFrame, period: Period = P2010) -> dict:
    return price_audit.record_succession_events(SqlitePriceAuditReads(config.DB_PATH), _writer(config.DB_PATH),
        issuer_evidence.reader(), _document, frame, period=period, audit_url=str(outputs(period)['url']))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=config.DB_PATH)
    parser.add_argument("--period", default=P2010.key, help="Historical period (2010-2015 or 2016-2025)")
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--quarterly", action="store_true", help="Audit every quarter end of the period")
    parser.add_argument("--promote", "--promote-tier-a", dest="promote", action="store_true",
                        help="Persist SEC-backed Tier A/B intervals (replaces earlier audit rows)")
    parser.add_argument("--terminal-events", action="store_true",
                        help="Record SEC-evidenced terminal events for members delisted before the next rebalance")
    args = parser.parse_args()
    period = get_period(args.period)
    dates = period.quarters if args.quarterly else None
    if args.promote and args.db != config.DB_PATH:
        raise ValueError("Promotion only supports the configured local database")
    paths = outputs(period)
    csv = Path(args.csv or paths["quarterly_csv" if args.quarterly else "csv"])
    report = Path(args.json or paths["quarterly_json" if args.quarterly else "json"])
    calendar = xcals.get_calendar("XNYS", start=period.series_start, end=f"{period.series_end[:4]}-12-31")
    evidence = issuer_evidence.reader()
    summary = price_audit.run(SqlitePriceAuditReads(args.db),
        lambda day: composition.constituents_as_of(historical_membership._composition(args.db), SqliteIdentityReads(args.db), day, source_id=period.membership_source,
            compare_reference=False, identity_source=period.identity_source), evidence,
        calendar=calendar, source_ids=source_ids(period), nominations=identity_nominations(),
        database_name=args.db.name, writer=_writer(args.db), document=_document,
        exporter=HistoricalAuditFiles(), csv=csv, report=report, audit_url=str(paths['url']),
        period=period, dates=dates, promote_prices=args.promote, terminal_events=args.terminal_events,
        prepare_evidence=evidence.prepare)
    print(json.dumps({key: summary[key] for key in ("years", "promotion", "terminal_events") if key in summary},
                     ensure_ascii=False, indent=2))


def _writer(db: Path):
    return SqliteHistoricalAuditWrites(db, today=date.today)


def _document(cik: str, report: dict) -> tuple[str, str]:
    url, path = issuer_evidence.fetch_report(cik, report)
    return url, path.read_text(encoding="utf-8", errors="ignore")


if __name__ == "__main__":
    main()
