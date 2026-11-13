"""The diary reads and updates the same local rows the retired Streamlit page wrote."""

import sqlite3

from fastapi.testclient import TestClient

from gabi.domain.portfolio.journal import compute_expected_value
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.journal import SCHEMA
from gabi_api.bootstrap import create_app


def rows(root) -> dict[int, sqlite3.Row]:
    with sqlite3.connect(root / "gabi.db") as db:
        db.row_factory = sqlite3.Row
        return {row["id"]: row for row in db.execute("SELECT * FROM journal_entries")}


def test_journal_reads_legacy_rows_and_writes_compatible_reviews(tmp_path):
    with sqlite3.connect(tmp_path / "gabi.db") as db:  # A row as the Streamlit diary stored it.
        db.executescript(SCHEMA)
        legacy_id = db.execute(
            "INSERT INTO journal_entries(symbol,created_at,entry_price,bear_price,base_price,bull_price,"
            "bear_prob,base_prob,bull_prob) VALUES('AAPL','2026-09-16',100,80,110,150,20,50,30)").lastrowid
    app = create_app(Settings(tmp_path))
    with TestClient(app) as api:
        entries = api.get("/api/v1/portfolio/journal").json()
        assert entries["total"] == 1
        assert entries["items"][0]["id"] == legacy_id
        assert entries["items"][0]["expected_value"] == compute_expected_value(
            100, 80, 110, 150, 20, 50, 30)
        response = api.post("/api/v1/portfolio/journal", json={
            "symbol": "msft", "thesis": "Tesis local", "entry_price": 200,
        })
        assert response.status_code == 201, response.text
        entry_id = response.json()["id"]
        assert rows(tmp_path)[entry_id]["symbol"] == "MSFT"
        review = api.post(f"/api/v1/portfolio/journal/{entry_id}/review",
                          json={"review_price": 210, "review_notes": "Revisada"})
        assert review.status_code == 200, review.text
        assert review.json()["status"] == "revisada"
        assert rows(tmp_path)[entry_id]["review_price"] == 210
        open_only = api.get("/api/v1/portfolio/journal?only_open=true").json()
        assert [item["id"] for item in open_only["items"]] == [legacy_id] and open_only["total"] == 1
        assert api.post(f"/api/v1/portfolio/journal/{entry_id}/review", json={}).status_code == 404
        assert api.post(f"/api/v1/portfolio/journal/{entry_id}/delete").status_code == 204
        assert entry_id not in rows(tmp_path)


def test_journal_get_is_read_only_and_invalid_post_does_not_create_db(tmp_path):
    app = create_app(Settings(tmp_path))
    with TestClient(app) as api:
        assert api.get("/api/v1/portfolio/journal").json()["items"] == []
        for invalid in ({"symbol": "../../secret"}, {"symbol": "AAPL", "entry_price": -1}):
            assert api.post("/api/v1/portfolio/journal", json=invalid).status_code == 422
    assert not (tmp_path / "gabi.db").exists()
