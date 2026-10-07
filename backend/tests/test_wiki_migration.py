"""Isolated reference comparisons; no production data, keys, network or holdouts."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from gabi.application.research.wiki_prices import FetchResponse, fetch, import_cached
from gabi.domain.research.wiki_prices import URL, wiki_ticker
from gabi.infrastructure.providers.wiki_prices import NasdaqWikiSource
from gabi.infrastructure.storage.historical_prices import SCHEMA, SqliteHistoricalPrices
from gabi.infrastructure.storage.wiki_prices import FileWikiCache, nasdaq_key

REFERENCE = json.loads((Path(__file__).parent / "fixtures/wiki_migration.json").read_text(encoding="utf8"))
COLUMNS = "ticker,date,open,high,low,close,volume,ex-dividend,split_ratio,adj_close".split(",")


def payload(rows=None):
    return {"columns": COLUMNS, "data": rows if rows is not None else [
        ["different-provider-label", "2012-11-07", 24.91, 25.17, 24.38, 24.54, 21609000.0, 0.0, 1.0, 23.23],
        ["EMC", "2012-11-08", 25, 26, 24, 25.5, 1000, 0, 1, 24],
        ["EMC", "2012-11-09", 25, 24, 24, 25.5, 1000, 0, 1, 24],  # Invalid high.
        ["EMC", "2007-12-31", 25, 26, 24, 25.5, 1000, 0, 1, 24],  # Excluded start.
        ["EMC", "2016-07-01", 25, 26, 24, 25.5, 1000, 0, 1, 24],  # Excluded end.
    ]}


def legacy(directory, db, *, events=None, wait=None, messages=None):
    def get_connection():
        # The old SQL implementation expects a context that commits. Close too.
        class Connection:
            def __enter__(self):
                self.connection = sqlite3.connect(db)
                return self.connection

            def __exit__(self, kind, value, trace):
                try:
                    if kind is None:
                        self.connection.commit()
                    else:
                        self.connection.rollback()
                finally:
                    self.connection.close()
        return Connection()

    sql = {"np": np, "pd": pd, "storage": SimpleNamespace(get_connection=get_connection), "SCHEMA": SCHEMA}
    exec(REFERENCE["prices"], sql)

    def register(source_id, metadata):
        with get_connection() as connection:
            connection.executescript(SCHEMA)
            connection.execute("INSERT OR REPLACE INTO historical_sources VALUES (?,?)",
                               (source_id, json.dumps(metadata, sort_keys=True)))

    source = REFERENCE["wiki"].replace("from . import config, historical_archive", "")
    if events is not None:
        source = source.replace("import requests", "").replace("import time", "")
    module = {"__name__": "original_wiki", "config": SimpleNamespace(DATA_DIR=directory.parent,
              load_nasdaq_data_link_key=lambda: "temporary-secret"),
              "historical_archive": SimpleNamespace(register_source=register, import_price_chunk=sql["import_price_chunk"])}
    if events is not None:
        import requests

        def get(*args, **kwargs):
            event = events.pop(0)
            if isinstance(event, Exception):
                raise event
            return SimpleNamespace(status_code=event.status, json=lambda: event.payload)

        module.update(requests=SimpleNamespace(get=get, RequestException=requests.RequestException),
                      time=SimpleNamespace(sleep=wait.append), print=lambda message, **kwargs: messages.append(message))
    exec(source, module)
    module["DIRECTORY"] = directory
    return SimpleNamespace(**module)


def read_database(path):
    with closing(sqlite3.connect(path)) as connection:
        return (connection.execute("SELECT * FROM historical_sources ORDER BY source_id").fetchall(),
                connection.execute("SELECT * FROM historical_prices ORDER BY source_id,symbol,date").fetchall())


def cache_files(directory):
    directory.mkdir(parents=True)
    (directory / "EMC.json").write_text(json.dumps(payload()), encoding="utf8")
    (directory / "BRK-B.json").write_text(json.dumps(payload(payload()["data"][:1])), encoding="utf8")
    (directory / "EMPTY.json").write_text(json.dumps(payload([])), encoding="utf8")


def test_whole_import_metadata_rows_and_idempotence_equal_original(tmp_path):
    old_dir, new_dir = tmp_path / "old", tmp_path / "new"
    cache_files(old_dir)
    cache_files(new_dir)
    old_db, new_db = tmp_path / "old.db", tmp_path / "new.db"
    original = legacy(old_dir, old_db)
    cache = FileWikiCache(new_dir)
    with closing(sqlite3.connect(new_db)) as connection:
        archive = SqliteHistoricalPrices(connection)
        for _ in range(2):
            assert import_cached(cache, archive) == original.import_cached() == {"files": 3, "accepted": 3, "rejected": 1}
            assert read_database(new_db) == read_database(old_db)
    metadata = json.loads(read_database(new_db)[0][0][1])
    assert metadata["files_sha256"]["EMPTY"] == hashlib.sha256((new_dir / "EMPTY.json").read_bytes()).hexdigest()
    assert "temporary-secret" not in json.dumps(metadata)
    assert all(row[-1] == "as_traded" for row in read_database(new_db)[1])


@pytest.mark.parametrize("empty", [False, True])
def test_fetch_retry_schedule_counts_messages_and_bytes_equal_original(tmp_path, empty):
    import requests

    raw = payload([] if empty else payload()["data"])
    response = {"meta": {"next_cursor_id": None}, "datatable": {
        "columns": [{"name": name} for name in COLUMNS], "data": raw["data"]}}
    old_wait, new_wait, old_messages, new_messages = [], [], [], []
    old_events = [requests.ConnectionError("private request URL contains temporary-secret"),
                  FetchResponse(429), FetchResponse(200, response), *[FetchResponse(429) for _ in range(6)],
                  FetchResponse(403)]
    new_events = [FetchResponse(error_name="ConnectionError"), FetchResponse(429), FetchResponse(200, response),
                  *[FetchResponse(429) for _ in range(6)], FetchResponse(403)]
    original = legacy(tmp_path / "old", tmp_path / "old.db", events=old_events, wait=old_wait, messages=old_messages)
    original.DIRECTORY.mkdir()
    (original.DIRECTORY / "CACHED.json").write_text("unparsed cache hit", encoding="utf8")
    cache = FileWikiCache(tmp_path / "new")
    cache.ensure_directory()
    (cache.directory / "CACHED.json").write_text("unparsed cache hit", encoding="utf8")
    source = SimpleNamespace(request=lambda *args: new_events.pop(0))
    symbols = ["BRK.B", "CACHED", "LIMIT", "DENIED", "BRK.B"]
    assert fetch(symbols, cache, source, api_key="temporary-secret", wait=new_wait.append,
                 progress=new_messages.append, pause=0.75) == original.fetch(symbols, pause=0.75)
    assert old_wait == new_wait == [300, 600, 0.75, *[600 for _ in range(6)]]
    assert old_messages == new_messages
    assert not any("temporary-secret" in message for message in new_messages)
    assert (cache.directory / "BRK.B.json").read_bytes() == (original.DIRECTORY / "BRK.B.json").read_bytes()
    assert not old_events and not new_events


def test_missing_key_does_not_touch_cache_or_source(tmp_path):
    source = SimpleNamespace(request=lambda *args: pytest.fail("No download"))
    cache = FileWikiCache(tmp_path / "missing")
    with pytest.raises(ValueError, match="API key missing"):
        fetch(["EMC"], cache, source, api_key=None, wait=lambda _: pytest.fail("No wait"),
              progress=lambda _: pytest.fail("No progress"))
    assert not cache.directory.exists()


def test_paginated_response_never_publishes_a_cache(tmp_path):
    cache = FileWikiCache(tmp_path / "cache")
    source = SimpleNamespace(request=lambda *args: FetchResponse(200, {"meta": {"next_cursor_id": "next"}}))
    with pytest.raises(ValueError, match="paginated"):
        fetch(["EMC"], cache, source, api_key="secret", wait=lambda _: None, progress=lambda _: None)
    assert not list(cache.directory.iterdir())


@pytest.mark.parametrize("limit", ["bytes", "total_bytes", "files", "rows", "import_rows"])
def test_limits_prevent_archive_writes(tmp_path, limit):
    cache_files(tmp_path / "cache")
    kwargs = {"max_bytes": 1} if limit == "bytes" else {"max_total_bytes": 1} if limit == "total_bytes" else \
        {"max_files": 1} if limit == "files" else {"max_rows": 1} if limit == "rows" else {}
    cache = FileWikiCache(tmp_path / "cache", **kwargs)
    archive = SimpleNamespace(register=lambda *args: pytest.fail("No metadata write"),
                              import_prices=lambda *args: pytest.fail("No SQL write"))
    with pytest.raises(ValueError, match="limit exceeded"):
        import_cached(cache, archive, max_rows=1 if limit == "import_rows" else 2_000_000)


def test_missing_cache_read_is_empty_without_creating_directory(tmp_path):
    cache = FileWikiCache(tmp_path / "missing")
    assert list(cache.records()) == []
    assert not cache.directory.exists()


@pytest.mark.parametrize("symbol", ["../outside", "..", ".", "a/b", "a\\b"])
def test_cache_names_cannot_escape_directory(tmp_path, symbol):
    cache = FileWikiCache(tmp_path / "cache")
    with pytest.raises(ValueError, match="symbol"):
        cache.save(symbol, payload())
    assert not cache.directory.exists()


def test_failed_write_preserves_previous_bytes_and_cleans_temporary(tmp_path, monkeypatch):
    cache = FileWikiCache(tmp_path / "cache")
    cache.save("EMC", payload())
    before = (cache.directory / "EMC.json").read_bytes()
    monkeypatch.setattr(Path, "replace", lambda *args: (_ for _ in ()).throw(OSError("simulated")))
    with pytest.raises(OSError, match="simulated"):
        cache.save("EMC", payload([]))
    assert (cache.directory / "EMC.json").read_bytes() == before
    assert [path.name for path in cache.directory.iterdir()] == ["EMC.json"]


def test_duplicate_dates_reject_without_writing_prices_like_original(tmp_path):
    cache = FileWikiCache(tmp_path / "cache")
    cache.save("EMC", payload([payload()["data"][0]] * 2))
    original = legacy(cache.directory, tmp_path / "old.db")
    with pytest.raises(ValueError, match="Duplicate price"):
        original.import_cached()
    with closing(sqlite3.connect(tmp_path / "new.db")) as connection:
        with pytest.raises(ValueError, match="Duplicate price"):
            import_cached(cache, SqliteHistoricalPrices(connection))
    assert read_database(tmp_path / "new.db") == read_database(tmp_path / "old.db")


def test_provider_streaming_params_closure_and_limit(tmp_path, monkeypatch):
    response_payload = {"meta": {}, "datatable": {"columns": [], "data": []}}
    data = json.dumps(response_payload).encode()
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
            yield data[:10]
            yield data[10:]

    response = Response()
    monkeypatch.setattr("gabi.infrastructure.providers.wiki_prices.requests.get",
                        lambda *args, **kwargs: (calls.append((args, kwargs)), response)[1])
    assert NasdaqWikiSource().request("BRK-B", "temporary-secret") == FetchResponse(200, response_payload)
    assert response.closed
    assert calls[0] == ((URL,), {"params": {"ticker": "BRK_B", "date.gte": "2008-01-01",
                          "date.lt": "2016-07-01", "qopts.columns": ",".join(COLUMNS), "api_key": "temporary-secret"},
                          "timeout": 90, "stream": True})
    response.closed = False
    with pytest.raises(ValueError, match="response byte limit"):
        NasdaqWikiSource(max_bytes=10).request("EMC", "temporary-secret")
    assert response.closed


def test_provider_network_error_only_retains_type(monkeypatch):
    import requests

    def fail(*args, **kwargs):
        raise requests.Timeout("https://private.invalid/?api_key=temporary-secret")

    monkeypatch.setattr("gabi.infrastructure.providers.wiki_prices.requests.get", fail)
    assert NasdaqWikiSource().request("EMC", "temporary-secret") == FetchResponse(error_name="Timeout")


def test_key_precedence_empty_and_byte_limit_use_temporary_files(tmp_path, monkeypatch):
    monkeypatch.delenv("NASDAQ_DATA_LINK_API_KEY", raising=False)
    assert nasdaq_key(tmp_path) is None
    path = tmp_path / "nasdaq_data_link_api_key.txt"
    path.write_text(" temporary-file-key \n", encoding="utf8")
    assert nasdaq_key(tmp_path) == "temporary-file-key"
    monkeypatch.setenv("NASDAQ_DATA_LINK_API_KEY", " temporary-env-key ")
    assert nasdaq_key(tmp_path) == "temporary-env-key"
    monkeypatch.setenv("NASDAQ_DATA_LINK_API_KEY", "  ")
    path.write_bytes(b"x" * 4097)
    with pytest.raises(ValueError, match="key file limit"):
        nasdaq_key(tmp_path)


def test_cli_without_actions_has_no_sql_network_cache_or_key_reads(tmp_path, monkeypatch, capsys):
    from gabi.infrastructure.settings import Settings
    from gabi_cli.research.bootstrap import wiki_prices

    monkeypatch.setattr(sqlite3, "connect", lambda *args: pytest.fail("No SQLite"))
    monkeypatch.setattr("gabi.infrastructure.storage.wiki_prices.nasdaq_key", lambda *args: pytest.fail("No key read"))
    monkeypatch.setattr(NasdaqWikiSource, "request", lambda *args: pytest.fail("No download"))
    wiki_prices(Settings(tmp_path), SimpleNamespace(cache=None, db=None, fetch=None, import_cached=False))
    assert capsys.readouterr().out == "{}\n"
    assert not list(tmp_path.iterdir())


def test_cli_import_explicit_paths_and_closes_connection(tmp_path, monkeypatch, capsys):
    from gabi.infrastructure.settings import Settings
    from gabi_cli.research.bootstrap import wiki_prices

    directory, db = tmp_path / "cache", tmp_path / "archive.db"
    cache_files(directory)
    original_connect, connections = sqlite3.connect, []

    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    monkeypatch.setattr(NasdaqWikiSource, "request", lambda *args: pytest.fail("No download during import"))
    wiki_prices(Settings(tmp_path), SimpleNamespace(cache=directory, db=db, fetch=None, import_cached=True))
    assert json.loads(capsys.readouterr().out) == {"import": {"files": 3, "accepted": 3, "rejected": 1}}
    assert len(connections) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")
    assert wiki_ticker("BRK.B") == wiki_ticker("BRK-B") == "BRK_B"


@pytest.mark.parametrize(("column", "value"), [
    ("open", 0), ("close", -1), ("high", 23), ("low", 26), ("adj_close", None),
    ("adj_close", "not-a-number"), ("volume", -1), ("volume", float("inf")),
    ("close", "24.54"), ("volume", 0),
])
def test_archive_validation_complete_rows_equal_original_for_edge_values(tmp_path, column, value):
    raw = payload(payload()["data"][:2])
    raw["data"][0][COLUMNS.index(column)] = value
    cache = FileWikiCache(tmp_path / "cache")
    cache.save("EMC", raw)
    original = legacy(cache.directory, tmp_path / "old.db")
    expected = original.import_cached()
    with closing(sqlite3.connect(tmp_path / "new.db")) as connection:
        assert import_cached(cache, SqliteHistoricalPrices(connection)) == expected
    assert read_database(tmp_path / "new.db") == read_database(tmp_path / "old.db")


def test_cli_fetch_uses_explicit_key_cache_and_source(tmp_path, monkeypatch, capsys):
    import time

    from gabi.infrastructure.settings import Settings
    from gabi_cli.research.bootstrap import wiki_prices

    symbols = tmp_path / "symbols.txt"
    symbols.write_text(" brk.b \n\n", encoding="utf8")
    monkeypatch.setenv("NASDAQ_DATA_LINK_API_KEY", "temporary-secret")
    calls, waits = [], []
    response = {"meta": {}, "datatable": {"columns": [{"name": name} for name in COLUMNS], "data": []}}

    def request(self, symbol, key):
        calls.append((symbol, key))
        return FetchResponse(200, response)

    monkeypatch.setattr(NasdaqWikiSource, "request", request)
    monkeypatch.setattr(sqlite3, "connect", lambda *args: pytest.fail("No SQL during download"))
    monkeypatch.setattr(time, "sleep", waits.append)
    wiki_prices(Settings(tmp_path), SimpleNamespace(cache=None, db=None, fetch=symbols, import_cached=False))
    assert calls == [("BRK.B", "temporary-secret")]
    assert waits == [0.5]
    data = (tmp_path / "history_refresh/nasdaq_wiki/BRK.B.json").read_bytes()
    assert data == json.dumps(payload([])).encode()
    assert "temporary-secret" not in capsys.readouterr().out


def test_symbol_limit_rejects_before_cache_directory_creation(tmp_path):
    cache = FileWikiCache(tmp_path / "cache")
    with pytest.raises(ValueError, match="symbol limit"):
        fetch(["AAA", "BBB"], cache, SimpleNamespace(request=lambda *args: pytest.fail("No download")),
              api_key="secret", wait=lambda _: None, progress=lambda _: None, max_symbols=1)
    assert not cache.directory.exists()
