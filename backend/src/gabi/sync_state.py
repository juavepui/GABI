"""Shared local checkpoints and measured update events; no alternate scheduler."""

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd
import requests

from gabi.domain.market.sync_events import event_checkpoint, validate_status

from . import storage

SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_checkpoints (
    source TEXT NOT NULL, entity TEXT NOT NULL, dataset TEXT NOT NULL,
    state_json TEXT NOT NULL, PRIMARY KEY (source, entity, dataset)
);
CREATE TABLE IF NOT EXISTS sync_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, entity TEXT NOT NULL,
    dataset TEXT NOT NULL, at TEXT NOT NULL, event_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sync_events_at ON sync_events(at);
"""
_PACE_LOCK = threading.Lock()
_NEXT_REQUEST: dict[str, float] = {}


def _pace(source: str, seconds: float) -> None:
    # Shared across workers: SEC's four threads must not each independently burst.
    with _PACE_LOCK:
        now = time.perf_counter()
        delay = max(0., _NEXT_REQUEST.get(source, now) - now)
        _NEXT_REQUEST[source] = now + delay + seconds
    if delay:
        time.sleep(delay)


def get(source: str, entity: str, dataset: str) -> dict:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        row = conn.execute("SELECT state_json FROM sync_checkpoints WHERE source=? AND entity=? AND dataset=?",
                           (source, entity, dataset)).fetchone()
    return json.loads(row[0]) if row else {}


def due(checkpoint: dict, hours: float, now: datetime | None = None) -> bool:
    if checkpoint.get("status") == "failed" or not checkpoint.get("last_success"):
        return True
    checked = datetime.fromisoformat(checkpoint["last_success"])
    return ((now or datetime.now(UTC)) - checked).total_seconds() >= hours * 3600


def fingerprint(value) -> str:
    safe = json.loads(json.dumps(value, default=str), parse_constant=lambda _: None)
    return hashlib.sha256(json.dumps(safe, sort_keys=True, allow_nan=False).encode()).hexdigest()


def delta_rows(old: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """Same observation key changed => revised; unseen key => new. NaNs equal."""
    if new.index.has_duplicates:
        raise ValueError("Observaciones duplicadas en la respuesta.")
    fresh = ~new.index.isin(old.index)
    aligned = old.reindex(index=new.index, columns=new.columns)
    equal = new.eq(aligned) | (new.isna() & aligned.isna())
    changed = ~equal.all(axis=1) & ~fresh
    return new.loc[fresh | changed], int(fresh.sum()), int(changed.sum())


def change_status(new: int, revised: int) -> str:
    # Counts preserve mixed outcomes; revised takes precedence over new.
    return "revised" if revised else "new" if new else "unchanged"


@dataclass
class Attempt:
    source: str
    entity: str
    dataset: str
    calls: int = 0
    payload_bytes: int = 0  # decoded payload; explicitly not wire bytes
    started: float = field(default_factory=time.perf_counter)
    cpu_started: float = field(default_factory=time.thread_time)

    def payload(self, value) -> None:
        self.payload_bytes += len(json.dumps(value, default=str).encode())

    def finish(self, status: str, *, state: dict | None = None, new: int = 0, revised: int = 0,
               unchanged: int = 0, reason: str = "", skipped: bool = False) -> dict:
        validate_status(status)
        now = datetime.now(UTC).isoformat()
        previous = get(self.source, self.entity, self.dataset)
        event, checkpoint = event_checkpoint(self.source, self.entity, self.dataset, previous, now,
            status=status, calls=self.calls, payload_bytes=self.payload_bytes,
            seconds=time.perf_counter() - self.started, cpu_seconds=time.thread_time() - self.cpu_started,
            state=state, new=new, revised=revised, unchanged=unchanged, reason=reason, skipped=skipped)
        with storage.get_connection() as conn:
            conn.executescript(SCHEMA)
            if not skipped:
                conn.execute("INSERT INTO sync_checkpoints VALUES (?,?,?,?) "
                             "ON CONFLICT(source,entity,dataset) DO UPDATE SET state_json=excluded.state_json",
                             (self.source, self.entity, self.dataset, json.dumps(checkpoint)))
            conn.execute("INSERT INTO sync_events(source,entity,dataset,at,event_json) VALUES (?,?,?,?,?)",
                         (self.source, self.entity, self.dataset, now, json.dumps(event)))
            conn.commit()
        return event


def retry(call, attempt: Attempt, *, attempts: int = 3, pace: float = .25):
    """Bounded retry; only transient network/rate failures. Never checkpoint here."""
    from .data_fetch import RETRYABLE_CATEGORIES, _classify_error

    for i in range(attempts):
        if pace:
            _pace(attempt.source, max(.15, pace) if attempt.source == "sec" else pace)
        attempt.calls += 1
        try:
            return call()
        except Exception as exc:
            category, _ = _classify_error(exc)
            response = getattr(exc, "response", None)
            transient = (category in RETRYABLE_CATEGORIES or isinstance(exc, (requests.Timeout, requests.ConnectionError))
                         or (response is not None and response.status_code >= 500))
            if not transient or i + 1 == attempts:
                raise
            # Respect Retry-After seconds, bounded to keep a failed run resumable.
            delay = min(30., 1.5 * 2 ** i)
            if response is not None:
                try:
                    delay = min(30., max(delay, float(response.headers.get("Retry-After", delay))))
                except ValueError:
                    pass
            time.sleep(delay)
    raise RuntimeError("No se completó la petición.")


def events_since(event_id: int = 0) -> list[dict]:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        rows = conn.execute("SELECT event_json FROM sync_events WHERE id>? ORDER BY id", (event_id,)).fetchall()
    return [json.loads(r[0]) for r in rows]


def latest_event_id() -> int:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        return int(conn.execute("SELECT COALESCE(MAX(id),0) FROM sync_events").fetchone()[0])


def failed_datasets(source: str) -> set[tuple[str, str]]:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        rows = conn.execute("SELECT entity,dataset FROM sync_checkpoints WHERE source=? "
                            "AND json_extract(state_json,'$.status')='failed'", (source,)).fetchall()
    return set(rows)


def totals(events: list[dict]) -> dict:
    return {**{k: sum(e.get(k, 0) for e in events)
               for k in ("calls", "payload_bytes", "seconds", "cpu_seconds", "new", "revised", "unchanged")},
            "statuses": {s: sum(e["status"] == s for e in events) for s in ("new", "revised", "unchanged", "failed")},
            "skipped": sum(e["skipped"] for e in events)}
