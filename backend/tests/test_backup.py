"""Daily copy of the records a refresh cannot rebuild: what it holds, what it leaves out and how many it keeps."""

import gzip
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from gabi.application.administration.periodic import PeriodicTasks
from gabi.infrastructure.storage import backup
from gabi.infrastructure.storage.score_history import SqliteScoreHistory

NOW = datetime(2026, 11, 13, 5, 30, tzinfo=UTC)


def _data(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    SqliteScoreHistory(data).record("2026-11-12", "GABI-MF-v5", "sec-engine-v1", [("AAA", 70.0, 1), ("BBB", 60.0, 2)], 2)
    with closing(sqlite3.connect(data / "gabi.db")) as db, db:
        db.execute("CREATE TABLE live_ledger (seq INTEGER PRIMARY KEY, prev_hash TEXT NOT NULL, "
                   "record_hash TEXT NOT NULL, payload_json TEXT NOT NULL)")
        db.execute("INSERT INTO live_ledger VALUES (1, '0', 'a1b2c3d4e5f60718293a', '{\"ranking\": [1]}')")
        db.execute("CREATE TABLE prices (symbol TEXT, date TEXT, close REAL)")  # Downloadable: left out.
        db.execute("INSERT INTO prices VALUES ('AAA', '2026-11-12', 10.0)")
    with closing(sqlite3.connect(data / "gabi_jobs.db")) as db, db:
        db.execute("CREATE TABLE jobs (id TEXT)")
        db.execute("INSERT INTO jobs VALUES ('j1')")
    (data / "weights.json").write_text('{"value": 0.3}', encoding="utf-8")
    (data / "fred_api_key.txt").write_text("secreto", encoding="utf-8")
    (data / "live_ledger").mkdir()
    (data / "live_ledger" / "head.json").write_text('{"seq": 1}', encoding="utf-8")
    return data


def test_copy_holds_the_records_and_small_files_but_not_prices_or_keys(tmp_path):
    data, root = _data(tmp_path), tmp_path / "copias"
    report = backup.create_backup(data, root, now=NOW)
    folder = root / "2026-11-13"
    assert report == {"carpeta": str(folder), "tablas": 1, "filas": 2, "ficheros": 4,
                      "registro_diario": {"entradas": 1, "nuevas": 1}, "borradas": []}
    with closing(sqlite3.connect(folder / "registros.db")) as db:
        tables = {name for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {"score_history"}
        assert db.execute("SELECT symbol, score, rank FROM score_history ORDER BY rank").fetchall() == [
            ("AAA", 70.0, 1), ("BBB", 60.0, 2)]
    with closing(sqlite3.connect(folder / "gabi_jobs.db")) as db:
        assert db.execute("SELECT id FROM jobs").fetchall() == [("j1",)]
    assert (folder / "live_ledger" / "head.json").read_text(encoding="utf-8") == '{"seq": 1}'
    assert not (folder / "fred_api_key.txt").exists()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["tablas"] == {"score_history": 2}
    # The ledger: each entry once, compressed, outside the day folders.
    [entry] = (root / "registro-diario").glob("*.json.gz")
    assert entry.name == "000001-a1b2c3d4e5f60718.json.gz"
    with gzip.open(entry, "rt", encoding="utf-8") as handle:
        assert json.load(handle) == {"seq": 1, "prev_hash": "0", "record_hash": "a1b2c3d4e5f60718293a",
                                     "payload_json": '{"ranking": [1]}'}
    assert set(manifest["ficheros"]) == {"registros.db", "gabi_jobs.db", "weights.json", "live_ledger/head.json"}
    assert (root / "LEEME.txt").is_file()
    assert not list(root.glob(".*.tmp"))


def test_rerun_replaces_the_day_and_only_the_latest_copies_stay(tmp_path):
    data, root = _data(tmp_path), tmp_path / "copias"
    (root / "otra-cosa").mkdir(parents=True)  # Not a day folder: never removed.
    for offset in range(4):
        backup.create_backup(data, root, now=NOW + timedelta(days=offset), keep=3)
    SqliteScoreHistory(data).record("2026-11-13", "GABI-MF-v5", None, [("AAA", 71.0, 1)], 2)
    report = backup.create_backup(data, root, now=NOW + timedelta(days=3), keep=3)
    assert report["filas"] == 3 and report["borradas"] == []
    assert report["registro_diario"] == {"entradas": 1, "nuevas": 0}
    assert sorted(path.name for path in root.iterdir() if path.is_dir()) == [
        "2026-11-14", "2026-11-15", "2026-11-16", "otra-cosa", "registro-diario"]


def test_a_ledger_entry_that_differs_from_its_copy_stops_the_backup(tmp_path):
    data, root = _data(tmp_path), tmp_path / "copias"
    (root / "registro-diario").mkdir(parents=True)
    (root / "registro-diario" / "000001-ffffffffffffffff.json.gz").write_bytes(b"")
    with pytest.raises(RuntimeError, match="no coincide"):
        backup.create_backup(data, root, now=NOW)
    assert not (root / "2026-11-13").exists()


def test_destination_comes_from_backup_dir_txt(tmp_path):
    assert backup.destination(tmp_path) == tmp_path / "backups"
    (tmp_path / "backup_dir.txt").write_text("  D:\\Copias GABI \n", encoding="utf-8")
    assert str(backup.destination(tmp_path)) == "D:\\Copias GABI"


def test_a_failed_copy_leaves_no_half_folder(tmp_path, monkeypatch):
    data, root = _data(tmp_path), tmp_path / "copias"

    def broken(source, target):
        raise OSError("disco lleno")

    monkeypatch.setattr(backup, "_copy_sqlite", broken)
    with pytest.raises(OSError):
        backup.create_backup(data, root, now=NOW)
    assert [path.name for path in root.iterdir()] == ["registro-diario"]  # Ledger entries are whole files.


def test_daily_maintenance_copies_last_and_a_failure_changes_nothing_else():
    class Operations:
        def __init__(self, fail):
            self.fail, self.calls = fail, []

        def verify_ledger(self):
            return {"ok": True}

        def install_ranking_revision(self):
            return {}

        def record_engine_fundamentals(self):
            return {}

        def capture_ledger(self, error, maintenance):
            return {"seq": 1, "record_hash": "h", "payload": {"status": "OK"}}

        def capture_active_ledger(self, error, maintenance):
            return None

        def record_scores(self):
            self.calls.append("scores")
            return {}

        def save_ranking(self):
            self.calls.append("save")
            return {}

        def backup(self):
            self.calls.append("copy")
            if self.fail:
                raise OSError("disco lleno")
            return {"carpeta": "x"}

    class Store:
        def log(self, event):
            pass

    for fail in (False, True):
        operations = Operations(fail)
        tasks = PeriodicTasks(Store(), operations, None, lambda: pd.Timestamp("2026-11-13T05:00Z").to_pydatetime(),
                              lambda: 0.0, lambda: 0.0)
        tasks.status = lambda: {}
        tasks.record_due = lambda: []
        tasks.smallmid_step = lambda: {}
        report = tasks.run(refresh=False)
        assert operations.calls == ["scores", "save", "copy"]
        assert "error" not in report and report["ledger"]["status"] == "OK"
        assert report["copia"] == ({"error": "OSError: disco lleno"} if fail else {"carpeta": "x"})
