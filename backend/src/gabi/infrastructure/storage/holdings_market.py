"""Atomic, bounded holdings-only snapshots: prices and split events from ONE Yahoo response.

Explicit refresh replaces the symbol snapshot, including an empty event history.
GET reads a single SQLite snapshot and never initializes schema. Old shared prices
remain a fallback, explicitly unverified; a fresh holdings snapshot is independent
of subsequent shared market-cache writes and cannot mix price/event generations.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

from gabi.application.errors import QueryError
from gabi.infrastructure.storage.bounded_reads import bounded_rows, read_only

SCHEMA = """
CREATE TABLE IF NOT EXISTS holdings_market_meta (
 symbol TEXT PRIMARY KEY, fetched_at TEXT NOT NULL, source TEXT NOT NULL, basis TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS holdings_market_prices (
 symbol TEXT NOT NULL, date TEXT NOT NULL, close REAL NOT NULL, adj_close REAL NOT NULL,
 PRIMARY KEY(symbol,date)
);
CREATE TABLE IF NOT EXISTS holdings_market_splits (
 symbol TEXT NOT NULL, date TEXT NOT NULL, ratio REAL NOT NULL, PRIMARY KEY(symbol,date)
);
"""
MAX_ROWS = 10000


class SqliteHoldingsMarket:
    def __init__(self, data_dir: Path):
        self.data_dir, self.path = data_dir, data_dir / 'gabi.db'

    def save(self, symbol: str, frame: pd.DataFrame, fetched_at: str) -> None:
        if frame.empty or len(frame) > MAX_ROWS:
            raise ValueError('El historial de cartera debe contener entre 1 y 10000 sesiones.')
        records = [(symbol, day.date().isoformat(), float(row.Close), float(row['Adj Close']))
                   for day, row in frame.iterrows()]
        events = frame.attrs.get('splits', [(day.date().isoformat(), float(ratio))
                                           for day, ratio in frame['Stock Splits'].items() if ratio != 0])
        if len(events) > 1000:
            raise ValueError('El historial supera 1000 desdoblamientos por símbolo.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.executescript(SCHEMA)
            db.execute('DELETE FROM holdings_market_prices WHERE symbol=?', (symbol,))
            db.executemany('INSERT INTO holdings_market_prices VALUES(?,?,?,?)', records)
            db.execute('DELETE FROM holdings_market_splits WHERE symbol=?', (symbol,))
            db.executemany('INSERT INTO holdings_market_splits VALUES(?,?,?)',
                           [(symbol, day, ratio) for day, ratio in events])
            db.execute('INSERT OR REPLACE INTO holdings_market_meta VALUES(?,?,?,?)',
                       (symbol, fetched_at, 'yahoo:history:actions', 'today_splits'))

    def prices(self, symbols: list[str], start: str) -> dict[str, pd.DataFrame]:
        if len(symbols) > 30:
            raise QueryError('resource_limit', 'La cartera supera el límite de 30 símbolos.')
        symbols = list(dict.fromkeys(symbols))
        if not symbols:
            return {}
        result = {}
        marks = ','.join('?' for _ in symbols)
        limits = dict(max_rows=MAX_ROWS * len(symbols), max_bytes=64 * 1024 * 1024, max_field_bytes=16384)

        def frames(rows, events, metadata):
            grouped: dict[str, list[tuple]] = {}
            split_rows: dict[str, list[tuple]] = {}
            for symbol, day, ratio in events:
                group = split_rows.setdefault(symbol, [])
                if len(group) >= 1000:
                    raise QueryError('resource_limit', 'Demasiados desdoblamientos de cartera.')
                group.append((day, ratio))
            for symbol, *row in rows:
                group = grouped.setdefault(symbol, [])
                if len(group) >= MAX_ROWS:
                    raise QueryError('resource_limit', 'El historial supera 10000 sesiones por símbolo.')
                group.append(tuple(row))
            for symbol in metadata:
                frame = pd.DataFrame(grouped.get(symbol, []), columns=['date', 'close', 'adj_close'])
                frame['date'] = pd.to_datetime(frame['date'])
                frame = frame.set_index('date')
                frame.attrs = metadata[symbol] | {'splits': split_rows.get(symbol, [])}
                result[symbol] = frame

        with read_only(self.path, 16384) as (db, tables):
            verified = {}
            if {'holdings_market_meta', 'holdings_market_prices', 'holdings_market_splits'} <= tables:
                meta_rows = bounded_rows(db, f'SELECT symbol,fetched_at,source,basis FROM holdings_market_meta '
                                         f'WHERE symbol IN ({marks})', symbols, **limits)
                verified = {symbol: dict(fetched_at=stamp, source=source, basis=basis, actions_verified=True)
                            for symbol, stamp, source, basis in meta_rows}
                rows = bounded_rows(db, 'SELECT symbol,date,close,adj_close FROM holdings_market_prices '
                                    f'WHERE symbol IN ({marks}) AND date>=? ORDER BY symbol,date',
                                    [*symbols, start], **limits)
                events = bounded_rows(db, 'SELECT symbol,date,ratio FROM holdings_market_splits '
                                      f'WHERE symbol IN ({marks}) ORDER BY symbol,date', symbols,
                                      **(limits | {'max_rows': 1000 * len(symbols)}))
                frames(rows, events, verified)
            fallback = [symbol for symbol in symbols if symbol not in verified]
            # Old events have no paired price provenance: they may help align the bases,
            # but never claim verified coverage (including an absent/empty splits table).
            if fallback and 'prices' in tables:
                marks = ','.join('?' for _ in fallback)
                columns = {row[1] for row in db.execute('PRAGMA table_info(prices)')}
                adj = 'adj_close' if 'adj_close' in columns else 'NULL AS adj_close'
                rows = bounded_rows(db, f'SELECT symbol,date,close,{adj} FROM prices WHERE symbol IN ({marks}) '
                                    'AND date>=? ORDER BY symbol,date', [*fallback, start], **limits)
                events = bounded_rows(db, f'SELECT symbol,date,ratio FROM splits WHERE symbol IN ({marks}) '
                                      'ORDER BY symbol,date', fallback,
                                      **(limits | {'max_rows': 1000 * len(fallback)})) if 'splits' in tables else []
                frames(rows, events, {symbol: dict(basis='today_splits', actions_verified=False,
                                                  source='legacy-cache:unverified') for symbol in fallback})
        return result
