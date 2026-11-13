"""Bounded current SEC maps; only synthetic provider data and temporary files."""

import ast
import json
import os
import sqlite3
import sys
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest
import requests

from gabi.application.administration.sync_events import SyncAttempt
from gabi.application.market.sec_cik import CikResolver, current_map, resolve
from gabi.domain.market.sec_cik import mapping_rows
from gabi.infrastructure.providers.sec_cik import SecTickerMap
from gabi.infrastructure.storage.sec_cik import FileCikMap, SqliteCikResolutions
from gabi.infrastructure.storage.sync_events import OperationSyncEvents

REFERENCE = json.loads((Path(__file__).parent / "fixtures/sec_cik_migration.json").read_text(encoding="utf-8"))
NOW = datetime(2024, 1, 10, 22, tzinfo=UTC)
PAYLOAD = {"0": {"ticker": "BRK-B", "cik_str": 1067983, "title": "Berkshire, Inc."},
           "1": {"ticker": "AAA", "cik_str": 1, "title": "Compañía A"}}


def read_tables(path):
    if not path.exists():
        return {table: [] for table in ("cik_resolutions", "sync_checkpoints", "sync_events")}
    with closing(sqlite3.connect(path)) as db:
        result = {}
        for table, order in [("cik_resolutions", "symbol"), ("sync_checkpoints", "source,entity,dataset"),
                             ("sync_events", "id")]:
            exists = db.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (table,)).fetchone()
            result[table] = db.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall() if exists else []
        return result


def original(directory, responses, monkeypatch):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "gabi.db"
    @contextmanager
    def connection():
        with closing(sqlite3.connect(path)) as db:
            with db:
                yield db
    class FixedDatetime:
        @staticmethod
        def now(zone):
            return NOW
    sync = ModuleType("original_sec_cik_sync")
    monkeypatch.setitem(sys.modules, sync.__name__, sync)
    sync.__dict__.update(storage=SimpleNamespace(get_connection=connection), datetime=FixedDatetime,
                        time=SimpleNamespace(perf_counter=lambda: 4., thread_time=lambda: 2., sleep=lambda _: None))
    source = REFERENCE["sync_state"].replace("from . import storage", "").replace("import time\n", "")
    source = source.replace("from datetime import UTC, datetime", "from datetime import UTC")
    exec(source, sync.__dict__)
    sync.retry = lambda call, attempt: counted(call, attempt)
    def get(*args, **kwargs):
        payload = next_response(responses)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    namespace = {"pd": pd, "datetime": FixedDatetime, "UTC": UTC, "sync_state": sync,
                 "config": SimpleNamespace(DATA_DIR=directory), "CIK_CACHE": directory / "sec_cik_map.csv",
                 "storage": SimpleNamespace(get_connection=connection), "requests": SimpleNamespace(get=get),
                 "TICKER_CIK_URL": "synthetic://sec", "_headers": lambda: {}}
    tree = ast.parse(REFERENCE["edgar"])
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "RESOLUTIONS_SCHEMA" for t in node.targets):
            exec(ast.get_source_segment(REFERENCE["edgar"], node), namespace)
        if isinstance(node, ast.FunctionDef) and node.name in {
            "get_cik_map", "get_cik_for_symbol", "_remember_cik_resolution", "_get_cached_cik_resolution"}:
            source = ast.get_source_segment(REFERENCE["edgar"], node).replace("    from . import sync_state\n", "")
            exec(source, namespace)
    return SimpleNamespace(**namespace)


def counted(call, attempt):
    attempt.calls += 1
    return call()


def next_response(responses):
    payload = responses.pop(0)
    if isinstance(payload, Exception):
        raise payload
    return payload


def modern(directory, responses):
    from gabi.infrastructure.legacy.source_errors import fingerprint
    path = directory / "gabi.db"
    events = OperationSyncEvents(path)
    def attempt():
        return SyncAttempt("sec", "all", "ticker-map", events, now=lambda: NOW,
                           wall_time=lambda: 4., cpu_time=lambda: 2.)
    return CikResolver(FileCikMap(directory / "sec_cik_map.csv"), SqliteCikResolutions(path, lambda: NOW),
        lambda: next_response(responses), attempt, lambda call, attempt: counted(call, attempt),
        lambda: events.get("sec", "all", "ticker-map"), fingerprint, lambda: NOW.timestamp())


