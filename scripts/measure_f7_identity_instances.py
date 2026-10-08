"""Compare captured and read-only local identity scans on synthetic SEC covers."""

import hashlib
import json
import re
import sqlite3
import sys
import tempfile
from bisect import bisect_right
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from lxml import etree
from measure_f7_historical_writers import measure

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend/src'))


def main():
    from gabi import historical_identity_audit as facade
    from gabi.application.research.identity_instances import scan
    from gabi.domain.research import historical_membership
    from gabi.domain.research.periods import P2010
    from gabi.domain.research.ticker_corrections import correct_symbols
    from gabi.infrastructure.storage.identity_instances import LocalIdentityInstances, SqliteIdentityInstances

    reference = json.loads((ROOT / 'backend/tests/fixtures/identity_instances_migration.json').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='gabi-identity-instances-') as directory:
        root = Path(directory)
        files = root / 'history_refresh/validation_1996_2015/instances'
        files.mkdir(parents=True)
        database = root / 'scan.db'
        with closing(sqlite3.connect(database)) as db, db:
            db.executescript('''CREATE TABLE sec_bulk_submissions (accn TEXT,cik TEXT,filed_date TEXT,instance TEXT,name TEXT);
                CREATE TABLE historical_issuer_candidates (symbol TEXT,cik TEXT,name TEXT,date_added TEXT,date_removed TEXT,observed_from TEXT,source_id TEXT);
                CREATE TABLE historical_membership (date TEXT,tickers TEXT,source_id TEXT);''')
            for index in range(1, 201):
                accession, symbol, cik = f'{index:04}', f'S{index:04}', str(index).zfill(10)
                db.execute('INSERT INTO sec_bulk_submissions VALUES (?,?,?,?,?)',
                           (accession, cik, '2014-05-01', accession + '.xml', 'Issuer'))
                db.execute('INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)',
                           (symbol, cik, 'Issuer', '2010-01-01', None, '2010-01-01', facade.CANDIDATE_SOURCE))
                if index <= 100:
                    (files / f'{accession}.xml').write_text(
                        '<xbrl xmlns:dei="http://xbrl.sec.gov/dei/2014-01-31">'
                        f'<context><identifier>{cik}</identifier></context><dei:TradingSymbol>{symbol}</dei:TradingSymbol>'
                        '<dei:EntityRegistrantName>Issuer</dei:EntityRegistrantName>' + '<extra/>' * 100 + '</xbrl>',
                        encoding='utf-8')
            db.execute('INSERT INTO historical_membership VALUES (?,?,?)',
                       ('2010-01-01', ','.join(f'S{i:04}' for i in range(1, 201)), P2010.membership_source))
        for index in range(500):
            (files / f'unindexed-{index}.xml').write_text('<broken>', encoding='utf-8')

        @contextmanager
        def connection():
            with closing(sqlite3.connect(database, timeout=30)) as db:
                db.execute('PRAGMA journal_mode=WAL')
                yield db

        old = {**vars(facade), 'pd': pd, 're': re, 'bisect_right': bisect_right, 'etree': etree,
               'hashlib': hashlib, 'historical_membership': historical_membership, 'correct_symbols': correct_symbols,
               'config': SimpleNamespace(DATA_DIR=root), 'storage': SimpleNamespace(get_connection=connection),
               'identity_nominations': lambda: ()}
        for name in ('_common_stock_symbols', 'extract_sec_instance', 'scan_local_sec_instances'):
            exec(reference[name], old)
        expected, before = measure(old['scan_local_sec_instances'])
        actual, after = measure(lambda: scan(SqliteIdentityInstances(database), LocalIdentityInstances(files), ()))
        assert actual == expected
        print(json.dumps(dict(metadata_filings=200, indexed_files=100, unindexed_files=500,
                              proofs=len(actual[0]), before=before, after=after), indent=2))


if __name__ == '__main__':
    main()
