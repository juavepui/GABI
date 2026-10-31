"""Issuer risk and the investable portfolio policy (#248) over hand-built inputs; no data files."""

import pytest

from gabi.domain.portfolio import risk_policy as rp

POLICY = rp.Policy(max_issuer_weight=0.10, max_sector_weight=0.30)


def position(symbol, value, *, issuer=None, sector="Tech", currency="USD", economic="USD", volume=1e9,
             scores=None):
    return {"symbol": symbol, "issuer": issuer or symbol, "value_eur": value, "sector": sector,
            "industry": None, "listing_currency": currency, "economic_currency": economic,
            "scores": scores or {}, "daily_volume_eur": volume}


def test_policy_validation_keeps_version_and_rejects_leverage_like_limits():
    policy = rp.validate_policy({"max_issuer_weight": 0.08, "max_sector_weight": 0.25, "cash_weight": 0.05})
    assert policy.version == rp.POLICY_VERSION and rp.stored(policy)["cash_weight"] == 0.05
    for bad in ({"max_issuer_weight": 1.5, "max_sector_weight": 0.3},
                {"max_issuer_weight": 0.1, "max_sector_weight": 0.3, "cash_weight": 1.0},
                {"max_issuer_weight": "x", "max_sector_weight": 0.3}):
        with pytest.raises(ValueError):
            rp.validate_policy(bad)


def test_two_share_classes_are_one_issuer_and_unknown_sector_is_visible():
    rows = [position("BRK-A", 600, issuer="cik:1067983", sector="Financials"),
            position("BRK-B", 600, issuer="cik:1067983", sector="Financials"),
            position("SAP.DE", 400, currency="EUR", economic="EUR", sector=None),
            position("AAA", 400, scores={"value": 80, "quality": 40})]
    result = rp.exposures(rows, POLICY)
    berkshire = result["issuers"][0]
    assert berkshire["symbols"] == ["BRK-A", "BRK-B"] and berkshire["weight"] == pytest.approx(0.6)
    assert berkshire["exceeds"] and any("cik:1067983" in text for text in result["breaches"])
    assert {row["name"] for row in result["sectors"]} == {"Financials", rp.UNKNOWN, "Tech"}
    assert {row["name"]: row["weight"] for row in result["listing_currency"]} == {"USD": 0.8, "EUR": 0.2}
    assert result["factors"]["value"] == {"score": 80, "coverage": 0.2}


def test_liquidity_is_measured_in_days_at_the_participation_rate():
    result = rp.exposures([position("SMALL", 1_000, volume=5_000), position("BIG", 1_000, volume=None)], POLICY)
    rows = {row["symbol"]: row for row in result["liquidity"]}
    assert rows["SMALL"]["days_to_trade"] == pytest.approx(2.0) and rows["SMALL"]["illiquid"]
    assert rows["BIG"]["days_to_trade"] is None and rows["BIG"]["illiquid"]


def test_limits_cap_issuer_and_sector_and_weights_plus_cash_add_up_to_one():
    symbols = ["A1", "A2", "B", "C", "D", "E"]
    issuers = {"A1": "a", "A2": "a"}
    sectors = {"B": "Energy", "C": "Energy", "D": "Energy", "E": None}
    result = rp.apply_limits(symbols, issuers, sectors, rp.Policy(max_issuer_weight=0.2, max_sector_weight=0.4,
                                                                   cash_weight=0.05))
    weights = result["weights"]
    assert weights["A1"] + weights["A2"] <= 0.2 + 1e-9
    assert weights["B"] + weights["C"] + weights["D"] <= 0.4 + 1e-9
    assert sum(weights.values()) + result["cash"] == pytest.approx(1.0)
    assert result["cash"] >= 0.05 - 1e-9 and "A1" in result["capped"]


def test_equal_weights_need_no_cap_when_the_limits_allow_them():
    result = rp.apply_limits([f"S{i}" for i in range(20)], {}, {f"S{i}": f"Sec{i % 5}" for i in range(20)}, POLICY)
    assert list(result["weights"].values()) == pytest.approx([0.05] * 20) and result["cash"] == pytest.approx(0)


def test_orders_fund_the_largest_gaps_and_report_costs_fx_and_residual_cash():
    result = rp.contribution_orders(
        {"A": 0.0, "B": 900.0}, {"A": 0.5, "B": 0.5}, 700.0, {"A": 100.0, "B": 50.0}, {"A": "USD", "B": "EUR"},
        commission_fixed_eur=1.0, commission_pct=0.0, fx_cost_pct=0.006, min_order_eur=0.0, fractional=False,
        max_cost_share=0.05)
    order = result["orders"][0]
    # Future total 1,600: A needs 800, B none; 700 € minus 1 € and 0.6 % FX buys 6 whole shares of A.
    assert [row["symbol"] for row in result["orders"]] == ["A"] and order["shares"] == 6
    assert order["fx_cost_eur"] == pytest.approx(699 * 0.006)
    assert result["residual_cash_eur"] == pytest.approx(700 - 600 - 1 - 699 * 0.006)


def test_small_orders_below_the_minimum_or_too_costly_are_merged_into_larger_ones():
    targets = {"A": 0.4, "B": 0.4, "C": 0.2}
    result = rp.contribution_orders(
        {"A": 0.0, "B": 0.0, "C": 900.0}, targets, 300.0, {"A": 10.0, "B": 10.0, "C": 10.0}, {},
        commission_fixed_eur=2.0, commission_pct=0.0, fx_cost_pct=0.0, min_order_eur=0.0, fractional=True,
        max_cost_share=0.01)
    # Two orders of 150 € would each pay 1.3 %; a single one of 300 € pays 0.7 %.
    assert len(result["orders"]) == 1 and result["orders"][0]["amount_eur"] == pytest.approx(298)
    assert result["unfunded"] == ["B"] or result["unfunded"] == ["A"]
    minimum = rp.contribution_orders({}, {"A": 1.0}, 50.0, {"A": 10.0}, {}, commission_fixed_eur=0,
                                     commission_pct=0, fx_cost_pct=0, min_order_eur=100, fractional=True,
                                     max_cost_share=0.05)
    assert minimum["orders"] == [] and minimum["residual_cash_eur"] == 50 and minimum["unfunded"] == ["A"]


def test_stress_uses_betas_correlation_one_the_euro_and_explains_the_tolerance():
    rows = [{"value_eur": 500, "beta": 1.5, "economic_currency": "USD", "days_to_trade": 0.1},
            {"value_eur": 500, "beta": None, "economic_currency": "EUR", "days_to_trade": 3}]
    result = rp.stress(rows, 0.20)
    scenarios = {row["id"]: row for row in result["scenarios"]}
    assert scenarios["market_beta"]["change"] == pytest.approx(-0.20 * (1.5 + 1.0) / 2)
    assert scenarios["market_correlated"]["change"] == -0.20 and scenarios["market_beta"]["exceeds_tolerance"]
    assert scenarios["euro"]["change"] == pytest.approx(0.5 * (1 / 1.1 - 1))
    assert "umbral de revisión" in result["notes"][0] and "1 posiciones" in result["notes"][1]