@pytest.mark.parametrize("symbol", ["AAA", "BRK.B", "BRK-B", "MISSING"])
def test_complete_refresh_resolution_cache_and_checkpoints_match_original(tmp_path, monkeypatch, symbol):
    revised = {key: {**value, "title": value["title"] + " revised"} for key, value in PAYLOAD.items()}
    sequence = [PAYLOAD, PAYLOAD, revised, requests.Timeout("timeout"), revised]
    old = original(tmp_path / "old", list(sequence), monkeypatch)
    service = modern(tmp_path / "new", list(sequence))
    for step in range(5):
        old_frame = old.get_cik_map(force_refresh=step > 0)
        new_frame = service.mapping(force_refresh=step > 0)
        pd.testing.assert_frame_equal(new_frame, old_frame)
        assert service.resolve(symbol, new_frame) == old.get_cik_for_symbol(symbol, old_frame)
        empty = pd.DataFrame(columns=["symbol", "cik", "title"])
        assert service.resolve(symbol, empty) == old.get_cik_for_symbol(symbol, empty)
        assert read_tables(tmp_path / "old/gabi.db") == read_tables(tmp_path / "new/gabi.db")
        assert old.CIK_CACHE.read_bytes() == service.cache.path.read_bytes()
        for path in (old.CIK_CACHE, service.cache.path):
            os.utime(path, (NOW.timestamp(), NOW.timestamp()))
        pd.testing.assert_frame_equal(old.get_cik_map(), service.mapping())
        assert read_tables(tmp_path / "old/gabi.db") == read_tables(tmp_path / "new/gabi.db")


@pytest.mark.parametrize("symbol", ["AAA", "BRK.B", "BRK-B", "aaa", "MISSING"])
def test_resolution_preference_and_fallback_match_captured_function(symbol):
    remembered, cached = [], []
    port = SimpleNamespace(remember=lambda *args: remembered.append(args),
                           cached=lambda value: cached.append(value) or ("0000000009", "Previous"))
    namespace = {"pd": pd, "_remember_cik_resolution": port.remember, "_get_cached_cik_resolution": port.cached}
    node = next(n for n in ast.parse(REFERENCE["edgar"]).body
                if isinstance(n, ast.FunctionDef) and n.name == "get_cik_for_symbol")
    exec(ast.get_source_segment(REFERENCE["edgar"], node), namespace)
    frame = pd.DataFrame(mapping_rows(PAYLOAD))
    expected = namespace["get_cik_for_symbol"](symbol, frame)
    original_calls = list(remembered), list(cached)
    remembered.clear()
    cached.clear()
    assert resolve(symbol, frame, port) == expected
    assert (remembered, cached) == original_calls


def test_map_ttl_force_refresh_fingerprint_and_failure_fallback(tmp_path):
    cache = FileCikMap(tmp_path / "map.csv")
    calls, events = [], []
    checkpoint = {}
    fail_mode = False
    class Attempt:
        calls = 0
        def payload(self, value):
            assert value == PAYLOAD
        def finish(self, status, **kwargs):
            events.append((status, kwargs))
            if status != "failed":
                checkpoint.update(kwargs["state"])
    def fetch():
        if fail_mode:
            raise requests.Timeout("timeout")
        calls.append(True)
        return PAYLOAD
    def run(**kwargs):
        return current_map(cache, fetch, Attempt, lambda call, attempt: call(), lambda: checkpoint,
                           lambda value: json.dumps(value), lambda: NOW.timestamp(), **kwargs)
    first = run()
    assert events[-1][0] == "new"
    os.utime(cache.path, (NOW.timestamp(), NOW.timestamp()))
    pd.testing.assert_frame_equal(run(), first)
    assert len(calls) == 1
    run(force_refresh=True)
    assert events[-1][0] == "unchanged"
    before = cache.path.read_bytes()
    fail_mode = True
    pd.testing.assert_frame_equal(run(force_refresh=True), first)
    assert events[-1][0] == "failed" and cache.path.read_bytes() == before
    cache.path.unlink()
    with pytest.raises(requests.Timeout):
        run()


def test_file_cache_exact_csv_and_limits(tmp_path):
    frame = pd.DataFrame(mapping_rows(PAYLOAD))
    cache = FileCikMap(tmp_path / "map.csv")
    cache.save(frame)
    original = tmp_path / "original.csv"
    frame.to_csv(original, index=False)
    assert cache.path.read_bytes() == original.read_bytes()
    pd.testing.assert_frame_equal(cache.read(), frame)
    assert not list(tmp_path.glob(".sec_cik_*.tmp"))
    with pytest.raises(ValueError, match="filas"):
        FileCikMap(cache.path, max_rows=1).read()
    with pytest.raises(ValueError, match="bytes"):
        FileCikMap(cache.path, max_bytes=1).read()
    with pytest.raises(ValueError, match="filas"):
        FileCikMap(cache.path, max_rows=1).save(frame)
    assert cache.path.read_bytes() == original.read_bytes()


