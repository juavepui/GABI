"""Empresas seguidas (#182): explicit writes, the view read in batch from the cache and its limits."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.application.errors import QueryError
from gabi.domain.market import model_policy
from gabi.domain.market import watchlist as rules
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.journal import SqliteJournal
from gabi.infrastructure.storage.watchlist import SqliteWatchlist
from gabi_api.bootstrap import create_app

TABLE = pd.DataFrame({"composite_score": [80.0, 60.0, 40.0], "name": ["Alfa", "Beta", None],
                      "sector": ["Energy", "Energy", None],
                      "next_earnings_date": ["2026-10-20", None, float("nan")],
                      "next_earnings_is_estimate": [True, None, None]}, index=["AAA", "BBB", "CCC"])


def _saved(symbol: str, **changes) -> dict:
    return {"symbol": symbol, "added_at": "2026-09-01T10:00:00+00:00", "note": None, "model_id": "M1",
            "score_at_add": 50.0, "rank_at_add": 3} | changes


def test_rows_measure_the_change_only_against_the_same_model():
    saved = [_saved("BBB", note="Vigilar márgenes"), _saved("AAA", model_id="M0"), _saved("GONE")]
    theses = {"BBB": {"open": 1, "total": 2}}
    bbb, aaa, gone = rules.rows(saved, TABLE, "M1", theses)
    assert (bbb["composite_score"], bbb["rank"], bbb["score_change"], bbb["rank_change"]) == (60.0, 2, 10.0, 1)
    assert bbb["note"] == "Vigilar márgenes" and (bbb["open_theses"], bbb["theses"]) == (1, 2)
    assert bbb["next_earnings_date"] is None and bbb["next_earnings_is_estimate"] is None
    # Added with another model: today's score is shown, the change is not comparable.
    assert aaa["composite_score"] == 80.0 and aaa["rank"] == 1 and not aaa["same_model"]
    assert aaa["score_change"] is None and aaa["rank_change"] is None
    assert aaa["next_earnings_date"] == "2026-10-20" and aaa["next_earnings_is_estimate"] is True
    assert not gone["in_ranking"] and gone["composite_score"] is None and gone["name"] is None
    assert gone["theses"] == 0
    # Without a ranking the list and its notes are still there.
    assert [row["symbol"] for row in rules.rows(saved, None, "M1", {})] == ["BBB", "AAA", "GONE"]


def test_notes_are_trimmed_and_bounded():
    assert rules.clean_note("  revisar deuda ") == "revisar deuda" and rules.clean_note("   ") is None
    with pytest.raises(ValueError, match="500"):
        rules.clean_note("x" * 501)


def test_the_store_keeps_the_first_addition_and_is_bounded(tmp_path):
    store = SqliteWatchlist(tmp_path)
    assert store.items() == [] and not (tmp_path / "gabi.db").exists()  # Reading never creates the database.
    assert store.add(_saved("AAA", note="primera"), "now")
    assert not store.add(_saved("AAA", note="segunda"), "now")
    assert store.item("AAA")["note"] == "primera"
    for index in range(rules.MAX_COMPANIES - 1):
        store.add(_saved(f"S{index:03}"), "now")
    with pytest.raises(QueryError, match=str(rules.MAX_COMPANIES)):
        store.add(_saved("ONE-MORE"), "now")
    assert len(store.items()) == rules.MAX_COMPANIES
    assert store.delete("AAA") and not store.delete("AAA") and store.update_note("AAA", "x", "now") is False


def test_following_from_the_api_writes_only_on_explicit_actions(tmp_path):
    seed_fixture(tmp_path)
    SqliteJournal(tmp_path).create({"symbol": "T001", "created_at": "2026-09-01T10:00:00", "thesis": "Margen"})
    stamp = (tmp_path / "gabi.db").stat().st_mtime_ns
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        assert api.get("/api/v1/watchlist").json()["items"] == []
        assert api.get("/api/v1/watchlist/symbols").json() == {"symbols": []}
        assert api.get("/api/v1/watchlist/checklist").json() == {"items": {}}
        assert (tmp_path / "gabi.db").stat().st_mtime_ns == stamp  # A GET never creates the table.
        created = api.post("/api/v1/watchlist", json={"symbol": "t001", "note": "  Revisar márgenes "})
        assert created.status_code == 201, created.text
        entry = created.json()
        table = api.app.state.market.repository.ranking(dict(model_policy.FROZEN_WEIGHTS), TODAY).table
        assert entry["symbol"] == "T001" and entry["note"] == "Revisar márgenes"
        assert entry["model_id"] == model_policy.FROZEN_MODEL_ID
        assert (entry["score_at_add"], entry["rank_at_add"]) == rules.standing(table, "T001")
        # Following it again keeps the first date, note and starting score.
        assert api.post("/api/v1/watchlist", json={"symbol": "T001", "note": "otra"}).json() == entry
        assert api.post("/api/v1/watchlist", json={"symbol": "NOPE"}).json()["error"]["code"] == "company_not_found"
        assert api.post("/api/v1/watchlist", json={"symbol": "T002", "note": "x" * 501}).status_code == 422
        assert api.post("/api/v1/watchlist", json={"symbol": "T002"}).status_code == 201
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:  # A restart keeps them.
        assert api.get("/api/v1/watchlist/symbols").json() == {"symbols": ["T001", "T002"]}
        body = api.get("/api/v1/watchlist").json()
        assert body["ranking_ready"] and body["model_id"] == model_policy.FROZEN_MODEL_ID
        first = body["items"][0]
        assert first["symbol"] == "T001" and first["name"] == "Company T001" and first["in_ranking"]
        assert first["same_model"] and first["score_change"] == 0 and first["rank_change"] == 0
        assert (first["open_theses"], first["theses"]) == (1, 1) and body["items"][1]["theses"] == 0
        checklists = api.get("/api/v1/watchlist/checklist").json()["items"]
        assert set(checklists) == {"T001", "T002"}
        assert all(item is None or item["evaluated"] <= item["applicable"] for item in checklists.values())
        edited = api.post("/api/v1/watchlist/T001", json={"note": ""}).json()
        assert edited["note"] is None and edited["added_at"] == first["added_at"]
        assert api.post("/api/v1/watchlist/T009", json={"note": "x"}).status_code == 404
        assert api.post("/api/v1/watchlist/t001/delete").json() == {"deleted": True}
        assert api.post("/api/v1/watchlist/T001/delete").status_code == 404
        assert api.get("/api/v1/watchlist/symbols").json() == {"symbols": ["T002"]}
