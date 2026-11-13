"""#342: the ranking no longer blocks small reads, survives unrelated writes and server restarts, and the heatmap
iterates without copying the ranking's attrs. Every number stays the same."""

import sqlite3
import threading
from datetime import timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.application.administration.periodic import PeriodicTasks
from gabi.application.market.evidence_assessment import build_evidence
from gabi.domain.market import heatmap, score_history
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage import market as market_storage
from gabi.infrastructure.storage import ranking_revision, ranking_snapshot_file
from gabi_api.bootstrap import create_app


def _app(root):
    return create_app(Settings(root), today=lambda: TODAY)


@pytest.fixture
def cache(tmp_path):
    seed_fixture(tmp_path, companies=12)
    app = _app(tmp_path)
    with TestClient(app) as client:
        yield client, app.state.market.repository, tmp_path


def _weights(repository):
    return dict(repository.policy.weights)


def _token(repository):
    with repository.lock:
        repository.connect()
        return repository.token(repository.small_file("sp500_constituents.csv"))


def _write(root, sql, params=()):
    with sqlite3.connect(root / "gabi.db") as writer:
        writer.execute(sql, params)


def _forbid_computing(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the ranking was computed")
    monkeypatch.setattr(market_storage, "build_ranking", refuse)


# Part 1: small reads never queue behind a ranking being computed.

def test_model_state_does_not_wait_for_a_ranking_being_computed(cache):
    client, repository, _ = cache
    repository.lock.acquire()  # As the warm thread does while it builds the ranking.
    try:
        result: dict = {}
        thread = threading.Thread(target=lambda: result.update(response=client.get("/api/v1/model")))
        thread.start()
        thread.join(timeout=10)
        assert not thread.is_alive() and result["response"].status_code == 200
    finally:
        repository.lock.release()


def test_company_events_do_not_wait_for_a_ranking_being_computed(cache):
    _, repository, _ = cache
    expected = repository.company_events("T000", TODAY)
    repository.lock.acquire()
    try:
        result: dict = {}
        thread = threading.Thread(target=lambda: result.update(events=repository.company_events("T000", TODAY)))
        thread.start()
        thread.join(timeout=10)
        assert not thread.is_alive() and result["events"] == expected
    finally:
        repository.lock.release()


def test_model_state_without_database_keeps_the_defaults(tmp_path):
    seed_fixture(tmp_path, companies=12)
    (tmp_path / "gabi.db").unlink()
    repository = _app(tmp_path).state.market.repository
    model = repository.local_model()
    assert model.mode == "INVESTOR" and model.blind_id is None and not model.weak_tracking
    assert not (tmp_path / "gabi.db").exists()


# Part 2: only the ranking's inputs invalidate it, once the triggers are installed.

def test_without_the_counter_any_write_still_invalidates(cache):
    _, repository, root = cache
    before = _token(repository)
    _write(root, "CREATE TABLE IF NOT EXISTS notes(text TEXT)")
    _write(root, "INSERT INTO notes VALUES('diario')")
    assert _token(repository) != before and not repository.tracked()


def test_with_the_counter_an_unrelated_write_keeps_the_ranking(cache, monkeypatch):
    _, repository, root = cache
    _write(root, "CREATE TABLE notes(text TEXT)")
    assert ranking_revision.install(root / "gabi.db")["instalado"]
    first = repository.ranking(_weights(repository), TODAY)
    _write(root, "INSERT INTO notes VALUES('diario')")
    _forbid_computing(monkeypatch)
    again = repository.ranking(_weights(repository), TODAY)
    assert again.cache_hit and again.revision == first.revision


@pytest.mark.parametrize("sql", [
    "UPDATE prices SET close = close WHERE rowid = (SELECT min(rowid) FROM prices)",
    "DELETE FROM prices WHERE rowid = (SELECT max(rowid) FROM prices)",
    "INSERT INTO prices(symbol,date,close) VALUES('ZZZ','2026-01-01',1.0)",
    "UPDATE fundamentals SET fetched_at = fetched_at",
    "ALTER TABLE prices ADD COLUMN extra REAL",
])
def test_with_the_counter_an_input_or_schema_change_invalidates(cache, sql):
    _, repository, root = cache
    ranking_revision.install(root / "gabi.db")
    before = _token(repository)
    assert repository.tracked()
    _write(root, sql)
    assert _token(repository) != before


def test_every_present_input_table_gets_its_triggers(cache):
    _, _, root = cache
    report = ranking_revision.install(root / "gabi.db")
    with sqlite3.connect(root / "gabi.db") as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        present = [table for table in ranking_revision.INPUT_TABLES if table in tables]
        assert {"prices", "fundamentals"} <= set(present)
        assert report["triggers_nuevos"] == 3 * len(present)
        assert ranking_revision.install(root / "gabi.db")["triggers_nuevos"] == 0  # Idempotent.
        assert ranking_revision.read(db) is not None


def test_a_missing_trigger_falls_back_to_the_file_token(cache):
    _, repository, root = cache
    ranking_revision.install(root / "gabi.db")
    _write(root, 'DROP TRIGGER "ranking_rev_prices_update"')
    assert not repository.tracked()
    before = _token(repository)
    _write(root, "CREATE TABLE notes(text TEXT)")
    assert _token(repository) != before


def test_install_never_creates_a_database(tmp_path):
    assert ranking_revision.install(tmp_path / "gabi.db") == {"instalado": False, "motivo": "sin base de datos"}
    assert not (tmp_path / "gabi.db").exists()


def test_queries_never_install_the_counter(cache):
    client, _, root = cache
    for path in ("/api/v1/model", "/api/v1/ranking", "/api/v1/market/heatmap", "/api/v1/home"):
        client.get(path)
    with sqlite3.connect(root / "gabi.db") as db:
        assert ranking_revision.read(db) is None
        assert not db.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (ranking_revision.TABLE,)).fetchone()


