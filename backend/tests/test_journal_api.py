"""The new diary reads and updates the same local rows as Streamlit."""

from fastapi.testclient import TestClient

from gabi import config, journal
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def test_journal_reads_legacy_rows_and_writes_compatible_reviews(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    legacy_id = journal.add_entry({
        "symbol": "AAPL", "created_at": "2026-09-16", "entry_price": 100,
        "bear_price": 80, "base_price": 110, "bull_price": 150,
        "bear_prob": 20, "base_prob": 50, "bull_prob": 30,
    })
    app = create_app(Settings(tmp_path))
    with TestClient(app) as api:
        entries = api.get("/api/v1/portfolio/journal").json()
        assert entries["total"] == 1
        assert entries["items"][0]["id"] == legacy_id
        assert entries["items"][0]["expected_value"] == journal.compute_expected_value(
            100, 80, 110, 150, 20, 50, 30)
        response = api.post("/api/v1/portfolio/journal", json={
            "symbol": "msft", "thesis": "Tesis local", "entry_price": 200,
        })
        assert response.status_code == 201, response.text
        entry_id = response.json()["id"]
        assert journal.list_entries().set_index("id").loc[entry_id, "symbol"] == "MSFT"
        review = api.post(f"/api/v1/portfolio/journal/{entry_id}/review",
                          json={"review_price": 210, "review_notes": "Revisada"})
        assert review.status_code == 200, review.text
        assert review.json()["status"] == "revisada"
        assert journal.list_entries().set_index("id").loc[entry_id, "review_price"] == 210
        assert api.post(f"/api/v1/portfolio/journal/{entry_id}/review", json={}).status_code == 404
        assert api.post(f"/api/v1/portfolio/journal/{entry_id}/delete").status_code == 204
        assert entry_id not in journal.list_entries()["id"].tolist()


def test_journal_get_is_read_only_and_invalid_post_does_not_create_db(tmp_path):
    app = create_app(Settings(tmp_path))
    with TestClient(app) as api:
        assert api.get("/api/v1/portfolio/journal").json()["items"] == []
        for invalid in ({"symbol": "../../secret"}, {"symbol": "AAPL", "entry_price": -1}):
            assert api.post("/api/v1/portfolio/journal", json=invalid).status_code == 422
    assert not (tmp_path / "gabi.db").exists()
