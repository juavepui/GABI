"""Bounded local quarter batches and atomic SQLite writes, without legacy imports."""

import sqlite3
import zipfile
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from gabi.infrastructure.storage.historical_write import initialize, transaction

SCHEMA = """
CREATE TABLE IF NOT EXISTS sec_archive_files (
 url TEXT PRIMARY KEY, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sec_bulk_submissions (
 accn TEXT PRIMARY KEY, cik TEXT NOT NULL, name TEXT, sic TEXT, form TEXT,
 filed_date TEXT, accepted TEXT, fy TEXT, fp TEXT, instance TEXT, source_url TEXT
);
CREATE TABLE IF NOT EXISTS sec_bulk_facts (
 accn TEXT, tag TEXT, version TEXT, end_month TEXT, qtrs INTEGER, unit TEXT, val REAL,
 PRIMARY KEY(accn,tag,version,end_month,qtrs,unit,val)
);
CREATE INDEX IF NOT EXISTS idx_sec_bulk_cik ON sec_bulk_submissions(cik,filed_date);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    # Never executescript: DDL/migration must participate in the caller's transaction.
    initialize(conn, SCHEMA)
    columns = conn.execute('PRAGMA table_info(sec_bulk_facts)').fetchall()
    if not next(column[5] for column in columns if column[1] == 'val'):
        conn.execute('ALTER TABLE sec_bulk_facts RENAME TO sec_bulk_facts_old')
        conn.execute('CREATE TABLE sec_bulk_facts ('
                     'accn TEXT, tag TEXT, version TEXT, end_month TEXT, qtrs INTEGER, unit TEXT, val REAL, '
                     'PRIMARY KEY(accn,tag,version,end_month,qtrs,unit,val))')
        conn.execute('INSERT INTO sec_bulk_facts SELECT * FROM sec_bulk_facts_old')
        conn.execute('DROP TABLE sec_bulk_facts_old')


def initialize_compatibility(conn: sqlite3.Connection) -> None:
    # The old public initializer committed pending work before running its DDL.
    # New imports use ensure_schema inside their own transaction instead.
    conn.commit()
    conn.execute('BEGIN IMMEDIATE')
    with conn:
        ensure_schema(conn)


class LocalSecQuarter:
    def __init__(self, path: Path, *, chunk_rows: int = 20000, max_sub_bytes: int = 256 * 1024**2,
                 max_num_bytes: int = 4 * 1024**3, max_rows: int = 25000000,
                 max_chunk_bytes: int = 64 * 1024**2, max_field_bytes: int = 1024**2,
                 max_archive_bytes: int = 4 * 1024**3):
        if min(chunk_rows, max_sub_bytes, max_num_bytes, max_rows, max_chunk_bytes,
               max_field_bytes, max_archive_bytes) <= 0:
            raise ValueError('Invalid SEC quarter read budgets')
        self.path, self.chunk_rows = path, chunk_rows
        self.member_bytes = {'sub.txt': max_sub_bytes, 'num.txt': max_num_bytes}
        self.max_rows, self.max_chunk_bytes, self.max_field_bytes = max_rows, max_chunk_bytes, max_field_bytes
        self.max_archive_bytes = max_archive_bytes

    @contextmanager
    def batches(self, member: str):
        limit = self.member_bytes[member]
        if self.path.stat().st_size > self.max_archive_bytes:
            raise ValueError('SEC quarter archive exceeds byte budget')
        with zipfile.ZipFile(self.path) as archive:
            info = archive.getinfo(member)
            if info.file_size > limit:
                raise ValueError('SEC quarter member exceeds byte budget')
            if sum(item.filename == member for item in archive.infolist()) != 1:
                raise ValueError('Ambiguous SEC quarter member')
            with archive.open(info) as stream:
                with pd.read_csv(stream, sep='\t', dtype=str, keep_default_na=False,
                                 chunksize=self.chunk_rows) as reader:
                    def bounded():
                        count = 0
                        for frame in reader:
                            count += len(frame)
                            if count > self.max_rows or frame.memory_usage(deep=True).sum() > self.max_chunk_bytes:
                                raise ValueError('SEC quarter batch exceeds row/byte budget')
                            if any(len(value.encode('utf-8')) > self.max_field_bytes
                                   for row in frame.itertuples(index=False, name=None) for value in row):
                                raise ValueError('SEC quarter field exceeds byte budget')
                            yield frame
                    yield bounded()


class _QuarterWrites:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def submissions(self, records: list[tuple]) -> None:
        self.conn.executemany('INSERT OR REPLACE INTO sec_bulk_submissions VALUES (?,?,?,?,?,?,?,?,?,?,?)', records)

    def facts(self, records: list[tuple]) -> None:
        self.conn.executemany('INSERT OR REPLACE INTO sec_bulk_facts VALUES (?,?,?,?,?,?,?)', records)


class SqliteSecQuarter:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def transaction(self):
        with transaction(self.path) as conn:
            ensure_schema(conn)
            yield _QuarterWrites(conn)
