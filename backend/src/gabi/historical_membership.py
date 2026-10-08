"""Offline, source-attributed S&P 500 membership and dated ticker intervals.

These are reconstructed community snapshots, not certified index records or
issuer identities. A snapshot persists only inside its declared source horizon.
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from gabi.application.research import historical_composition as composition
from gabi.domain.research import historical_membership as composition_rules
from gabi.infrastructure.storage.historical_composition import HistoricalCompositionFiles, LocalHistoricalComposition
from gabi.infrastructure.storage.identity import SqliteIdentityReads

from . import config, historical_archive, universe
from .historical_period import REFERENCE_SOURCE, REFERENCE_SOURCE_FULL

OPERATIONAL_SOURCE = "hanshof:local+reviewed-extension"
REFERENCE_SOURCES = (REFERENCE_SOURCE, REFERENCE_SOURCE_FULL)
# The pinned fja05680 file downloaded in #26 (see historical_sources_1996_2015.json).
REFERENCE_FILE = config.DATA_DIR / "history_refresh" / "1996_2015" / "membership.csv"


_members = composition_rules._members


_snapshots = composition_rules._snapshots


_segment = composition_rules._segment


intervals = composition_rules.intervals


def _operational() -> tuple[pd.DataFrame, str]:
    return composition.load_operational(_composition())


def _archive(source_id: str = REFERENCE_SOURCE) -> tuple[pd.DataFrame, str]:
    return composition.load_archive(_composition(), source_id)


def import_full_reference(path: Path = REFERENCE_FILE) -> dict:
    return composition.import_full_reference(_files(), historical_archive._writer(), path)


def historical_backfill_manifest() -> Path:
    return Path(__file__).with_name("resources") / "historical_sources_1996_2015.json"


def _identities(symbols: set[str], as_of: str, *,
                interval_source: str = historical_archive.IDENTITY_INTERVAL_SOURCE) -> dict[str, dict]:
    return SqliteIdentityReads(config.DB_PATH).accredited(symbols, as_of, interval_source)


def constituents_as_of(as_of: str, *, source_id: str = OPERATIONAL_SOURCE,
                       compare_reference: bool = True,
                       identity_source: str = historical_archive.IDENTITY_INTERVAL_SOURCE) -> dict:
    return composition.constituents_as_of(_composition(), SqliteIdentityReads(config.DB_PATH), as_of,
        source_id=source_id, compare_reference=compare_reference, identity_source=identity_source)


def overlap_report(start: str = "2010-01-01", end_exclusive: str = "2016-01-01") -> dict:
    return composition.overlap_report(_composition(), _files(), start, end_exclusive)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Compare local historical S&P 500 membership sources; no network")
    parser.add_argument("--start", default="2010-01-01")
    parser.add_argument("--end-exclusive", default="2016-01-01")
    parser.add_argument("--date", help="Inspect one membership date instead of the annual overlap report")
    parser.add_argument("--import-full-reference", action="store_true",
                        help="Import the pinned fja05680 file over its full coverage (#34)")
    args = parser.parse_args()
    if args.import_full_reference:
        output = import_full_reference()
    elif args.date:
        result = constituents_as_of(args.date)
        output = {key: result[key] for key in ("as_of", "source_id", "source_date", "coverage_start",
                                                 "coverage_end_exclusive", "source_end_exclusive",
                                                 "comparison", "quality")}
        output["member_count"] = len(result["symbols"])
        output["resolved_identity_count"] = sum(row["identity_status"] == "resolved" for row in result["members"])
    else:
        output = overlap_report(args.start, args.end_exclusive)
    print(json.dumps(output, ensure_ascii=False, indent=2))




def _composition(db: Path | None = None):
    return LocalHistoricalComposition(
        db if db is not None else config.DB_PATH, universe.HISTORICAL_MEMBERSHIP_CACHE,
        Path(__file__).with_name("resources") / "sp500_extension.json", today=date.today)


def _files():
    return HistoricalCompositionFiles(universe.HISTORICAL_MEMBERSHIP_CACHE, historical_backfill_manifest())


if __name__ == "__main__":
    main()
