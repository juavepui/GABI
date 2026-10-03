import sqlite3

from fastapi.testclient import TestClient

from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def test_macro_reads_existing_series_with_original_units_and_three_month_delta(tmp_path):
    with sqlite3.connect(tmp_path / "gabi.db") as db:
        db.execute("CREATE TABLE macro_series(series_id TEXT,date TEXT,value REAL)")
        db.executemany("INSERT INTO macro_series VALUES(?,?,?)", [
            ("DGS10", "2026-01-02", 3.0), ("DGS10", "2026-04-03", 4.25),
            ("CPIAUCSL", "2026-04-01", 2.1),
        ])
    stamp = (tmp_path / "gabi.db").stat().st_mtime_ns
    with TestClient(create_app(Settings(tmp_path))) as api:
        result = api.get("/api/v1/market/macro")
        assert result.status_code == 200, result.text
        rows = {row["series_id"]: row for row in result.json()["items"]}
        assert rows["DGS10"]["latest_value"] == 4.25
        assert rows["DGS10"]["change_3m"] == 1.25
        assert rows["DGS10"]["unit"] == "%" and rows["DGS10"]["change_unit"] == "p. p."
        assert rows["CPIAUCSL"]["change_3m"] is None
        assert rows["WALCL"]["latest_value"] is None
        assert result.json()["affects_score"] is False
    assert (tmp_path / "gabi.db").stat().st_mtime_ns == stamp


def test_macro_missing_cache_does_not_initialize_database(tmp_path):
    with TestClient(create_app(Settings(tmp_path))) as api:
        assert all(row["latest_value"] is None for row in api.get("/api/v1/market/macro").json()["items"])
    assert not (tmp_path / "gabi.db").exists()


def test_macro_publishes_unambiguous_units_and_the_fed_balance_in_dollars(tmp_path):
    with sqlite3.connect(tmp_path / "gabi.db") as db:
        db.execute("CREATE TABLE macro_series(series_id TEXT,date TEXT,value REAL)")
        db.executemany("INSERT INTO macro_series VALUES(?,?,?)", [
            ("WALCL", "2026-06-01", 6_736_424.0), ("WALCL", "2026-09-16", 6_746_548.0),
            ("T10Y2Y", "2026-09-22", 0.25), ("BAMLH0A0HYM2", "2026-09-21", 2.66),
        ])
    with TestClient(create_app(Settings(tmp_path))) as api:
        rows = {row["series_id"]: row for row in api.get("/api/v1/market/macro").json()["items"]}
    assert rows["WALCL"]["unit"] == "USD" and rows["WALCL"]["latest_value"] == 6_746_548e6
    assert rows["WALCL"]["change_3m"] == 10_124e6
    assert (rows["T10Y2Y"]["unit"], rows["T10Y2Y"]["change_unit"]) == ("p. p.", "p. p.")
    assert (rows["BAMLH0A0HYM2"]["unit"], rows["BAMLH0A0HYM2"]["change_unit"]) == ("%", "p. p.")
