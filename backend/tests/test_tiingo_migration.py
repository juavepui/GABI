"""Original Tiingo/cache/checkpoint comparisons using only synthetic local inputs."""

import hashlib
import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import requests

from gabi.application.administration.sync_events import SyncAttempt
from gabi.application.research.tiingo_prices import PriceResponse, fetch, import_cached
from gabi.domain.research.tiingo_prices import window
from gabi.infrastructure.storage.historical_prices import SqliteHistoricalPrices
from gabi.infrastructure.storage.sync_events import OperationSyncEvents
from gabi.infrastructure.storage.tiingo_prices import FileTiingoCache, read_current_listings

REFERENCE = json.loads((Path(__file__).parent / "fixtures/tiingo_migration.json").read_text(encoding="utf8"))
ARCHIVE_SCHEMA = REFERENCE["archive_schema"]
PRICE_REFERENCE = json.loads((Path(__file__).parent / "fixtures/wiki_migration.json").read_text(encoding="utf8"))
NOW = datetime(2024, 1, 10, 22, tzinfo=UTC)


def rows():
    return [{"date": date + "T00:00:00.000Z", "open": 25, "high": 26, "low": 24, "close": 25.5,
             "adjClose": 24, "volume": 1000, "divCash": 0, "splitFactor": 1}
            for date in ["2007-12-31", "2012-01-03", "2015-01-02", "2017-01-03", "2026-07-01"]]


def read_tables(path):
    with closing(sqlite3.connect(path)) as connection:
        result = {}
        for table, order in [("historical_sources", "source_id"), ("historical_prices", "source_id,symbol,date"),
                             ("sync_checkpoints", "source,entity,dataset"), ("sync_events", "id")]:
            if connection.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (table,)).fetchone():
                result[table] = connection.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
            else:
                result[table] = []
        return result


def original(directory, database, *, events=None, waits=None, messages=None):
    class Connection:
        def __enter__(self):
            self.connection = sqlite3.connect(database)
            return self.connection

        def __exit__(self, kind, value, trace):
            try:
                if kind is None:
                    self.connection.commit()
                else:
                    self.connection.rollback()
            finally:
                self.connection.close()

    storage = SimpleNamespace(get_connection=Connection)

    class FixedDatetime:
        @staticmethod
        def now(zone):
            return NOW

    timing = SimpleNamespace(perf_counter=lambda: 4., thread_time=lambda: 2., sleep=lambda _: None)
    sync = {"__name__": "original_sync", "storage": storage, "time": timing, "datetime": FixedDatetime}
    source = REFERENCE["sync_state"].replace("from . import storage", "").replace("import time", "")
    source = source.replace("from datetime import UTC, datetime", "from datetime import UTC")
    exec(source, sync)
    archive = {"pd": pd, "np": np, "storage": storage, "SCHEMA": ARCHIVE_SCHEMA}
    exec(PRICE_REFERENCE["prices"], archive)

    def register(source_id, metadata):
        with Connection() as connection:
            connection.executescript(ARCHIVE_SCHEMA)
            connection.execute("INSERT OR REPLACE INTO historical_sources VALUES (?,?)",
                               (source_id, json.dumps(metadata, sort_keys=True)))

    def get_prices(source_id, symbol, first, last):
        with Connection() as connection:
            frame = pd.read_sql_query("SELECT date,open,high,low,close,adj_close,volume,close_basis "
                                     "FROM historical_prices WHERE source_id=? AND symbol=? AND date>=? AND date<? "
                                     "ORDER BY date", connection, params=(source_id, symbol.replace(".", "-"), first, last))
        frame["date"] = pd.to_datetime(frame["date"])
        return frame.set_index("date")

    module = {"__name__": "original_tiingo", "storage": storage, "sync_state": SimpleNamespace(**sync),
              "config": SimpleNamespace(DATA_DIR=directory.parent, load_tiingo_key=lambda: "temporary-key"),
              "historical_archive": SimpleNamespace(SCHEMA=ARCHIVE_SCHEMA, register_source=register,
                  import_price_chunk=archive["import_price_chunk"], get_prices=get_prices)}
    source = REFERENCE["tiingo"].replace("from . import config, historical_archive, storage, sync_state", "")
    if events is not None:
        def get(*args, **kwargs):
            event = events.pop(0)
            if isinstance(event, Exception):
                raise event
            return SimpleNamespace(status_code=event.status, content=event.body, json=lambda: event.payload)

        module.update(requests=SimpleNamespace(get=get, RequestException=requests.RequestException),
                      time=SimpleNamespace(sleep=waits.append), print=lambda message, **kwargs: messages.append(message))
        source = source.replace("import requests", "").replace("import time", "")
    exec(source, module)
    module["DIRECTORY"] = directory
    return SimpleNamespace(**module)


