"""Descriptive sector and industry concentration of the target portfolio (#180)."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.domain.portfolio.concentration import concentration_warnings, industry_breakdown, sector_breakdown
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def _target(sectors: list[str | None]) -> pd.DataFrame:
    symbols = [f"S{i}" for i in range(len(sectors))]
    return pd.DataFrame({"sector": sectors, "weight_pct": 100 / len(sectors)}, index=symbols)


def test_sector_weights_compare_with_the_universe_capitalisation():
    target = _target(["Financials", "Financials", "Utilities", None])
    universe = pd.DataFrame({"sector": ["Financials", "Utilities", "Information Technology", "Energy"],
                             "market_cap": [100.0, 100.0, 300.0, float("nan")]})
    rows = {row["sector"]: row for row in sector_breakdown(target, universe)}
    assert rows["Financials"] == {"sector": "Financials", "positions": 2, "weight_pct": 50.0,
                                  "index_weight_pct": 20.0, "difference_pp": 30.0}
    assert rows["Information Technology"]["positions"] == 0  # Absent from the target: an underweight.
    assert rows["Information Technology"]["difference_pp"] == -60.0
    assert rows["Sin sector"]["weight_pct"] == 25.0 and rows["Sin sector"]["index_weight_pct"] == 0.0
    assert "Energy" not in rows  # No usable capitalisation and not held.
    assert sum(row["weight_pct"] for row in rows.values()) == pytest.approx(100)
    assert sum(row["index_weight_pct"] for row in rows.values()) == pytest.approx(100)
    assert list(rows)[0] == "Financials"  # Heaviest first.


def test_without_capitalisations_the_index_weight_is_unknown():
    rows = sector_breakdown(_target(["Energy"]), pd.DataFrame({"sector": ["Energy"]}))
    assert rows == [{"sector": "Energy", "positions": 1, "weight_pct": 100.0, "index_weight_pct": None,
                     "difference_pp": None}]


def test_industries_and_warnings_above_each_limit():
    target = _target(["Financials"] * 3 + ["Utilities"] * 2 + ["Energy"] * 15)
    industries = {"S0": "Property & Casualty Insurance", "S1": "Property & Casualty Insurance",
                  "S2": "Property & Casualty Insurance", "S3": "Electric Utilities"}
    held = industry_breakdown(target, industries)
    assert held[0] == {"industry": "Property & Casualty Insurance", "sector": "Financials", "positions": 3,
                       "weight_pct": 15.0}
    assert {row["industry"] for row in held} == {"Property & Casualty Insurance", "Electric Utilities"}
    sectors = sector_breakdown(target, pd.DataFrame())
    warnings = concentration_warnings(sectors, held, sector_limit_pct=25, industry_limit_pct=10)
    assert [(row["kind"], row["name"]) for row in warnings] == [
        ("sector", "Energy"), ("industry", "Property & Casualty Insurance")]
    # Exactly at the limit is not above it.
    assert concentration_warnings(sectors, held, sector_limit_pct=75, industry_limit_pct=15) == []


def test_plan_reports_the_breakdown_without_changing_the_selection(tmp_path):
    seed_fixture(tmp_path)
    universe = pd.read_csv(tmp_path / "sp500_constituents.csv")
    universe["industry"] = ["Application Software" if index % 2 else "Semiconductors" for index in universe.index]
    universe.to_csv(tmp_path / "sp500_constituents.csv", index=False)
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    stamp = (tmp_path / "gabi.db").stat().st_mtime_ns
    with TestClient(app) as api:
        plain = api.post("/api/v1/portfolio/plan", json={"n_positions": 5}).json()
        strict = api.post("/api/v1/portfolio/plan", json={"n_positions": 5, "sector_limit_percent": 100,
                                                          "industry_limit_percent": 100}).json()
        invalid = api.post("/api/v1/portfolio/plan", json={"sector_limit_percent": 0})
    assert [row["symbol"] for row in plain["target"]] == [row["symbol"] for row in strict["target"]]
    industries = dict(zip(universe["symbol"], universe["industry"], strict=True))
    assert all(row["industry"] == industries[row["symbol"]] for row in plain["target"])
    held = pd.Series([row["sector"] for row in plain["target"]]).value_counts()
    sectors = {row["sector"]: row for row in plain["sectors"]}
    for sector, positions in held.items():
        assert sectors[sector]["positions"] == positions
        assert sectors[sector]["weight_percent"] == pytest.approx(100 * positions / 5)
        assert sectors[sector]["difference_points"] == pytest.approx(
            sectors[sector]["weight_percent"] - sectors[sector]["index_weight_percent"])
    assert sum(row["index_weight_percent"] for row in plain["sectors"]) == pytest.approx(100)
    assert sum(row["weight_percent"] for row in plain["industries"]) == pytest.approx(100)
    heaviest = held.index[0]
    assert plain["concentration"][0] == {"kind": "sector", "name": heaviest, "positions": int(held.iloc[0]),
                                         "weight_percent": pytest.approx(100 * held.iloc[0] / 5), "limit_percent": 25}
    assert {row["kind"] for row in plain["concentration"]} == {"sector", "industry"}
    assert (plain["sector_limit_percent"], plain["industry_limit_percent"]) == (25, 15)
    assert strict["concentration"] == []
    assert invalid.status_code == 422
    assert (tmp_path / "gabi.db").stat().st_mtime_ns == stamp
