"""Consistent SQLite copies taken before explicit long-running data actions."""

import sqlite3
from contextlib import closing
from pathlib import Path


def backup_once(source: Path, target: Path) -> bool:
    """Copy the database once before ingestion; an absent source leaves an empty 'before' copy."""
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(target)) as backup:
        if source.is_file():
            with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)) as db:
                db.backup(backup)
        backup.commit()
    return True
