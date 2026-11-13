"""Semáforo del mercado (#308): fixed thresholds, days in the state and a read-only API."""

import hashlib
import re
import sqlite3

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gabi.domain.market import market_health as rules
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


@pytest.mark.parametrize(("close", "sma50", "sma200", "result"), [
    (110, 100, 100, "pass"), (90, 100, 100, "fail"), (100, 95, 105, "caution"), (100, 105, 95, "caution"),
    (100, 100, 100, "fail"),  # Equal is not above.
    (100, None, 100, None)])
def test_trend(close, sma50, sma200, result):
    assert rules.trend_check(close, sma50, sma200) == result


@pytest.mark.parametrize(("value", "result"), [(60.0, "pass"), (59.9, "caution"), (40.0, "caution"),
                                               (39.9, "fail"), (float("nan"), None)])
def test_breadth(value, result):
    assert rules.breadth_check(value) == result


@pytest.mark.parametrize(("days", "result"), [(0, "pass"), (3, "pass"), (4, "caution"), (5, "caution"),
                                              (6, "fail"), (None, None)])
def test_distribution(days, result):
    assert rules.distribution_check(days) == result


@pytest.mark.parametrize(("vix", "sma", "result"), [
    (15.0, 15.0, "pass"), (17.25, 15.0, "pass"), (17.26, 15.0, "caution"),  # More than 15 % above its average.
    (19.99, None, "pass"), (20.0, 20.0, "caution"), (29.99, 30.0, "caution"), (30.0, 40.0, "fail"),
    (None, 15.0, None)])
def test_volatility(vix, sma, result):
    assert rules.vix_check(vix, sma) == result


def test_rating_and_the_trend_brake():
    assert rules.rate({"trend": "pass", "breadth": "pass", "distribution": "caution", "volatility": "caution"}) == (
        75.0, "favorable")
    assert rules.rate({"trend": "fail", "breadth": "pass", "distribution": "pass", "volatility": "pass"}) == (
        75.0, "pressure")  # A falling index is never «Favorable».
    assert rules.rate({"trend": "pass", "breadth": "fail", "distribution": "caution", "volatility": None}) == (
        50.0, "pressure")  # Without the VIX, three checks count.
    assert rules.rate({"trend": "fail", "breadth": "fail", "distribution": "caution", "volatility": "pass"})[1] == (
        "correction")
    assert rules.rate({"trend": None}) == (None, None)


def _sessions(count: int, end: str = "2026-11-04") -> pd.DatetimeIndex:
    return pd.bdate_range(end=end, periods=count)


def _index(closes: np.ndarray, volumes: np.ndarray | None = None) -> pd.DataFrame:
    dates = _sessions(len(closes))
    volumes = np.full(len(closes), 1e6) if volumes is None else volumes
    return pd.DataFrame({"close": closes, "adj_close": closes, "volume": volumes}, index=dates)


def test_a_steady_rise_is_favorable_and_counts_its_days():
    closes = np.linspace(100, 200, 330)
    index = _index(closes)
    companies = pd.DataFrame({f"C{n}": closes * (1 + n / 100) for n in range(10)}, index=index.index)
    vix = pd.Series(14.0, index=index.index)
    result = rules.evaluate(index, companies, vix)
    assert result["status"] == "ready" and result["state"] == "favorable" and result["score"] == 100.0
    assert result["days_in_state"] == rules.HISTORY_SESSIONS and result["days_at_least"] is True
    checks = {check["key"]: check for check in result["checks"]}
    assert checks["breadth"]["values"]["above200"] == 100.0 and checks["breadth"]["values"]["new_highs"] == 10
    assert checks["trend"]["text"] == "El S&P 500 está por encima de sus medias de 50 y 200 sesiones."
    assert checks["volatility"]["text"] == "El VIX está en 14,0 (su media de 20 sesiones: 14,0)."