def attempts(database):
    store = OperationSyncEvents(database)

    def create(symbol, dataset):
        return SyncAttempt("tiingo", symbol, dataset, store, now=lambda: NOW,
                           wall_time=lambda: 4., cpu_time=lambda: 2.)
    return store, create


@pytest.mark.parametrize("window_name", ["2010-2015", "2016-2025", "smallmid"])
def test_whole_import_and_repeat_exact_rows_metadata_events_checkpoints(tmp_path, window_name):
    spec = window(window_name)
    old_dir, new_dir = tmp_path / "old", tmp_path / "new"
    for directory in [old_dir, new_dir]:
        target = directory / spec.subdirectory
        target.mkdir(parents=True)
        (target / "BRK-B.json").write_bytes(json.dumps(rows()).encode())
        (target / "EMPTY.json").write_bytes(b"[]")
    old_db, new_db = tmp_path / "old.db", tmp_path / "new.db"
    old = original(old_dir, old_db)
    cache = FileTiingoCache(new_dir / spec.subdirectory)
    store, create = attempts(new_db)
    with closing(sqlite3.connect(new_db)) as connection:
        archive = SqliteHistoricalPrices(connection)
        for _ in range(2):
            assert import_cached(spec, cache, archive, store, attempt_factory=create) == old.import_cached(window_name)
            assert read_tables(new_db) == read_tables(old_db)
    assert all(row[-1] == "as_traded" for row in read_tables(new_db)["historical_prices"])


@pytest.mark.parametrize("case", ["retry_then_success", "hourly", "monthly", "invalid_json", "offline", "last_429"])
def test_fetch_retries_counts_waits_raw_bytes_and_telemetry_equal_original(tmp_path, case):
    good_body = json.dumps(rows(), indent=1).encode()
    good = PriceResponse(200, good_body, rows())
    if case == "retry_then_success":
        modern = [PriceResponse(error_name="Timeout"), PriceResponse(429), good, PriceResponse(404)]
    elif case == "hourly":
        modern = [PriceResponse(429) for _ in range(12)]
    elif case == "monthly":
        modern = [PriceResponse(200, b'{"detail":"monthly cap"}', {"detail": "monthly cap"})]
    elif case == "invalid_json":
        modern = [PriceResponse(200, b"null", None), PriceResponse(404)]
    elif case == "offline":
        modern = [PriceResponse(error_name="Timeout") for _ in range(12)] + [PriceResponse(404)]
    else:
        modern = [PriceResponse(429)] + [PriceResponse(error_name="Timeout") for _ in range(11)]
    old_events = [requests.Timeout("secret not printed") if event.error_name else event for event in modern]
    old_waits, new_waits, old_messages, new_messages = [], [], [], []
    old_dir, new_dir = tmp_path / "old", tmp_path / "new"
    for directory in [old_dir, new_dir]:
        directory.mkdir()
        (directory / "CACHED.json").write_bytes(b"not parsed on a download hit")
    old = original(old_dir, tmp_path / "old.db", events=old_events, waits=old_waits, messages=old_messages)
    store, create = attempts(tmp_path / "new.db")
    symbols = ["CACHED", "BRK.B", "MISSING"]
    result = fetch(symbols, window("2010-2015"), FileTiingoCache(new_dir),
                   SimpleNamespace(request=lambda *args: modern.pop(0)), attempt_factory=create,
                   wait=new_waits.append, progress=new_messages.append, pace=.25)
    assert result == old.fetch(symbols, pace=.25)
    assert old_waits == new_waits
    assert old_messages == new_messages
    assert not old_events and not modern
    assert read_tables(tmp_path / "new.db") == read_tables(tmp_path / "old.db")
    assert {p.name: p.read_bytes() for p in old_dir.glob("*.json")} == {p.name: p.read_bytes() for p in new_dir.glob("*.json")}


