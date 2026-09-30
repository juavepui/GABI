"""Data preparation is an explicit job that repeats the Streamlit download calls."""

import pytest
from fastapi.testclient import TestClient

from gabi import config, data_fetch, edgar, multifactor_backtest, universe
from gabi.application.administration.jobs import JobCommand
from gabi.application.errors import QueryError
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.legacy.preparation import prepare_history
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app

SYMBOLS = [f"S{i:03d}" for i in range(60)]


@pytest.mark.parametrize(("start", "end", "options", "code"), [
    ("2009-12-31", None, {"scope": "date"}, "reserved_period"),
    ("2025-07-03", None, {"scope": "date"}, "reserved_period"),
    ("2019-01-02", "2019-06-01", {"scope": "date"}, "invalid_job"),
    ("2019-01-02", None, {"scope": "date", "universe_limit": 20}, "invalid_job"),
    ("2019-01-02", "2025-12-31", {"scope": "backtest", "months": 3}, "reserved_period"),
    ("2019-01-02", "2019-01-02", {"scope": "backtest", "months": 3}, "invalid_job"),
    ("2019-01-02", "2020-01-02", {"scope": "backtest", "months": 2}, "invalid_job"),
    ("2019-01-02", "2020-01-02", {"scope": "other"}, "invalid_job"),
])
def test_preparation_rejects_reserved_or_inconsistent_requests(start, end, options, code):
    with pytest.raises(QueryError) as error:
        JobCommand("prepare_history", start=start, end=end, preparation=options)
    assert error.value.code == code
    with pytest.raises(QueryError):
        JobCommand("quality", preparation={"scope": "date"})


def _fake_sources(monkeypatch, calls):
    monkeypatch.setattr(universe, "get_sp500_constituents_asof", lambda as_of: {
        "symbols": SYMBOLS, "is_exact": True, "note": f"composición a {as_of}"})
    monkeypatch.setattr(edgar, "ensure_edgar_data", lambda symbols, **kwargs: calls.append(
        ("edgar", list(symbols), kwargs)) or {"edgar_refreshed": 3, "failed": {"S001": "sin CIK"}})
    monkeypatch.setattr(data_fetch, "ensure_price_history_asof", lambda symbols, as_of: calls.append(
        ("asof", list(symbols), as_of)) or {"deep_fetched": 4, "already_covered": 11,
                                           "failed": {"S001": "sin precio", "S002": "vacío"}})
    monkeypatch.setattr(data_fetch, "fetch_prices_batch", lambda symbols, period: calls.append(
        ("batch", list(symbols), period)) or ({"SPY": "x"} if symbols == ["SPY"] else {}))
    monkeypatch.setattr(multifactor_backtest, "required_symbols", lambda *args: calls.append(
        ("required", args)) or SYMBOLS)


def test_preparation_repeats_both_streamlit_buttons(monkeypatch):
    calls = []
    _fake_sources(monkeypatch, calls)
    options = JobCommand("prepare_history", start="2019-06-03",
                         preparation={"scope": "date", "universe_limit": 15}).preparation
    result = prepare_history("2019-06-03", None, options)
    assert calls == [("edgar", SYMBOLS[:15], {"as_of": "2019-06-03"}), ("asof", SYMBOLS[:15], "2019-06-03")]
    assert (result["symbols"], result["edgar_refreshed"], result["prices_deep_fetched"]) == (15, 3, 4)
    assert result["failed_symbols"] == 2
    assert result["failures"] == [{"symbol": "S001", "etapa": "edgar", "motivo": "sin CIK"},
                                  {"symbol": "S001", "etapa": "precio", "motivo": "sin precio"},
                                  {"symbol": "S002", "etapa": "precio", "motivo": "vacío"}]

    calls.clear()
    options = JobCommand("prepare_history", start="2019-01-02", end="2020-01-02",
                         preparation={"scope": "backtest", "months": 3}).preparation
    result = prepare_history("2019-01-02", "2020-01-02", options)
    assert calls[0] == ("required", ("2019-01-02", "2020-01-02", 3, None))
    assert calls[1] == ("edgar", SYMBOLS, {})
    assert [call[1] for call in calls[2:]] == [SYMBOLS[:25], SYMBOLS[25:50], SYMBOLS[50:], ["SPY"]]
    assert all(call[2] == "max" for call in calls[2:])
    assert result["failures"] == [{"symbol": "S001", "etapa": "edgar", "motivo": "sin CIK"},
                                  {"symbol": "SPY", "etapa": "precio", "motivo": "x"}]


def test_preparation_job_publishes_typed_result(tmp_path, monkeypatch):
    calls = []
    _fake_sources(monkeypatch, calls)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    with TestClient(create_app(Settings(tmp_path))) as api:
        created = api.post("/api/v1/jobs", json={"kind": "prepare_history", "idempotency_key": "prepare-01",
                                                 "start": "2019-06-03",
                                                 "preparation": {"scope": "date", "universe_limit": 50}})
        assert created.status_code == 202, created.text
        assert Worker(SqliteJobs(tmp_path), LegacyExecutor(Settings(tmp_path)), tmp_path).run_once()
        job_id = created.json()["id"]
        response = api.get(f"/api/v1/research/preparations/{job_id}")
        assert response.status_code == 200, response.text
        data = response.json()
        assert (data["scope"], data["symbols"], data["universe_note"]) == ("date", 50, "composición a 2019-06-03")
        assert data["failures"][0]["etapa"] == "edgar"
        bad = api.post("/api/v1/jobs", json={"kind": "prepare_history", "idempotency_key": "prepare-02",
                                             "start": "2019-06-03", "preparation": {"scope": "date",
                                                                                    "universe_limit": 20}})
        assert bad.status_code == 422
