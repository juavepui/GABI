"""Explicit accreditation commands; adapters receive validated evidence."""
from typing import Protocol

from gabi.domain.research.price_accreditation import prepare_series, prepare_terminal


class HistoricalAuditWriter(Protocol):
    def record_series(self, *, cik: str, symbol: str, valid_from: str, valid_to: str,
                      source_id: str, adjustment_basis: str, status: str, refs: str) -> None: ...
    def record_terminal(self, **record) -> None: ...
    def remove_producer(self, producer: str) -> int: ...
    def replace_unknown_terminal(self, entity: str, symbol: str, after: str, through: str, record: dict) -> None: ...

def record_series(writer: HistoricalAuditWriter, **evidence) -> None:
    writer.record_series(**prepare_series(**evidence))

def record_terminal(writer: HistoricalAuditWriter, **evidence) -> None:
    writer.record_terminal(**prepare_terminal(**evidence))

def remove_producer(writer: HistoricalAuditWriter, producer: str) -> int:
    return writer.remove_producer(producer)

def replace_unknown_terminal(writer: HistoricalAuditWriter, *, after: str, through: str, **evidence) -> None:
    record = prepare_terminal(**evidence)
    writer.replace_unknown_terminal(f"cik:{record['cik']}", record['symbol'], after, through, record)
