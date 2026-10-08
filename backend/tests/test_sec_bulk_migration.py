"""Captured quarter parity, streaming budgets and atomic legacy-schema migration."""

import json
import math
import sqlite3
import zipfile
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from gabi import config, sec_history
from gabi.application.research.sec_bulk import import_quarter
from gabi.infrastructure.storage.sec_bulk import LocalSecQuarter, SqliteSecQuarter

REFERENCE = json.loads((Path(__file__).parent / 'fixtures/sec_bulk_import_migration.json').read_text(encoding='utf-8'))
TRACKED, SHARES = {'Revenues', 'NetIncomeLoss', 'Shares'}, {'Shares'}
CIKS = {'0000000123'}


def captured(database):
    @contextmanager
    def connection():
        with closing(sqlite3.connect(database, timeout=30)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            yield db

    scope = dict(SCHEMA=REFERENCE['schema'], sqlite3=sqlite3, pd=pd, math=math, Path=Path,
                 zipfile=zipfile, datetime=datetime, TRACKED=TRACKED,
                 edgar=SimpleNamespace(SHARES_TAGS=SHARES), storage=SimpleNamespace(get_connection=connection))
    for name in ('ensure_schema', 'date8', 'import_quarter'):
        exec(REFERENCE[name], scope)
    return scope['import_quarter']


def archive(path, *, facts=True, segments=True, malformed=False, duplicate_member=False):
    sub = dict(adsh='a', cik='123', name='Issuer', sic='1234', form='10-K', filed='20100201',
               accepted='2010-02-01 12:00:00', fy='2009', fp='FY', instance='a.xml')
    submissions = pd.DataFrame([sub, {**sub, 'filed': '20100202'},
        {**sub, 'adsh': 'b', 'form': '10-Q/A'}, {**sub, 'adsh': 'x', 'form': '8-K'},
        {**sub, 'adsh': 'other', 'cik': '999'}])
    base = dict(adsh='a', tag='Revenues', version='us-gaap/2009', ddate='20091231', qtrs='4',
                uom='USD', segments='', coreg='', value='100')
    numbers = pd.DataFrame([base, base, {**base, 'value': '101'},
        {**base, 'segments': 'Business=A'}, {**base, 'coreg': 'Subsidiary'},
        {**base, 'value': 'NaN'}, {**base, 'value': 'inf'}, {**base, 'qtrs': '-1'},
        {**base, 'qtrs': 'x'}, {**base, 'ddate': 'invalid'}, {**base, 'uom': 'EUR'},
        {**base, 'tag': 'Shares', 'uom': 'shares', 'value': '300'},
        {**base, 'adsh': 'b', 'qtrs': '0'}, {**base, 'version': 'custom/2009'},
        {**base, 'adsh': 'other'}, {**base, 'tag': 'Untracked'}])
    if not segments:
        numbers = numbers.drop(columns=['segments'])
    if malformed:
        numbers = numbers.drop(columns=['coreg'])
    with zipfile.ZipFile(path, 'w') as z:
        text = submissions.to_csv(sep='\t', index=False)
        z.writestr('sub.txt', text)
        if duplicate_member:
            with pytest.warns(UserWarning, match='Duplicate name'):
                z.writestr('sub.txt', text)
        if facts:
            z.writestr('num.txt', numbers.to_csv(sep='\t', index=False))
    return path


def contents(database):
    with closing(sqlite3.connect(database)) as db:
        return {name: db.execute(f'SELECT * FROM {name} ORDER BY 1,2,3,4,5,6,7').fetchall()
                for name in ('sec_bulk_submissions', 'sec_bulk_facts')}


def execute(path, database, *, facts=True, **limits):
    return import_quarter(LocalSecQuarter(path, **limits), SqliteSecQuarter(database), 'source-url', CIKS,
                          tracked=TRACKED, shares=SHARES, facts=facts)


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'compat.db')
    monkeypatch.setattr('requests.sessions.Session.request', lambda *a, **k: pytest.fail('Unexpected network'))


@pytest.mark.parametrize('facts', [False, True])
@pytest.mark.parametrize('chunk_rows', [1, 2, 20000])
def test_captured_parity_across_batches_and_reimports(tmp_path, facts, chunk_rows):
    path = archive(tmp_path / 'quarter.zip', facts=facts)
    old_db, new_db = tmp_path / 'old.db', tmp_path / 'new.db'
    old = captured(old_db)
    for _ in range(2):
        expected = old(path, 'source-url', CIKS, facts=facts)
        actual = execute(path, new_db, facts=facts, chunk_rows=chunk_rows)
        assert actual == expected
        assert contents(new_db) == contents(old_db)
    assert actual['submissions'] == 3
    assert actual['facts'] == (5 if facts else 0)
    assert actual['excluded_segment_or_coreg'] == (2 if facts else 0)
    assert actual['invalid'] == (6 if facts else 0)
    if facts:
        assert len(contents(new_db)['sec_bulk_facts']) == 4


