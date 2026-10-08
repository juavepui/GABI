"""Compare cached SEC provenance registration on synthetic temporary archives."""

import hashlib
import json
import sqlite3
import sys
import tempfile
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from measure_f7_historical_writers import measure

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend/src'))


def main():
    from gabi import sec_history
    from gabi.application.research.sec_archive_download import download
    from gabi.infrastructure.storage.sec_archive_download import SecArchiveFiles, SqliteSecArchiveProvenance

    now = datetime(2020, 1, 2, tzinfo=UTC)
    reference = json.loads((ROOT / 'backend/tests/fixtures/sec_archive_download_migration.json')
                           .read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='gabi-sec-download-') as directory:
        root = Path(directory)
        old_db, new_db = root / 'old.db', root / 'new.db'

        @contextmanager
        def connection():
            db = sqlite3.connect(old_db, timeout=30)
            db.execute('PRAGMA journal_mode=WAL')
            try:
                with db:
                    yield db
            finally:
                db.close()

        def no_network(*args, **kwargs):
            raise AssertionError('Cached registration must not download')

        old = dict(Path=Path, hashlib=hashlib, storage=SimpleNamespace(get_connection=connection),
                   ensure_schema=sec_history.ensure_schema, datetime=SimpleNamespace(now=lambda zone: now),
                   UTC=UTC, requests=SimpleNamespace(get=no_network), time=SimpleNamespace(sleep=no_network))
        exec(reference['download'], old)
        sources = []
        for index in range(32):
            path = root / f'{index}.xml'
            path.write_bytes(bytes([index]) * (256 * 1024))
            sources.append((f'https://www.sec.gov/test/{index}.xml', path))

        def previous():
            for url, path in sources:
                old['download'](url, path)
            return archived(old_db)

        def current():
            for url, path in sources:
                download(url, str(path), files=SecArchiveFiles(), provenance=SqliteSecArchiveProvenance(new_db),
                         source=no_network, now=lambda: now)
            return archived(new_db)

        def archived(database):
            with closing(sqlite3.connect(database)) as db:
                return db.execute('SELECT * FROM sec_archive_files ORDER BY url').fetchall()

        expected, before = measure(previous)
        actual, after = measure(current)
        assert actual == expected
        print(json.dumps(dict(files=len(sources), source_bytes=sum(p.stat().st_size for _, p in sources),
                              before=before, after=after), indent=2))


if __name__ == '__main__':
    main()
