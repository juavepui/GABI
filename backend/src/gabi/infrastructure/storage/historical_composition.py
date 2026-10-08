"""Bounded local CSV and read-only SQLite composition loaders; no cache."""

import hashlib
import json
from collections.abc import Callable
from datetime import date, timedelta
from io import BufferedReader, RawIOBase
from pathlib import Path

import pandas as pd

from gabi.domain.research.membership import apply_reviewed_extension
from gabi.infrastructure.storage.bounded_reads import bounded_rows, read_only


class _LimitedInput(RawIOBase):
    def __init__(self, stream, max_bytes: int):
        self.stream, self.remaining = stream, max_bytes

    def readable(self):
        return True

    def readinto(self, buffer):
        count = self.stream.readinto(memoryview(buffer)[:self.remaining + 1])
        if count > self.remaining:
            raise ValueError('Historical composition exceeds the read limit')
        self.remaining -= count
        return count


class LocalHistoricalComposition:
    def __init__(self, db: Path, cache: Path | None = None, ledger: Path | None = None,
                 *, today: Callable[[], date] = date.today, max_rows: int = 50000,
                 max_bytes: int = 16 * 1024 * 1024, max_field_bytes: int = 1024 * 1024):
        if min(max_rows, max_bytes, max_field_bytes) <= 0:
            raise ValueError('Invalid historical composition read limits')
        self.db, self.cache, self.ledger, self.today = db, cache, ledger, today
        self.limits = dict(max_rows=max_rows, max_bytes=max_bytes, max_field_bytes=max_field_bytes)

    def _json(self, path: Path) -> dict:
        with path.open('rb') as stream:
            raw = stream.read(self.limits['max_field_bytes'] + 1)
        if len(raw) > self.limits['max_field_bytes']:
            raise ValueError('Historical composition ledger exceeds the read limit')
        return json.loads(raw)

    def operational(self) -> tuple[pd.DataFrame, str]:
        if self.cache is None or not self.cache.is_file():
            raise ValueError('Historical membership cache is not available locally')
        with self.cache.open('rb') as stream:
            with BufferedReader(_LimitedInput(stream, self.limits['max_bytes'])) as bounded:
                frame = pd.read_csv(bounded, dtype={'date': str}, nrows=self.limits['max_rows'] + 1)
        if len(frame) > self.limits['max_rows']:
            raise ValueError('Historical composition exceeds the read limit')
        if any(len(str(value).encode()) > self.limits['max_field_bytes']
               for row in frame.itertuples(index=False, name=None) for value in row):
            raise ValueError('Historical composition field exceeds the read limit')
        if self.ledger is not None:
            frame = apply_reviewed_extension(frame, self._json(self.ledger), today=self.today())
        if len(frame) > self.limits['max_rows']:
            raise ValueError('Historical composition exceeds the read limit')
        if frame.empty:
            raise ValueError('Historical membership cache is empty')
        end = (date.fromisoformat(str(frame['date'].max())) + timedelta(days=1)).isoformat()
        return frame, end

    def _source(self, db, tables, source_id: str):
        rows = [] if 'historical_sources' not in tables else bounded_rows(
            db, 'SELECT metadata_json FROM historical_sources WHERE source_id=?',
            (source_id,), **self.limits)
        return json.loads(rows[0][0]) if rows else None

    def archive(self, source_id: str) -> tuple[pd.DataFrame, str]:
        with read_only(self.db, self.limits['max_field_bytes']) as (db, tables):
            if 'historical_sources' not in tables:
                raise ValueError('The fja05680 reference archive has not been imported')
            details = self._source(db, tables, source_id)
            if details is None:
                raise ValueError(f'The fja05680 reference archive has not been imported: {source_id}')
            rows = [] if 'historical_membership' not in tables else bounded_rows(
                db, 'SELECT date,tickers FROM historical_membership WHERE source_id=? ORDER BY date',
                (source_id,), **self.limits)
        return pd.DataFrame(rows, columns=['date', 'tickers']), details['end_exclusive']

    def membership(self, source_id: str, as_of: str) -> dict:
        with read_only(self.db, self.limits['max_field_bytes']) as (db, tables):
            details = self._source(db, tables, source_id)
            if details is None:
                raise ValueError('Unknown historical source')
            if not details['start'] <= as_of < details['end_exclusive']:
                raise ValueError('Date outside imported source coverage')
            rows = [] if 'historical_membership' not in tables else bounded_rows(
                db, 'SELECT * FROM (SELECT date,tickers FROM historical_membership WHERE source_id=? '
                'AND date<=? ORDER BY date DESC LIMIT 1)', (source_id, as_of), **self.limits)
        if not rows:
            raise ValueError('No source snapshot at this date')
        return dict(symbols=rows[0][1].split(','), source_date=rows[0][0], source_id=source_id,
                    quality='community_unverified', metadata=details)


class HistoricalCompositionFiles:
    def __init__(self, cache: Path, manifest: Path, *, max_bytes=16 * 1024 * 1024, max_rows=50000):
        self.cache, self.manifest = cache, manifest
        self.max_bytes, self.max_rows = max_bytes, max_rows

    def fingerprint(self) -> str:
        # Explicit comparison/import operation; never called by constituents_as_of.
        with self.cache.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()

    def pinned(self, path: Path) -> tuple[pd.DataFrame, str, dict]:
        with self.manifest.open('rb') as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('Historical source manifest exceeds the read limit')
        item = json.loads(raw)['sources']['membership']
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest != item['sha256']:
                raise ValueError(f'fja05680 file hash mismatch: {digest}')
            stream.seek(0)
            with BufferedReader(_LimitedInput(stream, self.max_bytes)) as bounded:
                frame = pd.read_csv(bounded, dtype=str, nrows=self.max_rows + 1)
        if len(frame) > self.max_rows:
            raise ValueError('Historical source exceeds the read limit')
        return frame, digest, item
