"""Streaming archive files and transactional SEC URL provenance; explicit paths."""

import hashlib
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from gabi.infrastructure.storage.historical_write import transaction


class SecArchiveFiles:
    def __init__(self, *, max_bytes: int = 4 * 1024**3):
        if max_bytes <= 0:
            raise ValueError('max_bytes must be positive')
        self.max_bytes = max_bytes

    def exists(self, path: str) -> bool:
        return Path(path).exists()

    def write(self, path: str, chunks: Iterable[bytes]) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=target.name + '.', suffix='.part',
                                             delete=False) as output:
                temporary = Path(output.name)
                size = 0
                for chunk in chunks:
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise ValueError('SEC archive file exceeds byte budget')
                    output.write(chunk)
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            close = getattr(chunks, 'close', None)
            if close is not None:
                close()

    def fingerprint(self, path: str) -> tuple[str, int]:
        # One bounded streaming pass: hash and byte count describe the same bytes.
        digest = hashlib.sha256()
        size = 0
        with Path(path).open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                size += len(chunk)
                if size > self.max_bytes:
                    raise ValueError('SEC archive file exceeds byte budget')
                digest.update(chunk)
        return digest.hexdigest(), size


class SqliteSecArchiveProvenance:
    def __init__(self, path: Path):
        self.path = path

    def register(self, url: str, digest: str, size: int, fetched_at: str) -> None:
        with transaction(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS sec_archive_files ('
                       'url TEXT PRIMARY KEY, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, '
                       'fetched_at TEXT NOT NULL)')
            prior = db.execute('SELECT sha256 FROM sec_archive_files WHERE url=?', (url,)).fetchone()
            if prior and prior[0] != digest:
                raise ValueError('Cached source changed; review before replacing its provenance')
            db.execute('INSERT OR IGNORE INTO sec_archive_files VALUES (?,?,?,?)',
                       (url, digest, size, fetched_at))
