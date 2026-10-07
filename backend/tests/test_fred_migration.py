"""Synthetic FRED responses and temporary databases against the captured source."""

import json
import sqlite3
import sys
from contextlib import closing, contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest
import requests

from gabi.application.administration.fred import synchronize
from gabi.application.administration.sync_events import SyncAttempt
from gabi.domain.market.fred import SERIES, observations, series_metadata
from gabi.infrastructure.providers.fred import FredSource, fred_key
from gabi.infrastructure.storage.fred import ERROR_SCHEMA, SqliteFred
from gabi.infrastructure.storage.sync_events import OperationSyncEvents

REFERENCE = json.loads((Path(__file__).parent / "fixtures/fred_migration.json").read_text(encoding="utf-8"))
NOW = datetime(2024, 1, 10, 22, tzinfo=UTC)


def tables(path):
    with closing(sqlite3.connect(path)) as db:
        result = {}
        for table, order in [("macro_series", "series_id,date"), ("macro_meta", "series_id"),
                             ("sync_checkpoints", "source,entity,dataset"), ("sync_events", "id"),
                             ("update_errors", "id")]:
            exists = db.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (table,)).fetchone()
            result[table] = db.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall() if exists else []
        return result


def original(path, monkeypatch):
    @contextmanager
    def connection():
        db = sqlite3.connect(path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def errors(source, failed):
        if not failed:
            return
        with connection() as db:
            db.executescript(ERROR_SCHEMA)
            db.executemany("INSERT INTO update_errors(source,symbol,reason,occurred_at) VALUES (?,?,?,?)",
                           [(source, sid, str(reason), NOW.isoformat()) for sid, reason in failed.items()])
            db.execute("DELETE FROM update_errors WHERE occurred_at < ?", ((NOW - timedelta(days=90)).isoformat(),))

    storage = SimpleNamespace(get_connection=connection, record_update_errors=errors)

    class FixedDatetime:
        fromisoformat = datetime.fromisoformat

        @staticmethod
        def now(zone):
            return NOW

    sync = ModuleType("original_fred_sync")
    monkeypatch.setitem(sys.modules, sync.__name__, sync)
    sync.__dict__.update(storage=storage, datetime=FixedDatetime,
                         time=SimpleNamespace(perf_counter=lambda: 4., thread_time=lambda: 2., sleep=lambda _: None))
    source = REFERENCE["sync_state"].replace("from . import storage", "")
    source = source.replace("import time\n", "")
    source = source.replace("from datetime import UTC, datetime", "from datetime import UTC")
    exec(source, sync.__dict__)
    module = {"storage": storage, "sync": sync, "datetime": FixedDatetime,
              "config": SimpleNamespace(load_fred_key=lambda: "synthetic-key")}
    source = REFERENCE["macro"].replace("from . import config, storage", "")
    source = source.replace("from datetime import UTC, date, datetime", "from datetime import UTC, date")
    source = source.replace("from .data_fetch import _classify_error", "from gabi.data_fetch import _classify_error")
    source = source.replace("    from . import sync_state as sync\n", "")
    exec(source, module)
    return module, sync


def modern(path, *, series=None):
    store = SqliteFred(path, lambda: NOW)
    events = OperationSyncEvents(path)

    def attempt(provider, sid, dataset):
        return SyncAttempt(provider, sid, dataset, events, now=lambda: NOW,
                           wall_time=lambda: 4., cpu_time=lambda: 2.)

    def run(fetch, **kwargs):
        return synchronize(store, series or {"TEST": {"units_param": "lin"}}, lambda: "synthetic-key", fetch,
                           events.get, attempt, lambda call, attempt: counted(call, attempt),
                           lambda exc: str(exc), lambda: NOW, **kwargs)

    return store, events, attempt, run


def counted(call, attempt):
    attempt.calls += 1
    return call()


@pytest.mark.parametrize("case", ["new", "unchanged", "withdrawal", "empty", "duplicate", "failure", "all_missing"])
def test_full_sync_result_rows_events_checkpoint_equal_original(tmp_path, monkeypatch, case):
    old_path, new_path = tmp_path / "old.db", tmp_path / "new.db"
    old, sync = original(old_path, monkeypatch)
    old["SERIES"] = {"TEST": {"units_param": "lin"}}
    store, events, attempt, run = modern(new_path)
    monkeypatch.setattr(sync.time, "perf_counter", lambda: 4.)
    monkeypatch.setattr(sync.time, "thread_time", lambda: 2.)
    monkeypatch.setattr(sync, "retry", lambda call, attempt: counted(call, attempt))
    baseline = [("2023-01-01", 1.), ("2024-01-01", 2.)]
    def fetch(*args, **kwargs):
        return baseline
    old["fetch_series"] = fetch
    assert old["ensure_macro_data"](force=True) == run(fetch, force=True)
    assert tables(old_path) == tables(new_path)
    payload = {"new": baseline + [("2024-01-10", 3.)], "unchanged": baseline,
               "withdrawal": [("2024-01-01", None), ("2024-01-10", 3.)],
               "all_missing": [("2024-01-01", None)], "empty": [],
               "duplicate": [("2024-01-01", 2.), ("2024-01-01", 3.)]}.get(case)
    calls = []
    def fetch(*args, **kwargs):
        calls.append(kwargs)
        if case == "failure":
            raise RuntimeError("synthetic failure")
        return payload
    old["fetch_series"] = fetch
    assert old["ensure_macro_data"](force=True) == run(fetch, force=True)
    assert calls[0] == calls[1]
    assert calls[0]["observation_start"] == "2022-11-27"
    assert tables(old_path) == tables(new_path)
    cp = events.get("fred", "TEST", "observations:lin")
    if case in {"empty", "duplicate", "failure"}:
        assert cp["status"] == "failed" and cp["watermark"] == "2024-01-01"
    if case == "all_missing":
        assert cp["watermark"] == "2024-01-01"


def test_missing_key_performs_no_repository_or_checkpoint_access():
    def forbidden(*args):
        pytest.fail("I/O without key")
    repo = SimpleNamespace(fetched_at=forbidden, failed=forbidden)
    assert synchronize(repo, SERIES, lambda: None, forbidden, forbidden, forbidden, forbidden,
                       forbidden, forbidden)["reason"] == "no_api_key"


def test_ttl_and_monthly_audit_boundaries_and_failed_retry(tmp_path):
    store, events, attempt, run = modern(tmp_path / "gabi.db")
    calls = []
    def fetch(*args, **kwargs):
        calls.append(kwargs)
        return [("2024-01-01", 2.)]
    run(fetch)
    assert run(fetch)["refreshed"] == 0
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE macro_meta SET fetched_at=?", ((NOW - timedelta(hours=24)).isoformat(),))
    assert run(fetch)["refreshed"] == 0  # Strict >24h, unlike >=30d audit.
    attempt("fred", "TEST", "observations:lin").finish("failed", reason="interrupted")
    assert run(fetch)["refreshed"] == 1
    attempt("fred", "TEST", "observations:lin").finish("unchanged", state={
        "full_audited_at": (NOW - timedelta(days=30)).isoformat()})
    run(fetch, force=True)
    assert calls[-1]["observation_start"] == "1776-07-04"
    assert events.get("fred", "TEST", "observations:lin")["full_audited_at"] == NOW.isoformat()


def test_readers_do_not_create_database_or_tables(tmp_path):
    store = SqliteFred(tmp_path / "absent/gabi.db", lambda: NOW)
    assert store.fetched_at(["TEST"]) == {} and store.failed(["TEST"]) == set()
    assert store.history("TEST").empty and not store.path.parent.exists()
    store.path = tmp_path / "empty.db"
    with sqlite3.connect(store.path) as db:
        db.execute("CREATE TABLE unrelated(x)")
    before = store.path.read_bytes()
    assert store.history("TEST").empty and store.fetched_at(["TEST"]) == {}
    assert store.path.read_bytes() == before


def test_database_and_key_limits_and_scoped_reads(tmp_path):
    store = SqliteFred(tmp_path / "gabi.db", lambda: NOW, max_rows=1)
    store.upsert("TEST", [("2024-01-01", 1.)])
    store.upsert("OTHER", [("2024-01-01", 2.)])
    assert list(store.history("TEST").value) == [1.]
    assert set(store.fetched_at(["TEST"])) == {"TEST"}
    store.upsert("TEST", [("2024-01-02", None)])
    with pytest.raises(ValueError, match="límite"):
        store.history("TEST")
    with pytest.raises(ValueError, match="límite"):
        store.upsert("TEST", [("1", 1.), ("2", 2.)])
    with pytest.raises(ValueError, match="100 series"):
        store.fetched_at(["TEST"] * 101)
    assert fred_key(tmp_path) is None
    key = tmp_path / "fred_api_key.txt"
    key.write_text("  synthetic-key \n")
    assert fred_key(tmp_path) == "synthetic-key"
    key.write_bytes(b"x" * 4097)
    with pytest.raises(ValueError, match="4096"):
        fred_key(tmp_path)


@pytest.mark.parametrize("status", [200, 400, 401, 403, 429, 500])
def test_provider_preserves_params_missing_values_and_closes_response(monkeypatch, status):
    captured, closed = [], []
    payload = {"observations": [{"date": "2024-01-02", "value": "."}, {"date": "2024-01-01", "value": "2"}]}
    class Response:
        status_code = status
        headers = {}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            closed.append(True)
        def iter_content(self, size):
            yield json.dumps(payload).encode()
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: captured.append((url, kwargs)) or Response())
    if status == 200:
        assert FredSource().fetch("TEST", "secret", units="pc1", observation_start="2023-01-01",
                                  include_missing=True) == [("2024-01-02", None), ("2024-01-01", 2.)]
    else:
        with pytest.raises((ValueError, requests.HTTPError)) as error:
            FredSource().fetch("TEST", "secret")
        assert "secret" not in str(error.value)
    assert closed == [True]
    assert captured[0][1]["timeout"] == 20 and captured[0][1]["stream"]
    assert captured[0][1]["params"]["sort_order"] == "desc"