def test_checkpoint_hash_hit_skips_even_invalid_json_without_import(tmp_path):
    cache = FileTiingoCache(tmp_path / "cache")
    body = b"not JSON; the hash checkpoint explicitly marks it imported"
    cache.save("AAA", body)
    digest = hashlib.sha256(body).hexdigest()
    store, create = attempts(tmp_path / "db.sqlite")
    create("AAA", "import:2010-2015").finish("unchanged", state={"fingerprint": digest})
    archive = SimpleNamespace(pinned=lambda _: {"AAA": digest}, register=lambda *args: None,
                              dates=lambda *args: pytest.fail("No date read"),
                              import_prices=lambda *args: pytest.fail("No import"))
    assert import_cached(window("2010-2015"), cache, archive, store, attempt_factory=create) == {
        "files": 1, "accepted": 0, "rejected": 0}


@pytest.mark.parametrize("pinned", [True, False])
def test_changed_snapshot_rejected_before_register_or_parse(tmp_path, pinned):
    cache = FileTiingoCache(tmp_path / "cache")
    cache.save("AAA", b"invalid JSON")
    store, create = attempts(tmp_path / "db.sqlite")
    if not pinned:
        create("AAA", "import:2010-2015").finish("unchanged", state={"fingerprint": "old"})
    archive = SimpleNamespace(pinned=lambda _: {"AAA": "old"} if pinned else {},
                              register=lambda *args: pytest.fail("No metadata write"))
    with pytest.raises(ValueError, match="alterado"):
        import_cached(window("2010-2015"), cache, archive, store, attempt_factory=create)


def test_invalid_rows_retry_without_advancing_successful_fingerprint(tmp_path):
    cache = FileTiingoCache(tmp_path / "cache")
    invalid = rows()[1:3]
    invalid[0]["high"] = 20
    cache.save("AAA", json.dumps(invalid).encode())
    store, create = attempts(tmp_path / "db.sqlite")
    with closing(sqlite3.connect(tmp_path / "db.sqlite")) as connection:
        archive = SqliteHistoricalPrices(connection)
        for _ in range(2):
            assert import_cached(window("2010-2015"), cache, archive, store, attempt_factory=create) == {
                "files": 1, "accepted": 1, "rejected": 1}
    cp = store.get("tiingo", "AAA", "import:2010-2015")
    assert cp["status"] == "failed" and "fingerprint" not in cp and "last_success" not in cp


@pytest.mark.parametrize("status", ["new", "revised", "unchanged", "failed"])
@pytest.mark.parametrize("skipped", [False, True])
def test_full_event_and_checkpoint_policy_matches_original(tmp_path, status, skipped):
    old = original(tmp_path / "cache", tmp_path / "old.db")
    store, create = attempts(tmp_path / "new.db")
    for attempt in [old.sync_state.Attempt("tiingo", "AAA", "test"), create("AAA", "test")]:
        attempt.finish("new", state={"fingerprint": "previous", "watermark": "2024-01-10"}, new=3)
    a, b = old.sync_state.Attempt("tiingo", "AAA", "test"), create("AAA", "test")
    for attempt in [a, b]:
        attempt.calls, attempt.payload_bytes = 2, 39
    options = {"state": {"fingerprint": "replacement", "watermark": "2024-01-05"}, "new": 1,
               "revised": 2, "unchanged": 3, "reason": "api_key=temporary-key&x=1 TOKEN=secret", "skipped": skipped}
    assert a.finish(status, **options) == b.finish(status, **options)
    assert read_tables(tmp_path / "new.db") == read_tables(tmp_path / "old.db")


def test_checkpoint_read_does_not_create_db_or_schema(tmp_path):
    path = tmp_path / "missing" / "db.sqlite"
    assert OperationSyncEvents(path).get("tiingo", "AAA", "test") == {}
    assert not path.parent.exists()
    path = tmp_path / "empty.sqlite"
    with closing(sqlite3.connect(path)):
        pass
    before = path.read_bytes()
    assert OperationSyncEvents(path).get("tiingo", "AAA", "test") == {}
    assert path.read_bytes() == before


