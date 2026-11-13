"""Saved-ranking follow-up matches the old Screener calls with bounded, read-only price reads."""

import sqlite3
from contextlib import closing
from datetime import timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture
from ranking_fixture import RankingFixture

from gabi import config
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


@pytest.fixture
def saved():
    root = config.DATA_DIR
    seed_fixture(root, companies=12)
    evaluation = RankingFixture(root, TODAY)
    table = pd.DataFrame({"composite_score": [80.0, 70.0, 60.0], "score_coverage": [.9, .9, .9],
                          "confidence": [90.0, 80.0, 70.0], "sector": ["X", "Y", "Z"]},
                         index=["T000", "T001", "MISSING"])
    as_of = (TODAY - timedelta(days=200)).isoformat()
    snapshot_id = evaluation.save_snapshot(table, as_of, top_n=3, name="Ranking de prueba")
    app = create_app(Settings(root), today=lambda: TODAY)
    with TestClient(app) as client:
        yield client, root, snapshot_id, as_of


def test_progress_curve_and_horizons_match_the_old_screener(saved):
    client, root, snapshot_id, as_of = saved
    evaluation = RankingFixture(root, TODAY)
    symbols = evaluation.snapshot_symbols(snapshot_id)
    expected = evaluation.progress_for(symbols, as_of, data_as_of=evaluation._latest_cached_date(symbols + ["SPY"]),
                                       today=TODAY)  # The page's call, with the app's date.
    curve = evaluation.snapshot_price_curve(snapshot_id)
    before = (root / "gabi.db").read_bytes()
    response = client.get(f"/api/v1/market/snapshots/{snapshot_id}/progress")
    assert response.status_code == 200, response.text
    body = response.json()
    for key in ("portfolio_return", "benchmark_return", "excess_return", "available", "requested", "missing",
                "stale"):
        assert body[key] == expected[key], key
    assert body["data_as_of"] == expected["data_as_of"]
    assert [row["return"] for row in body["detail"]] == [
        None if pd.isna(value) else value for value in expected["detail"]["return"]]
    assert [point["basket"] for point in body["curve"]] == curve["Cartera"].tolist()
    assert [point["spy"] for point in body["curve"]] == curve["SPY"].tolist()
    six, twelve = (evaluation.evaluate(symbols, as_of, months, today=TODAY) for months in (6, 12))
    assert {key: body["horizons"][0][key] for key in six} == six
    assert {key: body["horizons"][1][key] for key in twelve} == twelve
    assert six["status"] == "incomplete" and twelve["status"] == "pending"  # MISSING has no prices.
    assert (root / "gabi.db").read_bytes() == before


def test_rename_is_explicit_and_validated(saved):
    client, root, snapshot_id, _ = saved
    evaluation = RankingFixture(root, TODAY)
    renamed = client.post(f"/api/v1/market/snapshots/{snapshot_id}/rename", json={"name": "  Pesos 40/30  "})
    assert renamed.json() == {"id": snapshot_id, "name": "Pesos 40/30"}
    assert evaluation.list_snapshots().set_index("id").loc[snapshot_id, "name"] == "Pesos 40/30"
    assert client.post(f"/api/v1/market/snapshots/{snapshot_id}/rename", json={"name": " "}).status_code == 422
    assert client.post("/api/v1/market/snapshots/999/rename", json={"name": "x"}).status_code == 404
    assert client.get("/api/v1/market/snapshots/999/progress").status_code == 404


def test_dotted_share_classes_follow_the_current_dash_spelling(saved):
    """A snapshot saved as BRK.B reads the current BRK-B series, not the old dotted rows (#172)."""
    client, root, _, as_of = saved
    evaluation = RankingFixture(root, TODAY)
    table = pd.DataFrame({"composite_score": [80.0, 70.0], "score_coverage": [.9, .9],
                          "confidence": [90.0, 80.0], "sector": ["X", "Y"]})
    dotted = evaluation.save_snapshot(table.set_axis(["T000", "BRK.B"]), as_of, top_n=2, name="Con punto")
    dashed = evaluation.save_snapshot(table.set_axis(["T000", "BRK-B"]), as_of, top_n=2, name="Con guion")
    stale_end = (TODAY - timedelta(days=30)).isoformat()
    with closing(sqlite3.connect(root / "gabi.db")) as db, db:
        # Old dotted rows stop a month ago and have other prices: they must not be read.
        db.execute("INSERT INTO prices SELECT 'BRK.B',date,open*2,high*2,low*2,close*2,volume,adj_close*2 "
                   "FROM prices WHERE symbol='BRK-B' AND date<=?", (stale_end,))
    before = (root / "gabi.db").read_bytes()
    body = client.get(f"/api/v1/market/snapshots/{dotted}/progress").json()
    expected = client.get(f"/api/v1/market/snapshots/{dashed}/progress").json()
    assert body["available"] == body["requested"] == 2 and body["missing"] == []
    for key in ("portfolio_return", "excess_return", "detail", "curve", "horizons"):
        assert body[key] == expected[key], key
    assert evaluation.snapshot_symbols(dotted) == ["T000", "BRK.B"]  # The saved snapshot is not rewritten.
    assert (root / "gabi.db").read_bytes() == before