# Part 3: the daily task's saved ranking is reused after a restart, exactly, and only for the same key.

def _assert_same(left, right):
    pd.testing.assert_frame_equal(left.table, right.table, check_exact=True)
    assert left.table.attrs == right.table.attrs
    assert left.identities == right.identities and left.revision == right.revision


def test_a_restarted_server_reuses_the_saved_ranking_exactly(cache, monkeypatch):
    _, repository, root = cache
    ranking_revision.install(root / "gabi.db")
    report = repository.save_snapshot(_weights(repository), TODAY)
    computed = repository.ranking(_weights(repository), TODAY)
    assert report["guardado"] and report["empresas"] == len(computed.table) > 0
    restarted = _app(root).state.market.repository
    _forbid_computing(monkeypatch)
    loaded = restarted.ranking(_weights(restarted), TODAY)
    _assert_same(loaded, computed)
    assert loaded.cache_hit
    assert restarted.cached_ranking(_weights(restarted), TODAY) is not None


def test_the_saved_ranking_is_ignored_after_a_data_change_or_on_another_day(cache):
    _, repository, root = cache
    ranking_revision.install(root / "gabi.db")
    repository.save_snapshot(_weights(repository), TODAY)
    restarted = _app(root).state.market.repository
    assert restarted.cached_ranking(_weights(restarted), TODAY - timedelta(days=1)) is None
    _write(root, "UPDATE prices SET close = close * 1.01 WHERE rowid = (SELECT max(rowid) FROM prices)")
    assert restarted.cached_ranking(_weights(restarted), TODAY) is None
    fresh = restarted.ranking(_weights(restarted), TODAY)
    assert not fresh.cache_hit


def test_without_the_counter_nothing_is_saved(cache):
    _, repository, root = cache
    assert repository.save_snapshot(_weights(repository), TODAY) == {
        "guardado": False, "motivo": "sin contador de revisión de datos"}
    assert not (root / ranking_snapshot_file.NAME).exists()


