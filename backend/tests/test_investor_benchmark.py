"""Investor profile revisions and the SPY benchmark in EUR from cached prices (#244); temporary data only."""

import sqlite3
from contextlib import closing
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.application.errors import QueryError
from gabi.application.portfolio.benchmark import InvestorBenchmark, refresh_prices
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.investor_profile import SqliteInvestorProfile
from gabi_api.bootstrap import create_app

PROFILE = {"initial_eur": 11_000, "monthly_eur": 700, "horizon_months": 12, "loss_tolerance": 0.2,
           "commission_fixed_eur": 1, "fx_cost_pct": 0.006}


def _frame(column: str, values: list[float], start: str) -> pd.DataFrame:
    return pd.DataFrame({column: values}, index=pd.bdate_range(start, periods=len(values)))


def test_every_save_is_a_new_revision_and_invalid_profiles_are_rejected(tmp_path):
    service = InvestorBenchmark(SqliteInvestorProfile(tmp_path), lambda symbols, start: {}, lambda: TODAY)
    assert service.profile() is None and service.revisions() == []
    assert not (tmp_path / "gabi.db").exists()  # Reading never creates the database.
    first = service.save(PROFILE)
    second = service.save(PROFILE | {"monthly_eur": 500})
    assert (first["revision"], second["revision"]) == (1, 2)
    assert [row["profile"]["monthly_eur"] for row in service.revisions()] == [500, 700]
    with pytest.raises(QueryError) as error:
        service.save(PROFILE | {"loss_tolerance": 1.5})
    assert error.value.code == "invalid_profile"


def test_benchmark_buys_spy_with_the_profile_contributions_and_the_broker_costs(tmp_path):
    prices = {"SPY": _frame("adj_close", [500.0] * 30, "2026-08-03"),
              "USDEUR=X": _frame("close", [0.9] * 30, "2026-08-03")}
    service = InvestorBenchmark(SqliteInvestorProfile(tmp_path), lambda symbols, start: prices, lambda: TODAY)
    with pytest.raises(QueryError) as error:
        service.benchmark()
    assert error.value.code == "profile_missing"
    service.save(PROFILE | {"horizon_months": 1})
    result = service.benchmark(date(2026, 8, 3))
    performance = result["performance"]
    # 11,000 on 3 Aug and 700 on 3 Sep, each paying 1 € plus 0.6 % on the converted euros.
    assert performance["contributed_eur"] == 11_700
    assert performance["costs_eur"] == pytest.approx(2 + 0.006 * (10_999 + 699))
    assert performance["final_value_eur"] == pytest.approx(11_700 - performance["costs_eur"])
    assert result["source"]["series"] == "adj_close" and result["profile_revision"] == 1
    assert result["pending"] == []


def test_missing_cached_prices_are_reported_and_never_downloaded(tmp_path):
    asked = []
    service = InvestorBenchmark(SqliteInvestorProfile(tmp_path),
                                lambda symbols, start: asked.append(symbols) or {}, lambda: TODAY)
    service.save(PROFILE)
    with pytest.raises(QueryError) as error:
        service.benchmark()
    assert error.value.code == "benchmark_prices_missing" and "SPY, USDEUR=X" in error.value.message
    assert asked == [["SPY", "USDEUR=X"]]


def test_the_explicit_job_downloads_spy_and_the_rate():
    asked = []
    result = refresh_prices(lambda symbols: asked.append(symbols) or {"USDEUR=X": "sin datos"})
    assert asked == [["SPY", "USDEUR=X"]]
    assert result == {"kind": "benchmark_prices", "symbols": ["SPY", "USDEUR=X"], "updated": 1,
                      "failed": {"USDEUR=X": "sin datos"}}


def test_api_saves_revisions_and_reads_the_benchmark_without_writing(tmp_path):
    seed_fixture(tmp_path)
    with closing(sqlite3.connect(tmp_path / "gabi.db")) as db, db:
        db.executemany("INSERT INTO prices(symbol,date,close,adj_close) VALUES('USDEUR=X',?,0.9,0.9)",
                       [(day.date().isoformat(),) for day in pd.bdate_range(end=TODAY, periods=320)])
    stamp = (tmp_path / "gabi.db").stat().st_mtime_ns
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        assert api.get("/api/v1/portfolio/investor/profile").json() == {"current": None, "revisions": []}
        assert api.get("/api/v1/portfolio/investor/benchmark").json()["error"]["code"] == "profile_missing"
        assert (tmp_path / "gabi.db").stat().st_mtime_ns == stamp
        saved = api.post("/api/v1/portfolio/investor/profile", json=PROFILE)
        assert saved.status_code == 201, saved.text
        assert api.post("/api/v1/portfolio/investor/profile", json=PROFILE | {"horizon_months": 0}).status_code == 422
        stamp = (tmp_path / "gabi.db").stat().st_mtime_ns
        result = api.get("/api/v1/portfolio/investor/benchmark")
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["start"] == "2025-09-29" and body["performance"]["status"] == "ok"
        assert body["performance"]["contributed_eur"] == 11_000 + 12 * 700
        assert body["series"][-1]["date"] == TODAY.isoformat()
        assert api.get("/api/v1/portfolio/investor/benchmark", params={"start": "2027-01-01"}).status_code == 422
        assert (tmp_path / "gabi.db").stat().st_mtime_ns == stamp  # Reading the benchmark writes nothing.
