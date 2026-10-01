"""Read-only prospective ledger: streamed rows and head anchor, with no lock file, schema or write."""

import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path

from gabi.application.errors import QueryError
from gabi.domain.research.live_ledger import UNREADABLE

MAX_EVENTS = 100_000
MAX_PAYLOAD_CHARS = 50_000_000
MAX_ANCHOR_BYTES = 4_096
Row = tuple[int, str, str, str]


class SqliteLiveLedger:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi.db"
        self.anchor_path = data_dir / "live_ledger" / "head.json"

    def stamp(self) -> tuple:
        """Changes whenever the database, its WAL or the anchor may have changed."""
        stamps: list[tuple[int, int, int] | None] = []
        for path in (self.path, self.path.with_name("gabi.db-wal"), self.anchor_path):
            try:
                stat = path.stat()
                stamps.append((stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
            except FileNotFoundError:
                stamps.append(None)
        return tuple(stamps)

    def _anchor(self):
        if not self.anchor_path.exists():
            return {"seq": 0, "hash": ""}
        try:
            with self.anchor_path.open("rb") as stream:
                raw = stream.read(MAX_ANCHOR_BYTES + 1)
            return UNREADABLE if len(raw) > MAX_ANCHOR_BYTES else json.loads(raw)
        except (OSError, ValueError):
            return UNREADABLE

    def _connect(self):
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        db.execute("PRAGMA query_only=ON")
        return closing(db)

    @staticmethod
    def _exists(db) -> bool:
        return db.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name='live_ledger'").fetchone() is not None

    def scan(self, consume: Callable[[Iterator[Row], object], dict]) -> dict:
        """Run `consume(rows, anchor)` over every row in seq order inside one read snapshot."""
        if not self.path.is_file():
            return consume(iter(()), self._anchor())
        try:
            with self._connect() as db:
                db.execute("BEGIN")
                if not self._exists(db):
                    return consume(iter(()), self._anchor())
                count, largest = db.execute(
                    "SELECT COUNT(*), COALESCE(MAX(length(payload_json)),0) FROM live_ledger").fetchone()
                if count > MAX_EVENTS or largest > MAX_PAYLOAD_CHARS:
                    raise QueryError("live_ledger_limit", "El registro prospectivo supera el límite de lectura.", 503)
                anchor = self._anchor()  # The writer anchors after committing; read it inside the snapshot.
                return consume(db.execute(
                    "SELECT seq,prev_hash,record_hash,payload_json FROM live_ledger ORDER BY seq"), anchor)
        except sqlite3.Error as exc:
            raise QueryError("live_ledger_unavailable", "No se puede leer el registro prospectivo.", 503) from exc

    def row(self, seq: int) -> Row | None:
        if not self.path.is_file():
            return None
        try:
            with self._connect() as db:
                if not self._exists(db):
                    return None
                found = db.execute("SELECT seq,prev_hash,record_hash,payload_json FROM live_ledger WHERE seq=? "
                                   "AND length(payload_json) <= ?", (seq, MAX_PAYLOAD_CHARS)).fetchone()
                return tuple(found) if found else None
        except sqlite3.Error as exc:
            raise QueryError("live_ledger_unavailable", "No se puede leer el registro prospectivo.", 503) from exc
