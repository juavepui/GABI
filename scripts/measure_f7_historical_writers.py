"""Compare composition loading and explicit accreditation on synthetic temporary data."""

import json
import sqlite3
import statistics
import sys
import tempfile
import time
import tracemalloc
from contextlib import closing, contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from pandas.testing import assert_frame_equal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend/src'))


def measure(execute):
    actual_connect = sqlite3.connect
    elapsed, peaks, counters = [], [], []
    result = None
    for _ in range(4):
        count = dict(connections=0, selects=0, rows=0)

        class Cursor:
            def __init__(self, cursor):
                self.cursor = cursor

            def __getattr__(self, name):
                return getattr(self.cursor, name)

            def __iter__(self):
                for row in self.cursor:
                    count['rows'] += 1
                    yield row

            def fetchall(self):
                rows = self.cursor.fetchall()
                count['rows'] += len(rows)
                return rows

            def fetchone(self):
                row = self.cursor.fetchone()
                count['rows'] += int(row is not None)
                return row

        class Connection(sqlite3.Connection):
            def execute(self, *args, **kwargs):
                return Cursor(super().execute(*args, **kwargs))

            def cursor(self, *args, **kwargs):
                return Cursor(super().cursor(*args, **kwargs))

        def connect(*args, **kwargs):
            count['connections'] += 1
            kwargs['factory'] = Connection
            db = actual_connect(*args, **kwargs)
            db.set_trace_callback(lambda sql: count.__setitem__('selects', count['selects'] + 1)
                                  if sql.lstrip().upper().startswith('SELECT') else None)
            return db

        sqlite3.connect = connect
        try:
            tracemalloc.start()
            started = time.perf_counter()
            result = execute()
            elapsed.append(time.perf_counter() - started)
            peaks.append(tracemalloc.get_traced_memory()[1] / 1024 ** 2)
            counters.append(count)
        finally:
            tracemalloc.stop()
            sqlite3.connect = actual_connect
    return result, dict(cold_seconds=elapsed[0], warm_median_seconds=statistics.median(elapsed[1:]),
                         python_peak_mib=max(peaks), sql=counters)


def main():
    from gabi.application.research.historical_accreditation import record_series
    from gabi.application.research.historical_archive import import_membership, register_source
    from gabi.infrastructure.storage.historical_archive_writes import SqliteHistoricalArchiveWrites
    from gabi.infrastructure.storage.historical_audit_writes import SqliteHistoricalAuditWrites
    from gabi.infrastructure.storage.historical_composition import LocalHistoricalComposition

    references = json.loads((ROOT / 'backend/tests/fixtures/historical_writers_migration.json').read_text(encoding='utf-8'))
    identity_reference = json.loads((ROOT / 'backend/tests/fixtures/identity_migration.json').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='gabi-historical-writers-measure-') as directory:
        path = Path(directory) / 'composition.db'
        writer = SqliteHistoricalArchiveWrites(path, date.today)
        register_source(writer, 'synthetic', dict(start='2000-01-01', end_exclusive='2004-01-01'))
        snapshots = pd.DataFrame(dict(date=pd.date_range('2000-01-01', periods=1000).strftime('%Y-%m-%d'),
                                      tickers=','.join(f'S{i:04}' for i in range(500))))
        import_membership(writer, 'synthetic', snapshots, '2000-01-01', '2004-01-01')

        def connection_for(path):
            @contextmanager
            def connection():
                with closing(sqlite3.connect(path)) as db:
                    db.execute('PRAGMA journal_mode=WAL')
                    yield db
            return SimpleNamespace(get_connection=connection)

        old = dict(__name__='gabi._measured_composition', __package__='gabi')
        exec(references['historical_membership'], old)
        old['storage'] = connection_for(path)
        original, old_stats = measure(lambda: old['_archive']('synthetic'))
        migrated, new_stats = measure(lambda: LocalHistoricalComposition(path).archive('synthetic'))
        assert_frame_equal(original[0], migrated[0])
        assert original[1] == migrated[1]
        results = dict(snapshots=1000, symbols_per_snapshot=500, downloads=0,
                       composition=dict(original=old_stats, migrated=new_stats))
        cache = Path(directory) / 'membership.csv'
        snapshots.to_csv(cache, index=False)
        old['universe'] = SimpleNamespace(HISTORICAL_MEMBERSHIP_CACHE=cache)
        ledger = ROOT / 'backend/src/gabi/resources/sp500_extension.json'
        original, old_stats = measure(old['_operational'])
        migrated, new_stats = measure(lambda: LocalHistoricalComposition(path, cache, ledger, today=date.today).operational())
        assert_frame_equal(original[0], migrated[0])
        assert original[1] == migrated[1]
        results['operational_csv'] = dict(original=old_stats, migrated=new_stats)

        # Independent, initially empty destinations, without global configuration changes.
        paths = [Path(directory) / 'old.db', Path(directory) / 'new.db']
        original_identity = dict(__name__='gabi._measured_identity', __package__='gabi')
        exec(identity_reference['identity'], original_identity)
        original_identity['storage'] = connection_for(paths[0])
        policy = dict(__name__='gabi._measured_policy', __package__='gabi')
        exec(references['historical_price_policy'], policy)
        policy['storage'] = connection_for(paths[0])
        policy['identity'] = SimpleNamespace(**original_identity)
        evidence = [dict(kind='identity', source_url='https://synthetic.example/identity'),
                    dict(kind='source', source_url='https://synthetic.example/prices', producer='synthetic')]
        arguments = dict(cik='1', symbol='AAA', valid_from='2010-01-01', valid_to='2011-01-01',
                          source_id='yahoo:legacy-cache', adjustment_basis='split_and_dividend_adjusted',
                          status='tier_a', evidence=evidence)
        _, old_stats = measure(lambda: policy['record_series'](**arguments))
        _, new_stats = measure(lambda: record_series(SqliteHistoricalAuditWrites(paths[1], date.today), **arguments))
        payloads = []
        for database in paths:
            with closing(sqlite3.connect(database)) as db:
                tables = sorted(name for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'"))
                payloads.append({table: db.execute(f'SELECT * FROM {table} ORDER BY 1,2').fetchall() for table in tables})
        assert payloads[0] == payloads[1]
        results.update(accreditation=dict(original=old_stats, migrated=new_stats), parity='exact')
        print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
