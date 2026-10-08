"""Captured issuer-file parity, local invalidation, budgets and isolated operations."""

import hashlib
import json
from pathlib import Path

import pytest

from gabi import historical_issuer_evidence as facade
from gabi.infrastructure.storage.historical_issuer_evidence import HistoricalIssuerFiles

PERIODS = ['CY2012Q1', 'CY2013Q1', 'CY2016Q1', 'CY2017Q1']
REFERENCE = json.loads((Path(__file__).parent / 'fixtures/historical_runners_migration.json').read_text(encoding='utf-8'))


def captured(frames, submissions):
    scope = dict(__name__='gabi._captured_issuer_files', __package__='gabi')
    exec(REFERENCE['historical_issuer_evidence'], scope)
    scope.update(FRAMES_DIR=frames, SUBMISSIONS_DIR=submissions, PERIODS=PERIODS, ANNUAL_PERIODS=PERIODS)
    return scope


def frame(directory, kind, period, rows):
    taxonomy, tag, unit, instant = facade.FRAME_SPECS[kind]
    suffix = 'I' if instant else ''
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{taxonomy}_{tag}_{unit}_{period}{suffix}.json'
    path.write_text(json.dumps(dict(ccp=period + suffix, data=rows)), encoding='utf-8')
    return path


def filings(rows):
    return {key: [row[index] for row in rows] for index, key in enumerate(
        ('form', 'filingDate', 'accessionNumber', 'items', 'primaryDocument'))}


def submission(directory, *, cik='0000000001', pages=None):
    directory.mkdir(parents=True, exist_ok=True)
    payload = dict(cik=cik, name='Issuer é', formerNames=[dict(name='Original Corp')], tickers=['AAA'],
        filings=dict(recent=filings([
            ('10-K', '2005-03-01', 'a', '', 'a.htm'), ('10-Q', '2012-05-01', 'b', '', 'b.htm'),
            ('25-NSE', '2012-06-01', 'c', '', 'c.htm'), ('10-Q', '2012-08-01', 'd', '', 'd.htm'),
            ('8-K12B', '2013-01-01', 'e', '', 'e.htm'), ('8-K', '2013-07-01', 'f', '2.01', 'f.htm'),
            ('25-NSE', '2013-07-18', 'g', '', 'g.htm')]), files=pages or []))
    path = directory / f'CIK{cik}.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


@pytest.fixture
def files(tmp_path, monkeypatch):
    frames, submissions = tmp_path / 'frames', tmp_path / 'submissions'
    monkeypatch.setattr(facade, 'FRAMES_DIR', frames)
    monkeypatch.setattr(facade, 'SUBMISSIONS_DIR', submissions)
    monkeypatch.setattr('requests.sessions.Session.request', lambda *a, **kw: pytest.fail('Unexpected network'))
    monkeypatch.setattr('sqlite3.connect', lambda *a, **kw: pytest.fail('Unexpected SQLite access'))
    for year in (2012, 2013, 2016, 2017):
        frame(frames, 'public_float', f'CY{year}Q1', [
            dict(cik=cik, accn=f'{cik}-{year}', end=f'{year}-03-31', val=cik * 100.) for cik in range(1, 5)])
    frame(frames, 'cover_shares', 'CY2012Q1', [dict(cik=1, accn='a', end='2012-03-31', val=100.)])
    submission(submissions)
    return frames, submissions


def reader(files, **kwargs):
    return HistoricalIssuerFiles(*files, periods=PERIODS, annual_periods=PERIODS, **kwargs)


@pytest.mark.parametrize('horizon', [None, 2016, 2012])
def test_frame_facts_and_listing_life_match_captured(files, horizon):
    old, new = captured(*files), reader(files)
    new.prepare({'1', '2', '5'}, horizon)
    for cik in ('1', '2', '5'):
        assert new.issuer_facts(cik, horizon) == old['issuer_facts'](cik, horizon)
    assert new.listing_life('1', '2016-01-01', horizon) == old['listing_life']('1', '2016-01-01', horizon)
    assert new.all_facts() == old['load_frames']()


def test_missing_overlapping_page_fails_closed_and_present_pages_match(files):
    frames, directory = files
    pages = [dict(name='older.json', filingFrom='2009-01-01', filingTo='2011-12-31')]
    submission(directory, pages=pages)
    old, new = captured(*files), reader(files)
    assert new.listing_life('1') is None
    assert old['listing_life']('1') is None
    (directory / 'older.json').write_text(json.dumps(filings([
        ('10-K', '2000-03-01', 'old', '', 'old.htm')])), encoding='utf-8')
    old['listing_life'].cache_clear()
    assert new.listing_life('1') == old['listing_life']('1')
    assert new.listing_life('1')['first_periodic'] == '2000-03-01'


