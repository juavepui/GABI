"""SQLite backup and coverage counts for the explicit 1996-2015 backfill command."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path


class SqliteHistoricalBackfill:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        # Same 30 s lock wait and WAL journal as the compatibility connection it replaces.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn

    def backup(self, destination: Path) -> None:
        with self._connection() as conn, closing(sqlite3.connect(destination)) as copy:
            conn.backup(copy)

    @staticmethod
    def _old_symbols(conn, end: str) -> tuple[set[str], set[str]]:
        facts = {s for s, in conn.execute("SELECT DISTINCT symbol FROM edgar_facts WHERE filed_date<?", (end,))}
        prices = {s for s, in conn.execute("SELECT DISTINCT symbol FROM prices WHERE date<? AND adj_close IS NOT NULL", (end,))}
        return facts, prices

    def operational(self, end: str) -> tuple[dict[str, str], set[str], set[str]]:
        """Stored CIKs and the symbols that already have facts/adjusted prices before ``end``."""
        with self._connection() as conn:
            stored = dict(conn.execute("SELECT symbol,cik FROM edgar_metrics"))
            return stored, *self._old_symbols(conn, end)

    def summary(self, price_source: str, issuer_source: str, end: str) -> dict:
        with self._connection() as conn:
            archive = dict(zip(["rows", "symbols", "first", "last"], conn.execute(
                "SELECT COUNT(*),COUNT(DISTINCT symbol),MIN(date),MAX(date) FROM historical_prices WHERE source_id=?",
                (price_source,)).fetchone(), strict=True))
            facts, prices = self._old_symbols(conn, end)
            sec = dict(zip(["rows", "candidate_symbols", "issuers", "first_filed", "last_filed"],
                conn.execute("SELECT COUNT(*),COUNT(DISTINCT candidate_symbol),COUNT(DISTINCT cik),"
                             "MIN(filed_date),MAX(filed_date) FROM historical_facts WHERE source_id=?",
                             (issuer_source,)).fetchone(), strict=True))
            integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        return {"archive_coverage": archive, "old_facts": facts, "old_prices": prices,
                "archived_sec_facts": sec, "sqlite_integrity": integrity}