def test_provider_bounds_and_release_calendar(monkeypatch):
    source = FredSource(max_bytes=5)
    class Response:
        status_code = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def iter_content(self, size):
            yield b"123456"
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: Response())
    with pytest.raises(ValueError, match="bytes"):
        source.fetch("TEST", "secret")
    assert source.next_release("DGS10", "secret", date(2024, 1, 1)) is None
    monkeypatch.setattr(source, "_payload", lambda *args, **kwargs: {"release_dates": [
        {"date": "2024-02-01"}, {"date": "2024-01-01"}]})
    assert source.next_release("CPIAUCSL", "secret", date(2024, 1, 1)) == date(2024, 1, 1)
    monkeypatch.setattr(source, "_payload", lambda *args, **kwargs: {"observations": [], "count": 100001})
    with pytest.raises(ValueError, match="paginación"):
        source.fetch("TEST", "secret", limit=100000)


def test_metadata_and_parser_equal_captured_source(tmp_path, monkeypatch):
    old, _ = original(tmp_path / "old.db", monkeypatch)
    assert {key: dict(value) for key, value in SERIES.items()} == old["SERIES"]
    assert series_metadata() == {key: {field: value[field] for field in ("label", "unit", "help")}
                                 for key, value in old["SERIES"].items()}
    with pytest.raises(TypeError):
        SERIES["DGS10"]["unit"] = "changed"
    payload = {"observations": [{"date": "a", "value": None}, {"date": "b", "value": "."},
                                {"date": "c", "value": "4.20"}]}
    assert observations(payload) == [("c", 4.2)]
    assert observations(payload, include_missing=True) == [("a", None), ("b", None), ("c", 4.2)]


