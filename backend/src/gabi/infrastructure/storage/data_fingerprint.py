"""SHA-256 v2 of the local cache content, read in one consistent read-only transaction."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

TABLES = ("prices", "splits", "fundamentals", "edgar_metrics", "edgar_facts",
          "entity_snapshots", "cik_resolutions", "macro_series", "macro_meta",
          "entities", "entity_aliases", "entity_observations", "entity_candidates")
FILES = ("sp500_constituents.csv", "sp500_historical_membership.csv", "sec_cik_map.csv")
# Download times do not change the actual financial input.
IGNORED_COLUMNS = {"fetched_at", "resolved_at"}


def fingerprint(database: Path, data_dir: Path, selected: list[str] | None, inputs: dict) -> str:
    """``selected`` None hashes every symbol; an absent database hashes as empty tables, without creating it."""
    digest = hashlib.sha256()

    def feed(value):
        digest.update(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":"), default=str).encode("utf-8"))
        digest.update(b"\n")

    feed({"version": 2, "symbols": selected, "inputs": inputs})
    if database.is_file():
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            _tables(conn, selected, feed)
    else:
        for table in TABLES:
            feed(table)
    for name in FILES:
        path = data_dir / name
        feed(name)
        if path.exists():
            frame = pd.read_csv(path, dtype=str).fillna("")
            columns = sorted(frame.columns)
            feed(columns)
            for row in sorted(frame[columns].itertuples(index=False, name=None)):
                feed(row)
    return "v2:" + digest.hexdigest()


def _tables(conn: sqlite3.Connection, selected: list[str] | None, feed) -> None:
    existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in TABLES:
        feed(table)
        if table not in existing:
            continue
        columns = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")') if r[1] not in IGNORED_COLUMNS]
        feed(columns)
        fields = ",".join(f'"{c}"' for c in columns)
        query = f'SELECT {fields} FROM "{table}"'
        params: list[str] = []
        if selected is not None and "symbol" in columns and not table.startswith("entit"):
            query += " WHERE symbol IN (" + ",".join("?" for _ in selected) + ")"
            params = selected
        query += " ORDER BY " + fields
        for row in conn.execute(query, params):
            feed([json.loads(value) if column.endswith("_json") and value else value
                  for column, value in zip(columns, row, strict=True)])
