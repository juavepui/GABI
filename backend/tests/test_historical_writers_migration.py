"""Captured parity and effects of historical composition and audit persistence."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from gabi import config, historical_archive, historical_membership, historical_price_policy, identity, storage, universe
from gabi.application.research import historical_accreditation as accreditation
from gabi.application.research import historical_archive as imports
from gabi.application.research import historical_archive_reads as reads
from gabi.infrastructure.storage.historical_archive_reads import SqliteHistoricalArchiveReads
from gabi.infrastructure.storage.historical_archive_writes import SqliteHistoricalArchiveWrites
from gabi.infrastructure.storage.historical_audit_writes import SqliteHistoricalAuditWrites
from gabi.infrastructure.storage.historical_composition import LocalHistoricalComposition

REFERENCE = json.loads((Path(__file__).parent / 'fixtures/historical_writers_migration.json').read_text(encoding='utf-8'))


def captured(name):
    scope = dict(__name__=f'gabi._captured_{name}', __package__='gabi')
    exec(REFERENCE[name], scope)
    return scope


def dump(path):
    with closing(sqlite3.connect(path)) as db:
        tables = sorted(name for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'"))
        return {name: sorted(db.execute(f'SELECT * FROM {name}').fetchall(), key=repr) for name in tables}


def refs():
    return [{'kind': 'identity', 'source_url': 'https://sec.example/é'},
            {'kind': 'source', 'source_url': 'https://prices.example', 'producer': 'audit:v2'}]


def series(**changes):
    return dict(cik='1', symbol='AAA', valid_from='2010-01-01', valid_to='2011-01-01',
                source_id=historical_price_policy.YAHOO_SOURCE, adjustment_basis=historical_price_policy.ADJUSTED,
                status='tier_a', evidence=refs()) | changes


def terminal(**changes):
    return dict(cik='1', symbol='AAA', event_date='2010-06-01', event_type='cash_acquisition',
                status='terminal_return_confirmed', evidence=refs(), cash_per_share=25.) | changes


def exercise_archive(api):
    api['register_source']('fixture:é', dict(start='2010-01-01', end_exclusive='2011-01-01'))
    frame = pd.DataFrame([('2010-01-01', 'BF.B,AAA'), ('2010-06-01', 'BBB')], columns=['date', 'tickers'])
    assert api['import_membership']('fixture:é', frame, '2010-01-01', '2011-01-01') == 2
    candidates = pd.DataFrame([('BF.B', '1', 'Issuer é', '2000-01-01', '', '2000-01-01')],
                              columns=['symbol', 'cik', 'name', 'date_added', 'date_removed', 'created_at'])
    assert api['import_issuer_candidates']('fixture:é', candidates) == 1
    prices = pd.DataFrame(dict(symbol=['BF.B'], date=['2010-01-04'], open=[10.], high=[11.], low=[9.],
                               close=[10.], adjusted_close=[5.], volume=[1000.]))
    for _ in range(2):
        assert api['import_price_chunk']('fixture:é', prices, {'BF-B'}, '2010-01-01', '2011-01-01') == {'accepted': 1, 'rejected': 0}
    fact = dict(tag='Revenues', unit='USD', start_date='2009-01-01', end_date='2009-12-31',
                val=123., filed_date='2010-02-01', accn='a', form='10-K', fp='FY', fy=2009)
    assert api['import_sec_facts']('fixture:é', 'BF.B', '1', [fact]) == 1
    filing = dict(cik='1', symbol='BF.B', accession='a', filed_date='2010-02-01', sha256='a' * 64,
                  source_url='https://www.sec.gov/Archives/edgar/data/1/a', historical_name='Issuer é')
    assert api['import_filing_identity_evidence']([filing]) == 1
    interval = dict(symbol='BF.B', cik='1', valid_from='2010-01-01', valid_to='2011-01-01',
                    status='corroborated_candidate', evidence_count=1, source_refs=refs())
    assert api['replace_identity_intervals']('fixture:é', [interval]) == 1


def test_all_archive_writes_and_read_contracts_match_captured(tmp_path, monkeypatch):
    old = captured('historical_archive')
    paths = [tmp_path / 'old.db', tmp_path / 'new.db']
    for path, api in zip(paths, (old, vars(historical_archive)), strict=True):
        monkeypatch.setattr(config, 'DB_PATH', path)
        exercise_archive(api)
    assert dump(paths[0]) == dump(paths[1])
    monkeypatch.setattr(config, 'DB_PATH', paths[0])
    expected = {name: old[name](*args) for name, args in [
        ('get_membership', ('fixture:é', '2010-01-04')),
        ('get_filing_identity_evidence', ('BF.B', '2010-02-01')),
        ('list_filing_identity_evidence_as_of', ('BF.B', '2010-02-02')),
        ('source_summary', ())]}
    monkeypatch.setattr(config, 'DB_PATH', paths[1])
    for name, result in expected.items():
        args = {'get_membership': ('fixture:é', '2010-01-04'),
                'get_filing_identity_evidence': ('BF.B', '2010-02-01'),
                'list_filing_identity_evidence_as_of': ('BF.B', '2010-02-02'), 'source_summary': ()}[name]
        assert getattr(historical_archive, name)(*args) == result
    old['storage'] = type('Storage', (), {'get_connection': staticmethod(lambda: closing(sqlite3.connect(paths[0])))})
    assert_frame_equal(old['get_prices']('fixture:é', 'BF.B', '2010-01-01', '2011-01-01'),
                       historical_archive.get_prices('fixture:é', 'BF.B', '2010-01-01', '2011-01-01'))


def test_price_writes_and_strict_read_match_captured(tmp_path, monkeypatch):
    old = captured('historical_price_policy')
    paths = [tmp_path / 'old.db', tmp_path / 'new.db']
    frames, events = [], []
    for path, api in zip(paths, (old, vars(historical_price_policy)), strict=True):
        monkeypatch.setattr(config, 'DB_PATH', path)
        storage.init_db()
        with storage.get_connection() as db:
            db.execute('INSERT INTO prices(symbol,date,open,high,low,close,adj_close,volume) VALUES (?,?,?,?,?,?,?,?)',
                       ('AAA', '2010-01-04', 10., 11., 9., 10., 5., 1000.))
            db.commit()
        for _ in range(2):
            api['record_series'](**series())
        frames.append(api['price_history'](cik='1', symbol='AAA', start='2010-01-01', end='2010-02-01'))
        for _ in range(2):
            api['record_terminal'](**terminal())
        events.append(api['terminal_event'](cik='1', symbol='AAA', start='2010-01-01', end='2011-01-01'))
    assert dump(paths[0]) == dump(paths[1])
    assert_frame_equal(*frames)
    assert frames[0].attrs == frames[1].attrs
    assert events[0] == events[1]


@pytest.mark.parametrize('change', [dict(status='other'), dict(valid_to='2010-01-01'),
                                  dict(evidence=[]), dict(source_id='archive:test'), dict(adjustment_basis='unknown')])
def test_invalid_accreditation_matches_original_without_creating_database(tmp_path, monkeypatch, change):
    path = tmp_path / 'missing' / 'gabi.db'
    monkeypatch.setattr(config, 'DB_PATH', path)
    old = captured('historical_price_policy')
    with pytest.raises(ValueError) as original:
        old['record_series'](**series(**change))
    with pytest.raises(ValueError, match=str(original.value)):
        historical_price_policy.record_series(**series(**change))
    assert not path.parent.exists()


def test_composition_loaders_parity_and_observe_file_and_archive_changes(tmp_path, monkeypatch):
    path, cache = tmp_path / 'gabi.db', tmp_path / 'members.csv'
    monkeypatch.setattr(config, 'DB_PATH', path)
    monkeypatch.setattr(universe, 'HISTORICAL_MEMBERSHIP_CACHE', cache)
    old = captured('historical_membership')
    frame = pd.DataFrame([('2010-01-01', 'AAA,BBB'), ('2010-06-01', 'BBB,CCC')], columns=['date', 'tickers'])
    frame.to_csv(cache, index=False)
    source = historical_membership.REFERENCE_SOURCE
    for name, api in [('old', old), ('new', vars(historical_membership))]:
        historical_archive.register_source(source, dict(start='2010-01-01', end_exclusive='2011-01-01'))
        historical_archive.import_membership(source, frame, '2010-01-01', '2011-01-01')
        for loader in ['_operational', '_archive']:
            actual, end = api[loader]()
            assert_frame_equal(actual, frame)
            assert end == ('2010-06-02' if loader == '_operational' else '2011-01-01')
        assert api['constituents_as_of']('2010-03-01')['symbols'] == ['AAA', 'BBB']
    frame.loc[0, 'tickers'] = 'BBB'
    frame.to_csv(cache, index=False)
    assert historical_membership.constituents_as_of('2010-03-01')['symbols'] == ['BBB']
    historical_archive.import_membership(source, frame, '2010-01-01', '2011-01-01')
    assert historical_membership._archive()[0].iloc[0].tickers == 'BBB'


def test_queries_are_read_only_and_do_not_use_legacy_sql_or_network(tmp_path, monkeypatch):
    path = tmp_path / 'missing' / 'gabi.db'
    monkeypatch.setattr(config, 'DB_PATH', path)
    monkeypatch.setattr(storage, 'get_connection', lambda: pytest.fail('legacy SQL'))
    monkeypatch.setattr('requests.sessions.Session.request', lambda *a, **k: pytest.fail('network'))
    assert historical_archive.get_prices('fixture', 'AAA', '2010-01-01', '2011-01-01').empty
    assert historical_archive.get_filing_identity_evidence('AAA', '2010-01-01')['status'] == 'unresolved'
    assert historical_archive.list_filing_identity_evidence_as_of('AAA', '2010-01-01')['status'] == 'no_evidence'
    assert historical_archive.source_summary() == []
    assert historical_price_policy.terminal_event(cik='1', symbol='AAA', start='2010-01-01', end='2011-01-01') is None
    with pytest.raises(ValueError, match='No unique'):
        historical_price_policy.price_history(cik='1', symbol='AAA', start='2010-01-01', end='2011-01-01')
    with pytest.raises(ValueError, match='not been imported'):
        historical_membership._archive()
    assert not path.parent.exists()
    path.parent.mkdir()
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE unrelated(x)')
        db.commit()
    before = hashlib.sha256(path.read_bytes()).digest()
    assert historical_archive.source_summary() == []
    assert historical_archive.get_prices('fixture', 'AAA', '2010-01-01', '2011-01-01').empty
    assert hashlib.sha256(path.read_bytes()).digest() == before
    assert dump(path) == {'unrelated': []}


def test_composition_and_archive_bounds_fail_closed(tmp_path):
    path, cache = tmp_path / 'gabi.db', tmp_path / 'members.csv'
    cache.write_text('date,tickers\n2010-01-01,AAA\n2010-02-01,BBB\n', encoding='utf-8')
    for options in [dict(max_bytes=8), dict(max_rows=1), dict(max_field_bytes=2)]:
        with pytest.raises(ValueError, match='limit'):
            LocalHistoricalComposition(path, cache, **options).operational()
    writer = SqliteHistoricalArchiveWrites(path, date.today)
    imports.register_source(writer, 'fixture', dict(start='2010-01-01', end_exclusive='2011-01-01'))
    imports.import_membership(writer, 'fixture', pd.read_csv(cache), '2010-01-01', '2011-01-01')
    with pytest.raises(ValueError, match='límite'):
        LocalHistoricalComposition(path, max_rows=1).archive('fixture')
    with closing(sqlite3.connect(path)) as db:
        db.execute("INSERT INTO historical_prices VALUES ('fixture','AAA','2010-01-01',1,1,1,1,1,1,'as_traded')")
        db.execute("INSERT INTO historical_prices VALUES ('fixture','AAA','2010-01-02',1,1,1,1,1,1,'as_traded')")
        db.commit()
    with pytest.raises(ValueError, match='límite'):
        reads.raw_prices(SqliteHistoricalArchiveReads(path, max_rows=1), 'fixture', 'AAA', '2010-01-01', '2011-01-01')


def test_failed_fact_dual_write_rolls_back_entity_archive_and_observations(tmp_path, monkeypatch):
    path = tmp_path / 'gabi.db'
    monkeypatch.setattr(config, 'DB_PATH', path)
    historical_archive.register_source('fixture', {})
    identity.ensure_entity('2')
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TRIGGER deny_observation BEFORE INSERT ON entity_observations BEGIN SELECT RAISE(ABORT,'fixture'); END")
        db.commit()
    before = dump(path)
    with pytest.raises(sqlite3.IntegrityError, match='fixture'):
        historical_archive.import_sec_facts('fixture', 'AAA', '1', [dict(filed_date='2010-01-01')])
    assert dump(path) == before


def test_failed_interval_replacement_retains_previous_rows(tmp_path):
    path = tmp_path / 'gabi.db'
    writer = SqliteHistoricalArchiveWrites(path, date.today)
    first = dict(symbol='AAA', cik='1', valid_from='2010-01-01', valid_to='2011-01-01',
                 status='corroborated_candidate', evidence_count=1)
    imports.replace_identity_intervals(writer, 'fixture', [first])
    before = dump(path)
    with pytest.raises(sqlite3.IntegrityError):
        imports.replace_identity_intervals(writer, 'fixture', [first, first])
    assert dump(path) == before


def test_rejected_owner_and_failed_succession_leave_previous_evidence(tmp_path, monkeypatch):
    path = tmp_path / 'gabi.db'
    monkeypatch.setattr(config, 'DB_PATH', path)
    writer = SqliteHistoricalAuditWrites(path, date.today)
    accreditation.record_series(writer, **series())
    before = dump(path)
    with pytest.raises(ValueError, match='another issuer'):
        accreditation.record_series(writer, **series(cik='2'))
    assert dump(path) == before
    accreditation.record_terminal(writer, **terminal(status='terminal_return_unknown', cash_per_share=None))
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TRIGGER deny_event BEFORE INSERT ON historical_terminal_events BEGIN SELECT RAISE(ABORT,'fixture'); END")
        db.commit()
    before = dump(path)
    with pytest.raises(sqlite3.IntegrityError, match='fixture'):
        accreditation.replace_unknown_terminal(writer, after='2010-01-01', through='2011-01-01',
                                                 **terminal(event_type='succession', exchange_ratio=1., successor_symbol='AAA'))
    assert dump(path) == before
