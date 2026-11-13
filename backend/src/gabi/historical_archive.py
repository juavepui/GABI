"""Versioned historical source data, kept separate from operational Yahoo series.

Research archives can use different split conventions and reused tickers. Their
rows are queryable here without silently replacing the operational price cache.
"""
from datetime import date

import pandas as pd

from gabi.application.research import historical_archive as archive_imports
from gabi.application.research import historical_archive_reads as archive_queries
from gabi.application.research import historical_composition as composition
from gabi.domain.market.sec_identity import ACCREDITED_IDENTITY_TIERS as ACCREDITED_IDENTITY_TIERS
from gabi.domain.research import coverage as _coverage
from gabi.infrastructure.storage.historical_archive_reads import SqliteHistoricalArchiveReads
from gabi.infrastructure.storage.historical_archive_schema import SCHEMA as ARCHIVE_SCHEMA
from gabi.infrastructure.storage.historical_archive_writes import SqliteHistoricalArchiveWrites
from gabi.infrastructure.storage.historical_composition import LocalHistoricalComposition

from . import identity


def _reader():
    return SqliteHistoricalArchiveReads(identity._reader().path)


def _writer():
    return SqliteHistoricalArchiveWrites(identity._reader().path, today=date.today)


IDENTITY_INTERVAL_SOURCE = "sec-identity-evidence:2010-2015:v1"
# Research tiers that may attribute a historical label to one CIK. The
# historical-ticker tier covers labels applied retroactively by the source.

SCHEMA = ARCHIVE_SCHEMA


def register_source(source_id: str, metadata: dict):
    return archive_imports.register_source(_writer(), source_id, metadata)


def import_membership(source_id: str, frame: pd.DataFrame, start: str, end: str) -> int:
    return archive_imports.import_membership(_writer(), source_id, frame, start, end)


def get_membership(source_id: str, as_of: str) -> dict:
    return composition.membership(LocalHistoricalComposition(identity._reader().path), source_id, as_of)


def import_issuer_candidates(source_id: str, frame: pd.DataFrame) -> int:
    return archive_imports.import_issuer_candidates(_writer(), source_id, frame)


def import_price_chunk(source_id: str, frame: pd.DataFrame, symbols: set[str], start: str, end: str) -> dict:
    return archive_imports.import_price_chunk(_writer(), source_id, frame, symbols, start, end)


def get_prices(source_id: str, symbol: str, start: str, end: str) -> pd.DataFrame:
    return archive_queries.raw_prices(_reader(), source_id, symbol, start, end)


def import_sec_facts(source_id: str, candidate_symbol: str, cik: str, rows: list[dict], *, source_url: str | None = None) -> int:
    return archive_imports.import_sec_facts(_writer(), source_id, candidate_symbol, cik, rows, source_url=source_url)


def import_filing_identity_evidence(rows: list[dict]) -> int:
    return archive_imports.import_filing_identity_evidence(_writer(), rows)


def get_filing_identity_evidence(symbol: str, as_of: str) -> dict:
    return archive_queries.filing_identity(_reader(), symbol, as_of)


def list_filing_identity_evidence_as_of(symbol: str, as_of: str) -> dict:
    return archive_queries.filing_evidence_as_of(_reader(), symbol, as_of)


def replace_identity_intervals(source_id: str, rows: list[dict]) -> int:
    return archive_imports.replace_identity_intervals(_writer(), source_id, rows)


def source_summary() -> list[dict]:
    return archive_queries.source_summary(_reader())


def unique_historical_ciks(frame: pd.DataFrame, targets: set[str], live: dict, stored: dict) -> tuple[dict, dict]:
    return _coverage.unique_historical_ciks(frame, targets, live, stored)
