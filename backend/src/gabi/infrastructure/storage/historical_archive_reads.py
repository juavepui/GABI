"""Bounded archive queries and a consistent snapshot for strict price reads."""

from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from gabi.domain.research.historical_pit import YAHOO_SOURCE
from gabi.infrastructure.storage.bounded_reads import bounded_rows, read_only


class _PriceSnapshot:
    def __init__(self, db, tables, limits):
        self.db, self.tables, self.limits = db, tables, limits

    def _rows(self, table, query, params=()):
        if table not in self.tables:
            return []
        return bounded_rows(self.db, query, params, **self.limits)

    def provenance(self, entity, symbol, start, end):
        return self._rows('historical_price_provenance',
                          'SELECT source_id,adjustment_basis,status,evidence_json,valid_from,valid_to '
                          'FROM historical_price_provenance WHERE entity_id=? AND symbol=? '
                          "AND valid_from<=? AND valid_to>=? AND status IN ('tier_a','tier_b')",
                          (entity, symbol, start, end))

    def terminals(self, entity, symbol, start, end):
        return self._rows('historical_terminal_events',
                          'SELECT event_date,event_type,status,cash_per_share,exchange_ratio,successor_symbol,'
                          'lower_return,upper_return,evidence_json FROM historical_terminal_events '
                          'WHERE entity_id=? AND symbol=? AND event_date>=? AND event_date<? ORDER BY event_date',
                          (entity, symbol, start, end))

    def prices(self, source, symbol, start, end, *, raw=False):
        table = 'historical_prices' if raw or source != YAHOO_SOURCE else 'prices'
        columns = 'date,open,high,low,close,adj_close,volume,close_basis' if raw else 'date,open,high,low,close,volume,adj_close'
        source_clause = 'source_id=? AND ' if table == 'historical_prices' else ''
        params = (source, symbol, start, end) if source_clause else (symbol, start, end)
        rows = self._rows(table, f'SELECT {columns} FROM {table} WHERE {source_clause}'
                          'symbol=? AND date>=? AND date<? ORDER BY date', params)
        frame = pd.DataFrame(rows, columns=columns.split(','))
        frame['date'] = pd.to_datetime(frame['date'])
        return frame.set_index('date')


class SqliteHistoricalArchiveReads:
    def __init__(self, path: Path, *, max_rows=25000, max_bytes=16 * 1024 * 1024,
                 max_field_bytes=1024 * 1024):
        if min(max_rows, max_bytes, max_field_bytes) <= 0:
            raise ValueError('Invalid historical archive read limits')
        self.path = path
        self.limits = dict(max_rows=max_rows, max_bytes=max_bytes, max_field_bytes=max_field_bytes)

    @contextmanager
    def snapshot(self):
        with read_only(self.path, self.limits['max_field_bytes']) as (db, tables):
            yield _PriceSnapshot(db, tables, self.limits)

    def raw_prices(self, source, symbol, start, end):
        with self.snapshot() as snapshot:
            return snapshot.prices(source, symbol, start, end, raw=True)

    def filing_observations(self, symbol, cutoff=None):
        with self.snapshot() as snapshot:
            clause = " AND json_extract(payload_json,'$.filed_date')<=?" if cutoff else ''
            params = (symbol, cutoff) if cutoff else (symbol,)
            return snapshot._rows('entity_observations',
                                  'SELECT entity_id,payload_json,source FROM entity_observations '
                                  "WHERE dataset='filing_identity' AND symbol=?" + clause, params)

    def summary(self):
        result: list[dict] = []
        with self.snapshot() as snapshot:
            if 'historical_sources' not in snapshot.tables:
                return result
            for table, kind, column in [('historical_membership', 'Composición', 'date'),
                                        ('historical_prices', 'Precios', 'date'),
                                        ('historical_facts', 'Fundamentales SEC por CIK', 'filed_date')]:
                rows = snapshot._rows(table, f'SELECT source_id,COUNT(*),MIN({column}),MAX({column}) '
                                      f'FROM {table} GROUP BY source_id')
                result.extend(dict(zip(('Fuente', 'Datos', 'Filas', 'Desde', 'Hasta'),
                                       (sid, kind, count, first, last), strict=True))
                              for sid, count, first, last in rows)
        return result
