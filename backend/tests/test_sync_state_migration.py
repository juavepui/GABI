"""Captured parity of source error classification, retry/pacing, fingerprints and sync checkpoints/events."""

import ast
import json
import sqlite3
import time
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
import sync_checkpoints as sync_state

from gabi import config, storage
from gabi.domain.market import source_errors
from gabi.domain.market.sync_events import event_checkpoint, validate_status
from gabi.infrastructure.legacy import data_fetch
from gabi.infrastructure.providers import source_retry
from gabi.infrastructure.storage import sync_events as event_store

REFERENCE = json.loads((Path(__file__).parent / "fixtures/sync_state_migration.json").read_text(encoding="utf-8"))
MESSAGES = ["429 Client Error: Too Many Requests", "Rate limit exceeded", "possibly delisted; no price data found",
            "404 Not Found", "HTTPSConnectionPool: Read timed out", "timeout", "Failed to establish a new connection",
            "Could not resolve host", "network unreachable", "Expecting value: line 1 column 1 (char 0)", "bad JSON",
            "algo muy raro pasó", "", "x" * 500, "RATE LIMIT and timeout", "connection timed out"]


def captured_data_fetch() -> dict:
    namespace: dict = {}
    for node in ast.parse(REFERENCE["data_fetch"]).body:
        if isinstance(node, ast.FunctionDef) and node.name == "_classify_error" or isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "RETRYABLE_CATEGORIES" for t in node.targets):
            exec(ast.get_source_segment(REFERENCE["data_fetch"], node), namespace)
    return namespace


def captured_sync(path: Path, clock) -> SimpleNamespace:
    @contextmanager
    def get_connection():
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=30)) as db:
            yield db
    source = REFERENCE["sync_state"].replace("from . import storage", "")
    source = source.replace("    from .data_fetch import RETRYABLE_CATEGORIES, _classify_error\n", "")
    old = captured_data_fetch()
    namespace = {"__name__": "captured_sync_state", "storage": SimpleNamespace(get_connection=get_connection),
                 "RETRYABLE_CATEGORIES": old["RETRYABLE_CATEGORIES"], "_classify_error": old["_classify_error"]}
    exec(source, namespace)
    namespace["datetime"] = clock
    namespace["time"] = time
    return SimpleNamespace(**namespace)


