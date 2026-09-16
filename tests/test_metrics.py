import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import metrics


def test_compute_fundamental_metrics_basic():
    record = {
        "info": {
            "trailingPE": 25.5, "pegRatio": 1.8, "priceToBook": 6.2,
            "priceToSalesTrailing12Months": 4.1, "enterpriseToEbitda": 15.0,
            "returnOnEquity": 0.28, "returnOnAssets": 0.12,
            "operatingMargins": 0.22, "grossMargins": 0.45, "profitMargins": 0.18,
            "debtToEquity": 55.0, "currentRatio": 1.6,
            "revenueGrowth": 0.09, "earningsGrowth": 0.12,
            "freeCashflow": 1_000_000_000, "marketCap": 50_000_000_000,
            "beta": 1.1, "sector": "Technology", "shortName": "Acme Corp",
        },
        "quarterly_income": {},
    }
    m = metrics.compute_fundamental_metrics(record)
    assert m["pe"] == 25.5
    assert m["roe"] == 0.28
    assert m["sector"] == "Technology"
    assert m["name"] == "Acme Corp"
    assert m["market_cap"] == 50_000_000_000


def test_negative_pe_becomes_none():
    record = {"info": {"trailingPE": -12.0, "pegRatio": -0.5, "enterpriseToEbitda": 0}, "quarterly_income": {}}
    m = metrics.compute_fundamental_metrics(record)
    assert m["pe"] is None
    assert m["peg"] is None
    assert m["ev_ebitda"] is None


def test_empty_record_returns_empty_dict():
    assert metrics.compute_fundamental_metrics(None) == {}
    assert metrics.compute_fundamental_metrics({}) == {}


def test_revenue_growth_from_quarterly_needs_8_quarters():
    # Solo 4 trimestres disponibles -> no se puede calcular crecimiento interanual TTM.
    qi = {f"2024-0{i}-01": {"Total Revenue": 100 + i} for i in range(1, 5)}
    record = {"info": {}, "quarterly_income": qi}
    m = metrics.compute_fundamental_metrics(record)
    assert m["revenue_growth_ttm_yoy"] is None


def test_revenue_growth_from_quarterly_with_enough_data():
    dates = [f"2023-{q:02d}-01" for q in (1, 4, 7, 10)] + [f"2024-{q:02d}-01" for q in (1, 4, 7, 10)]
    values = [100, 100, 100, 100, 110, 110, 110, 110]  # TTM pasa de 400 a 440 -> +10%
    qi = {d: {"Total Revenue": v} for d, v in zip(dates, values)}
    record = {"info": {}, "quarterly_income": qi}
    m = metrics.compute_fundamental_metrics(record)
    assert m["revenue_growth_ttm_yoy"] is not None
    assert round(m["revenue_growth_ttm_yoy"], 3) == 0.1
