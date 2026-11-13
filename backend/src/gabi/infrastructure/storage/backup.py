"""Daily copy of what cannot be downloaded again: stored days, the live ledger, the user's records and settings.

Prices and SEC filings (most of the 15 GB of gabi.db) are left out: a refresh downloads them again. What is
copied is dated or written by hand, so a lost day is lost for good. Each copy is one folder per day under the
destination (`data/backup_dir.txt`, else `data/backups`); the latest KEEP copies stay, older ones are removed.

The live ledger is append-only and each entry holds a whole ranking (about 5 MB), so it is not copied every day:
each entry is written once, compressed, to `registro-diario/` and never removed.
"""

import gzip
import hashlib
import json
import re
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

# Tables of gabi.db that a refresh cannot rebuild; a missing one (never used yet) is skipped.
RECORD_TABLES = (
    "score_history", "engine_fundamentals", "estimate_snapshots", "ranking_snapshots",
    "signal_events", "decision_runs", "journal_entries", "investor_profiles", "portfolio_policies",
    "portfolio_holdings", "watchlist", "investment_cards", "idea_events", "idea_observations", "idea_alerts",
    "idea_notes", "sim_portfolios", "sim_trades", "blind_validations", "blind_validation_options",
    "blind_validation_periods", "blind_validation_rankings", "experiments", "entity_snapshots",
    "cik_resolutions", "filing_comparisons",
)
# Small files next to gabi.db (API keys are never copied).
FILES = ("weights.json", "app_mode.json", "checklist_thresholds.json", "sp500_constituents.csv",
         "live_ledger/head.json")
LEDGER_DIR = "registro-diario"
JOBS_DB = "gabi_jobs.db"
RECORDS_DB = "registros.db"
DESTINATION_FILE = "backup_dir.txt"
KEEP = 30
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
README = """Copias diarias de GABI
======================

Cada carpeta (AAAA-MM-DD) es la copia de un día de lo que no se puede volver a descargar:
- registros.db: los días de puntuación guardados, Mi cartera, empresas seguidas, diario, fotos del
  ranking y otros registros fechados.
- gabi_jobs.db: el historial de tareas.
- weights.json, app_mode.json, sp500_constituents.csv, live_ledger/head.json: ajustes y cabecera del registro.
- manifest.json: filas de cada tabla y huella (SHA-256) de cada fichero, para comprobar la copia.

registro-diario/ guarda cada entrada del registro diario (ledger) una sola vez, comprimida
(NNNNNN-huella.json.gz con seq, prev_hash, record_hash y payload_json). No se borra nunca.

Los precios y las cuentas de la SEC no se copian: «Actualizar todo» los descarga de nuevo.

Para recuperar una tabla (con GABI parado), por ejemplo score_history:
  sqlite3 data\\gabi.db
  ATTACH 'RUTA\\AAAA-MM-DD\\registros.db' AS copia;
  INSERT OR IGNORE INTO score_history SELECT * FROM copia.score_history;
"""


def destination(data_dir: Path) -> Path:
    """The folder named in `data/backup_dir.txt`, else `data/backups`."""
    configured = data_dir / DESTINATION_FILE
    if configured.is_file():
        text = configured.read_text(encoding="utf-8").strip()
        if text:
            return Path(text)
    return data_dir / "backups"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_records(source: Path, target: Path) -> dict[str, int]:
    """The record tables, read in one transaction (one consistent moment) and checked by row count."""
    counts: dict[str, int] = {}
    with closing(sqlite3.connect(target, uri=True)) as db:
        db.execute("ATTACH DATABASE ? AS src", (source.as_uri() + "?mode=ro",))
        db.execute("BEGIN")
        present = dict(db.execute("SELECT name, sql FROM src.sqlite_master WHERE type='table'").fetchall())
        for table in RECORD_TABLES:
            if table not in present:
                continue
            db.execute(present[table])  # Created in main: the copy keeps the original schema.
            db.execute(f'INSERT INTO main."{table}" SELECT * FROM src."{table}"')
            counts[table] = db.execute(f'SELECT COUNT(*) FROM src."{table}"').fetchone()[0]
        db.commit()
        db.execute("DETACH DATABASE src")
        for table, rows in counts.items():
            copied = db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if copied != rows:
                raise RuntimeError(f"La copia de {table} tiene {copied} filas y el original {rows}.")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("La copia no supera la comprobación de integridad de SQLite.")
    return counts


