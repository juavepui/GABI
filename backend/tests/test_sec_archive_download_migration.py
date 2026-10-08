"""Captured download parity and failure isolation using temporary archives only."""

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from gabi import config, sec_history, storage
from gabi.application.research.sec_archive_download import download
from gabi.infrastructure.storage.sec_archive_download import SecArchiveFiles, SqliteSecArchiveProvenance

NOW = datetime(2020, 1, 2, tzinfo=UTC)
URL = 'https://www.sec.gov/test.xml'
CONTENT = b'<xbrl>issuer evidence</xbrl>'


@pytest.fixture
def http(monkeypatch):
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            calls.append('closed')

        def raise_for_status(self):
            pass

        def iter_content(self, size):
            assert size == 1024 * 1024
            yield CONTENT[:7]
            yield b''
            yield CONTENT[7:]

    def get(url, **kwargs):
        assert kwargs == dict(headers={'User-Agent': 'temporary-test'}, timeout=(20, 90), stream=True)
        calls.append(url)
        return Response()

    monkeypatch.setattr(requests, 'get', get)
    monkeypatch.setattr(sec_history.edgar, '_headers', lambda: {'User-Agent': 'temporary-test'})
    monkeypatch.setattr(sec_history.time, 'sleep', lambda delay: calls.append(delay))
    monkeypatch.setattr('requests.sessions.Session.request', lambda *a, **k: pytest.fail('Real network'))
    return calls


def rows(path):
    with sqlite3.connect(path) as db:
        return db.execute('SELECT * FROM sec_archive_files').fetchall()


def test_captured_download_parity_and_cached_idempotence(tmp_path, monkeypatch, http):
    monkeypatch.setattr(config, 'DATA_DIR', tmp_path)
    reference = json.loads((Path(__file__).parent / 'fixtures/sec_archive_download_migration.json')
                           .read_text(encoding='utf-8'))
    clock = SimpleNamespace(now=lambda zone: NOW)
    scope = dict(Path=Path, hashlib=hashlib, time=sec_history.time, requests=requests,
                 edgar=sec_history.edgar, storage=storage, ensure_schema=sec_history.ensure_schema,
                 datetime=clock, UTC=UTC)
    exec(reference['download'], scope)
    monkeypatch.setattr(sec_history, 'datetime', clock)
    results = []
    for label, action in [('old', scope['download']), ('new', sec_history.download)]:
        database = tmp_path / f'{label}.db'
        monkeypatch.setattr(config, 'DB_PATH', database)
        path = tmp_path / label / 'source.xml'
        assert action(URL, path) == path
        count = len(http)
        assert action(URL, path) == path
        assert len(http) == count
        results.append((path.read_bytes(), rows(database)))
        assert not list(path.parent.glob('*.part'))
    assert results[0] == results[1] == (CONTENT, [(URL, hashlib.sha256(CONTENT).hexdigest(),
                                                 len(CONTENT), NOW.isoformat())])
    assert http == [0.15, URL, 'closed', 0.15, URL, 'closed']


def test_cached_revision_rejected_without_replacing_provenance(tmp_path):
    database, path = tmp_path / 'archive.db', tmp_path / 'cached.xml'
    provenance = SqliteSecArchiveProvenance(database)
    args = dict(files=SecArchiveFiles(), provenance=provenance,
                source=lambda url: iter([CONTENT]), now=lambda: NOW)
    download(URL, str(path), **args)
    prior = rows(database)
    path.write_bytes(b'revised')
    with pytest.raises(ValueError, match='Cached source changed'):
        download(URL, str(path), **{**args, 'source': lambda url: pytest.fail('Cached network')})
    assert rows(database) == prior
    assert path.read_bytes() == b'revised'


@pytest.mark.parametrize('failure', ['network', 'budget'])
def test_failed_stream_closes_and_removes_partial_without_registering(tmp_path, failure):
    database, path = tmp_path / 'archive.db', tmp_path / 'files' / 'source.xml'
    closed = []

    def source(url):
        try:
            yield b'first'
            if failure == 'network':
                raise requests.ConnectionError('interrupted')
            yield b'too large'
        finally:
            closed.append(True)

    with pytest.raises((requests.ConnectionError, ValueError)):
        download(URL, str(path), files=SecArchiveFiles(max_bytes=5),
                 provenance=SqliteSecArchiveProvenance(database), source=source, now=lambda: NOW)
    assert closed == [True]
    assert not path.exists()
    assert not database.exists()
    assert list(path.parent.iterdir()) == []


def test_cached_budget_and_legacy_bulk_schema_are_untouched(tmp_path):
    database, path = tmp_path / 'archive.db', tmp_path / 'source.xml'
    path.write_bytes(CONTENT)
    with sqlite3.connect(database) as db:
        db.executescript('CREATE TABLE sec_bulk_facts (val REAL); INSERT INTO sec_bulk_facts VALUES (7);')
    args = dict(provenance=SqliteSecArchiveProvenance(database),
                source=lambda url: pytest.fail('Cached network'), now=lambda: NOW)
    with pytest.raises(ValueError, match='budget'):
        download(URL, str(path), files=SecArchiveFiles(max_bytes=1), **args)
    download(URL, str(path), files=SecArchiveFiles(), **args)
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT * FROM sec_bulk_facts').fetchall() == [(7,)]
        assert {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {
            'sec_bulk_facts', 'sec_archive_files'}


def test_explicit_operations_isolated_and_competing_url_registration(tmp_path):
    databases = [tmp_path / 'a.db', tmp_path / 'b.db']
    for index, database in enumerate(databases):
        download(URL, str(tmp_path / f'{index}.xml'), files=SecArchiveFiles(),
                 provenance=SqliteSecArchiveProvenance(database), source=lambda url: iter([CONTENT]),
                 now=lambda: NOW)
    before = rows(databases[1])
    repository = SqliteSecArchiveProvenance(databases[0])

    def register(digest):
        try:
            repository.register(URL + '/other', digest, 1, NOW.isoformat())
            return 'ok'
        except ValueError:
            return 'conflict'

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(register, ['a' * 64, 'b' * 64])) == ['conflict', 'ok']
    assert rows(databases[1]) == before
    assert len(rows(databases[0])) == 2


def test_failed_stream_preserves_existing_destination(tmp_path):
    path = tmp_path / 'source.xml'
    path.write_bytes(CONTENT)

    def chunks():
        yield b'partial'
        raise OSError('interrupted')

    with pytest.raises(OSError):
        SecArchiveFiles().write(str(path), chunks())
    assert path.read_bytes() == CONTENT
    assert list(tmp_path.iterdir()) == [path]


def test_registration_failure_can_resume_from_complete_cached_file(tmp_path):
    database, path = tmp_path / 'archive.db', tmp_path / 'source.xml'

    class UnavailableProvenance:
        def register(self, *args):
            raise sqlite3.OperationalError('database unavailable')

    with pytest.raises(sqlite3.OperationalError):
        download(URL, str(path), files=SecArchiveFiles(), provenance=UnavailableProvenance(),
                 source=lambda url: iter([CONTENT]), now=lambda: NOW)
    assert path.read_bytes() == CONTENT
    assert not database.exists()
    download(URL, str(path), files=SecArchiveFiles(), provenance=SqliteSecArchiveProvenance(database),
             source=lambda url: pytest.fail('Retry must use cached file'), now=lambda: NOW)
    assert rows(database) == [(URL, hashlib.sha256(CONTENT).hexdigest(), len(CONTENT), NOW.isoformat())]
