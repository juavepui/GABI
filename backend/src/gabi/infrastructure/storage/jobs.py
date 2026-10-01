"""Small WAL queue separate from the large market database.

Reading jobs never creates a database. All state changes use short transactions;
the worker lease fences terminal updates after a process restart.
"""

import hashlib
import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from gabi.application.administration.jobs import JobCommand
from gabi.application.errors import QueryError

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, parameters TEXT NOT NULL,
 idempotency_key TEXT NOT NULL UNIQUE, origin TEXT NOT NULL,
 status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
 phase TEXT NOT NULL DEFAULT 'En espera', cancel_requested INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
 worker_token TEXT, lease_until TEXT, error_code TEXT,
 result_ref TEXT, result_sha256 TEXT, checkpoint TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS jobs_latest ON jobs(created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS jobs_one_running ON jobs((1)) WHERE status='running';
CREATE TABLE IF NOT EXISTS job_events (
 id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
 at TEXT NOT NULL, message TEXT NOT NULL
);
"""
PUBLIC = ("id", "kind", "parameters", "origin", "status", "progress", "phase", "cancel_requested",
          "created_at", "started_at", "finished_at", "error_code", "result_ref", "result_sha256", "checkpoint")


def now() -> str:
    return datetime.now(UTC).isoformat()


class SqliteJobs:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "gabi_jobs.db"
        self.data_dir = data_dir
        self._ready = False
        self._init_lock = threading.Lock()

    @contextmanager
    def connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection | None]:
        if not write and not self.path.is_file():
            yield None
            return
        if write:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=5)
            with self._init_lock:
                if not self._ready:
                    for attempt in range(10):
                        try:
                            connection.execute("PRAGMA journal_mode=WAL")
                            connection.executescript(SCHEMA)
                            self._ready = True
                            break
                        except sqlite3.OperationalError as exc:
                            if "locked" not in str(exc).lower() or attempt == 9:
                                connection.close()
                                raise
                            time.sleep(0.05 * (attempt + 1))
        else:
            connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
            connection.execute("PRAGMA query_only=ON")
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            if write:
                connection.commit()
        except Exception:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def public(row: sqlite3.Row, events: list[sqlite3.Row] | None = None) -> dict:
        result = {key: row[key] for key in PUBLIC}
        result["parameters"] = json.loads(result["parameters"])
        result["checkpoint"] = json.loads(result["checkpoint"])
        result["cancel_requested"] = bool(result["cancel_requested"])
        if events is not None:
            result["events"] = [{"at": event["at"], "message": event["message"]} for event in events]
        return result

    def enqueue(self, command: JobCommand, key: str, origin: str) -> dict:
        payload: dict[str, object] = {"symbols": command.symbols, "start": command.start, "end": command.end}
        if command.portfolio_id is not None:
            payload["portfolio_id"] = command.portfolio_id
        if command.decision_policy is not None:
            payload["decision_policy"] = command.decision_policy
            payload["holdings_text"] = command.holdings_text
        if command.snapshot_id is not None:
            payload["snapshot_id"] = command.snapshot_id
        if command.kind == "factor_analysis":
            payload["factor_months"] = command.factor_months
            payload["factor_mode"] = command.factor_mode
            payload["factor_max_symbols"] = command.factor_max_symbols
        if command.backtest_options is not None:
            payload["backtest_options"] = command.backtest_options
        if command.research_log is not None:
            payload["research_log"] = command.research_log
        if command.factor_contrast is not None:
            payload["factor_contrast"] = command.factor_contrast
        if command.preparation is not None:
            payload["preparation"] = command.preparation
        if command.outcomes is not None:
            payload["outcomes"] = command.outcomes
        if command.experiment_analysis is not None:
            payload["experiment_analysis"] = command.experiment_analysis
        parameters = json.dumps(payload, sort_keys=True)
        with self.connection(write=True) as db:
            assert db is not None
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM jobs WHERE idempotency_key=?", (key,)).fetchone()
            if existing:
                if existing["kind"] != command.kind or existing["parameters"] != parameters:
                    raise QueryError("idempotency_conflict", "Esta clave ya corresponde a otro trabajo.", 409)
                return self.public(existing)
            if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running') AND kind=? LIMIT 1",
                          (command.kind,)).fetchone():
                raise QueryError("job_conflict", "Ya hay un trabajo de este tipo pendiente o en curso.", 409)
            job_id = uuid4().hex
            db.execute("INSERT INTO jobs(id,kind,parameters,idempotency_key,origin,status,created_at) "
                       "VALUES(?,?,?,?,?,'queued',?)", (job_id, command.kind, parameters, key, origin, now()))
            db.execute("INSERT INTO job_events(job_id,at,message) VALUES(?,?,?)", (job_id, now(), "Trabajo encolado"))
            return self.public(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def list(self, limit: int = 30) -> list[dict]:
        with self.connection() as db:
            if db is None:
                return []
            return [self.public(row) for row in db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))]

    def get(self, job_id: str) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone() if db else None
            if row is None:
                raise QueryError("job_not_found", "El trabajo no existe.", 404)
            assert db is not None
            events = db.execute("SELECT at,message FROM job_events WHERE job_id=? ORDER BY id DESC LIMIT 30", (job_id,))
            return self.public(row, list(reversed(events.fetchall())))

    def result(self, job_id: str) -> dict:
        job = self.get(job_id)
        if job["status"] != "succeeded" or job["result_ref"] != job_id or not job["result_sha256"]:
            raise QueryError("result_unavailable", "El resultado aún no está disponible.", 404)
        artifact = self.data_dir / "jobs" / "results" / f"{job_id}.json"
        try:
            raw = artifact.read_bytes()
            if len(raw) > 10_000_000 or hashlib.sha256(raw).hexdigest() != job["result_sha256"]:
                raise ValueError("Result hash mismatch")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("Invalid result")
            return result
        except (OSError, ValueError) as exc:
            raise QueryError("result_unavailable", "El artefacto no se puede verificar.", 503) from exc

    def cancel(self, job_id: str) -> dict:
        with self.connection(write=True) as db:
            assert db is not None
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise QueryError("job_not_found", "El trabajo no existe.", 404)
            if row["status"] == "queued":
                db.execute("UPDATE jobs SET status='cancelled', phase='Cancelado', finished_at=? WHERE id=?", (now(), job_id))
            elif row["status"] == "running":
                db.execute("UPDATE jobs SET cancel_requested=1, phase='Cancelación solicitada' WHERE id=?", (job_id,))
            else:
                return self.public(row)
            db.execute("INSERT INTO job_events(job_id,at,message) VALUES(?,?,?)", (job_id, now(), "Cancelación solicitada"))
            return self.public(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def claim(self, token: str) -> dict | None:
        with self.connection(write=True) as db:
            assert db is not None
            db.execute("BEGIN IMMEDIATE")
            running = db.execute("SELECT * FROM jobs WHERE status='running'").fetchone()
            if running:
                if running["lease_until"] > now():
                    return None
                db.execute("UPDATE jobs SET status='failed', phase='Interrumpido', error_code='worker_interrupted', "
                           "finished_at=?, worker_token=NULL WHERE id=?", (now(), running["id"]))
                db.execute("INSERT INTO job_events(job_id,at,message) VALUES(?,?,?)",
                           (running["id"], now(), "Worker interrumpido; resultado no publicado"))
            row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1").fetchone()
            if row is None:
                return None
            until = (datetime.now(UTC) + timedelta(seconds=30)).isoformat()
            db.execute("UPDATE jobs SET status='running', started_at=?, worker_token=?, lease_until=?, "
                       "phase='Iniciando' WHERE id=?", (now(), token, until, row["id"]))
            db.execute("INSERT INTO job_events(job_id,at,message) VALUES(?,?,?)", (row["id"], now(), "Worker iniciado"))
            return self.public(db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())

    def heartbeat(self, job_id: str, token: str) -> bool:
        with self.connection(write=True) as db:
            assert db is not None
            until = (datetime.now(UTC) + timedelta(seconds=30)).isoformat()
            updated = db.execute("UPDATE jobs SET lease_until=? WHERE id=? AND worker_token=? AND status='running'",
                                 (until, job_id, token)).rowcount
            return bool(updated)

    def progress(self, job_id: str, token: str, value: int, phase: str, checkpoint: dict | None = None) -> bool:
        with self.connection(write=True) as db:
            assert db is not None
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT cancel_requested FROM jobs WHERE id=? AND worker_token=? AND status='running'",
                             (job_id, token)).fetchone()
            if row is None:
                return True
            if checkpoint is None:
                db.execute("UPDATE jobs SET progress=?, phase=? WHERE id=?", (value, phase, job_id))
            else:
                db.execute("UPDATE jobs SET progress=?, phase=?, checkpoint=? WHERE id=?",
                           (value, phase, json.dumps(checkpoint), job_id))
            db.execute("INSERT INTO job_events(job_id,at,message) VALUES(?,?,?)", (job_id, now(), phase))
            return bool(row["cancel_requested"])

    def finish(self, job_id: str, token: str, status: str, *, error: str | None = None,
               ref: str | None = None, digest: str | None = None) -> bool:
        with self.connection(write=True) as db:
            assert db is not None
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT cancel_requested FROM jobs WHERE id=? AND worker_token=? AND status='running'",
                             (job_id, token)).fetchone()
            if row is None:
                return False
            if row["cancel_requested"]:
                status, error, ref, digest = "cancelled", None, None, None
            phase = {"succeeded": "Completado", "failed": "Fallido", "cancelled": "Cancelado"}[status]
            db.execute("UPDATE jobs SET status=?, progress=?, phase=?, finished_at=?, error_code=?, "
                       "result_ref=?, result_sha256=?, worker_token=NULL, lease_until=NULL WHERE id=?",
                       (status, 100 if status == "succeeded" else 0, phase, now(), error, ref, digest, job_id))
            db.execute("INSERT INTO job_events(job_id,at,message) VALUES(?,?,?)", (job_id, now(), phase))
            return status == "succeeded"
