"""Captured cover/scan parity and bounded read-only effects with temporary data."""

import hashlib
import json
import re
import sqlite3
from bisect import bisect_right
from contextlib import closing, contextmanager
from pathlib import Path

import pandas as pd
import pytest
from lxml import etree

from gabi import config, historical_membership
from gabi import historical_identity_audit as facade
from gabi.application.research.identity_instances import scan
from gabi.domain.research.periods import P2010, P2016
from gabi.domain.research.ticker_corrections import correct_symbols
from gabi.infrastructure.storage.identity_instances import (
    InstanceBudgetExceeded,
    LocalIdentityInstances,
    SqliteIdentityInstances,
)

REFERENCE = json.loads((Path(__file__).parent / 'fixtures/identity_instances_migration.json').read_text(encoding='utf-8'))


def captured():
    scope = {**vars(facade), 'pd': pd, 're': re, 'bisect_right': bisect_right, 'etree': etree,
             'historical_membership': historical_membership, 'correct_symbols': correct_symbols}
    for name in ('_common_stock_symbols', 'extract_sec_instance', 'scan_local_sec_instances'):
        exec(REFERENCE[name], scope)
    return scope


def cover(path, *, cik='1', symbols=('AAA',), name='Original Corp', titles=(), members=(), namespace='sec'):
    path.parent.mkdir(parents=True, exist_ok=True)
    contexts, facts = [], []
    for index, symbol in enumerate(symbols):
        member = f'<xbrldi:explicitMember>{members[index]}</xbrldi:explicitMember>' if members else ''
        contexts.append(f'<context id="c{index}"><entity><identifier>{cik}</identifier>{member}</entity></context>')
        facts.append(f'<dei:TradingSymbol contextRef="c{index}">{symbol}</dei:TradingSymbol>')
        if titles:
            facts.append(f'<dei:Security12bTitle contextRef="c{index}">{titles[index]}</dei:Security12bTitle>')
    path.write_text(f'<xbrl xmlns:dei="http://xbrl.{namespace}.gov/dei/2014-01-31" '
                    'xmlns:xbrldi="http://xbrl.org/2006/xbrldi">' + ''.join(contexts + facts) +
                    f'<dei:EntityRegistrantName>{name}</dei:EntityRegistrantName></xbrl>', encoding='utf-8')
    return path


@pytest.fixture
def local(tmp_path, monkeypatch):
    database = tmp_path / 'test.db'
    directory = tmp_path / 'history_refresh/validation_1996_2015/instances'
    monkeypatch.setattr(config, 'DB_PATH', database)
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path)
    monkeypatch.setattr('requests.sessions.Session.request', lambda *a, **k: pytest.fail('Unexpected network'))
    with closing(sqlite3.connect(database)) as db, db:
        db.executescript('''CREATE TABLE sec_bulk_submissions (accn TEXT PRIMARY KEY,cik TEXT,filed_date TEXT,instance TEXT,name TEXT);
            CREATE TABLE historical_issuer_candidates (symbol TEXT,cik TEXT,name TEXT,date_added TEXT,date_removed TEXT,observed_from TEXT,source_id TEXT);
            CREATE TABLE historical_membership (date TEXT,tickers TEXT,source_id TEXT);''')
    return database, directory