def test_file_revisions_and_new_files_invalidate_same_operation(files):
    frames, directory = files
    new = reader(files)
    first = new.issuer_facts('1')
    frame(frames, 'public_float', 'CY2012Q1', [dict(cik=1, accn='changed', end='2012-03-31', val=999.)])
    new.prepare({'1'})
    assert new.issuer_facts('1')['public_float'][0]['val'] == 999.
    assert first['public_float'][0]['val'] == 100.
    added = frame(frames, 'weighted_shares', 'CY2013Q1', [dict(cik=1, accn='new', end='2013-03-31', val=7.)])
    new.prepare({'1'})
    assert new.issuer_facts('1')['weighted_shares'][0]['val'] == 7.
    added.unlink()
    new.prepare({'1'})
    assert new.issuer_facts('1')['weighted_shares'] == []
    path = directory / 'CIK0000000001.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    assert new.listing_life('1')['name'] == 'Issuer é'
    payload['name'] = 'Revised issuer'
    path.write_text(json.dumps(payload), encoding='utf-8')
    assert new.listing_life('1')['name'] == 'Revised issuer'


def test_batches_retain_only_requested_issuers_and_return_independent_values(files):
    new = reader(files)
    new.prepare({'1', '2'}, 2016)
    assert set(new._facts) == {('0000000001', 2016), ('0000000002', 2016)}
    facts = new.issuer_facts('1', 2016)
    facts['public_float'][0]['val'] = 0
    assert new.issuer_facts('1', 2016)['public_float'][0]['val'] == 100.
    assert new.cached_bytes <= new.cache_bytes


def test_official_names_preserve_hash_and_observe_revisions(files):
    _, directory = files
    path = directory / 'CIK0000000001.json'
    new = reader(files)
    result = new.official_name_chain('1')
    assert result == dict(names=['Issuer é', 'Original Corp'],
                          source_url='https://data.sec.gov/submissions/CIK0000000001.json',
                          sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['name'] = 'Changed issuer'
    path.write_text(json.dumps(payload), encoding='utf-8')
    assert new.official_name_chain('1')['sha256'] != result['sha256']
    assert new.official_name_chain('1')['names'][0] == 'Changed issuer'


def test_batch_and_catalog_limits_fail_before_reading_content(files):
    with pytest.raises(ValueError, match='issuer limit'):
        reader(files, max_issuers=1).prepare({'1', '2'})
    with pytest.raises(ValueError, match='file limit'):
        reader(files, max_files=1).prepare({'1'})


@pytest.mark.parametrize('limits', [dict(max_file_bytes=1), dict(max_file_rows=1),
                                    dict(max_facts=1), dict(facts_bytes=1)])
def test_exceeding_budgets_never_publishes_partial_facts(files, limits):
    new = reader(files, **limits)
    with pytest.raises(ValueError, match='limit|budget'):
        new.prepare({'1'})
    assert new._facts == {}


def test_submissions_reject_wrong_cik_and_paths_outside_directory(files):
    _, directory = files
    path = directory / 'CIK0000000001.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['cik'] = '2'
    path.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises(ValueError, match='CIK mismatch'):
        reader(files).listing_life('1')
    submission(directory, pages=[dict(name='../outside.json')])
    with pytest.raises(ValueError, match='inside its directory'):
        reader(files).listing_life('1')


def test_reads_do_not_create_directories_and_instances_are_isolated(tmp_path):
    paths = tmp_path / 'absent-frames', tmp_path / 'absent-submissions'
    new = reader(paths)
    assert new.listing_life('1') is None
    assert all(not rows for rows in new.issuer_facts('1').values())
    assert not any(path.exists() for path in paths)
    other = reader((tmp_path / 'other', tmp_path / 'other-submissions'))
    assert other._facts == {} and other.cache == {}


def test_pages_and_filing_rows_have_separate_budgets(files):
    _, directory = files
    submission(directory, pages=[dict(name='missing.json'), dict(name='missing2.json')])
    with pytest.raises(ValueError, match='page limit'):
        reader(files, max_pages=1).listing_life('1')
    submission(directory)
    with pytest.raises(ValueError, match='filing row limit'):
        reader(files, max_file_rows=1).listing_life('1')
