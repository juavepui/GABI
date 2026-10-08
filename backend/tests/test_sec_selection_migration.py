"""Reference selection/batch parity and bounded, offline historical identity."""

import ast
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from gabi.application.market.sec_selection import batch, refresh
from gabi.domain.market.sec_identity import resolve_accredited
from gabi.infrastructure.jobs.sec_batch import run
from gabi.infrastructure.storage.sec_cik import SqliteCikResolutions
from gabi.infrastructure.storage.sec_selection import SqliteSecSelection

REFERENCE = json.loads((Path(__file__).parent / "fixtures/sec_selection_migration.json").read_text(encoding="utf-8"))
NOW = datetime(2024, 1, 10, 22, tzinfo=UTC)
MAP = pd.DataFrame({"symbol": ["A", "BRK-B"], "cik": ["0000000001", "0000000002"], "title": ["Issuer A", "B"]})


def captured(name, function, namespace):
    node = next(n for n in ast.parse(REFERENCE[name]).body if isinstance(n, ast.FunctionDef) and n.name == function)
    code = ast.get_source_segment(REFERENCE[name], node)
    code = code.replace("    from . import sync_state\n", "").replace("        from . import identity\n", "")
    exec(code, namespace)
    return namespace[function]


def selection_fixture(*, historical=False):
    state = SimpleNamespace(fetched={"A": NOW}, covered={"A"}, failures=set(),
                            cached={"OLD": ("0000000003", "Former")}, mapping=MAP.copy(), map_error=None,
                            history={"A": {"cik": "0000000001", "entity_id": "cik:0000000001"},
                                     "UNKNOWN": {"cik": None, "entity_id": None}}, covered_entities=set(),
                            batch_failed={})
    calls, remembered, errors = [], [], []
    def mapping(**options):
        calls.append(("map", options))
        if state.map_error:
            raise state.map_error
        return state.mapping
    def download(symbols, ciks, **options):
        calls.append(("batch", list(symbols), dict(ciks), dict(options)))
        return dict(state.batch_failed)
    def remember(symbol, cik, title):
        remembered.append((symbol, cik, title))
    def cached(symbol):
        return state.cached.get(symbol, (None, None))
    def resolve(symbol, cik_map):
        row = cik_map[cik_map.symbol == symbol]
        if row.empty and "." in symbol:
            row = cik_map[cik_map.symbol == symbol.replace(".", "-")]
        if row.empty:
            return cached(symbol)
        item = row.iloc[0]
        remember(symbol, item.cik, item.title)
        return item.cik, item.title
    namespace = {"datetime": SimpleNamespace(now=lambda tz: NOW), "UTC": UTC,
                 "config": SimpleNamespace(EDGAR_CACHE_MAX_AGE_HOURS=24),
                 "_classify_error": lambda exc, **k: ("test", str(exc)), "get_cik_map": mapping,
                 "get_edgar_fetched_at": lambda symbols: state.fetched,
                 "get_symbols_with_facts": lambda symbols: state.covered,
                 "get_cik_for_symbol": resolve, "_get_cached_cik_resolution": cached,
                 "fetch_edgar_batch": download, "storage": SimpleNamespace(record_update_errors=lambda source, failed: errors.append((source, dict(failed)))),
                 "sync_state": SimpleNamespace(failed_datasets=lambda source: state.failures),
                 "identity": SimpleNamespace(resolve=lambda symbol, day: state.history[symbol],
                                             observations=lambda entity, dataset: pd.DataFrame([{"x": 1}])
                                             if entity in state.covered_entities else pd.DataFrame())}
    old = captured("edgar", "ensure_edgar_data", namespace)
    store = SimpleNamespace(current=lambda symbols: (state.fetched, state.covered,
                            {symbol: {entity for entity, dataset in state.failures if dataset == f"facts:{symbol}"}
                             for symbol in symbols}), historical=lambda symbols, day: {s: state.history[s] for s in symbols},
                            covered_entities=lambda entities: state.covered_entities,
                            errors=lambda failed: errors.append(("sec_edgar", dict(failed))))
    resolutions = SimpleNamespace(cached_many=lambda symbols: {s: cached(s) for s in symbols},
                                  remember_many=lambda values: [remember(s, *pair) for s, pair in values.items()])
    modern = partial(refresh, store=store, mapping=mapping, resolutions=resolutions, download_batch=download,
                     classify_error=str, now=lambda: NOW, default_max_age_hours=24)
    return state, old, modern, calls, remembered, errors


@pytest.mark.parametrize("scenario", ["fresh", "missing_facts", "stale", "exact_boundary", "force", "full",
                                      "failed_owner", "failed_other_owner", "invalid_date", "fallback", "no_map",
                                      "historical", "historical_cached", "historical_force", "partial_failure"])
