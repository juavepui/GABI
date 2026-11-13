"""Load local composition sources without implicit imports or downloads."""

from datetime import date, timedelta
from typing import Protocol

import pandas as pd

from gabi.application.research.historical_archive import HistoricalArchiveWriter, import_membership, register_source
from gabi.domain.research.historical_membership import compare_compositions, composition_at
from gabi.domain.research.periods import REFERENCE_SOURCE, REFERENCE_SOURCE_FULL
from gabi.domain.research.ticker_corrections import correct_symbols

OPERATIONAL_SOURCE = "hanshof:local+reviewed-extension"

class CompositionReader(Protocol):
    def operational(self) -> tuple[pd.DataFrame, str]: ...
    def archive(self, source_id: str) -> tuple[pd.DataFrame, str]: ...
    def membership(self, source_id: str, as_of: str) -> dict: ...


def load_operational(reader: CompositionReader) -> tuple[pd.DataFrame, str]:
    return reader.operational()


def load_archive(reader: CompositionReader, source_id: str) -> tuple[pd.DataFrame, str]:
    return reader.archive(source_id)


def membership(reader: CompositionReader, source_id: str, as_of: str) -> dict:
    return reader.membership(source_id, as_of)


class CompositionIdentityReader(Protocol):
    def accredited(self, symbols: set[str], as_of: str, interval_source: str) -> dict[str, dict]: ...


class CompositionFiles(Protocol):
    def fingerprint(self) -> str: ...
    def pinned(self, path) -> tuple[pd.DataFrame, str, dict]: ...


def constituents_as_of(reader: CompositionReader, identities: CompositionIdentityReader, as_of: str, *,
                       source_id: str = OPERATIONAL_SOURCE, compare_reference: bool = True,
                       identity_source: str) -> dict:
    day = date.fromisoformat(as_of).isoformat()
    if source_id == OPERATIONAL_SOURCE:
        frame, end = reader.operational()
    elif source_id in (REFERENCE_SOURCE, REFERENCE_SOURCE_FULL):
        frame, end = reader.archive(source_id)
    else:
        raise ValueError(f"Unknown membership source: {source_id}")
    source_end, end, dates, source_date, symbols, corrections, corrected_intervals = composition_at(frame, day, end, source_id)
    resolved = identities.accredited(symbols, day, identity_source)
    members = [{**corrected_intervals[symbol], **resolved[symbol], "source_id": source_id,
                "membership_status": "community_unverified"} for symbol in sorted(symbols)]
    accredited_symbols = sorted(row["symbol"] for row in members if row["identity_status"] == "resolved")
    excluded_identity_symbols = sorted(row["symbol"] for row in members if row["identity_status"] != "resolved")
    comparison: dict[str, object] = {"status": "not_requested", "reference_source_id": REFERENCE_SOURCE}
    if compare_reference and source_id == OPERATIONAL_SOURCE:
        try:
            reference = reader.membership(REFERENCE_SOURCE, day)
        except ValueError:
            comparison["status"] = "outside_reference_coverage_or_not_imported"
        else:
            other, _ = correct_symbols(set(reference["symbols"]), day)
            comparison.update(status="agree" if symbols == other else "conflict",
                              primary_only=sorted(symbols - other), reference_only=sorted(other - symbols),
                              reference_date=reference["source_date"])
    return {"as_of": day, "source_id": source_id, "source_date": source_date,
            "coverage_start": dates[0], "coverage_end_exclusive": end,
            "source_end_exclusive": source_end,
            "symbols": sorted(symbols), "members": members, "comparison": comparison,
            "accredited_symbols": accredited_symbols,
            "excluded_identity_symbols": excluded_identity_symbols,
            "label_corrections": corrections,
            "quality": "community_unverified"}

def overlap_report(reader: CompositionReader, files: CompositionFiles, start: str, end_exclusive: str) -> dict:
    date.fromisoformat(start)
    date.fromisoformat(end_exclusive)
    primary, primary_end = reader.operational()
    reference, reference_end = reader.archive(REFERENCE_SOURCE)
    return compare_compositions(primary, primary_end, reference, reference_end, start, end_exclusive,
                                files.fingerprint(), OPERATIONAL_SOURCE, REFERENCE_SOURCE)


def import_full_reference(files: CompositionFiles, writer: HistoricalArchiveWriter, path) -> dict:
    frame, digest, item = files.pinned(path)
    start = str(frame['date'].min())
    end = (date.fromisoformat(str(frame['date'].max())) + timedelta(days=1)).isoformat()
    register_source(writer, REFERENCE_SOURCE_FULL, {
        **item, "start": start, "end_exclusive": end, "quality": "community_reference",
        "note": "same pinned file as the 2010-2015 source, imported over its full coverage (#34)"})
    snapshots = import_membership(writer, REFERENCE_SOURCE_FULL, frame, start, end)
    return dict(source_id=REFERENCE_SOURCE_FULL, sha256=digest, start=start, end_exclusive=end, snapshots=snapshots)
