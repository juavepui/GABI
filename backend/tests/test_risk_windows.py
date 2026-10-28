"""Windows and dates of drawdown and volatility (#175): the full window is exactly the ranking's figure."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.domain.market.risk import compute_risk_metrics
from gabi.domain.market.risk_windows import drawdown, risk_windows
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def _frame(points, adjusted=True):
    days = [day for day, _ in points]
    closes = [close for _, close in points]
    return pd.DataFrame({"date": days, "close": closes, "adj_close": closes if adjusted else [None] * len(closes)})


def test_drawdown_dates_its_peak_and_trough():
    series = pd.Series([100.0, 120.0, 60.0, 90.0, 130.0, 117.0],
                       index=pd.to_datetime(["2014-06-02", "2014-06-30", "2020-03-23", "2021-01-04",
                                             "2024-01-02", "2026-09-29"]))
    assert drawdown(series) == {"value": pytest.approx(-0.5), "peak_date": "2014-06-30",
                                "trough_date": "2020-03-23", "start": "2014-06-02"}
    assert drawdown(pd.Series(dtype=float))["value"] is None


def test_windows_cut_by_calendar_and_flag_a_short_history():
    points = [("2018-01-02", 100.0), ("2019-06-03", 50.0), ("2022-01-03", 80.0), ("2024-06-03", 60.0),
              ("2026-09-29", 75.0)]
    body = risk_windows(_frame(points))
    rows = {row["window"]: row for row in body["drawdowns"]}
    assert body["history_start"] == "2018-01-02" and body["history_end"] == "2026-09-29" and body["sessions"] == 5
    assert body["price_basis"] == "adj_close"
    assert rows["full"]["value"] == pytest.approx(-0.5) and rows["full"]["trough_date"] == "2019-06-03"
    # The last 5 years start after 2021-09-29: the 2019 fall is outside, the 2024 one is inside.
    assert rows["5y"] == {"window": "5y", "complete": True, "value": pytest.approx(-0.25),
                          "peak_date": "2022-01-03", "trough_date": "2024-06-03", "start": "2022-01-03"}
    assert rows["3y"]["start"] == "2024-06-03" and rows["3y"]["value"] == pytest.approx(0.0)
    short = {row["window"]: row for row in risk_windows(_frame(points[-2:]))["drawdowns"]}
    assert not short["5y"]["complete"] and not short["3y"]["complete"] and short["full"]["complete"]
    # Without an adjusted close in every session, plain closes, as the ranking does.
    assert risk_windows(_frame(points, adjusted=False))["price_basis"] == "close"
    empty = risk_windows(pd.DataFrame())
    assert empty["sessions"] == 0 and all(row["value"] is None for row in empty["drawdowns"])


@pytest.fixture
def api(tmp_path):
    seed_fixture(tmp_path)
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, app.state.market.repository, tmp_path


def test_full_window_is_the_rankings_drawdown_and_reads_nothing_else(api):
    client, repository, root = api
    before = (root / "gabi.db").read_bytes()
    ranking = {row["symbol"]: row for row in client.get("/api/v1/ranking?hide_no_data=false&limit=500").json()["items"]}
    # BRK-B lacks one adjusted close: it is measured on plain closes, like its ranking figure.
    body = client.get("/api/v1/risk-windows?symbols=T001&symbols=brk.b&symbols=SHORT").json()
    assert [item["symbol"] for item in body["items"]] == ["T001", "BRK-B", "SHORT"]
    for item in body["items"]:
        full = next(row for row in item["drawdowns"] if row["window"] == "full")
        assert full["value"] == pytest.approx(ranking[item["symbol"]]["metrics"]["max_drawdown"]["value"])
        frame = repository.price_history(item["symbol"], 10_000, body["revision"])
        assert full["value"] == pytest.approx(compute_risk_metrics(frame.set_index(pd.to_datetime(frame["date"])))
                                              ["max_drawdown"])
        assert item["volatility_window"] == "cached_history" and item["history_end"] == TODAY.isoformat()
    brk = body["items"][1]
    assert brk["price_basis"] == "close"
    short = body["items"][2]
    assert short["sessions"] == 5 and not next(row for row in short["drawdowns"] if row["window"] == "3y")["complete"]
    assert (root / "gabi.db").read_bytes() == before


@pytest.mark.parametrize("query, status", [
    ("", 422), ("symbols=" + "&symbols=".join(f"T00{i}" for i in range(6)), 422), ("symbols=NOPE", 404),
])
def test_invalid_requests(api, query, status):
    client, _, _ = api
    assert client.get("/api/v1/risk-windows?" + query).status_code == status
