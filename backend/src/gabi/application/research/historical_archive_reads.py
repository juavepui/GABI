"""Source-specific queries and strict price selection, without I/O side effects."""

import json
from contextlib import AbstractContextManager
from datetime import date
from typing import Protocol

import pandas as pd

from gabi.domain.market.identity import normalize_cik, normalize_symbol
from gabi.domain.research.historical_pit import ADJUSTED, YAHOO_SOURCE


class PriceSnapshot(Protocol):
    def provenance(self, entity: str, symbol: str, start: str, end: str) -> list[tuple]: ...
    def terminals(self, entity: str, symbol: str, start: str, end: str) -> list[tuple]: ...
    def prices(self, source: str, symbol: str, start: str, end: str) -> pd.DataFrame: ...


class HistoricalArchiveReader(Protocol):
    def snapshot(self) -> AbstractContextManager[PriceSnapshot]: ...
    def raw_prices(self, source: str, symbol: str, start: str, end: str) -> pd.DataFrame: ...
    def filing_observations(self, symbol: str, cutoff: str | None = None) -> list[tuple]: ...
    def summary(self) -> list[dict]: ...


def raw_prices(reader: HistoricalArchiveReader, source: str, symbol: str, start: str, end: str) -> pd.DataFrame:
    frame = reader.raw_prices(source, symbol.replace('.', '-'), start, end)
    frame.attrs.update(source_id=source, identity_status='unverified', close_basis='as_traded')
    return frame


def terminal_event(reader: HistoricalArchiveReader, *, cik: str, symbol: str, start: str, end: str) -> dict | None:
    with reader.snapshot() as snapshot:
        rows = snapshot.terminals(f'cik:{normalize_cik(cik)}', normalize_symbol(symbol), start, end)
    if len(rows) > 1:
        raise ValueError('Multiple terminal events require explicit review')
    if not rows:
        return None
    result = dict(zip(('event_date', 'event_type', 'status', 'cash_per_share', 'exchange_ratio',
                       'successor_symbol', 'lower_return', 'upper_return', 'evidence'), rows[0], strict=True))
    result['evidence'] = json.loads(result['evidence'])
    return result


def price_history(reader: HistoricalArchiveReader, *, cik: str, symbol: str, start: str, end: str,
                  sessions: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    cik, symbol = normalize_cik(cik), normalize_symbol(symbol)
    if date.fromisoformat(start) >= date.fromisoformat(end):
        raise ValueError('Empty price request')
    with reader.snapshot() as snapshot:
        rows = sorted(snapshot.provenance(f'cik:{cik}', symbol, start, end),
                      key=lambda row: (row[0] != YAHOO_SOURCE, row[0]))
        if not rows or rows[0][1] != ADJUSTED:
            raise ValueError('No unique accredited adjusted price interval')
        source_id, basis, status, refs, valid_from, valid_to = rows[0]
        if snapshot.terminals(f'cik:{cik}', symbol, start, end):
            raise ValueError('Interval crosses a terminal event; calculate its return explicitly')
        frame = snapshot.prices(source_id, symbol, start, end)
    if frame.empty or frame['adj_close'].isna().any() or frame['adj_close'].le(0).any():
        raise ValueError('Missing or invalid adjusted price')
    if sessions is not None and not sessions.difference(frame.index).empty:
        raise ValueError('Missing exchange session; no price forward-fill')
    frame.attrs.update(entity_id=f'cik:{cik}', cik=cik, symbol=symbol,
                       valid_from=valid_from, valid_to=valid_to, source_id=source_id,
                       adjustment_basis=basis, price_source_status=status, evidence=json.loads(refs))
    return frame


def filing_identity(reader: HistoricalArchiveReader, symbol: str, as_of: str) -> dict:
    day = pd.Timestamp(as_of).date().isoformat()
    matches = [(entity, json.loads(payload)) for entity, payload, _ in
               reader.filing_observations(normalize_symbol(symbol)) if json.loads(payload).get('filed_date') == day]
    entities = {row[0] for row in matches}
    if len(entities) != 1:
        return dict(status='ambiguous' if entities else 'unresolved', entity_id=None, cik=None,
                    evidence=[row[1] for row in matches])
    entity = next(iter(entities))
    return dict(status='resolved', entity_id=entity, cik=entity.removeprefix('cik:'), evidence=[row[1] for row in matches])


def filing_evidence_as_of(reader: HistoricalArchiveReader, symbol: str, as_of: str) -> dict:
    cutoff = pd.Timestamp(as_of).date().isoformat()
    evidence = [{**json.loads(payload), 'cik': entity.removeprefix('cik:')}
                for entity, payload, _ in reader.filing_observations(normalize_symbol(symbol), cutoff)]
    evidence.sort(key=lambda row: (row['filed_date'], row['accession'], row['cik']))
    ciks = sorted({row['cik'] for row in evidence})
    return dict(symbol=normalize_symbol(symbol), as_of=cutoff,
                status='no_evidence' if not ciks else 'conflicting_ciks' if len(ciks) > 1 else 'observed',
                ciks=ciks, evidence=evidence)


def source_summary(reader: HistoricalArchiveReader) -> list[dict]:
    return reader.summary()