class Clock(datetime):
    moment = datetime(2026, 5, 4, 12, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls.moment


@pytest.mark.parametrize("service", ["Yahoo Finance", "SEC EDGAR", "FRED"])
def test_classification_matches_capture(service):
    old = captured_data_fetch()
    assert data_fetch.RETRYABLE_CATEGORIES == old["RETRYABLE_CATEGORIES"] == set(source_errors.RETRYABLE_CATEGORIES)
    for message in MESSAGES:
        assert data_fetch._classify_error(Exception(message), service) == old["_classify_error"](Exception(message), service)
        assert source_errors.classify(message, service) == old["_classify_error"](Exception(message), service)


def test_pure_rules_match_capture(tmp_path):
    old = captured_sync(tmp_path / "old.db", Clock)
    values = [{"b": 1, "a": [1.5, float("nan"), None]}, {"when": Clock.moment}, [float("inf")], "text", 3]
    for value in values:
        assert sync_state.fingerprint(value) == old.fingerprint(value)
    now = Clock.moment
    for checkpoint in [{}, {"status": "failed", "last_success": now.isoformat()},
                       {"last_success": (now - timedelta(hours=23)).isoformat()},
                       {"last_success": (now - timedelta(hours=24)).isoformat()}]:
        for hours in (0, 24, 48):
            assert sync_state.due(checkpoint, hours, now) == old.due(checkpoint, hours, now)
    events = [{"calls": 2, "payload_bytes": 10, "seconds": 1.5, "cpu_seconds": .2, "new": 1, "revised": 0,
               "unchanged": 3, "status": "new", "skipped": False},
              {"calls": 1, "status": "failed", "skipped": True}]
    assert sync_state.totals(events) == old.totals(events) and sync_state.totals([]) == old.totals([])


def dump(path):
    with closing(sqlite3.connect(path)) as db:
        return {table: db.execute(f"SELECT * FROM {table} ORDER BY 1,2,3").fetchall()
                for table in ("sync_checkpoints", "sync_events")}


def test_checkpoints_events_and_failures_match_capture(tmp_path, monkeypatch):
    times = iter(range(100))
    monkeypatch.setattr(time, "perf_counter", lambda: float(next(times)) / 4)
    monkeypatch.setattr(time, "thread_time", lambda: 1.)
    results = []
    for label in ("old", "new"):
        path = tmp_path / label / "gabi.db"
        monkeypatch.setattr(config, "DB_PATH", path)
        times = iter(range(100))
        target = captured_sync(path, Clock) if label == "old" else sync_state
        if label == "new":
            monkeypatch.setattr(event_store, "datetime", Clock)
        outcomes = [target.get("sec", "cik:1", "facts:A"), target.events_since(), target.latest_event_id(),
                    sorted(target.failed_datasets("sec"))]
        attempt = target.Attempt("sec", "cik:1", "facts:A")
        attempt.payload({"x": [1, 2, 3]})
        attempt.calls += 2
        outcomes.append(attempt.finish("new", state={"watermark": "2024-01-02", "token": "a"}, new=4))
        outcomes.append(target.Attempt("sec", "cik:1", "facts:A").finish("unchanged", state={"watermark": "2023-12-01"},
                                                                          unchanged=4))
        outcomes.append(target.Attempt("sec", "cik:2", "facts:B").finish("failed", reason="boom api_key=SECRET"))
        outcomes.append(target.Attempt("yahoo", "AAA", "prices:A").finish("unchanged", skipped=True))
        with pytest.raises(ValueError):
            target.Attempt("sec", "cik:1", "facts:A").finish("weird")
        outcomes += [target.get("sec", "cik:1", "facts:A"), target.get("sec", "cik:2", "facts:B"),
                     sorted(target.failed_datasets("sec")), sorted(target.failed_datasets("yahoo")),
                     target.events_since(), target.events_since(2), target.latest_event_id()]
        results.append((outcomes, dump(path)))
    assert results[0] == results[1]
    assert "SECRET" not in json.dumps(results[1])


def test_reads_never_create_storage(tmp_path, monkeypatch):
    path = tmp_path / "absent" / "gabi.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("legacy connection"))
    assert sync_state.get("sec", "x", "y") == {} and sync_state.events_since() == []
    assert sync_state.latest_event_id() == 0 and sync_state.failed_datasets("sec") == set()
    assert not path.parent.exists()


def failing(errors):
    queue = list(errors)

    def call():
        if queue:
            raise queue.pop(0)
        return "ok"
    return call


def http_error(status, retry_after=None):
    response = requests.Response()
    response.status_code = status
    if retry_after is not None:
        response.headers["Retry-After"] = retry_after
    return requests.HTTPError(f"{status} error", response=response)


SCENARIOS = [
    [], [requests.Timeout("read timed out")], [requests.ConnectionError("x"), requests.ConnectionError("y")],
    [http_error(503)], [http_error(429, "7")], [http_error(429, "120")], [http_error(429, "soon")],
    [http_error(404)], [ValueError("not found")], [Exception("429 Too Many Requests")] * 3,
    [Exception("connection reset"), ValueError("invalid")],
]


@pytest.mark.parametrize("errors", SCENARIOS)
@pytest.mark.parametrize("source, pace", [("sec", .25), ("sec", .05), ("yahoo", .25), ("fred", 0)])
def test_retry_waits_pacing_and_outcomes_match_capture(tmp_path, monkeypatch, errors, source, pace):
    results = []
    for label in ("old", "new"):
        sleeps, ticks = [], iter(x * .01 for x in range(1000))
        monkeypatch.setattr(time, "sleep", sleeps.append)
        monkeypatch.setattr(time, "perf_counter", lambda: next(ticks))
        if label == "old":
            target = captured_sync(tmp_path / "old.db", Clock)
        else:
            target = source_retry
            monkeypatch.setattr(source_retry, "_NEXT_REQUEST", {})
        attempt = SimpleNamespace(source=source, calls=0)
        try:
            outcome = target.retry(failing(errors), attempt, pace=pace)
        except Exception as exc:
            outcome = (type(exc).__name__, str(exc))
        results.append((outcome, attempt.calls, [round(s, 6) for s in sleeps]))
    assert results[0] == results[1]


def test_pacing_is_shared_with_the_bootstrap_bridge():
    from gabi.infrastructure.legacy import source_errors as bridge
    assert bridge.retry is source_retry.retry
    assert bridge.fingerprint({"a": 1}) == sync_state.fingerprint({"a": 1})
    for message in MESSAGES:
        assert bridge.sec_error(Exception(message)) == data_fetch._classify_error(Exception(message), "SEC EDGAR")[1]


def test_periodic_bridge_reads_events_of_its_explicit_directory(tmp_path, monkeypatch):
    from gabi.infrastructure.legacy.periodic import LegacyPeriodicOperations

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("legacy connection"))
    operations = LegacyPeriodicOperations(tmp_path)
    assert operations.latest_event_id() == 0 and operations.universe_checkpoint() == {}
    assert operations.universe_due({}) is True
    event = operations.universe_attempt().finish("new", state={"fingerprint": operations.fingerprint([1])})
    assert operations.events_since(0) == [event] and operations.latest_event_id() == 1
    assert operations.universe_checkpoint()["fingerprint"] == sync_state.fingerprint([1])
    assert operations.totals([event])["statuses"]["new"] == 1
    validate_status(event["status"])
    assert event_checkpoint  # shared rule module stays the single policy source