@pytest.mark.parametrize('symbols,titles,members,reviewed', [
    (('BRK.B',), (), (), frozenset()),
    (('AAA', 'AAA-P'), ('Common Stock', 'Preferred Stock'), (), frozenset()),
    (('AAA', 'AAA-P'), (), ('us-gaap:CommonStockMember', 'vendor:PreferredMember'), frozenset()),
    (('GOOG', 'GOOGL'), ('Capital Stock', 'Class A Common Stock'), (), frozenset({'GOOG', 'GOOGL'})),
])
def test_captured_cover_parity(tmp_path, symbols, titles, members, reviewed):
    path = cover(tmp_path / 'cover.xml', symbols=symbols, titles=titles, members=members, name='Issuer é')
    args = dict(cik='0000000001', common_stock_only=True, multi_class=reviewed)
    assert facade.extract_sec_instance(path, **args) == captured()['extract_sec_instance'](path, **args)
    assert facade.extract_sec_instance(path, **args)['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('period', [P2010, P2016])
def test_captured_complete_scan_crosschecks_order_and_rejections(local, period):
    database, directory = local
    day = '2014-05-01' if period is P2010 else '2020-05-01'
    with closing(sqlite3.connect(database)) as db, db:
        for accession, symbol, name in [('a', 'AAA', ''), ('b', 'BBB', 'Issuer'), ('c', 'CCC', 'Issuer'),
                                        ('d', 'DDD', 'Issuer'), ('e', 'EEE', 'Issuer'), ('f', 'FFF', 'Issuer')]:
            cover(directory / f'{accession}.xml', symbols=(symbol,), name=name, cik='2' if accession == 'e' else '1')
            db.execute('INSERT INTO sec_bulk_submissions VALUES (?,?,?,?,?)', (accession, '0000000001', day, accession+'.xml', 'Index name'))
        (directory / 'f.xml').write_text('<broken>', encoding='utf-8')
        # Unindexed files must not be parsed or hashed.
        (directory / 'ignored.xml').write_text('<broken>', encoding='utf-8')
        for symbol, cik in [('AAA', '1'), ('BBB', '2'), ('CCC', '1'), ('CCC', '2')]:
            db.execute('INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)',
                       (symbol, cik, 'Candidate', period.start, None, period.start, facade.CANDIDATE_SOURCE))
        db.execute('INSERT INTO historical_membership VALUES (?,?,?)', (period.start, 'AAA,CCC', period.membership_source))
    expected = captured()['scan_local_sec_instances'](period)
    before = database.read_bytes()
    actual = facade.scan_local_sec_instances(period)
    assert actual == expected
    assert database.read_bytes() == before
    records, summary = actual
    assert [row['candidate_status'] for row in records] == ['agrees', 'conflicts', 'ambiguous', 'missing']
    assert records[0]['historical_name_source'] == 'sec_sub_index'
    assert summary['ticker_proofs'] == 4
    assert sum(summary['rejections'].values()) == 2


def test_multiclass_scan_preserves_legacy_crosscheck_and_summary(local, monkeypatch):
    database, directory = local
    cover(directory / 'a.xml', symbols=('GOOGL', 'GOOG'), titles=('Common Stock', 'Capital Stock'))
    nomination = dict(reason='multi_class_issuer', cik='0000000001', valid_from='2016-01-01',
                      valid_to='2026-01-01', sec_tickers=['GOOG', 'GOOGL'])
    monkeypatch.setattr(facade, 'identity_nominations', lambda: (nomination,))
    with closing(sqlite3.connect(database)) as db, db:
        db.execute('INSERT INTO sec_bulk_submissions VALUES (?,?,?,?,?)', ('a', '0000000001', '2020-05-01', 'a.xml', 'Issuer'))
        db.execute('INSERT INTO historical_membership VALUES (?,?,?)', ('2016-01-01', 'GOOG,GOOGL', P2016.membership_source))
    assert facade.scan_local_sec_instances(P2016) == captured()['scan_local_sec_instances'](P2016)
    records, summary = facade.scan_local_sec_instances(P2016)
    assert [row['symbol'] for row in records] == ['GOOG', 'GOOGL']
    assert summary['filings_with_local_instance'] == 2
    assert all('symbols' not in row for row in records)


@pytest.mark.parametrize('limits', [dict(max_file_bytes=1), dict(max_scan_bytes=1), dict(max_nodes=1)])
def test_file_budgets_abort_instead_of_returning_partial_evidence(tmp_path, limits):
    path = cover(tmp_path / 'a.xml')
    with pytest.raises(InstanceBudgetExceeded):
        LocalIdentityInstances(tmp_path, **limits).extract(path, cik='1')


def test_aggregate_file_count_bytes_and_revision_are_per_operation(tmp_path):
    first, second = cover(tmp_path / 'a.xml'), cover(tmp_path / 'b.xml')
    with pytest.raises(InstanceBudgetExceeded):
        LocalIdentityInstances(tmp_path, max_files=1).accessions({'a', 'b'})
    files = LocalIdentityInstances(tmp_path, max_scan_bytes=first.stat().st_size)
    files.extract(first, cik='1')
    with pytest.raises(InstanceBudgetExceeded):
        files.extract(second, cik='1')
    cover(first, symbols=('NEW',))
    assert LocalIdentityInstances(tmp_path).extract(first, cik='1')['symbol'] == 'NEW'


def test_missing_metadata_or_directories_have_no_creation_effect(tmp_path):
    database, directory = tmp_path / 'missing/db.sqlite', tmp_path / 'absent'
    with pytest.raises(ValueError, match='not been imported'):
        scan(SqliteIdentityInstances(database), LocalIdentityInstances(directory), ())
    assert not database.parent.exists()
    assert not directory.exists()


@pytest.mark.parametrize('limits', [dict(max_rows=1), dict(max_bytes=1), dict(max_field_bytes=1)])
def test_metadata_budgets_preserve_database(local, limits):
    database, directory = local
    with closing(sqlite3.connect(database)) as db, db:
        db.executemany('INSERT INTO sec_bulk_submissions VALUES (?,?,?,?,?)',
                       [(name, '0000000001', '2014-05-01', 'a.xml', 'Issuer') for name in ('a', 'b')])
    before = database.read_bytes()
    with pytest.raises(ValueError, match='límite'):
        scan(SqliteIdentityInstances(database, **limits), LocalIdentityInstances(directory), ())
    assert database.read_bytes() == before


def test_unsafe_accession_and_external_entities_do_not_read_external_content(tmp_path):
    with pytest.raises(ValueError, match='Unsafe'):
        LocalIdentityInstances(tmp_path).accessions({'../outside'})
    secret = tmp_path / 'secret.txt'
    secret.write_text('HIDDEN', encoding='utf-8')
    path = cover(tmp_path / 'cover.xml')
    text = path.read_text(encoding='utf-8').replace('Original Corp', '&secret;')
    path.write_text(f'<!DOCTYPE xbrl [<!ENTITY secret SYSTEM "{secret.as_uri()}">]>' + text, encoding='utf-8')
    proof = facade.extract_sec_instance(path, cik='1')
    assert proof['historical_name'] is None


def test_record_budget_fails_without_partial_result(local):
    database, directory = local
    for name in ('a', 'b'):
        cover(directory / f'{name}.xml')
    with closing(sqlite3.connect(database)) as db, db:
        db.executemany('INSERT INTO sec_bulk_submissions VALUES (?,?,?,?,?)',
                       [(name, '0000000001', '2014-05-01', 'a.xml', 'Issuer') for name in ('a', 'b')])
    with pytest.raises(ValueError, match='record budget'):
        scan(SqliteIdentityInstances(database), LocalIdentityInstances(directory), (), max_records=1)


def test_revision_during_read_is_not_published_as_evidence(tmp_path, monkeypatch):
    path = cover(tmp_path / 'a.xml')
    original_open = Path.open

    @contextmanager
    def changing_file(target, *args, **kwargs):
        with original_open(target, *args, **kwargs) as source:
            yield source
        if target == path and args == ('rb',):
            with original_open(path, 'wb') as output:
                output.write(b'revised')

    monkeypatch.setattr(Path, 'open', changing_file)
    with pytest.raises(ValueError, match='changed during read'):
        LocalIdentityInstances(tmp_path).extract(path, cik='1')
