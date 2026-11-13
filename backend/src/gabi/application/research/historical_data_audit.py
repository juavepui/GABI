"""Offline annual inventory over a bounded, read-only audit port."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd

from gabi.domain.research.coverage import CoverageParameters
from gabi.domain.research.historical_data_audit import old_block_counts, pick_snapshot, verified_owners


@dataclass(frozen=True)
class AuditMetadata:
    operational: pd.DataFrame
    old_detail: pd.DataFrame
    archive: pd.DataFrame
    aliases: pd.DataFrame
    issuer_entities_by_year: dict[str, int]
    last_spy: str | None


class AnnualAuditReader(Protocol):
    def metadata(self) -> AuditMetadata: ...
    def annual_metrics(self, symbols: list[str], day: str, parameters: CoverageParameters) -> dict[str, int]: ...
    def year_counts(self, symbols: list[str], year: int, day: str) -> dict[str, int]: ...


class AuditWriter(Protocol):
    def save(self, frame: pd.DataFrame) -> None: ...


def audit_rows(reader: AnnualAuditReader, *, parameters: CoverageParameters = CoverageParameters(),
               progress: Callable[[str], None] | None = None) -> Iterator[dict]:
    """One year at a time; the input cache is never changed or downloaded."""
    metadata = reader.metadata()
    if metadata.last_spy is None:
        raise ValueError("SPY has no adjusted close")
    for year in range(2008, min(2026, date.fromisoformat(metadata.last_spy).year) + 1):
        source = metadata.archive if year <= 2015 else metadata.operational
        day = min(f"{year}-12-31", metadata.last_spy, str(source.date.max()))
        snapshot, symbols = pick_snapshot(source, day)
        symbols = list(dict.fromkeys(symbols))
        if year <= 2015:
            metrics = old_block_counts(metadata.old_detail, f"{year}-12-31", parameters=parameters)
            quarter = metadata.old_detail[metadata.old_detail.date == f"{year}-12-31"]
            if len(quarter) != len(symbols) or set(quarter.symbol) != set(symbols):
                raise ValueError(f"Historical audit membership changed in {year}; regenerate it")
            metric_source = "issuer_exact_candidate_CIK"
        else:
            metrics = reader.annual_metrics(symbols, day, parameters)
            metric_source = "legacy_ticker_approximate"
        counts = reader.year_counts(symbols, year, day)
        row = {"year": year, "as_of": day, "membership_snapshot": snapshot,
               "membership_source": "fja_archive" if year <= 2015 else "hans_reviewed_extension",
               "members": len(symbols), "aliases_verified": verified_owners(metadata.aliases, symbols, day),
               **counts, "issuer_entities_filed_year": metadata.issuer_entities_by_year.get(str(year), 0),
               "metric_source": metric_source, **metrics}
        # Preserve the original CSV field order independently of port internals.
        order = ("year", "as_of", "membership_snapshot", "membership_source", "members", "aliases_verified",
                 "prices_year", "adjusted_prices_year", "adjusted_price_recent_10d", "archive_prices_year",
                 "archive_adjusted_year", "split_events_year", "legacy_sec_recent", "issuer_entities_filed_year",
                 "archive_ciks_filed_year", "metric_source", *metrics)
        yield {key: row[key] for key in order}
        if progress:
            progress(f"{year}: {len(symbols)} members, {metrics['all_13']} with 13 numeric metrics")


def audit(reader: AnnualAuditReader, *, parameters: CoverageParameters = CoverageParameters(),
          progress: Callable[[str], None] | None = None) -> pd.DataFrame:
    return pd.DataFrame(audit_rows(reader, parameters=parameters, progress=progress))


def publish_audit(reader: AnnualAuditReader, writer: AuditWriter, *,
                  parameters: CoverageParameters = CoverageParameters(),
                  progress: Callable[[str], None] | None = None) -> pd.DataFrame:
    frame = audit(reader, parameters=parameters, progress=progress)
    writer.save(frame)
    return frame