def test_absent_segments_column_keeps_previous_consolidation_rule(tmp_path):
    path = archive(tmp_path / 'quarter.zip', segments=False)
    expected = captured(tmp_path / 'old.db')(path, 'source-url', CIKS)
    assert execute(path, tmp_path / 'new.db', chunk_rows=1) == expected
    assert contents(tmp_path / 'new.db') == contents(tmp_path / 'old.db')


def test_flat_facade_preserves_injected_policy_and_public_schema(tmp_path, monkeypatch):
    path = archive(tmp_path / 'quarter.zip')
    monkeypatch.setattr(sec_history, 'TRACKED', TRACKED)
    monkeypatch.setattr(sec_history.edgar, 'SHARES_TAGS', list(SHARES))
    assert sec_history.SCHEMA == REFERENCE['schema']
    assert sec_history.import_quarter(path, 'source-url', CIKS) == captured(tmp_path / 'old.db')(
        path, 'source-url', CIKS)
    assert contents(config.DB_PATH) == contents(tmp_path / 'old.db')


def test_failed_import_rolls_back_legacy_schema_migration_and_prior_data(tmp_path):
    database = tmp_path / 'old-schema.db'
    schema = REFERENCE['schema'].replace('PRIMARY KEY(accn,tag,version,end_month,qtrs,unit,val)',
                                        'PRIMARY KEY(accn,tag,version,end_month,qtrs,unit)')
    with closing(sqlite3.connect(database)) as db, db:
        db.executescript(schema)
        db.execute('INSERT INTO sec_bulk_facts VALUES (?,?,?,?,?,?,?)',
                   ('original', 'Revenues', 'us-gaap/2009', '2009-12-31', 4, 'USD', 7))
    prior = contents(database)
    with pytest.raises(AttributeError, match='coreg'):
        execute(archive(tmp_path / 'bad.zip', malformed=True), database, chunk_rows=1)
    assert contents(database) == prior
    with closing(sqlite3.connect(database)) as db:
        assert next(row[5] for row in db.execute('PRAGMA table_info(sec_bulk_facts)') if row[1] == 'val') == 0
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='sec_bulk_facts_old'").fetchall()
    execute(archive(tmp_path / 'good.zip'), database, chunk_rows=1)
    assert prior['sec_bulk_facts'][0] in contents(database)['sec_bulk_facts']
    assert len(contents(database)['sec_bulk_facts']) == 5


@pytest.mark.parametrize('limits', [dict(max_archive_bytes=1), dict(max_sub_bytes=1), dict(max_num_bytes=1),
    dict(chunk_rows=1, max_rows=1), dict(max_chunk_bytes=1), dict(max_field_bytes=1)])
def test_read_budgets_abort_without_partial_records(tmp_path, limits):
    path, database = archive(tmp_path / 'quarter.zip'), tmp_path / 'archive.db'
    with pytest.raises(ValueError, match='budget'):
        execute(path, database, **limits)
    if database.exists():
        with closing(sqlite3.connect(database)) as db:
            assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


def test_accession_budget_is_atomic(tmp_path):
    path, database = archive(tmp_path / 'quarter.zip'), tmp_path / 'archive.db'
    with pytest.raises(ValueError, match='accession budget'):
        import_quarter(LocalSecQuarter(path, chunk_rows=1), SqliteSecQuarter(database), 'source-url', CIKS,
                       tracked=TRACKED, shares=SHARES, max_accessions=1)
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


def test_duplicate_zip_member_and_missing_archive_never_create_database(tmp_path):
    database = tmp_path / 'archive.db'
    with pytest.raises(ValueError, match='Ambiguous'):
        execute(archive(tmp_path / 'duplicate.zip', duplicate_member=True), database)
    assert not database.exists()
    with pytest.raises(FileNotFoundError):
        execute(tmp_path / 'absent.zip', database)
    assert not database.exists()


def test_compatibility_initializer_commits_and_preserves_num_alternatives(tmp_path):
    with closing(sqlite3.connect(tmp_path / 'archive.db')) as db:
        sec_history.ensure_schema(db)
        row = ('a', 'Revenues', 'us-gaap/2009', '2009-12-31', 4, 'USD', 100)
        db.execute('INSERT INTO sec_bulk_facts VALUES (?,?,?,?,?,?,?)', row)
        sec_history.ensure_schema(db)
        assert not db.in_transaction
        db.execute('INSERT INTO sec_bulk_facts VALUES (?,?,?,?,?,?,?)', (*row[:-1], 101))
        db.commit()
        assert db.execute('SELECT val FROM sec_bulk_facts ORDER BY val').fetchall() == [(100,), (101,)]