def test_supported_listings_full_frame_equals_original_and_is_bounded(tmp_path):
    frame = pd.DataFrame({"ticker": ["aaa", "AAA", "EMC", None, "EUR"],
                          "priceCurrency": ["USD", "USD", "USD", "USD", "EUR"],
                          "startDate": ["1990-01-01", "2020-01-01", "2023-01-01", "2000-01-01", "2000-01-01"],
                          "endDate": ["2010-01-01", "2026-01-01", "2026-01-01", "2026-01-01", "2026-01-01"],
                          "assetType": ["Stock", "Stock", "ETF", "Stock", "Stock"]})
    path = tmp_path / "supported.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("supported_tickers.csv", frame.to_csv(index=False))
    old = original(tmp_path / "cache", tmp_path / "old.db")
    pd.testing.assert_frame_equal(read_current_listings(path), old.current_listings(path))
    assert not old.eligible(read_current_listings(path), "EMC", "2009-01-01", "2015-01-01")
    for kwargs in [{"max_bytes": 1}, {"max_csv_bytes": 1}, {"max_rows": 1}]:
        with pytest.raises(ValueError, match="limit exceeded"):
            read_current_listings(path, **kwargs)


@pytest.mark.parametrize("limit", ["bytes", "total", "files", "rows", "total_rows"])
def test_cache_and_import_limits_reject_without_price_metadata_write(tmp_path, limit):
    directory = tmp_path / "cache"
    directory.mkdir()
    for name in ["AAA", "BBB"]:
        (directory / f"{name}.json").write_bytes(json.dumps(rows()).encode())
    kwargs = {"max_bytes": 1} if limit == "bytes" else {"max_total_bytes": 1} if limit == "total" else \
        {"max_files": 1} if limit == "files" else {}
    cache = FileTiingoCache(directory, **kwargs)
    store, create = attempts(tmp_path / "db.sqlite")
    archive = SimpleNamespace(pinned=lambda _: {}, register=lambda *args: pytest.fail("No metadata write"))
    with pytest.raises(ValueError, match="limit exceeded"):
        import_cached(window("2010-2015"), cache, archive, store, attempt_factory=create,
                      max_rows_per_file=1 if limit == "rows" else 10_000,
                      max_rows=1 if limit == "total_rows" else 2_000_000)
    assert not (tmp_path / "db.sqlite").exists()


def test_atomic_failure_preserves_raw_bytes_and_removes_pending(tmp_path, monkeypatch):
    cache = FileTiingoCache(tmp_path / "cache")
    cache.save("AAA", b"[]")
    monkeypatch.setattr(Path, "replace", lambda *args: (_ for _ in ()).throw(OSError("simulated")))
    with pytest.raises(OSError, match="simulated"):
        cache.save("AAA", b"new")
    assert (cache.directory / "AAA.json").read_bytes() == b"[]"
    assert [path.name for path in cache.directory.iterdir()] == ["AAA.json"]


@pytest.mark.parametrize("symbol", ["../outside", "..", ".", "a/b", "a\\b"])
def test_invalid_cache_symbol_cannot_escape(tmp_path, symbol):
    with pytest.raises(ValueError, match="symbol"):
        FileTiingoCache(tmp_path / "cache").save(symbol, b"[]")
    assert not (tmp_path / "cache").exists()


def test_streaming_source_headers_raw_bytes_closure_and_limits(monkeypatch):
    from gabi.infrastructure.providers.tiingo_prices import TiingoPrices

    body = json.dumps(rows(), indent=2).encode()
    calls = []

    class Response:
        status_code = 200
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def iter_content(self, chunk_size):
            assert chunk_size == 64_000
            yield body[:15]
            yield body[15:]

    response = Response()
    monkeypatch.setattr("gabi.infrastructure.providers.tiingo_prices.requests.get",
                        lambda *args, **kwargs: (calls.append((args, kwargs)), response)[1])
    assert TiingoPrices(lambda: "temporary-key").request("BRK.B", "2008-01-01", "2016-12-31") == \
        PriceResponse(200, body, rows())
    assert response.closed
    assert calls[0] == (("https://api.tiingo.com/tiingo/daily/brk-b/prices?startDate=2008-01-01&endDate=2016-12-31",),
                        {"headers": {"Authorization": "Token temporary-key", "Content-Type": "application/json"},
                         "timeout": 60, "stream": True})
    response.closed = False
    with pytest.raises(ValueError, match="response byte limit"):
        TiingoPrices(lambda: "temporary-key", max_bytes=15).request("AAA", "2008-01-01", "2016-12-31")
    assert response.closed


