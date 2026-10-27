"""The diary in the company page (#186): a thesis captures price, score and checklist; what changed since."""

import sqlite3
from contextlib import closing
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.domain.market import model_policy
from gabi.domain.portfolio import alerts
from gabi.domain.portfolio.journal import changes
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.journal import ADDED_COLUMNS, SCHEMA, SqliteJournal
from gabi_api.bootstrap import create_app


def test_changes_compare_now_with_what_the_thesis_captured():
    entry = {"entry_price": 100.0, "entry_score": 60.0, "model_id": "M1", "entry_checklist_passed": 5,
             "entry_checklist_evaluated": 9}
    now = {"price": 110.0, "price_date": "2026-09-29", "score": 55.5, "model_id": "M1",
           "checklist_passed": 7, "checklist_evaluated": 10}
    result = changes(entry, now)
    assert result["price_return"] == pytest.approx(0.1) and result["score_change"] == pytest.approx(-4.5)
    assert result["checklist_change"] == 2 and result["same_model"]
    # Another model, or a value missing on either side, gives no change instead of a made-up one.
    other = changes(entry | {"model_id": "M0"}, now)
    assert other["score_change"] is None and not other["same_model"]
    empty = changes({"entry_price": None}, {"price": None})
    assert empty["price_return"] is None and empty["score_change"] is None and empty["checklist_change"] is None


def test_a_written_review_date_drives_the_home_alert():
    entries = [{"id": 1, "symbol": "A", "status": "abierta", "created_at": "2026-09-01",
                "horizon": "Largo (>12 meses)", "review_due": "2026-09-20"},
               {"id": 2, "symbol": "B", "status": "abierta", "created_at": "2025-01-01",
                "horizon": "Corto (<6 meses)", "review_due": "2026-12-01"},  # Its own date, not the horizon.
               {"id": 3, "symbol": "C", "status": "revisada", "created_at": "2025-01-01", "review_due": "2026-01-01"}]
    due = alerts.overdue_theses(entries, today=TODAY)
    assert [(alert["symbols"], alert["date"]) for alert in due] == [(["A"], "2026-09-20")]


def test_an_older_table_gains_the_new_columns_only_on_a_write(tmp_path):
    with closing(sqlite3.connect(tmp_path / "gabi.db")) as db, db:
        db.executescript(SCHEMA)  # The table as the Streamlit diary created it.
        db.execute("INSERT INTO journal_entries(symbol,created_at) VALUES('AAA','2026-01-01')")
    store = SqliteJournal(tmp_path)
    assert store.list_entries(10, 0, symbol="AAA")[0][0]["symbol"] == "AAA"  # A read changes nothing.
    with closing(sqlite3.connect(tmp_path / "gabi.db")) as db:
        assert "review_due" not in {row[1] for row in db.execute("PRAGMA table_info(journal_entries)")}
    store.create({"symbol": "BBB", "created_at": "2026-02-01", "review_due": "2026-12-01", "entry_score": 50.0})
    with closing(sqlite3.connect(tmp_path / "gabi.db")) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(journal_entries)")}
    assert {name for name, _ in ADDED_COLUMNS} <= columns
    assert store.thesis_counts() == {"AAA": {"open": 1, "total": 1}, "BBB": {"open": 1, "total": 1}}


def test_a_thesis_from_the_company_page_captures_price_score_and_checklist(tmp_path):
    seed_fixture(tmp_path)
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        assert api.get("/api/v1/portfolio/journal/symbols").json() == {"items": {}}
        due = (TODAY + timedelta(days=90)).isoformat()
        created = api.post("/api/v1/portfolio/journal", json={
            "symbol": "t001", "thesis": "Barata y rentable", "invalidation": "Si cae el margen", "review_due": due})
        assert created.status_code == 201, created.text
        entry = created.json()
        snapshot = api.app.state.market.repository.ranking(dict(model_policy.FROZEN_WEIGHTS), TODAY)
        table = snapshot.table
        assert entry["entry_price"] == pytest.approx(float(table.at["T001", "price"]))
        assert entry["entry_price_date"] == snapshot.table.attrs["sources"]["T001"]["price_date"]
        assert entry["entry_score"] == pytest.approx(float(table.at["T001", "composite_score"]))
        assert entry["model_id"] == model_policy.FROZEN_MODEL_ID
        assert entry["review_due"] == due and entry["invalidation"] == "Si cae el margen"
        checklist = api.get("/api/v1/companies/T001/checklist").json()["summary"]
        assert (entry["entry_checklist_passed"], entry["entry_checklist_evaluated"]) == (
            checklist["passed"], checklist["evaluated"])
        # A typed entry price wins over the captured close.
        typed = api.post("/api/v1/portfolio/journal", json={"symbol": "T002", "entry_price": 12.5}).json()
        assert typed["entry_price"] == 12.5 and typed["entry_price_date"] is None
        for wrong in (TODAY.isoformat(), (TODAY + timedelta(days=366 * 11)).isoformat()):
            assert api.post("/api/v1/portfolio/journal", json={"symbol": "T003", "review_due": wrong}
                            ).status_code == 422
        mine = api.get("/api/v1/portfolio/journal", params={"symbol": "T001"}).json()
        assert [item["id"] for item in mine["items"]] == [entry["id"]] and mine["total"] == 1
        assert api.get("/api/v1/portfolio/journal/symbols").json()["items"] == {
            "T001": {"open": 1, "total": 1}, "T002": {"open": 1, "total": 1}}
        stamp = (tmp_path / "gabi.db").stat().st_mtime_ns
        moved = api.get(f"/api/v1/portfolio/journal/{entry['id']}/changes").json()
        assert (tmp_path / "gabi.db").stat().st_mtime_ns == stamp  # Reading the changes writes nothing.
        assert moved["symbol"] == "T001" and moved["same_model"]
        assert moved["price_return"] == pytest.approx(0) and moved["score_change"] == pytest.approx(0)
        assert moved["checklist_change"] == 0
        assert api.get("/api/v1/portfolio/journal/999/changes").status_code == 404
