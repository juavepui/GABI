"""Compare captured and bounded quarter ingestion on synthetic temporary SEC data."""

import json
import math
import sqlite3
import sys
import tempfile
import zipfile
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from measure_f7_historical_writers import measure

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend/src'))


def main():
    from gabi.application.research.sec_bulk import import_quarter
    from gabi.infrastructure.storage.sec_bulk import LocalSecQuarter, SqliteSecQuarter

    reference = json.loads((ROOT / 'backend/tests/fixtures/sec_bulk_import_migration.json').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='gabi-sec-bulk-') as directory:
        root = Path(directory)
        old_db, new_db, path = root / 'old.db', root / 'new.db', root / 'quarter.zip'

        @contextmanager
        def connection():
            with closing(sqlite3.connect(old_db, timeout=30)) as db:
                db.execute('PRAGMA journal_mode=WAL')
                yield db

        old = dict(Path=Path, SCHEMA=reference['schema'], sqlite3=sqlite3, pd=pd, math=math,
                   zipfile=zipfile, datetime=datetime, TRACKED={'Revenues'},
                   edgar=SimpleNamespace(SHARES_TAGS=set()), storage=SimpleNamespace(get_connection=connection))
        for name in ('ensure_schema', 'date8', 'import_quarter'):
            exec(reference[name], old)
        sub = pd.DataFrame([dict(adsh=f'a{index}', cik=str(index % 500 + 1), name='Synthetic issuer',
            sic='1234', form='10-K', filed='20100201', accepted='2010-02-01 12:00:00',
            fy='2009', fp='FY', instance=f'a{index}.xml') for index in range(5000)])
        num = pd.DataFrame([dict(adsh=f'a{index % 5000}', tag='Revenues', version='us-gaap/2009',
            ddate='20091231', qtrs='4', uom='USD', segments='', coreg='', value=str(index % 7))
            for index in range(100000)])
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('sub.txt', sub.to_csv(sep='\t', index=False))
            archive.writestr('num.txt', num.to_csv(sep='\t', index=False))
        ciks = {str(cik).zfill(10) for cik in range(1, 51)}

        def contents(database):
            with closing(sqlite3.connect(database)) as db:
                return {table: db.execute(f'SELECT * FROM {table} ORDER BY 1,2,3,4,5,6,7').fetchall()
                        for table in ('sec_bulk_submissions', 'sec_bulk_facts')}

        def previous():
            report = old['import_quarter'](path, 'synthetic-url', ciks)
            return report, contents(old_db)

        def current():
            report = import_quarter(LocalSecQuarter(path), SqliteSecQuarter(new_db), 'synthetic-url', ciks,
                                    tracked={'Revenues'}, shares=set())
            return report, contents(new_db)

        expected, before = measure(previous)
        actual, after = measure(current)
        assert actual == expected
        print(json.dumps(dict(submissions_available=len(sub), num_rows=len(num), ciks=len(ciks),
                              report=actual[0], before=before, after=after), indent=2))


if __name__ == '__main__':
    main()
