"""Explicit archive imports; each operation commits or rolls back as one unit."""
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

from gabi.domain.market.identity import DATA_KEYS
from gabi.infrastructure.storage.historical_archive_schema import SCHEMA
from gabi.infrastructure.storage.historical_write import ensure_entity, initialize, transaction
from gabi.infrastructure.storage.identity_writes import put_observations


class SqliteHistoricalArchiveWrites:
    def __init__(self, path: Path, today: Callable[[], date]):
        self.path, self.today = path, today

    def _save(self, statement: str, records: list[tuple]) -> None:
        with transaction(self.path) as conn:
            initialize(conn, SCHEMA)
            conn.executemany(statement, records)

    def register_sources(self, records: list[tuple]) -> None:
        self._save('INSERT OR REPLACE INTO historical_sources VALUES (?,?)', records)

    def import_membership(self, records: list[tuple]) -> None:
        self._save('INSERT OR REPLACE INTO historical_membership VALUES (?,?,?)', records)

    def import_candidates(self, records: list[tuple]) -> None:
        self._save('INSERT OR REPLACE INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)', records)

    def import_prices(self, records: list[tuple]) -> None:
        self._save('INSERT OR IGNORE INTO historical_prices VALUES (?,?,?,?,?,?,?,?,?,?)', records)

    def replace_intervals(self, source_id: str, records: list[tuple]) -> None:
        with transaction(self.path) as conn:
            initialize(conn, SCHEMA)
            conn.execute('DELETE FROM historical_identity_intervals WHERE source_id=?', (source_id,))
            conn.executemany('INSERT INTO historical_identity_intervals VALUES (?,?,?,?,?,?,?,?,?,?)', records)

    def import_facts(self, source_id: str, symbol: str, cik: str, rows: list[dict], source_url: str) -> int:
        records = [(source_id, symbol, cik,
                    json.dumps([r.get(k, '') for k in DATA_KEYS['edgar_facts']]),
                    r['filed_date'], json.dumps(r, allow_nan=False)) for r in rows]
        with transaction(self.path) as conn:
            initialize(conn, SCHEMA)
            entity = ensure_entity(conn, cik, self.today())
            conn.executemany('INSERT OR REPLACE INTO historical_facts VALUES (?,?,?,?,?,?)', records)
            put_observations(conn, entity, 'edgar_facts', symbol, rows, source_url)
        return len(records)

    def import_filings(self, records: list[tuple]) -> int:
        with transaction(self.path) as conn:
            for cik, symbol, payload, source_url in records:
                entity = ensure_entity(conn, cik, self.today())
                put_observations(conn, entity, 'filing_identity', symbol, [payload], source_url)
        return len(records)