def _copy_sqlite(source: Path, target: Path) -> None:
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src, \
            closing(sqlite3.connect(target)) as dst:
        src.backup(dst)


def _copy_ledger(source: Path, folder: Path) -> dict:
    """Writes each ledger entry not copied yet; an existing entry with another hash stops the copy."""
    folder.mkdir(parents=True, exist_ok=True)
    stored = {}
    for path in folder.glob("*.json.gz"):
        seq, _, digest = path.name.removesuffix(".json.gz").partition("-")
        stored[int(seq)] = digest
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='live_ledger'").fetchone() is None:
            return {"entradas": 0, "nuevas": 0}
        rows = db.execute("SELECT seq, prev_hash, record_hash, payload_json FROM live_ledger ORDER BY seq")
        total = new = 0
        for seq, prev_hash, record_hash, payload in rows:
            total += 1
            if seq in stored:
                if stored[seq] != record_hash[:16]:
                    raise RuntimeError(f"La entrada {seq} del registro diario no coincide con su copia anterior.")
                continue
            work = folder / f".{seq:06d}.tmp"
            with gzip.open(work, "wt", encoding="utf-8") as handle:
                json.dump({"seq": seq, "prev_hash": prev_hash, "record_hash": record_hash,
                           "payload_json": payload}, handle, ensure_ascii=False)
            work.replace(folder / f"{seq:06d}-{record_hash[:16]}.json.gz")
            new += 1
    return {"entradas": total, "nuevas": new}


def _prune(root: Path, keep: int) -> list[str]:
    """Removes the oldest day folders beyond `keep`; anything else in the folder is left alone."""
    days = sorted(path for path in root.iterdir() if path.is_dir() and DAY.match(path.name))
    removed = days[:-keep] if len(days) > keep else []
    for path in removed:
        shutil.rmtree(path)
    return [path.name for path in removed]


def create_backup(data_dir: Path, root: Path | None = None, *, now: datetime | None = None,
                  keep: int = KEEP) -> dict:
    """Writes today's copy (a rerun the same day replaces it) and returns what it holds."""
    root = root or destination(data_dir)
    now = now or datetime.now(UTC)
    day = now.date().isoformat()
    root.mkdir(parents=True, exist_ok=True)
    ledger = _copy_ledger(data_dir / "gabi.db", root / LEDGER_DIR)
    work = root / f".{day}.tmp"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    try:
        tables = _copy_records(data_dir / "gabi.db", work / RECORDS_DB)
        files = [RECORDS_DB]
        if (data_dir / JOBS_DB).is_file():
            _copy_sqlite(data_dir / JOBS_DB, work / JOBS_DB)
            files.append(JOBS_DB)
        for name in FILES:
            if (data_dir / name).is_file():
                (work / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(data_dir / name, work / name)
                files.append(name)
        manifest = {"creada": now.isoformat(timespec="seconds"), "origen": str(data_dir), "tablas": tables,
                    "registro_diario": ledger, "ficheros": {name: _sha256(work / name) for name in files}}
        (work / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        final = root / day
        if final.exists():
            shutil.rmtree(final)
        work.rename(final)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    readme = root / "LEEME.txt"
    if not readme.is_file():
        readme.write_text(README, encoding="utf-8")
    removed = _prune(root, keep)
    return {"carpeta": str(final), "tablas": len(tables), "filas": sum(tables.values()),
            "ficheros": len(files), "registro_diario": ledger, "borradas": removed}