def test_a_fall_with_heavy_selling_is_a_correction_and_the_state_change_restarts_the_count():
    closes = np.concatenate([np.linspace(100, 200, 300), np.linspace(199, 150, 30)])
    volumes = np.where(np.arange(330) % 2 == 0, 2e6, 1e6)  # Every other falling day has more volume.
    index = _index(closes, volumes)
    companies = pd.DataFrame({f"C{n}": closes for n in range(5)}, index=index.index)
    vix = pd.Series(np.concatenate([np.full(300, 14.0), np.full(30, 35.0)]), index=index.index)
    result = rules.evaluate(index, companies, vix)
    checks = {check["key"]: check["result"] for check in result["checks"]}
    assert checks["distribution"] == "fail" and checks["volatility"] == "fail" and checks["breadth"] == "fail"
    assert result["state"] == "correction" and result["state_label"] == "En corrección"
    assert 0 < result["days_in_state"] < 30 and result["days_at_least"] is False


def test_without_enough_history_or_vix_it_says_so():
    assert rules.evaluate(_index(np.linspace(100, 110, 150)), pd.DataFrame(), None)["status"] == "no_data"
    result = rules.evaluate(_index(np.linspace(100, 200, 260)), pd.DataFrame(), pd.Series(dtype=float))
    checks = {check["key"]: check for check in result["checks"]}
    assert checks["volatility"]["result"] is None and checks["breadth"]["result"] is None
    assert checks["volatility"]["text"].startswith("Sin dato del VIX")
    assert result["score"] == 100.0  # Trend and heavy-selling days only.


def test_every_number_in_the_texts_comes_from_the_values():
    closes = np.linspace(100, 200, 330)
    index = _index(closes)
    companies = pd.DataFrame({f"C{n}": closes - n for n in range(7)}, index=index.index)
    result = rules.evaluate(index, companies, pd.Series(np.linspace(12, 22, 330), index=index.index))
    for check in result["checks"]:
        allowed = set()
        for value in check["values"].values():
            if isinstance(value, int | float) and value is not None:
                allowed |= {f"{value:.1f}".replace(".", ","), str(int(value))}
        text = check["text"].replace("S&P 500", "")
        for number in re.findall(r"\d+(?:,\d+)?", text):
            assert number in allowed or number in {"50", "200", "20"}, (number, check)  # The averages' lengths.


def _seed(tmp_path, sessions: int = 260):
    dates = [day.date().isoformat() for day in _sessions(sessions)]
    rows = []
    for symbol, scale in (("SPY", 1.0), ("AAA", 2.0), ("BBB", 0.5)):
        rows += [(symbol, day, 100 * scale + n, 100 * scale + n, 1e6) for n, day in enumerate(dates)]
    with sqlite3.connect(tmp_path / "gabi.db") as db:
        db.execute("CREATE TABLE prices(symbol TEXT,date TEXT,close REAL,adj_close REAL,volume REAL,"
                   "PRIMARY KEY(symbol,date))")
        db.executemany("INSERT INTO prices VALUES(?,?,?,?,?)", rows)
        db.execute("CREATE TABLE macro_series(series_id TEXT,date TEXT,value REAL)")
        db.executemany("INSERT INTO macro_series VALUES('VIXCLS',?,16.0)", [(day,) for day in dates[-40:]])
    (tmp_path / "sp500_constituents.csv").write_text("symbol,name\nAAA,A\nBBB,B\n", encoding="utf-8")


def test_api_reads_stored_prices_and_vix_without_writing(tmp_path):
    _seed(tmp_path)
    before = hashlib.sha256((tmp_path / "gabi.db").read_bytes()).hexdigest()
    app = create_app(Settings(tmp_path), today=lambda: pd.Timestamp("2026-11-05").date())
    with TestClient(app) as api:
        body = api.get("/api/v1/market/health").json()
        again = api.get("/api/v1/market/health").json()
    assert body == again and body["status"] == "ready" and body["benchmark"] == "SPY"
    assert body["universe_count"] == 2 and body["affects_score"] is False
    assert body["state"] == "favorable" and body["as_of"] == "2026-11-04"
    checks = {check["key"]: check for check in body["checks"]}
    assert checks["breadth"]["values"]["above200"] == 100.0 and checks["volatility"]["values"]["vix"] == 16.0
    assert hashlib.sha256((tmp_path / "gabi.db").read_bytes()).hexdigest() == before


def test_api_without_data_does_not_create_a_database(tmp_path):
    with TestClient(create_app(Settings(tmp_path))) as api:
        body = api.get("/api/v1/market/health").json()
    assert body["status"] == "no_data" and body["sessions"] == 0
    assert not (tmp_path / "gabi.db").exists()