def test_a_corrupt_or_foreign_file_is_a_cache_miss(cache):
    _, repository, root = cache
    ranking_revision.install(root / "gabi.db")
    path = root / ranking_snapshot_file.NAME
    for contents in (b"garbage", b'{"format": "gabi-ranking-snapshot-v1"}\n\x80', b""):
        path.write_bytes(contents)
        assert repository.cached_ranking(_weights(repository), TODAY) is None
    assert not repository.ranking(_weights(repository), TODAY).cache_hit


def test_queries_never_write_the_saved_ranking(cache):
    client, _, root = cache
    ranking_revision.install(root / "gabi.db")
    for path in ("/api/v1/ranking", "/api/v1/market/heatmap", "/api/v1/home?compute=true"):
        assert client.get(path).status_code == 200
    assert not (root / ranking_snapshot_file.NAME).exists()


def test_the_daily_task_installs_first_and_saves_last_without_breaking_on_failure():
    class Operations:
        def __init__(self, fail):
            self.fail, self.calls = fail, []

        def verify_ledger(self):
            return {"ok": True}

        def install_ranking_revision(self):
            self.calls.append("install")
            if self.fail:
                raise OSError("bloqueada")
            return {"instalado": True, "triggers_nuevos": 0}

        def capture_ledger(self, error, maintenance):
            self.calls.append("ledger")
            return {"seq": 1, "record_hash": "h", "payload": {"status": "OK"}}

        def capture_active_ledger(self, error, maintenance):
            return None

        def record_scores(self):
            self.calls.append("scores")
            return {"guardadas": 1}

        def save_ranking(self):
            self.calls.append("save")
            if self.fail:
                raise OSError("disco lleno")
            return {"guardado": True}

    def run(fail):
        operations = Operations(fail)
        tasks = PeriodicTasks(type("Store", (), {"log": lambda self, event: None})(), operations, None,
                              lambda: pd.Timestamp("2026-11-05T05:00Z").to_pydatetime(), lambda: 0.0, lambda: 0.0)
        tasks.status = lambda: (operations.calls.append("status"), {})[1]
        tasks.record_due = lambda: []
        tasks.smallmid_step = lambda: {}
        return operations, tasks.run(refresh=False)

    operations, report = run(False)
    assert operations.calls == ["install", "status", "status", "ledger", "scores", "save"]
    assert report["ranking_guardado"] == {"guardado": True}
    operations, report = run(True)
    assert report["ledger"]["status"] == "OK" and "error" not in report
    assert report["contador_ranking"] == {"error": "OSError: bloqueada"}
    assert report["ranking_guardado"] == {"error": "OSError: disco lleno"}


# Part 4: same heatmap and score rows, without copying attrs into every row.

def test_heatmap_and_score_rows_are_identical_and_leave_attrs_untouched(cache):
    _, repository, _ = cache
    table = repository.ranking(_weights(repository), TODAY).table
    attrs = dict(table.attrs)
    plain = table.copy()
    plain.attrs = {}
    assert heatmap.build(table) == heatmap.build(plain)
    assert score_history.rows(table) == score_history.rows(plain)
    assert table.attrs == attrs and table.attrs["sources"]


def test_evidence_keeps_the_sources_freshness_and_leaves_the_ranking_attrs_untouched(cache):
    _, repository, _ = cache
    table = repository.ranking(_weights(repository), TODAY).table
    attrs = {key: dict(value) if isinstance(value, dict) else value for key, value in table.attrs.items()}
    def evidence(frame):
        return build_evidence(frame, _weights(repository), now=pd.Timestamp("2026-09-30T12:00Z").to_pydatetime(),
                              market_date="2026-09-29", catalogue={}, matching=True, metadata={},
                              analyze_stability=lambda frame, weights: (None, None, pd.DataFrame()),
                              model_id="M", benchmark="SPY")

    with_sources = evidence(table)
    without = table.copy()
    without.attrs = {}
    assert with_sources != evidence(without)  # The per-company sources still reach the freshness check.
    assert table.attrs == attrs
