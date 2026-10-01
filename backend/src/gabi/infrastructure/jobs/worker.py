"""Single local worker with a renewable lease and atomic artifact publication."""

import hashlib
import json
import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from gabi.application.administration.jobs import JobCommand
from gabi.infrastructure.storage.jobs import SqliteJobs


@contextmanager
def process_lock(data_dir: Path) -> Iterator[bool]:
    """Kernel-held lock prevents a suspended old worker racing a new one."""
    directory = data_dir / "jobs"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "worker.lock").open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


class _Cancelled(Exception):
    """Cancellation requested while the executor was reporting progress."""


class Worker:
    """Runs queued jobs. An executor with `reports_progress = True` is called as
    `execute(command, progress)`, where `progress(fraction, phase)` moves the job between 5 % and 90 %."""

    def __init__(self, store: SqliteJobs, execute: Callable[..., dict], data_dir: Path):
        self.store, self.execute, self.data_dir = store, execute, data_dir

    def _progress(self, job_id: str, token: str) -> Callable[[float, str], None]:
        last: dict = {"value": None, "phase": None}

        def report(fraction: float, phase: str) -> None:
            value = 5 + round(85 * min(max(float(fraction), 0.0), 1.0))
            if (value, phase) == (last["value"], last["phase"]):
                return
            last.update(value=value, phase=phase)
            if self.store.progress(job_id, token, value, phase[:200]):
                raise _Cancelled
        return report

    def run_once(self) -> bool:
        with process_lock(self.data_dir) as acquired:
            return self._run_locked() if acquired else False

    def _run_locked(self) -> bool:
        token = uuid4().hex
        job = self.store.claim(token)
        if job is None:
            return False
        job_id = job["id"]
        stop = threading.Event()

        def pulse() -> None:
            while not stop.wait(5):
                if not self.store.heartbeat(job_id, token):
                    return

        heartbeat = threading.Thread(target=pulse, daemon=True)
        heartbeat.start()
        artifact: Path | None = None
        try:
            if self.store.progress(job_id, token, 5, "Preparando datos", {"stage": "started"}):
                self.store.finish(job_id, token, "cancelled")
                return True
            command = JobCommand(job["kind"], tuple(job["parameters"]["symbols"]),
                                 job["parameters"]["start"], job["parameters"]["end"],
                                 job["parameters"].get("portfolio_id"),
                                 job["parameters"].get("decision_policy"),
                                 job["parameters"].get("holdings_text"),
                                 job["parameters"].get("snapshot_id"),
                                 job["parameters"].get("factor_months"),
                                 job["parameters"].get("factor_mode"),
                                 job["parameters"].get("factor_max_symbols"),
                                 job["parameters"].get("backtest_options"),
                                 job["parameters"].get("research_log"),
                                 job["parameters"].get("factor_contrast"),
                                 job["parameters"].get("preparation"),
                                 job["parameters"].get("outcomes"),
                                 job["parameters"].get("experiment_analysis"),
                                 job["parameters"].get("live_report"),
                                 job["parameters"].get("blind"),
                                 job["parameters"].get("portfolio_options"),
                                 job["parameters"].get("company"),
                                 job["parameters"].get("update"),
                                 job["parameters"].get("health"))
            if getattr(self.execute, "reports_progress", False):
                result = self.execute(command, self._progress(job_id, token))
            else:
                result = self.execute(command)
            if self.store.progress(job_id, token, 90, "Guardando resultado", {"stage": "computed"}):
                self.store.finish(job_id, token, "cancelled")
                return True
            raw = json.dumps(result, ensure_ascii=False, allow_nan=False, default=str, sort_keys=True).encode()
            if len(raw) > 10_000_000:
                raise ValueError("Resultado superior al límite de 10 MB.")
            directory = self.data_dir / "jobs" / "results"
            directory.mkdir(parents=True, exist_ok=True)
            artifact = directory / f"{job_id}.json"
            temporary = directory / f"{job_id}.{token}.tmp"
            try:
                temporary.write_bytes(raw)
                temporary.replace(artifact)
            finally:
                temporary.unlink(missing_ok=True)
            digest = hashlib.sha256(raw).hexdigest()
            if not self.store.finish(job_id, token, "succeeded", ref=job_id, digest=digest):
                artifact.unlink(missing_ok=True)
        except _Cancelled:
            self.store.finish(job_id, token, "cancelled")
        except Exception:
            # No exception text, local paths, credentials or blind output in the HTTP log.
            self.store.finish(job_id, token, "failed", error="job_failed")
            if artifact is not None:
                artifact.unlink(missing_ok=True)
        finally:
            stop.set()
            heartbeat.join(timeout=6)
        return True