def test_empty_actions_and_cache_hit_have_no_key_sql_or_download(tmp_path, monkeypatch, capsys):
    from gabi.infrastructure.settings import Settings
    from gabi_cli.research.bootstrap import tiingo_prices
    from gabi_cli.sources.bootstrap import build_tiingo_operations

    monkeypatch.setattr("gabi.infrastructure.storage.tiingo_prices.tiingo_key", lambda *args: pytest.fail("No key read"))
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: pytest.fail("No SQL"))
    monkeypatch.setattr("gabi.infrastructure.providers.tiingo_prices.TiingoPrices.request",
                        lambda *args: pytest.fail("No download"))
    tiingo_prices(Settings(tmp_path), SimpleNamespace(window="2010-2015", cache=None, db=None, fetch=None, import_cached=False))
    assert capsys.readouterr().out == "{}\n" and not list(tmp_path.iterdir())
    directory = tmp_path / "history_refresh/tiingo"
    directory.mkdir(parents=True)
    (directory / "AAA.json").write_bytes(b"invalid JSON cache hit")
    download, _ = build_tiingo_operations(Settings(tmp_path), window_name="2010-2015")
    assert download(["AAA"]) == {"fetched": 0, "cached": 1, "failed": 0}


def test_actual_worker_uses_injected_tiingo_without_legacy_fetch_import(tmp_path, monkeypatch):
    from gabi import config, historical_tiingo, smallmid_test
    from gabi.application.administration.jobs import JobCommand, Jobs
    from gabi.infrastructure.jobs.worker import Worker
    from gabi.infrastructure.settings import Settings
    from gabi.infrastructure.storage.jobs import SqliteJobs
    from gabi_cli.bootstrap import build_executor

    data = config.DATA_DIR
    smallmid_test.WORK.mkdir(parents=True, exist_ok=True)
    directory = data / "history_refresh/tiingo/smallmid"
    cache = FileTiingoCache(directory)
    cache.save("AAA", json.dumps(rows()[1:4]).encode())
    queue = data / "smallmid_test/tiingo_symbols.txt"
    queue.parent.mkdir(parents=True)
    queue.write_text("AAA", encoding="utf8")
    monkeypatch.setattr(historical_tiingo, "fetch", lambda *args, **kwargs: pytest.fail("No legacy fetch"))
    monkeypatch.setattr(historical_tiingo, "import_cached", lambda *args, **kwargs: pytest.fail("No legacy import"))
    monkeypatch.setattr("gabi.infrastructure.providers.tiingo_prices.TiingoPrices.request",
                        lambda *args: pytest.fail("No download on cached worker queue"))
    store = SqliteJobs(data)
    job = Jobs(store).submit(JobCommand("tiingo"), "tiingo-worker-test", origin="scheduler")
    assert Worker(store, build_executor(Settings(data), now=lambda: NOW), data).run_once()
    assert store.get(job["id"])["status"] == "succeeded"
    assert len(read_tables(data / "gabi.db")["historical_prices"]) == 3
    assert not (data / "periodic_tasks/tiingo.lock").exists()
    assert smallmid_test.tiingo_complete_path().is_file()


def test_bootstrap_callback_import_closes_every_connection(tmp_path, monkeypatch):
    from gabi.infrastructure.settings import Settings
    from gabi_cli.sources.bootstrap import build_tiingo_operations

    directory = tmp_path / "cache"
    FileTiingoCache(directory).save("AAA", b"[]")
    actual_connect, connections = sqlite3.connect, []

    def connect(*args, **kwargs):
        connection = actual_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    _, run_import = build_tiingo_operations(Settings(tmp_path), window_name="2010-2015", cache_directory=directory)
    assert run_import() == {"files": 1, "accepted": 0, "rejected": 0}
    assert len(connections) >= 2
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_sql_checkpoint_and_source_metadata_limits(tmp_path):
    from gabi.infrastructure.storage.sync_events import SqliteSyncEvents

    _, create = attempts(tmp_path / "db.sqlite")
    create("AAA", "test").finish("new", state={"fingerprint": "x" * 200})
    with closing(sqlite3.connect(tmp_path / "db.sqlite")) as connection:
        with pytest.raises(ValueError, match="checkpoint byte limit"):
            SqliteSyncEvents(connection, max_state_bytes=10).get("tiingo", "AAA", "test")
        archive = SqliteHistoricalPrices(connection)
        archive.register("test", {"files_sha256": {"AAA": "x" * 200}})
        with pytest.raises(ValueError, match="metadata byte limit"):
            archive.pinned("test", max_bytes=10)


