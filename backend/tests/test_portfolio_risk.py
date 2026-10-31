"""Issuer risk panel and policy proposal (#248) through the use case and the API; temporary data only."""

import sqlite3
from contextlib import closing
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.application.errors import QueryError
from gabi.application.portfolio.risk import PortfolioRisk
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.investor_profile import SqliteInvestorProfile
from gabi_api.bootstrap import create_app

TABLE = pd.DataFrame({
    "composite_score": [90.0, 80.0, 70.0, 60.0, 50.0, 40.0],
    "score_coverage": [1.0] * 6,
    "sector": ["Financials", "Financials", "Tech", "Tech", "Energy", None],
    "price": [100.0, 50.0, 20.0, 10.0, 5.0, None],
    "avg_volume": [1e6, 1e6, 1e6, 10.0, 1e6, 1e6],
    "beta_calc": [1.2, 1.2, 1.0, 1.0, 0.8, None],
    "value_score": [60.0, 60.0, 50.0, 50.0, 40.0, 30.0],
}, index=["BRK-A", "BRK-B", "AAA", "TINY", "OIL", "NOPRICE"])


def _service(tmp_path, positions=None, rate=0.9, profile=None):
    return PortfolioRisk(
        SqliteInvestorProfile(tmp_path, "portfolio_policies"),
        lambda: positions or [],
        lambda: TABLE, lambda symbols: {s: "cik:berkshire" for s in symbols if s.startswith("BRK")},
        lambda: {"AAA": "Software"}, lambda: profile, lambda: rate, lambda: date(2026, 10, 31))


def test_policy_revisions_are_kept_apart_from_the_investor_profile(tmp_path):
    service = _service(tmp_path)
    assert service.policy_state()["current"] is None
    service.save_policy({"max_issuer_weight": 0.2, "max_sector_weight": 0.5})
    service.save_policy({"max_issuer_weight": 0.1, "max_sector_weight": 0.5})
    assert [row["profile"]["max_issuer_weight"] for row in service.policy_state()["revisions"]] == [0.1, 0.2]
    assert SqliteInvestorProfile(tmp_path).latest() is None  # Another table, another history.
    with pytest.raises(QueryError):
        service.save_policy({"max_issuer_weight": 2, "max_sector_weight": 0.5})


def test_panel_aggregates_share_classes_and_flags_illiquidity(tmp_path):
    positions = [{"symbol": "BRK-A", "currency": "USD", "value_eur": 600.0, "status": "ok"},
                 {"symbol": "BRK-B", "currency": "USD", "value_eur": 400.0, "status": "ok"},
                 {"symbol": "SAP.DE", "currency": "EUR", "value_eur": 1000.0, "status": "ok"},
                 {"symbol": "GONE", "currency": "USD", "value_eur": None, "status": "missing_price"}]
    panel = _service(tmp_path, positions, profile={"profile": {"loss_tolerance": 0.15}}).panel()
    issuers = panel["exposure"]["issuers"]
    assert {row["issuer"]: row["weight"] for row in issuers}["cik:berkshire"] == pytest.approx(0.5)
    assert {row["name"]: row["weight"] for row in panel["exposure"]["economic_currency"]} == {"USD": 0.5,
                                                                                            "EUR": 0.5}
    assert panel["unvalued"] == ["GONE"] and panel["loss_tolerance"] == 0.15
    sap = {row["symbol"]: row for row in panel["exposure"]["liquidity"]}["SAP.DE"]
    assert sap["daily_volume_eur"] is None and sap["illiquid"]  # Outside the universe: no volume data.


def test_proposal_compares_equal_weight_with_the_limits_and_proposes_orders(tmp_path):
    service = _service(tmp_path, profile={"profile": {"commission_fixed_eur": 1.0, "fx_cost_pct": 0.006}})
    service.save_policy({"max_issuer_weight": 0.25, "max_sector_weight": 0.5, "min_daily_dollar_volume": 1e6})
    result = service.proposal(700.0, 6)
    assert {row["symbol"]: row["reason"] for row in result["excluded"]} == {"TINY": "illiquid",
                                                                            "NOPRICE": "no_price"}
    equal, limited = result["alternatives"]
    assert any("cik:berkshire" in text for text in equal["breaches"])  # Two classes: one third in one issuer.
    weights = {row["symbol"]: row["weight"] for row in limited["weights"]}
    assert weights["BRK-A"] + weights["BRK-B"] <= 0.25 + 1e-9 and limited["breaches"] == []
    assert sum(weights.values()) + limited["cash"] == pytest.approx(1.0)
    spent = sum(row["amount_eur"] + row["commission_eur"] + row["fx_cost_eur"] for row in limited["orders"])
    assert spent + limited["residual_cash_eur"] == pytest.approx(700.0)
    with pytest.raises(QueryError) as error:
        _service(tmp_path, rate=None).proposal(700.0)
    assert error.value.code == "benchmark_prices_missing"


def test_api_reads_the_panel_without_writing_and_saves_policy_revisions(tmp_path):
    seed_fixture(tmp_path)
    with closing(sqlite3.connect(tmp_path / "gabi.db")) as db, db:
        db.executemany("INSERT INTO prices(symbol,date,close,adj_close) VALUES('USDEUR=X',?,0.9,0.9)",
                       [(day.date().isoformat(),) for day in pd.bdate_range(end=TODAY, periods=30)])
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        for symbol in ("BRK-A", "BRK-B"):
            assert api.post("/api/v1/portfolio/holdings", json={
                "symbol": symbol, "shares": 1, "price": 100, "purchase_date": "2026-09-01", "currency": "USD",
                "fx_rate": 0.9}).status_code == 201
        stamp = (tmp_path / "gabi.db").stat().st_mtime_ns
        panel = api.get("/api/v1/portfolio/risk")
        assert panel.status_code == 200, panel.text
        issuers = panel.json()["exposure"]["issuers"]
        assert len(issuers) == 1 and issuers[0]["symbols"] == ["BRK-A", "BRK-B"]
        proposal = api.get("/api/v1/portfolio/risk/proposal", params={"contribution_eur": 700})
        assert proposal.status_code == 200, proposal.text
        assert [row["label"] for row in proposal.json()["alternatives"]][0].startswith("Equiponderada")
        assert (tmp_path / "gabi.db").stat().st_mtime_ns == stamp
        assert api.post("/api/v1/portfolio/risk/policy",
                        json={"max_issuer_weight": 0.08, "max_sector_weight": 0.3}).status_code == 201
        state = api.get("/api/v1/portfolio/risk/policy").json()
        assert state["current"]["profile"]["max_issuer_weight"] == 0.08 and state["version"] == "portfolio-policy-v1"
