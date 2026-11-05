"""¿Esto sube, baja o es lo normal? (#327): monthly points and fixed reading rules."""

import sqlite3
from datetime import date

from fastapi.testclient import TestClient

from gabi.domain.market import macro_trend as trend
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def _months(values: list[float], start: date = date(2021, 11, 1)) -> list[tuple[date, float]]:
    points = []
    for index, value in enumerate(values):
        year, month = start.year + (start.month - 1 + index) // 12, (start.month - 1 + index) % 12 + 1
        points.append((date(year, month, 15), value))
    return points


def test_one_point_per_month_the_last_one_and_at_most_five_years():
    points = [(date(2026, 1, 5), 1.0), (date(2026, 1, 28), 2.0), (date(2026, 2, 3), 3.0)]
    assert trend.monthly(points) == [(date(2026, 1, 28), 2.0), (date(2026, 2, 3), 3.0)]
    assert len(trend.monthly(_months([1.0] * 80))) == trend.WINDOW_MONTHS


def test_direction_uses_ten_percent_of_its_five_year_range():
    base = [2.0, 6.0] + [4.0] * 46  # Range 4 → threshold 0,4.
    up = trend.read(_months(base[:-1] + [4.41]), "%")
    assert up["direction"] == "up" and up["text"].startswith("Subiendo en los últimos 12 meses (de 4,0 a 4,4).")
    flat = trend.read(_months(base[:-1] + [4.39]), "%")
    assert flat["direction"] == "flat" and flat["text"].startswith("Estable")
    down = trend.read(_months(base[:-1] + [3.5]), "%")
    assert down["direction"] == "down" and down["level"] == "below"
    assert "Hoy está por debajo de sus últimos 4 años (mediana de 4,0)." in down["text"]


def test_short_history_says_so_and_unspoken_units_keep_only_words():
    short = trend.read(_months([1.0] * 12), "%")
    assert short["direction"] is None and short["text"].startswith("Todavía no hay 12 meses")
    no_level = trend.read(_months([1.0] * 13 + [5.0] * 5), "%")
    assert no_level["direction"] == "up" and no_level["level"] is None and "Hoy está" not in no_level["text"]
    dollars = trend.read(_months([7e12] * 30 + [6e12] * 12), "USD")
    assert dollars["text"] == "Bajando en los últimos 12 meses. Hoy está por debajo de sus últimos 3 años."
    small = trend.read(_months([0.5] * 24 + [0.08] + [0.05] * 11 + [0.03]), "p. p.")
    assert "(de 0,08 a 0,03)" in small["text"]


def test_api_publishes_the_trend_in_the_level_unit_without_writing(tmp_path):
    with sqlite3.connect(tmp_path / "gabi.db") as db:
        db.execute("CREATE TABLE macro_series(series_id TEXT,date TEXT,value REAL)")
        db.executemany("INSERT INTO macro_series VALUES('DGS10',?,?)",
                       [(day.isoformat(), value) for day, value in _months([3.0] * 30 + [4.5] * 12)])
        db.executemany("INSERT INTO macro_series VALUES('WALCL',?,?)",
                       [(day.isoformat(), value) for day, value in _months([7_000_000.0] * 30)])
    stamp = (tmp_path / "gabi.db").stat().st_mtime_ns
    with TestClient(create_app(Settings(tmp_path))) as api:
        rows = {row["series_id"]: row for row in api.get("/api/v1/market/macro").json()["items"]}
    assert (tmp_path / "gabi.db").stat().st_mtime_ns == stamp
    assert rows["DGS10"]["trend"]["direction"] == "up" and len(rows["DGS10"]["trend"]["points"]) == 42
    assert rows["WALCL"]["trend"]["points"][0]["value"] == 7e12  # Millions of dollars → dollars, as the level.
    assert rows["NFCI"]["trend"]["points"] == [] and rows["NFCI"]["trend"]["text"].startswith("Todavía no hay")
