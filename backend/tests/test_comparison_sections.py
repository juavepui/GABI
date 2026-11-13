"""Comparar (#194): checklist digest and rebased prices of 2–5 companies, read-only and bounded."""

import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture
from test_checklist import _excel_example, _frame

from gabi.application.market.comparison import CRITERIA
from gabi.domain.market.comparison import rebased
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.sec_xbrl import FACTS_SCHEMA
from gabi_api.bootstrap import create_app


def test_rebased_starts_where_every_series_has_a_close_and_never_fills_gaps():
    start, points = rebased({
        "A": [("2026-01-01", 10.0), ("2026-01-02", 20.0), ("2026-01-03", 30.0), ("2026-01-05", 40.0)],
        "B": [("2026-01-01", None), ("2026-01-02", 50.0), ("2026-01-03", 0.0), ("2026-01-05", 75.0)],
    })
    assert start == "2026-01-02"
    assert [point["date"] for point in points] == ["2026-01-02", "2026-01-03", "2026-01-05"]
    assert points[0]["values"] == {"A": 100.0, "B": 100.0}
    assert points[1]["values"] == {"A": 150.0, "B": None}  # a zero close is not a price
    assert points[2]["values"] == {"A": 200.0, "B": 150.0}


def test_rebased_without_a_common_session_is_empty():
    assert rebased({"A": [("2026-01-01", 1.0)], "B": [("2026-01-02", 1.0)]}) == (None, [])
    assert rebased({"A": [("2026-01-01", 1.0)], "B": []}) == (None, [])


@pytest.fixture
def api(tmp_path):
    seed_fixture(tmp_path)
    frame = _frame(_excel_example())
    with closing(sqlite3.connect(tmp_path / "gabi.db")) as db:
        db.executescript(FACTS_SCHEMA)
        db.executemany("INSERT INTO edgar_facts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       [("T001", r.tag, r.unit, r.start_date, r.end_date, r.val, r.form, r.fp, r.fy, r.filed_date,
                         r.accn) for r in frame.itertuples()])
        db.commit()
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as client:
        yield client, tmp_path


def test_prices_rebase_companies_and_spy_over_the_same_bounded_sessions(api):
    client, root = api
    before = (root / "gabi.db").read_bytes()
    body = client.get("/api/v1/comparison/prices?symbols=t001&symbols=BRK.B&bars=320").json()
    assert body["symbols"] == ["T001", "BRK-B"] and body["benchmark"] == "SPY" and body["unit"] == "index_100"
    # BRK-B has no adjusted close in the first fixture session: the base moves to the next one.
    assert body["base_date"] == body["points"][0]["date"] and len(body["points"]) == 319
    assert body["points"][0]["values"] == {"T001": 100.0, "BRK-B": 100.0, "SPY": 100.0}
    assert body["points"][-1]["date"] == TODAY.isoformat()
    page = client.get("/api/v1/companies/T001?bars=320").json()["prices"]
    closes = {point["date"]: point["adj_close"] for point in page}
    last = body["points"][-1]["values"]["T001"]
    assert last == pytest.approx(closes[TODAY.isoformat()] / closes[body["base_date"]] * 100)
    assert len(client.get("/api/v1/comparison/prices?symbols=T001&symbols=T002&bars=20").json()["points"]) == 20
    assert (root / "gabi.db").read_bytes() == before


@pytest.mark.parametrize("query, status", [
    ("symbols=T001", 422), ("symbols=T001&symbols=T001", 422), ("symbols=T001&symbols=NOPE", 404),
    ("symbols=T001&symbols=T002&bars=5000", 422),
])
def test_invalid_comparisons_are_rejected(api, query, status):
    client, _ = api
    assert client.get("/api/v1/comparison/prices?" + query).status_code == status


def test_checklist_digest_is_the_company_checklist_with_its_sector(api):
    client, root = api
    before = (root / "gabi.db").read_bytes()
    body = client.get("/api/v1/comparison/checklist?symbols=T001&symbols=T002").json()
    assert [item["symbol"] for item in body["items"]] == ["T001", "T002"]
    own = client.get("/api/v1/companies/T001/checklist").json()
    sector = client.get("/api/v1/companies/T001/checklist/sector").json()
    first = body["items"][0]
    assert first["summary"] == own["summary"] and first["fiscal_year_end"] == own["fiscal_year_end"]
    criteria = {item["key"]: item for item in own["criteria"]}
    assert [item["key"] for item in first["criteria"]] == list(CRITERIA)
    for item in first["criteria"]:
        assert item["value"] == criteria[item["key"]]["value"] and item["verdict"] == criteria[item["key"]]["verdict"]
    assert first["active_alarms"] == [alarm["label"] for alarm in own["alarms"] if alarm["status"] == "active"]
    assert first["history_medians"] == own["multiples_history"]["median"]
    assert first["sector"] == sector["sector"] and first["sector_medians"] == sector["medians"]
    assert body["items"][1]["fiscal_year_end"] is None and body["items"][1]["summary"]["evaluated"] == 0
    assert client.get("/api/v1/comparison/checklist?symbols=T001&symbols=NOPE").status_code == 404
    assert (root / "gabi.db").read_bytes() == before
    assert not (root / "checklist_thresholds.json").exists()
