"""Bounded compatibility price reads, without schema initialization or attribution."""

from pathlib import Path

import pandas as pd

from gabi.infrastructure.storage.bounded_reads import bounded_records, read_only

PRICE_COLUMNS = ['date', 'open', 'high', 'low', 'close', 'volume', 'adj_close']


class SqliteTickerPrices:
    def __init__(self, path: Path, *, max_symbols=1000, max_rows=250000,
                 max_bytes=64 * 1024 * 1024, max_field_bytes=16384, max_symbol_rows=25000):
        if min(max_symbols, max_rows, max_bytes, max_field_bytes, max_symbol_rows) <= 0:
            raise ValueError('Compatibility price limits must be positive')
        self.path = path
        self.max_symbols, self.max_symbol_rows = max_symbols, max_symbol_rows
        self.limits = dict(max_rows=max_rows, max_bytes=max_bytes, max_field_bytes=max_field_bytes)

    def many(self, symbols: list[str]) -> dict[str, pd.DataFrame]:
        requested = list(dict.fromkeys(symbols))
        if len(requested) > self.max_symbols:
            raise ValueError('Too many symbols for a compatibility price read')
        if not requested:
            return {}
        result = {}
        total_rows, consumed = 0, 0

        def frame(symbol, rows):
            data = pd.DataFrame(rows, columns=PRICE_COLUMNS)
            data['date'] = pd.to_datetime(data['date'])
            result[symbol] = data.set_index('date')

        with read_only(self.path, self.limits['max_field_bytes']) as (db, tables):
            if 'prices' not in tables:
                return {}
            columns = {r[1] for r in db.execute('PRAGMA table_info(prices)')}
            # Old databases may lack adj_close; a query must not ALTER TABLE.
            selected = ','.join(name if name in columns else f'NULL AS {name}' for name in PRICE_COLUMNS)
            for index in range(0, len(requested), 200):
                batch = requested[index:index + 200]
                limits = self.limits | dict(max_rows=self.limits['max_rows'] - total_rows,
                                           max_bytes=self.limits['max_bytes'] - consumed)
                records = bounded_records(db, f'SELECT symbol,{selected} FROM prices WHERE symbol IN '
                    f"({','.join('?' for _ in batch)}) ORDER BY symbol,date ASC", tuple(batch), **limits)
                current = None
                rows: list[tuple] = []
                for row in records:
                    if current is not None and row[0] != current:
                        frame(current, rows)
                        rows = []
                    current = row[0]
                    if len(rows) >= self.max_symbol_rows:
                        raise ValueError('Compatibility price series exceeds the row limit')
                    rows.append(row[1:])
                    total_rows += 1
                    consumed += sum(len(v.encode()) if isinstance(v, str) else 8 for v in row)
                if rows:
                    frame(current, rows)
        return dict(sorted(result.items()))

    def get(self, symbol: str) -> pd.DataFrame:
        return self.many([symbol]).get(symbol, pd.DataFrame(columns=PRICE_COLUMNS))

    def for_backtest(self, symbols: list[str]) -> dict[str, pd.DataFrame]:
        found = self.many(symbols)
        return {symbol: found.get(symbol, pd.DataFrame(columns=PRICE_COLUMNS)) for symbol in symbols}