def test_cache_detects_changed_open_file_and_atomic_failure_preserves_old_bytes(tmp_path, monkeypatch):
    frame = pd.DataFrame(mapping_rows(PAYLOAD))
    cache = FileCikMap(tmp_path / "map.csv")
    cache.save(frame)
    before = cache.path.read_bytes()
    actual_stat = os.fstat
    with monkeypatch.context() as patch:
        patch.setattr(os, "fstat", lambda fd: SimpleNamespace(st_size=actual_stat(fd).st_size - 1))
        with pytest.raises(ValueError, match="cambió"):
            cache.read()
    actual_replace = Path.replace
    def fail_pending(path, target):
        if path.name.startswith(".sec_cik_"):
            raise PermissionError("synthetic replace failure")
        return actual_replace(path, target)
    monkeypatch.setattr(Path, "replace", fail_pending)
    with pytest.raises(PermissionError):
        cache.save(frame.assign(title="Changed"))
    assert cache.path.read_bytes() == before
    assert not list(tmp_path.glob(".sec_cik_*.tmp"))


def test_exact_seven_day_boundary_triggers_refresh(tmp_path):
    service = modern(tmp_path, [PAYLOAD])
    service.cache.save(pd.DataFrame(mapping_rows(PAYLOAD)))
    boundary = NOW.timestamp() - 7 * 86400
    os.utime(service.cache.path, (boundary, boundary))
    service.mapping()
    assert read_tables(tmp_path / "gabi.db")["sync_events"]


def test_resolution_read_does_not_initialize_and_remember_uses_explicit_clock(tmp_path):
    port = SqliteCikResolutions(tmp_path / "absent/gabi.db", lambda: NOW)
    assert port.cached("AAA") == (None, None)
    assert not port.path.parent.exists()
    port.path = tmp_path / "gabi.db"
    with closing(sqlite3.connect(port.path)) as db:
        db.execute("CREATE TABLE unrelated(x)")
    before = port.path.read_bytes()
    assert port.cached("AAA") == (None, None) and port.path.read_bytes() == before
    port.remember("AAA", "0000000001", "Current")
    assert port.cached("AAA") == ("0000000001", "Current")
    with closing(sqlite3.connect(port.path)) as db:
        assert db.execute("SELECT resolved_at FROM cik_resolutions").fetchone()[0] == NOW.isoformat()
    with pytest.raises(ValueError, match="campo"):
        SqliteCikResolutions(port.path, lambda: NOW, max_field_bytes=1).cached("AAA")


def test_provider_preserves_headers_timeout_and_closes_response(monkeypatch):
    calls, closed = [], []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            closed.append(True)
        def raise_for_status(self):
            pass
        def iter_content(self, size):
            yield json.dumps(PAYLOAD).encode()
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: calls.append(kwargs) or Response())
    assert SecTickerMap("test contact").fetch() == PAYLOAD
    assert calls[0] == {"headers": {"User-Agent": "test contact"}, "timeout": 20, "stream": True}
    with pytest.raises(ValueError, match="bytes"):
        SecTickerMap("test", max_bytes=1).fetch()
    with pytest.raises(ValueError, match="filas"):
        SecTickerMap("test", max_rows=1).fetch()
    assert closed == [True, True, True]


def test_bootstrap_is_lazy_and_worker_uses_explicit_resolver(tmp_path, monkeypatch):
    from gabi import edgar
    from gabi.infrastructure.settings import Settings
    from gabi_cli.bootstrap import build_executor
    from gabi_cli.sources.bootstrap import build_cik_resolver

    settings = Settings(tmp_path)
    monkeypatch.setattr(edgar, "get_cik_map", lambda **kwargs: pytest.fail("legacy map"))
    monkeypatch.setattr(edgar, "get_cik_for_symbol", lambda **kwargs: pytest.fail("legacy resolution"))
    service = build_cik_resolver(settings, "test", now=lambda: NOW)
    assert not (tmp_path / "gabi.db").exists()
    service.cache.save(pd.DataFrame(mapping_rows(PAYLOAD)))
    os.utime(service.cache.path, (NOW.timestamp(), NOW.timestamp()))
    executor = build_executor(settings, now=lambda: NOW)
    source = executor.insider_sync.keywords["source"]
    mapping = source.mapping()
    assert source.resolve("BRK.B", mapping) == "0001067983"
    assert service.resolutions.cached("BRK.B") == ("0001067983", "Berkshire, Inc.")
