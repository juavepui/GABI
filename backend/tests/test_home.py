"""The home page answers at once from the cache, builds the frozen ranking only on request and never writes."""

import hashlib
import sqlite3
import threading
from datetime import timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi import app_mode
from gabi.domain.portfolio.selection import target_portfolio
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


@pytest.fixture
def home(tmp_path):
    seed_fixture(tmp_path, companies=30)
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    with TestClient(app) as client:
        yield client, app, tmp_path


def _files(root):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.iterdir() if path.is_file()}


def test_without_cache_home_answers_at_once_and_compute_builds_the_frozen_target(home):
    client, app, root = home
    before = _files(root)
    first = client.get("/api/v1/home").json()
    assert first["ranking_ready"] is False and first["data"] is None and first["target"] == []
    assert first["steps"]["universe"] is True and first["steps"]["fred_key"] is False
    assert first["steps"]["data_loaded"] is None
    computed = client.get("/api/v1/home", params={"compute": "true"}).json()
    table = app.state.market.repository.ranking(dict(app_mode.FROZEN_WEIGHTS), TODAY).table
    expected = target_portfolio(table, 20)
    assert [row["symbol"] for row in computed["target"]] == list(expected.index)
    assert computed["target"][0]["weight_pct"] == pytest.approx(100 / len(expected))
    assert computed["ranking_ready"] and computed["steps"]["data_loaded"] is True
    assert client.get("/api/v1/home").json()["ranking_ready"] is True  # Now from the cache.
    assert _files(root) == before


def test_home_does_not_wait_for_a_ranking_being_computed(home):
    client, app, _ = home
    repository = app.state.market.repository
    repository.lock.acquire()
    try:
        result: dict = {}
        thread = threading.Thread(target=lambda: result.update(client.get("/api/v1/home").json()))
        thread.start()
        thread.join(timeout=10)
        assert not thread.is_alive() and result["ranking_ready"] is False
    finally:
        repository.lock.release()


def test_last_update_reports_the_latest_successful_data_job(home):
    client, app, _ = home
    jobs = app.state.jobs
    jobs.list = lambda: [{"kind": "quality", "status": "succeeded", "finished_at": "2026-09-29T10:00:00"},
                         {"kind": "data_update", "status": "failed", "finished_at": "2026-09-29T09:00:00"},
                         {"kind": "data_update", "status": "succeeded", "finished_at": "2026-09-28T09:00:00"}]
    body = client.get("/api/v1/home").json()
    assert body["last_update"] == {"kind": "data_update", "finished_at": "2026-09-28T09:00:00"}
    assert body["steps"]["updated"] is True


def test_serve_warm_up_fills_both_rankings_read_only(home):
    from gabi_cli.bootstrap import warm_rankings

    client, app, root = home
    before = _files(root)
    warm_rankings(app)
    assert client.get("/api/v1/home").json()["ranking_ready"] is True
    assert client.get("/api/v1/ranking", params={"limit": 1}).json()["cache_hit"] is True
    assert _files(root) == before


def test_warm_up_without_data_does_not_raise(tmp_path):
    from gabi_cli.bootstrap import warm_rankings

    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as client:
        warm_rankings(client.app)
        assert client.get("/api/v1/home").json()["ranking_ready"] in (True, False)


def test_cache_outlives_idle_minutes_and_still_follows_the_data_revision(home):
    client, app, root = home
    assert app.state.settings.cache_seconds >= 3600
    assert client.get("/api/v1/ranking", params={"limit": 1}).json()["cache_hit"] is False
    assert client.get("/api/v1/ranking", params={"limit": 1}).json()["cache_hit"] is True
    with sqlite3.connect(root / "gabi.db") as db:  # Any write changes the revision and invalidates the entry.
        db.execute("CREATE TABLE IF NOT EXISTS touch (x)")
    assert client.get("/api/v1/ranking", params={"limit": 1}).json()["cache_hit"] is False


@pytest.mark.parametrize(("behind", "current"), [(0, True), (1, False)])
def test_home_says_whether_prices_include_the_last_closed_session(tmp_path, behind, current):
    seed_fixture(tmp_path, companies=30)
    session = TODAY + timedelta(days=behind)
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY, session=lambda: session)) as client:
        data = client.get("/api/v1/home", params={"compute": "true"}).json()["data"]
        assert data["status"] == "ready"  # The 7-day ranking tolerance alone would call both «ready».
        assert data["last_session"] == session.isoformat() and data["prices_current"] is current
        assert client.get("/api/v1/data/status").json()["prices_current"] is current


def test_ranking_reads_only_close_columns_with_the_same_values(home):
    """#85: the ranking's close-only read gives the same frames as the full read, minus unused columns."""
    _, app, _ = home
    repository = app.state.market.repository
    with repository.lock:
        repository.connect()
        repository.discover()
        symbols = ("T000", "T001", "T002")
        full = repository.prices(symbols, 160_000)
        closes = repository.closes(symbols, 160_000)
    assert set(closes) == set(full) and closes
    for symbol, frame in closes.items():
        assert list(frame.columns) == ["close", "adj_close"]
        pd.testing.assert_frame_equal(frame, full[symbol][["close", "adj_close"]], check_exact=True)
