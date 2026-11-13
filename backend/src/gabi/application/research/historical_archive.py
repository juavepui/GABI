"""Source-specific historical imports through an explicit writer port."""
import json
from typing import Protocol

import pandas as pd

from gabi.domain.market.identity import normalize_cik, normalize_symbol
from gabi.domain.research import historical_archive as rules
from gabi.domain.research.historical_prices import prepare_price_chunk


class HistoricalArchiveWriter(Protocol):
    def register_sources(self, records: list[tuple]) -> None: ...
    def import_membership(self, records: list[tuple]) -> None: ...
    def import_candidates(self, records: list[tuple]) -> None: ...
    def import_prices(self, records: list[tuple]) -> None: ...
    def replace_intervals(self, source_id: str, records: list[tuple]) -> None: ...
    def import_facts(self, source_id: str, symbol: str, cik: str, rows: list[dict], source_url: str) -> int: ...
    def import_filings(self, records: list[tuple]) -> int: ...


def register_source(writer: HistoricalArchiveWriter, source_id: str, metadata: dict):
    writer.register_sources([(source_id, json.dumps(metadata, sort_keys=True))])


def import_membership(writer: HistoricalArchiveWriter, source_id: str, frame: pd.DataFrame, start: str, end: str) -> int:
    rows = rules.prepare_import_membership(source_id, frame, start, end)
    writer.import_membership(rows)
    return len(rows)


def import_issuer_candidates(writer: HistoricalArchiveWriter, source_id: str, frame: pd.DataFrame) -> int:
    rows = rules.prepare_import_issuer_candidates(source_id, frame)
    writer.import_candidates(rows)
    return len(rows)


def import_price_chunk(writer: HistoricalArchiveWriter, source_id: str, frame: pd.DataFrame,
                       symbols: set[str], start: str, end: str) -> dict:
    frame, rejected = prepare_price_chunk(frame, symbols, start, end)
    rows = [(source_id, row.symbol, row.date, row.open, row.high, row.low, row.close, row.adj_close,
             row.volume, 'as_traded') for row in frame.itertuples(index=False)]
    writer.import_prices(rows)
    return {'accepted': len(rows), 'rejected': rejected}


def replace_identity_intervals(writer: HistoricalArchiveWriter, source_id: str, rows: list[dict]) -> int:
    records = rules.prepare_replace_identity_intervals(source_id, rows)
    writer.replace_intervals(source_id, records)
    return len(records)


def import_sec_facts(writer: HistoricalArchiveWriter, source_id: str, candidate_symbol: str,
                     cik: str, rows: list[dict], *, source_url: str | None = None) -> int:
    cik = normalize_cik(cik)
    return writer.import_facts(source_id, candidate_symbol, cik, rows,
                               source_url or f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json')


def import_filing_identity_evidence(writer: HistoricalArchiveWriter, rows: list[dict]) -> int:
    records = []
    for row in rows:
        if not str(row['source_url']).startswith('https://www.sec.gov/Archives/edgar/data/'):
            raise ValueError('Original SEC filing URL required')
        if len(str(row['sha256'])) != 64:
            raise ValueError('Original SEC filing SHA-256 required')
        pd.Timestamp(row['filed_date'])
        payload = {'accession': row['accession'], 'filed_date': row['filed_date'],
                   'historical_name': row.get('historical_name'), 'sha256': row['sha256'],
                   'historical_name_source': row.get('historical_name_source'), 'source_url': row['source_url']}
        records.append((normalize_cik(row['cik']), normalize_symbol(row['symbol']), payload, row['source_url']))
    return writer.import_filings(records)