def test_selection_resolution_errors_and_flags_match_captured_original(scenario):
    state, old, modern, calls, remembered, errors = selection_fixture()
    symbols, options = ["A", "A", "BRK.B", "OLD", "UNKNOWN"], {}
    if scenario == "missing_facts":
        state.covered = set()
    elif scenario in ("stale", "exact_boundary"):
        state.fetched["A"] = NOW - timedelta(hours=24, seconds=scenario == "stale")
    elif scenario in ("force", "full"):
        options["force" if scenario == "force" else "full_refresh"] = True
    elif scenario.startswith("failed_"):
        state.failures = {(f"cik:000000000{1 if scenario == 'failed_owner' else 9}", "facts:A")}
    elif scenario == "invalid_date":
        state.fetched["A"] = None
    elif scenario in ("fallback", "no_map"):
        state.map_error = ValueError("synthetic unavailable map")
        if scenario == "no_map":
            state.cached = {}
    elif scenario.startswith("historical"):
        symbols, options = ["A", "A", "UNKNOWN"], {"as_of": "2019-01-01"}
        if scenario == "historical_cached":
            state.covered_entities = {"cik:0000000001"}
        if scenario == "historical_force":
            options["force"] = True
    elif scenario == "partial_failure":
        state.batch_failed = {"OLD": "synthetic source error"}
    expected = old(symbols, **options)
    expected_effects = list(calls), list(remembered), list(errors)
    calls.clear()
    remembered.clear()
    errors.clear()
    assert modern(symbols, **options) == expected
    assert (calls, remembered, errors) == expected_effects


def test_empty_selection_and_zero_max_age_preserve_published_behavior():
    _, old, modern, calls, remembered, errors = selection_fixture()
    for symbols, options in (([], {}), (["A"], {"max_age_hours": 0})):
        expected = old(symbols, **options)
        effects = list(calls), list(remembered), list(errors)
        calls.clear()
        remembered.clear()
        errors.clear()
        assert modern(symbols, **options) == expected
        assert (calls, remembered, errors) == effects
        calls.clear()
        remembered.clear()
        errors.clear()


def test_batch_error_progress_and_missing_cik_match_original():
    class Executor:
        def __init__(self, **options):
            assert options["max_workers"] == 4
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def submit(self, execute, *args, **options):
            class Future:
                def result(self):
                    return execute(*args, **options)
            return Future()
    calls, progress = [], []
    def fetch(symbol, cik):
        calls.append((symbol, cik))
        if symbol == "BAD":
            raise ValueError("synthetic failed issuer")
        return {}, []
    namespace = {"cf": SimpleNamespace(ThreadPoolExecutor=Executor, as_completed=lambda futures: list(futures)),
                 "_fetch_one": fetch, "upsert_edgar_metrics": lambda *a: None, "upsert_edgar_facts": lambda *a, **k: None,
                 "_classify_error": lambda exc, **k: ("test", str(exc))}
    old = captured("edgar", "fetch_edgar_batch", namespace)
    symbols, ciks = ["OK", "MISSING", "BAD"], {"OK": "1", "BAD": "2"}
    expected = old(symbols, ciks, incremental=False, progress_cb=lambda *args: progress.append(args))
    old_calls, old_progress = list(calls), list(progress)
    calls.clear()
    progress.clear()
    def runner(tasks, execute):
        for symbol, cik in tasks:
            error = None
            try:
                execute(symbol, cik)
            except Exception as exc:
                error = exc
            yield symbol, error
    assert batch(symbols, ciks, operation=fetch, runner=runner, classify_error=str,
                 progress_cb=lambda *args: progress.append(args)) == expected
    assert calls == old_calls and progress == old_progress


@pytest.mark.parametrize("claims,intervals,proofs", [([], [], []),
    ([("A", "cik:0000000001", "0000000001", 1.)], [], []),
    ([], [("A", "0000000001", "corroborated_candidate", "source")], []),
    ([], [("A", "0000000001", "ambiguous", "source")], []),
    ([], [("A", "0000000001", "corroborated_candidate", "source"),
          ("A", "0000000002", "confirmed_historical_ticker", "source")], []),
    ([], [("A", "0000000001", "corroborated_candidate", "source")],
     [("A", "cik:0000000001", json.dumps({"filed_date": "2012-01-01"}), "filing")])])
def test_accredited_policy_matches_original(claims, intervals, proofs):
    node = next(n for n in ast.parse(REFERENCE["historical_membership"]).body
                if isinstance(n, ast.FunctionDef) and n.name == "_identities")
    code = ast.get_source_segment(REFERENCE["historical_membership"], node)
    namespace = {"json": json, "historical_archive": SimpleNamespace(ACCREDITED_IDENTITY_TIERS=(
        "confirmed_by_multiple_evidence", "confirmed_historical_ticker", "corroborated_candidate")),
                 "identity": SimpleNamespace(MIN_CONFIDENCE=.9)}
    pure = "def original_policy(symbols, as_of, rows, evidence, intervals):\n" + code[code.index("    candidates: dict"):]
    exec(pure, namespace)
    expected = namespace["original_policy"]({"A", "MISSING"}, "2012-01-01", claims, proofs, intervals)
    assert resolve_accredited({"A", "MISSING"}, "2012-01-01", claims, proofs, intervals) == expected


