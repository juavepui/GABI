"""Accredited historical price intervals and terminal-event accounting.

The research archive and the operational Yahoo cache remain separate. This
module stores the evidence needed to use a *specific* source/symbol/CIK interval
and fails closed when an adjusted-return series cannot be established.
"""

from datetime import date

import pandas as pd

from gabi.application.research import historical_accreditation as accreditation
from gabi.application.research import historical_archive_reads as archive_queries
from gabi.domain.research import price_accreditation
from gabi.infrastructure.storage import historical_audit_writes as audit_storage
from gabi.infrastructure.storage.historical_archive_reads import SqliteHistoricalArchiveReads
from gabi.infrastructure.storage.historical_archive_schema import SCHEMA as _ARCHIVE_SCHEMA

from . import identity


def _reader():
    return SqliteHistoricalArchiveReads(identity._reader().path)


def _writer():
    return audit_storage.SqliteHistoricalAuditWrites(identity._reader().path, today=date.today)


YAHOO_SOURCE = price_accreditation.YAHOO_SOURCE
ADJUSTED = price_accreditation.ADJUSTED
UNKNOWN = price_accreditation.UNKNOWN
SCHEMA = audit_storage.SCHEMA
ARCHIVE_SCHEMA = _ARCHIVE_SCHEMA

EVENT_TYPES = price_accreditation.EVENT_TYPES


qualify_fallback = price_accreditation.qualify_fallback


_refs = price_accreditation._refs


def record_series(*, cik: str, symbol: str, valid_from: str, valid_to: str,
                  source_id: str, adjustment_basis: str, status: str,
                  evidence: list[dict]) -> None:
    accreditation.record_series(
        _writer(), cik=cik, symbol=symbol, valid_from=valid_from, valid_to=valid_to,
        source_id=source_id, adjustment_basis=adjustment_basis, status=status, evidence=evidence)


_producer = price_accreditation._producer


_adjusted = audit_storage._adjusted


_sources_agree = audit_storage._sources_agree


def terminal_event(*, cik: str, symbol: str, start: str, end: str) -> dict | None:
    return archive_queries.terminal_event(_reader(), cik=cik, symbol=symbol, start=start, end=end)


def record_terminal(*, cik: str, symbol: str, event_date: str, event_type: str,
                    status: str, evidence: list[dict], cash_per_share: float | None = None,
                    exchange_ratio: float | None = None, successor_symbol: str | None = None,
                    lower_return: float | None = None, upper_return: float | None = None) -> None:
    accreditation.record_terminal(
        _writer(), cik=cik, symbol=symbol, event_date=event_date, event_type=event_type,
        status=status, evidence=evidence, cash_per_share=cash_per_share, exchange_ratio=exchange_ratio,
        successor_symbol=successor_symbol, lower_return=lower_return, upper_return=upper_return)


terminal_return = price_accreditation.terminal_return


def price_history(*, cik: str, symbol: str, start: str, end: str,
                  sessions: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    return archive_queries.price_history(_reader(), cik=cik, symbol=symbol, start=start, end=end, sessions=sessions)
