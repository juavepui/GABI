"""Revision counter of the ranking's inputs inside gabi.db (#342).

The ranking cache used to be keyed by the size and date of ``gabi.db`` and its WAL, so writing a journal note,
following a company or recording a purchase discarded a ranking that takes about a minute to rebuild. Here,
SQLite triggers on every table the ranking reads add one to ``ranking_input_revision`` on each INSERT, UPDATE or
DELETE, whoever the writer is; the rest of the database no longer invalidates the ranking.

Invalidation contract:
- ``install`` is an explicit write (daily task); a query never creates the table or the triggers.
- ``read`` returns None unless the table and the three triggers of every present input table exist, so an old
  database, a table created later or a table dropped and recreated falls back to the file-stamp token: a stale
  ranking is never served.
- ``PRAGMA schema_version`` is part of the result, so an added column (``adj_close``) also invalidates.
- ``lineage`` is a random id written once: a database restored from another lineage never matches a counter.
"""

import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

# Every table ReadOnlyMarket.ranking reads (SqlInputs, batches, sec, identities).
INPUT_TABLES = ("prices", "fundamentals", "edgar_metrics", "sec_metrics_v2", "sec_revenue_growth",
                "macro_series", "entities", "entity_aliases", "engine_fundamentals")
OPERATIONS = ("insert", "update", "delete")
TABLE = "ranking_input_revision"


def trigger_name(table: str, operation: str) -> str:
    return f"ranking_rev_{table}_{operation}"


def install(database: Path) -> dict:
    """Create the counter and the missing triggers in one transaction; idempotent. Never creates ``database``."""
    if not database.is_file():
        return {"instalado": False, "motivo": "sin base de datos"}
    with closing(sqlite3.connect(database, timeout=30)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} (id INTEGER PRIMARY KEY CHECK (id = 1), "
                       "lineage TEXT NOT NULL, revision INTEGER NOT NULL)")
            db.execute(f"INSERT OR IGNORE INTO {TABLE} (id, lineage, revision) VALUES (1, ?, 0)", (uuid.uuid4().hex,))
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            created = []
            for table in INPUT_TABLES:
                if table not in tables:
                    continue
                for operation in OPERATIONS:
                    name = trigger_name(table, operation)
                    if db.execute("SELECT 1 FROM sqlite_schema WHERE type='trigger' AND name=?", (name,)).fetchone():
                        continue
                    db.execute(f'CREATE TRIGGER "{name}" AFTER {operation.upper()} ON "{table}" BEGIN '
                               f"UPDATE {TABLE} SET revision = revision + 1 WHERE id = 1; END")
                    created.append(name)
            if created:  # Writes made before a trigger existed are not counted: start a new revision.
                db.execute(f"UPDATE {TABLE} SET revision = revision + 1 WHERE id = 1")
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return {"instalado": True, "triggers_nuevos": len(created)}


def read(db: sqlite3.Connection) -> tuple | None:
    """(lineage, revision, schema_version, present input tables) or None when the counter cannot be trusted."""
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
    if TABLE not in tables:
        return None
    triggers = {(row[0], row[1]) for row in db.execute(
        "SELECT name, tbl_name FROM sqlite_schema WHERE type='trigger' AND name LIKE 'ranking_rev_%'")}
    present = tuple(table for table in INPUT_TABLES if table in tables)
    if any((trigger_name(table, operation), table) not in triggers for table in present for operation in OPERATIONS):
        return None
    row = db.execute(f"SELECT lineage, revision FROM {TABLE} WHERE id = 1").fetchone()
    if row is None:
        return None
    schema = db.execute("PRAGMA schema_version").fetchone()[0]
    return str(row[0]), int(row[1]), int(schema), present