def seed_identity(path):
    from gabi import historical_archive, identity
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        identity.ensure_schema(db)
        db.executescript(historical_archive.SCHEMA)
        db.executemany("INSERT INTO entities VALUES (?,?,?,?)", [
            ("cik:0000000001", "0000000001", "Old", "2010-01-01"),
            ("cik:0000000002", "0000000002", "New", "2020-01-01")])
        db.executemany("INSERT INTO entity_aliases VALUES (?,?,?,?,?,?)", [
            ("cik:0000000001", "REC", "2010-01-01", "2020-01-01", "dated-old", 1.),
            ("cik:0000000002", "REC", "2020-01-01", None, "dated-new", 1.)])
        db.execute("INSERT INTO historical_identity_intervals VALUES (?,?,?,?,?,?,?,?,?,?)",
                   ("sec-identity-evidence:2010-2015:v1", "DELISTED", "0000000001", "2010-01-01", "2016-01-01",
                    "corroborated_candidate", 2, "2010-01-01", "2011-01-01", "[]"))
        db.commit()


def test_historical_resolution_matches_legacy_and_never_uses_current_map(tmp_path, monkeypatch):
    from gabi import config, identity
    path = tmp_path / "gabi.db"
    seed_identity(path)
    monkeypatch.setattr(config, "DB_PATH", path)
    store = SqliteSecSelection(path, lambda: NOW)
    before = path.read_bytes()
    for day in ("2012-01-01", "2019-01-01", "2020-01-01"):
        symbols = ["rec", "DELISTED", "UNKNOWN"]
        actual = store.historical(symbols, day)
        assert path.read_bytes() == before
        expected = {symbol: identity.resolve(symbol, day) for symbol in symbols}
        assert actual == expected
        before = path.read_bytes()


def test_readers_do_not_initialize_missing_database_or_schema(tmp_path):
    store = SqliteSecSelection(tmp_path / "absent/gabi.db", lambda: NOW)
    assert store.current(["A"]) == ({}, set(), {})
    assert store.covered_entities(["cik:0000000001"]) == set()
    assert store.historical(["A"], "2012-01-01")["A"]["cik"] is None
    assert not store.path.parent.exists()
    store.path.parent.mkdir()
    with closing(sqlite3.connect(store.path)) as db:
        db.execute("CREATE TABLE unrelated(x)")
    before = store.path.read_bytes()
    assert store.current(["A"]) == ({}, set(), {})
    assert store.historical(["A"], "2019-01-01")["A"]["cik"] is None
    assert store.path.read_bytes() == before


def test_bulk_resolutions_and_reads_are_bounded(tmp_path):
    port = SqliteCikResolutions(tmp_path / "gabi.db", lambda: NOW)
    assert port.cached_many(["A"]) == {"A": (None, None)}
    assert not port.path.exists()
    values = {f"S{i}": (str(i).zfill(10), "Issuer") for i in range(205)}
    port.remember_many(values)
    assert port.cached_many(list(values)) == values
    with pytest.raises(ValueError, match="campo"):
        SqliteCikResolutions(port.path, lambda: NOW, max_field_bytes=1).cached_many(["S1"])
    with pytest.raises(ValueError, match="símbolos"):
        port.cached_many([f"S{i}" for i in range(1001)])
    store = SqliteSecSelection(port.path, lambda: NOW, max_symbols=1)
    with pytest.raises(ValueError, match="símbolos"):
        store.current(["A", "B"])


def test_error_rows_and_retention_preserve_published_policy(tmp_path):
    store = SqliteSecSelection(tmp_path / "gabi.db", lambda: NOW)
    store.errors({})
    assert not store.path.exists()
    store.errors({"A": "first"})
    with closing(sqlite3.connect(store.path)) as db:
        db.execute("INSERT INTO update_errors(source,symbol,reason,occurred_at) VALUES ('other','B','old',?)",
                   ((NOW - timedelta(days=91)).isoformat(),))
        db.commit()
    store.errors({"A": "second"})
    with closing(sqlite3.connect(store.path)) as db:
        assert db.execute("SELECT source,symbol,reason,occurred_at FROM update_errors ORDER BY id").fetchall() == [
            ("sec_edgar", "A", "first", NOW.isoformat()), ("sec_edgar", "A", "second", NOW.isoformat())]


def test_thread_pool_preserves_per_symbol_failures_and_limits():
    def execute(symbol, cik):
        if symbol == "BAD":
            raise ValueError("bad issuer")
    result = dict(run([("OK", "1"), ("BAD", "2")], execute))
    assert result["OK"] is None and isinstance(result["BAD"], ValueError)
    with pytest.raises(ValueError, match="workers"):
        list(run([], execute, max_workers=5))