def test_archive_reads_missing_tables_do_not_initialize_schema(tmp_path):
    path = tmp_path / "empty.sqlite"
    with closing(sqlite3.connect(path)) as connection:
        archive = SqliteHistoricalPrices(connection)
        before = path.read_bytes()
        assert archive.pinned("missing") == {}
        assert archive.dates("missing", "AAA", "2008-01-01", "2016-07-01").empty
        assert path.read_bytes() == before
        assert connection.execute("SELECT name FROM sqlite_schema").fetchall() == []


def test_existing_archive_dates_are_windowed_and_bounded(tmp_path):
    from gabi.domain.research.tiingo_prices import price_frame

    with closing(sqlite3.connect(tmp_path / "db.sqlite")) as connection:
        archive = SqliteHistoricalPrices(connection)
        archive.import_prices("test", price_frame("AAA", rows()), {"AAA"}, "2008-01-01", "2016-07-01")
        assert archive.dates("test", "AAA", "2013-01-01", "2016-07-01").tolist() == [pd.Timestamp("2015-01-02")]
        with pytest.raises(ValueError, match="date row limit"):
            archive.dates("test", "AAA", "2008-01-01", "2016-07-01", max_rows=1)


def test_response_rows_limit_does_not_publish_or_checkpoint(tmp_path):
    cache = FileTiingoCache(tmp_path / "cache")
    _, create = attempts(tmp_path / "db.sqlite")
    source = SimpleNamespace(request=lambda *args: PriceResponse(200, json.dumps(rows()).encode(), rows()))
    with pytest.raises(ValueError, match="response row limit"):
        fetch(["AAA"], window("2010-2015"), cache, source, attempt_factory=create,
              wait=lambda _: None, progress=lambda _: None, max_rows=1)
    assert not list(cache.directory.iterdir()) and not (tmp_path / "db.sqlite").exists()


def test_provider_key_and_network_failure_never_expose_secret(tmp_path, monkeypatch):
    from gabi.infrastructure.providers.tiingo_prices import TiingoPrices
    from gabi.infrastructure.storage.tiingo_prices import tiingo_key

    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    assert tiingo_key(tmp_path) is None
    path = tmp_path / "tiingo_api_key.txt"
    path.write_text(" temporary-file-key \n", encoding="utf8")
    assert tiingo_key(tmp_path) == "temporary-file-key"
    monkeypatch.setenv("TIINGO_API_KEY", " temporary-env-key ")
    assert tiingo_key(tmp_path) == "temporary-env-key"
    monkeypatch.setenv("TIINGO_API_KEY", "")
    path.write_bytes(b"x" * 4097)
    with pytest.raises(ValueError, match="key file limit"):
        tiingo_key(tmp_path)

    def fail(*args, **kwargs):
        raise requests.Timeout("Authorization: Token temporary-secret")

    monkeypatch.setattr("gabi.infrastructure.providers.tiingo_prices.requests.get", fail)
    assert TiingoPrices(lambda: "temporary-secret").request("AAA", "2008-01-01", "2016-07-01") == \
        PriceResponse(error_name="Timeout")
    with pytest.raises(ValueError, match="API key missing"):
        TiingoPrices(lambda: None).request("AAA", "2008-01-01", "2016-07-01")


def test_invalid_status_is_rejected_without_checkpoint_read(tmp_path):
    store = SimpleNamespace(get=lambda *args: pytest.fail("No read"), save=lambda *args: pytest.fail("No write"))
    attempt = SyncAttempt("tiingo", "AAA", "test", store, now=lambda: NOW, wall_time=lambda: 4., cpu_time=lambda: 2.)
    with pytest.raises(ValueError, match="desconocido"):
        attempt.finish("unknown")