def test_bootstrap_uses_modern_macro_without_global_config_mutation(tmp_path, monkeypatch):
    from gabi import macro
    from gabi.infrastructure.settings import Settings
    from gabi_cli.bootstrap import build_executor
    from gabi_cli.sources.bootstrap import build_fred_operation

    monkeypatch.setattr(macro, "ensure_macro_data", lambda **kwargs: pytest.fail("legacy refresh"))
    settings = Settings(data_dir=tmp_path)
    operation = build_fred_operation(settings, now=lambda: NOW)
    assert operation()["reason"] == "no_api_key"
    assert not (tmp_path / "gabi.db").exists()
    executor = build_executor(settings, now=lambda: NOW)
    assert executor.macro_sync()["reason"] == "no_api_key"


def test_legacy_snapshot_missing_values_and_dates_equal_original(tmp_path, monkeypatch):
    from gabi import macro
    old, _ = original(tmp_path / "unused.db", monkeypatch)
    histories = {sid: pd.DataFrame(columns=["date", "value"]) for sid in SERIES}
    histories["DGS10"] = pd.DataFrame({"value": [3., 4., None]},
        index=pd.to_datetime(["2023-01-01", "2023-05-01", "2024-01-01"]))
    old["get_series_history"] = histories.__getitem__
    monkeypatch.setattr(macro, "get_series_history", histories.__getitem__)
    pd.testing.assert_frame_equal(macro.get_snapshot(), old["get_snapshot"]())


def test_network_error_retains_retryable_type_without_exposing_key(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError("connection https://fred/?api_key=secret")
    monkeypatch.setattr(requests, "get", fail)
    with pytest.raises(requests.ConnectionError) as error:
        FredSource().fetch("TEST", "secret")
    assert str(error.value) == "ConnectionError"


def test_periodic_injects_modern_callback_and_preserves_full_refresh(monkeypatch):
    from gabi import config, macro
    from gabi.infrastructure.legacy.periodic import LegacyPeriodicOperations
    calls = []
    monkeypatch.setattr(macro, "ensure_macro_data", lambda **kwargs: pytest.fail("legacy call"))
    operations = LegacyPeriodicOperations(config.DATA_DIR,
        macro_sync=lambda **kwargs: calls.append(kwargs) or {"ok": True})
    assert operations.refresh_macro(True) == {"ok": True}
    assert calls == [{"full_refresh": True}]
