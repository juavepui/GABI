"""Bounded local inputs for price audits; a run owns one read-only snapshot and LRU."""

from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from gabi.infrastructure.storage.bounded_reads import bounded_rows, read_only


class _PriceAuditSnapshot:
    def __init__(self, db, tables, limits, cache_bytes):
        self.db, self.tables, self.limits = db, tables, limits
        self.cache_bytes, self.cached_bytes = cache_bytes, 0
        self.cache = OrderedDict()

    def rows(self, table, query, params=()):
        return bounded_rows(self.db, query, params, **self.limits) if table in self.tables else []

    def series(self, symbol, start, end, *, archive, source_id):
        key = (symbol, start, end, archive, source_id)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key][0]
        values = self.price_values(symbol, start, end, archive=archive, source_id=source_id, inclusive=True)
        frame = pd.DataFrame(values, columns=['date', 'close', 'adj_close'])
        frame['date'] = pd.to_datetime(frame['date'])
        frame = frame.set_index('date')
        if frame.empty:
            frame = pd.DataFrame(columns=['close', 'adj_close'], index=pd.DatetimeIndex([], name='date'))
        size = int(frame.memory_usage(index=True, deep=True).sum())
        if size <= self.cache_bytes:
            while self.cache and self.cached_bytes + size > self.cache_bytes:
                _, (_, previous) = self.cache.popitem(last=False)
                self.cached_bytes -= previous
            self.cache[key] = (frame, size)
            self.cached_bytes += size
        return frame

    def price_values(self, symbol, start, end, *, archive, source_id, inclusive=False):
        table = 'historical_prices' if archive else 'prices'
        source_clause = ' AND source_id=?' if archive else ''
        params = (symbol, start, end, source_id) if archive else (symbol, start, end)
        return self.rows(table, f'SELECT date,close,adj_close FROM {table} WHERE symbol=? '
                         f"AND date>=? AND date{'<=' if inclusive else '<'}?{source_clause} ORDER BY date", params)

    def splits(self, symbol):
        rows = self.rows('splits', 'SELECT symbol,date,ratio FROM splits WHERE symbol=?', (symbol,))
        return pd.DataFrame(rows, columns=['symbol', 'date', 'ratio'])

    def conflicts(self, source, symbol, start, end):
        rows = self.rows('historical_identity_intervals',
                         'SELECT COUNT(DISTINCT cik) FROM historical_identity_intervals '
                         'WHERE source_id=? AND symbol=? AND valid_from<=? AND valid_to>?',
                         (source, symbol, end, start))
        return rows[0][0] if rows else 0

    def provenance(self, entity, symbol, source, start, end, producer):
        return self.rows('historical_price_provenance',
                         'SELECT source_id,adjustment_basis,status FROM historical_price_provenance '
                         'WHERE entity_id=? AND symbol=? AND source_id=? AND valid_from<=? AND valid_to>=? '
                         "AND status IN ('tier_a','tier_b') AND evidence_json LIKE ?",
                         (entity, symbol, source, start, end, f'%"producer": "{producer}"%'))

    def events(self, entity, start, end):
        return self.rows('historical_terminal_events', 'SELECT status FROM historical_terminal_events '
                         'WHERE entity_id=? AND event_date>? AND event_date<=?', (entity, start, end))

    def boundaries(self, source, label, symbol, cik, day):
        first = self.rows('historical_identity_intervals',
                          'SELECT MIN(valid_to) FROM historical_identity_intervals WHERE source_id=? AND symbol=? '
                          'AND cik=? AND valid_from<=? AND valid_to>?', (source, label, cik, day, day))
        second = self.rows('historical_identity_intervals',
                           'SELECT MIN(valid_from) FROM historical_identity_intervals WHERE source_id=? '
                           'AND symbol IN (?,?) AND cik<>? AND valid_from>?', (source, label, symbol, cik, day))
        return (first[0][0] if first else None, second[0][0] if second else None)

    def sic(self, cik, day):
        rows = self.rows('sec_bulk_submissions',
                         'SELECT * FROM (SELECT sic FROM sec_bulk_submissions WHERE cik=? AND filed_date<=? '
                         "AND sic IS NOT NULL AND sic!='' ORDER BY filed_date DESC LIMIT 1)", (cik, day))
        return rows[0] if rows else None

    def identity_rows(self, source):
        return self.rows('historical_identity_intervals',
                         'SELECT symbol,cik,valid_from,valid_to,status,source_refs_json '
                         'FROM historical_identity_intervals WHERE source_id=?', (source,))


class SqlitePriceAuditReads:
    def __init__(self, path: Path, *, max_rows=25000, max_bytes=16 * 1024 * 1024,
                 max_field_bytes=1024 * 1024, cache_bytes=32 * 1024 * 1024):
        if min(max_rows, max_bytes, max_field_bytes) <= 0 or cache_bytes < 0:
            raise ValueError('Price audit limits must be positive and cache nonnegative')
        self.path, self.cache_bytes = path, cache_bytes
        self.limits = dict(max_rows=max_rows, max_bytes=max_bytes, max_field_bytes=max_field_bytes)

    @contextmanager
    def snapshot(self):
        with read_only(self.path, self.limits['max_field_bytes']) as (db, tables):
            yield _PriceAuditSnapshot(db, tables, self.limits, self.cache_bytes)


def series_from_connection(conn, symbol, start, end, *, archive, source_id):
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    snapshot = _PriceAuditSnapshot(conn, tables, dict(max_rows=25000, max_bytes=16 * 1024 * 1024,
                                                   max_field_bytes=1024 * 1024), 0)
    return snapshot.series(symbol, start, end, archive=archive, source_id=source_id)
