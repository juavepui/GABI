"""Compare captured runners and ticker fallback using only synthetic temporary data."""

import json
import sqlite3
import sys
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from measure_f7_historical_writers import measure
from pandas.testing import assert_frame_equal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend/src'))



def main():
    from gabi import historical_price_audit as facade
    from gabi.application.research.historical_price_audit import audit
    from gabi.domain.research.periods import P2010
    from gabi.infrastructure.storage.historical_price_audit import SqlitePriceAuditReads
    from gabi.infrastructure.storage.ticker_prices import SqliteTickerPrices

    reference = json.loads((ROOT / 'backend/tests/fixtures/historical_runners_migration.json').read_text(encoding='utf-8'))
    old = dict(__name__='gabi._captured_price_audit', __package__='gabi', __file__=facade.__file__)
    exec(reference['historical_price_audit'], old)
    dates = pd.bdate_range('2009-01-01', '2016-12-31')
    calendar = SimpleNamespace(sessions=dates)
    symbols = [f'T{index:02}' for index in range(20)]
    members = dict(members=[dict(symbol=s, cik=None, identity_tier=None) for s in symbols])
    old['historical_membership'] = SimpleNamespace(constituents_as_of=lambda *a, **kw: members)
    old['xcals'] = SimpleNamespace(get_calendar=lambda *a, **kw: calendar)
    @contextmanager
    def readonly(path):
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            yield db
    # The captured context manager did not close its handle; close it for Windows cleanup.
    old['connect_readonly'] = readonly
    evidence = SimpleNamespace(listing_life=lambda *a: None, issuer_facts=lambda *a: {})
    with tempfile.TemporaryDirectory(prefix='gabi-runners-') as directory:
        path = Path(directory) / 'synthetic.db'
        with closing(sqlite3.connect(path)) as db:
            db.executescript('''
                CREATE TABLE prices(symbol TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,adj_close REAL);
                CREATE INDEX price_symbol ON prices(symbol,date);
                CREATE TABLE splits(symbol TEXT,date TEXT,ratio REAL);
                CREATE TABLE historical_prices(source_id TEXT,symbol TEXT,date TEXT,close REAL,adj_close REAL);
                CREATE TABLE historical_identity_intervals(source_id TEXT,symbol TEXT,cik TEXT,valid_from TEXT,valid_to TEXT);
            ''')
            db.executemany('INSERT INTO prices VALUES (?,?,?,?,?,?,?,?)',
                [(symbol, day.date().isoformat(), 10., 10., 10., 10., 100., 10.)
                 for symbol in [*symbols, 'SPY'] for day in dates])
            db.commit()
        selected = ['2012-12-31', '2013-12-31']
        previous, old_stats = measure(lambda: old['audit'](path, dates=selected))
        current, new_stats = measure(lambda: audit(SqlitePriceAuditReads(path), lambda day: members, evidence,
            calendar=calendar, source_ids=facade.source_ids(P2010), nominations=(), database_name=path.name, dates=selected))
        assert_frame_equal(previous[0], current[0])
        assert previous[1] == current[1]

        def single_reads():
            result = {}
            for symbol in symbols:
                with closing(sqlite3.connect(path)) as db:
                    frame = pd.read_sql_query('SELECT date,open,high,low,close,volume,adj_close '
                                              'FROM prices WHERE symbol=? ORDER BY date ASC', db, params=(symbol,))
                frame['date'] = pd.to_datetime(frame['date'])
                result[symbol] = frame.set_index('date')
            return result

        previous, ticker_old = measure(single_reads)
        current, ticker_new = measure(lambda: SqliteTickerPrices(path).many(symbols))
        for symbol in symbols:
            assert_frame_equal(previous[symbol], current[symbol])
        print(json.dumps(dict(symbols=len(symbols), rows_per_symbol=len(dates), audit_dates=selected,
            audit=dict(previous=old_stats, current=new_stats),
            ticker=dict(previous=ticker_old, current=ticker_new)), indent=2))


if __name__ == '__main__':
    main()
