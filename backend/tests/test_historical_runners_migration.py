"""Captured runner parity, explicit effects and bounded historical reads."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from gabi import config, historical_archive, historical_identity_audit, historical_membership, sec_history, storage
from gabi import historical_price_audit as facade
from gabi.application.research import historical_composition as composition
from gabi.application.research import historical_identity_audit as identities
from gabi.application.research import historical_price_audit as prices
from gabi.domain.research.periods import P2010
from gabi.infrastructure.storage.historical_archive_writes import SqliteHistoricalArchiveWrites
from gabi.infrastructure.storage.historical_audit_exports import HistoricalAuditFiles
from gabi.infrastructure.storage.historical_audit_writes import SqliteHistoricalAuditWrites
from gabi.infrastructure.storage.historical_composition import HistoricalCompositionFiles
from gabi.infrastructure.storage.historical_identity_audit import SqliteIdentityAuditReads
from gabi.infrastructure.storage.historical_price_audit import SqlitePriceAuditReads
from gabi.infrastructure.storage.ticker_prices import SqliteTickerPrices

REFERENCE = json.loads((Path(__file__).parent / 'fixtures/historical_runners_migration.json').read_text(encoding='utf-8'))


def captured(name):
    scope = dict(__name__=f'gabi._captured_{name}', __package__='gabi',
                 __file__=str(Path(facade.__file__).with_name(name + '.py')))
    exec(REFERENCE[name], scope)
    return scope


@pytest.fixture
def local(tmp_path, monkeypatch):
    path = tmp_path / 'fixture.db'
    monkeypatch.setattr(config, 'DB_PATH', path)
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(facade.issuer_evidence, 'FRAMES_DIR', tmp_path / 'frames')
    monkeypatch.setattr(facade.issuer_evidence, 'SUBMISSIONS_DIR', tmp_path / 'submissions')
    monkeypatch.setattr('requests.sessions.Session.request', lambda *a, **kw: pytest.fail('Unexpected network'))
    historical_archive.register_source(P2010.membership_source,
        dict(start=P2010.start, end_exclusive=P2010.end_exclusive))
    historical_archive.import_membership(P2010.membership_source,
        pd.DataFrame([('2010-01-01', 'AAA,REC'), ('2014-01-01', 'AAA,REC,BBB')], columns=['date', 'tickers']),
        P2010.start, P2010.end_exclusive)
    historical_archive.import_issuer_candidates(historical_identity_audit.CANDIDATE_SOURCE,
        pd.DataFrame([('AAA', '1', 'Alpha', '2009-01-01', '', '2020-01-01'),
                      ('REC', '2', 'Recycled', '2010-01-01', '2012-01-01', '2010-01-01'),
                      ('REC', '3', 'New issuer', '2012-01-01', '', '2013-01-01')],
                     columns=['symbol', 'cik', 'name', 'date_added', 'date_removed', 'created_at']))
    historical_archive.import_filing_identity_evidence([
        dict(symbol='AAA', cik='1', accession=f'a-{day}', filed_date=day, historical_name='Alpha Inc',
             sha256='a' * 64, source_url=f'https://www.sec.gov/Archives/edgar/data/1/{day}/x.xml')
        for day in ['2011-02-01', '2013-02-01', '2016-02-01']])
    with storage.get_connection() as db:
        db.executescript(storage.SCHEMA)
        db.executescript(sec_history.SCHEMA)
        db.commit()
    return path


def test_identity_build_and_quarterly_coverage_match_captured(local, monkeypatch):
    old = captured('historical_identity_audit')
    monkeypatch.setattr(historical_identity_audit.issuer_evidence, 'listing_life', lambda cik: None)
    old['identity_nominations'] = lambda: ()
    old['apply_nominations'] = lambda rows: rows
    reader = SqliteIdentityAuditReads(local)
    expected = old['build_evidence_intervals']()
    before = local.read_bytes()
    actual = identities.build_evidence_intervals(reader, lambda cik: None, lambda cik: None, ())
    assert actual == expected
    assert {row['status'] for row in actual} == {'confirmed_by_multiple_evidence', 'unresolved'}
    assert local.read_bytes() == before
    historical_archive.replace_identity_intervals(P2010.identity_source, actual)
    assert identities.coverage_report(reader) == old['coverage_report']()


def test_composition_overlap_and_pinned_import_match_captured(tmp_path, monkeypatch):
    primary = pd.DataFrame([('2010-01-01', 'AAA,BBB'), ('2011-01-01', 'AAA,CCC')], columns=['date', 'tickers'])
    reference = pd.DataFrame([('2010-01-01', 'AAA,BBB'), ('2011-01-01', 'BBB,CCC')], columns=['date', 'tickers'])
    cache, manifest = tmp_path / 'membership.csv', tmp_path / 'manifest.json'
    primary.to_csv(cache, index=False)
    digest = hashlib.sha256(cache.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(dict(sources=dict(membership=dict(sha256=digest)))), encoding='utf-8')
    files = HistoricalCompositionFiles(cache, manifest)
    old = captured('historical_membership')
    old['_operational'] = lambda: (primary, '2016-01-01')
    old['_archive'] = lambda source=None: (reference, '2016-01-01')
    old['universe'] = SimpleNamespace(HISTORICAL_MEMBERSHIP_CACHE=cache)
    reader = SimpleNamespace(operational=old['_operational'], archive=old['_archive'])
    assert composition.overlap_report(reader, files, '2010-01-01', '2016-01-01') == old['overlap_report']()
    previous, current = tmp_path / 'previous.db', tmp_path / 'current.db'
    old['historical_backfill_manifest'] = lambda: manifest
    monkeypatch.setattr(config, 'DB_PATH', previous)
    expected = old['import_full_reference'](cache)
    actual = composition.import_full_reference(files, SqliteHistoricalArchiveWrites(current, today=date.today), cache)
    assert actual == expected
    for table in ('historical_sources', 'historical_membership'):
        with closing(sqlite3.connect(previous)) as db, closing(sqlite3.connect(current)) as new:
            assert db.execute(f'SELECT * FROM {table}').fetchall() == new.execute(f'SELECT * FROM {table}').fetchall()
    cache.write_text('date,tickers\n2010-01-01,CHANGED\n', encoding='utf-8')
    with pytest.raises(ValueError, match='hash mismatch'):
        files.pinned(cache)


def price_inputs(local):
    sessions = pd.bdate_range('2009-01-01', '2016-12-31')
    with closing(sqlite3.connect(local)) as db:
        db.executemany('INSERT INTO prices(symbol,date,close,adj_close) VALUES (?,?,?,?)',
            [(symbol, day.date().isoformat(), 10. + i / 100, 10. + i / 100)
             for symbol in ('AAA', 'SPY') for i, day in enumerate(sessions)])
        db.commit()
    members = dict(members=[dict(symbol='AAA', cik='0000000001', identity_tier='confirmed_by_multiple_evidence',
                                entity_id='cik:0000000001'), dict(symbol='MISSING', cik=None)])
    evidence = SimpleNamespace(listing_life=lambda *a: None,
        issuer_facts=lambda *a: dict(public_float=[], cover_shares=[], weighted_shares=[],
                                   dividends_declared=[], dividends_paid=[]))
    return SimpleNamespace(sessions=sessions), members, evidence


def test_multi_date_price_runner_matches_captured_and_is_read_only(local, monkeypatch):
    calendar, members, evidence = price_inputs(local)
    old = captured('historical_price_audit')
    monkeypatch.setattr(facade.xcals, 'get_calendar', lambda *a, **kw: calendar)
    monkeypatch.setattr(historical_membership, 'constituents_as_of', lambda *a, **kw: members)
    monkeypatch.setattr(facade.issuer_evidence, 'listing_life', evidence.listing_life)
    monkeypatch.setattr(facade.issuer_evidence, 'issuer_facts', evidence.issuer_facts)
    monkeypatch.setattr(facade.issuer_evidence, 'reader', lambda: SimpleNamespace(
        listing_life=evidence.listing_life, issuer_facts=evidence.issuer_facts, prepare=lambda *args: None))
    dates = ['2012-12-31', '2013-12-31']
    expected, summary = old['audit'](local, dates=dates)
    before = local.read_bytes()
    actual, result = prices.audit(SqlitePriceAuditReads(local), lambda day: members, evidence,
        calendar=calendar, source_ids=facade.source_ids(P2010), nominations=(), database_name=local.name, dates=dates)
    assert_frame_equal(actual, expected)
    assert result == summary
    assert local.read_bytes() == before


def test_price_facade_uses_explicit_database_for_membership(local, tmp_path, monkeypatch):
    calendar, _, evidence = price_inputs(local)
    monkeypatch.setattr(facade.xcals, 'get_calendar', lambda *a, **kw: calendar)
    monkeypatch.setattr(facade.issuer_evidence, 'listing_life', evidence.listing_life)
    monkeypatch.setattr(facade.issuer_evidence, 'issuer_facts', evidence.issuer_facts)
    other = tmp_path / 'absent-configured.db'
    monkeypatch.setattr(config, 'DB_PATH', other)
    frame, _ = facade.audit(local, dates=['2012-12-31'])
    assert set(frame.symbol) == {'AAA', 'REC', 'SPY'}
    assert not other.exists()


def test_runner_only_writes_and_fetches_documents_when_requested(local, tmp_path, monkeypatch):
    calendar, members, evidence = price_inputs(local)
    def unexpected(*a, **kw):
        pytest.fail('Unexpected write or document fetch')
    sentinel = SimpleNamespace(remove_producer=unexpected, record_series=unexpected,
                               record_terminal=unexpected, replace_unknown_terminal=unexpected)
    csv, report = tmp_path / 'audit.csv', tmp_path / 'audit.json'
    result = prices.run(SqlitePriceAuditReads(local), lambda day: members, evidence,
        calendar=calendar, source_ids=facade.source_ids(P2010), nominations=(), database_name=local.name,
        writer=sentinel, document=unexpected, exporter=HistoricalAuditFiles(), csv=csv, report=report,
        audit_url='https://audit.example', dates=['2012-12-31', '2013-12-31'])
    assert json.loads(report.read_text(encoding='utf-8')) == result
    assert 'evidence_refs' not in pd.read_csv(csv).columns


def test_terminal_command_processes_multiple_issuers(local):
    calls = []
    def listing(cik, *args):
        calls.append(cik)
        return dict(source_url=f'https://sec.example/{cik}', delisting=dict(filed='2012-02-01'),
                    events=[], current_reports=[], annual_reports=[])
    evidence = SimpleNamespace(listing_life=listing)
    # No completion filing: the conservative unknown terminal event is still stored.
    frame = pd.DataFrame([dict(symbol=s, cik=c, as_of='2011-12-31', sec_delisting='2012-02-01')
                          for s, c in [('AAA', '0000000001'), ('REC', '0000000002')]])
    writer = SqliteHistoricalAuditWrites(local, today=lambda: date(2026, 1, 1))
    result = prices.record_terminal_events(writer, evidence, lambda *a: pytest.fail('Unexpected fetch'), frame)
    assert calls == ['0000000001', '0000000002']
    assert sum(result.values()) == 2


def test_promotion_merges_windows_and_persists_same_evidence_as_captured(local, tmp_path, monkeypatch):
    price_inputs(local)
    historical_archive.replace_identity_intervals(P2010.identity_source, [dict(
        symbol='AAA', cik='1', valid_from='2010-01-01', valid_to='2016-01-01',
        status='confirmed_by_multiple_evidence', evidence_count=2,
        source_refs=[dict(source_url='https://www.sec.gov/Archives/edgar/data/1/proof.xml')])])
    frame = pd.DataFrame([dict(symbol='AAA', source_symbol='AAA', cik='0000000001', selected_source='yahoo',
        as_of=day, yahoo_first=start, yahoo_last=day, holding_covered_until=until,
        evidence_refs=dict(listing=[], adjustment=[], level=[]))
        for day, start, until in [('2012-12-31', '2012-01-01', '2013-03-31'),
                                  ('2013-03-31', '2012-04-01', '2013-06-30')]])
    previous = tmp_path / 'previous.db'
    with closing(sqlite3.connect(local)) as source, closing(sqlite3.connect(previous)) as target:
        source.backup(target)
    old = captured('historical_price_audit')
    monkeypatch.setattr(config, 'DB_PATH', previous)
    expected = old['promote'](previous, frame)
    writer = SqliteHistoricalAuditWrites(local, today=date.today)
    actual = prices.promote(SqlitePriceAuditReads(local), writer, frame, period=P2010,
        source_ids=facade.source_ids(P2010), audit_url=str(facade.outputs(P2010)['url']))
    assert actual == expected
    assert actual['intervals_promoted'] == dict(tier_a=1, tier_b=0)
    for table in ('historical_price_provenance', 'entities'):
        with closing(sqlite3.connect(local)) as db, closing(sqlite3.connect(previous)) as reference:
            assert db.execute(f'SELECT * FROM {table}').fetchall() == reference.execute(f'SELECT * FROM {table}').fetchall()


def test_export_bytes_and_failed_replacement(tmp_path, monkeypatch):
    exporter = HistoricalAuditFiles()
    records = [dict(symbol='AAA', value=None, name='Emisor é', source_refs=[{'z': 1, 'a': 'é'}])]
    expected, actual = tmp_path / 'expected.csv', tmp_path / 'actual.csv'
    pd.DataFrame(records).to_csv(expected, index=False)
    exporter.evidence(records, actual)
    assert actual.read_bytes() == expected.read_bytes()
    pd.DataFrame([{**r, 'source_refs': json.dumps(r['source_refs'], sort_keys=True)} for r in records]).to_csv(expected, index=False)
    exporter.intervals(records, actual)
    assert actual.read_bytes() == expected.read_bytes()
    expected.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    exporter.report(records, actual)
    assert actual.read_bytes() == expected.read_bytes()
    previous = actual.read_bytes()
    monkeypatch.setattr('gabi.infrastructure.storage.historical_audit_exports.os.replace',
                        lambda *a: (_ for _ in ()).throw(OSError('replacement failed')))
    with pytest.raises(OSError, match='replacement failed'):
        exporter.report({'changed': True}, actual)
    assert actual.read_bytes() == previous
    assert not list(tmp_path.glob('.*.tmp'))


def test_ticker_adapter_matches_legacy_and_does_not_initialize_schema(local, tmp_path):
    price_inputs(local)
    old = captured('storage')
    expected = old['get_prices_multi'](['AAA', 'SPY', 'missing'])
    actual = SqliteTickerPrices(local).many(['AAA', 'SPY', 'missing'])
    assert actual.keys() == expected.keys()
    for symbol in actual:
        assert_frame_equal(actual[symbol], expected[symbol])
    missing = tmp_path / 'missing' / 'db.sqlite'
    assert SqliteTickerPrices(missing).many(['AAA']) == {}
    assert SqliteTickerPrices(missing).get('AAA').empty
    assert not missing.parent.exists()
    with pytest.raises(ValueError):
        SqliteTickerPrices(local, max_rows=1).many(['AAA'])


def test_ticker_limits_span_batches_and_old_schema_is_not_altered(tmp_path):
    path = tmp_path / 'old-schema.db'
    symbols = [f'S{index:03}' for index in range(201)]
    with closing(sqlite3.connect(path)) as db:
        db.execute('CREATE TABLE prices(symbol TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)')
        db.executemany('INSERT INTO prices VALUES (?, ?,1,1,1,1,1)', [(s, '2012-01-02') for s in symbols])
        db.commit()
    before = path.read_bytes()
    with pytest.raises(ValueError, match='límite'):
        SqliteTickerPrices(path, max_rows=200).many(symbols)
    frames = SqliteTickerPrices(path).many(symbols)
    assert list(frames) == symbols
    assert frames['S000'].adj_close.isna().all()
    assert path.read_bytes() == before


def test_identity_missing_database_and_row_limits_are_read_only(tmp_path, local):
    path = tmp_path / 'missing.db'
    with pytest.raises(ValueError, match='Missing local identity tables'):
        identities.coverage_report(SqliteIdentityAuditReads(path))
    with pytest.raises(ValueError, match='snapshots missing'):
        identities.build_evidence_intervals(SqliteIdentityAuditReads(path), lambda c: None, lambda c: None, ())
    assert not path.exists()
    with pytest.raises(ValueError, match='límite'):
        SqliteIdentityAuditReads(local, max_rows=1).evidence_inputs(P2010)


def test_price_snapshot_cache_is_bounded_and_expires_between_operations(local):
    price_inputs(local)
    reader = SqlitePriceAuditReads(local, cache_bytes=100000)
    with reader.snapshot() as data:
        first = data.series('AAA', '2012-01-01', '2013-01-01', archive=False, source_id='')
        assert first is data.series('AAA', '2012-01-01', '2013-01-01', archive=False, source_id='')
        for year in range(2009, 2016):
            data.series('AAA', f'{year}-01-01', f'{year}-12-31', archive=False, source_id='')
        assert data.cached_bytes <= reader.cache_bytes
    with closing(sqlite3.connect(local)) as db:
        db.execute("UPDATE prices SET close=777 WHERE symbol='AAA' AND date='2012-01-02'")
        db.commit()
    with reader.snapshot() as data:
        assert data.series('AAA', '2012-01-01', '2013-01-01', archive=False, source_id='').loc['2012-01-02', 'close'] == 777
