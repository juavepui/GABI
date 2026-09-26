"""#30: the 7 SEC-based Composite metrics, point in time (2010-2015 and 2016+)."""

import pandas as pd
import pytest

from gabi import edgar, screener_asof


def _annual(tag, values, *, month_day="12-31", filed_lag_year=1, form="10-K"):
    rows = []
    for year, value in values.items():
        rows.append({"start": f"{year - 1}-{month_day}" if month_day != "12-31" else f"{year}-01-01",
                     "end": f"{year}-{month_day}", "val": value, "form": form, "fp": "FY",
                     "filed": f"{year + filed_lag_year}-02-20", "accn": f"{tag}-{year}"})
    return {tag: {"units": {"USD": rows}}}


def _instant(tag, values):
    return {tag: {"units": {"USD": [{"end": end, "val": value, "form": "10-K", "fp": "FY", "filed": filed,
                                     "accn": f"{tag}-{filed}"} for end, value, filed in values]}}}


def _facts(*parts):
    merged = {}
    for part in parts:
        merged.update(part)
    return {"facts": {"us-gaap": merged}}


def test_fiscal_year_ending_in_june_gives_a_three_year_cagr():
    facts = _facts(_annual("Revenues", {2011: 100.0, 2012: 110.0, 2013: 121.0, 2014: 133.1}, month_day="06-30"))
    metrics = edgar.compute_edgar_metrics(facts)
    assert metrics["revenue_cagr_3y"] == pytest.approx(0.10)
    assert metrics["latest_period_end"] == "2014-06-30"
    assert edgar.fundamental_missing_reasons(facts)["revenue_cagr_3y"] is None


def test_three_year_cagr_needs_four_consecutive_positive_annual_values():
    three = _facts(_annual("Revenues", {2012: 100.0, 2013: 110.0, 2014: 121.0}))
    assert edgar.compute_edgar_metrics(three)["revenue_cagr_3y"] is None
    assert edgar.fundamental_missing_reasons(three)["revenue_cagr_3y"] == "fewer_than_4_annual_revenue_values"
    gap = _facts(_annual("Revenues", {2009: 90.0, 2012: 100.0, 2013: 110.0, 2014: 121.0}))
    assert edgar.fundamental_missing_reasons(gap)["revenue_cagr_3y"] == "non_consecutive_fiscal_years"
    negative = _facts(_annual("Revenues", {2011: -5.0, 2012: 100.0, 2013: 110.0, 2014: 121.0}))
    assert edgar.fundamental_missing_reasons(negative)["revenue_cagr_3y"] == "non_positive_start_or_end_value"


def test_balance_restatement_keeps_the_latest_filing_known_at_the_cutoff():
    # The same year-end is reported as current year (2013) and restated as a
    # comparative (2014); rows arrive in arbitrary order in the CIK path.
    restated = _instant("StockholdersEquity", [("2012-12-31", 90.0, "2014-02-20"),
                                               ("2012-12-31", 100.0, "2013-02-20")])
    assert edgar._extract_instant_values(_facts(restated), ["StockholdersEquity"]) == [("2012-12-31", 90.0)]
    known_in_2013 = {"units": {"USD": [row for row in restated["StockholdersEquity"]["units"]["USD"]
                                       if row["filed"] <= "2013-06-30"]}}
    assert edgar._extract_instant_values(_facts({"StockholdersEquity": known_in_2013}),
                                         ["StockholdersEquity"]) == [("2012-12-31", 100.0)]


def test_roic_and_margin_missing_reasons_are_explicit():
    no_debt = _facts(_annual("NetIncomeLoss", {2014: 10.0}), _instant("StockholdersEquity", [("2014-12-31", 50.0,
                                                                                               "2015-02-20")]),
                     _annual("Revenues", {2014: 100.0}))
    reasons = edgar.fundamental_missing_reasons(no_debt)
    assert reasons["roic"] == "no_long_term_debt" and edgar.compute_edgar_metrics(no_debt)["roic"] is None
    assert reasons["operating_margin"] == "no_operating_income"
    negative_capital = _facts(_annual("NetIncomeLoss", {2014: 10.0}),
                              _instant("StockholdersEquity", [("2014-12-31", -80.0, "2015-02-20")]),
                              _instant("LongTermDebt", [("2014-12-31", 30.0, "2015-02-20")]))
    assert edgar.fundamental_missing_reasons(negative_capital)["roic"] == "non_positive_invested_capital"


def test_mixed_fiscal_years_are_current_behaviour_and_documented():
    """Pins today's semantics (see docs/fundamental-metrics.md and #38): each
    component takes its own latest annual value, so a tag that stops being
    reported leaves an older year in the ratio."""
    facts = _facts(_annual("Revenues", {2013: 200.0, 2014: 250.0}),
                   _annual("OperatingIncomeLoss", {2012: 40.0}))
    metrics = edgar.compute_edgar_metrics(facts)
    assert metrics["operating_margin"] == pytest.approx(40.0 / 250.0)


def _classic(monkeypatch, metrics, *, price=10.0, shares=100.0):
    monkeypatch.setattr(edgar, "compute_edgar_metrics_as_of", lambda *a, **k: metrics)
    monkeypatch.setattr(edgar, "get_shares_outstanding_as_of", lambda *a, **k: shares)
    monkeypatch.setattr(edgar, "get_edgar_facts", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(screener_asof.storage, "has_verified_price_as_of", lambda *a, **k: price is not None)
    monkeypatch.setattr(screener_asof.storage, "get_price_as_of", lambda *a, **k: price)
    monkeypatch.setattr(screener_asof.storage, "get_split_factor_since", lambda *a, **k: 1.0)
    monkeypatch.setattr(screener_asof.quality_persistence, "as_of", lambda *a, **k: {})
    return screener_asof._classic_metrics_as_of("AAA", "2017-06-30")


def test_multiples_are_missing_for_non_positive_denominators(monkeypatch):
    result = _classic(monkeypatch, {"latest_net_income": -5.0, "latest_equity": 0.0, "latest_ebitda": -1.0,
                                    "latest_debt": 200.0, "latest_cash": 50.0, "latest_revenue": 100.0})
    assert result["market_cap"] == 1000.0
    assert result["pe"] is None and result["pb"] is None and result["ev_ebitda"] is None


def test_enterprise_value_treats_missing_debt_or_cash_as_zero_today(monkeypatch):
    """Current approximation (documented): EV = market cap + long-term debt -
    cash, with a missing component counted as zero."""
    base = {"latest_net_income": 50.0, "latest_equity": 400.0, "latest_ebitda": 100.0, "latest_revenue": 500.0}
    both = _classic(monkeypatch, {**base, "latest_debt": 200.0, "latest_cash": 50.0})
    assert both["enterprise_value"] == 1150.0 and both["ev_ebitda"] == pytest.approx(11.5)
    no_debt = _classic(monkeypatch, {**base, "latest_debt": None, "latest_cash": 50.0})
    assert no_debt["enterprise_value"] == 950.0
    no_cash = _classic(monkeypatch, {**base, "latest_debt": 200.0, "latest_cash": None})
    assert no_cash["enterprise_value"] == 1200.0
    no_price = _classic(monkeypatch, {**base, "latest_debt": 200.0, "latest_cash": 50.0}, price=None)
    assert no_price["enterprise_value"] is None and no_price["pe"] is None


def test_fiscal_alignment_leaves_stale_components_missing_not_older_or_zero():
    """#38: with alignment every ratio component belongs to the anchor year."""
    facts = _facts(_annual("Revenues", {2013: 200.0, 2014: 250.0}),
                   _annual("OperatingIncomeLoss", {2012: 40.0}),
                   _annual("NetIncomeLoss", {2013: 20.0, 2014: 25.0}),
                   _instant("StockholdersEquity", [("2014-12-31", 100.0, "2015-02-20")]),
                   _instant("LongTermDebt", [("2012-12-31", 80.0, "2013-02-20")]))
    with edgar.fiscal_alignment():
        metrics = edgar.compute_edgar_metrics(facts)
        reasons = edgar.fundamental_missing_reasons(facts)
    assert metrics["fiscal_anchor"] == "2014-12-31"
    assert metrics["operating_margin"] is None and metrics["latest_debt"] is None
    assert metrics["stale_components"] == ["debt", "operating_income"]
    assert metrics["roic"] is None and reasons["roic"] == "stale_component"
    assert reasons["operating_margin"] == "stale_component"
    assert metrics["latest_net_income"] == 25.0 and metrics["latest_equity"] == 100.0
    assert metrics["profit_margin"] == pytest.approx(0.1)
    # Off by default: frozen audits keep today's semantics.
    assert not edgar.fiscal_alignment_enabled()
    assert edgar.compute_edgar_metrics(facts)["operating_margin"] == pytest.approx(40.0 / 250.0)


def test_fiscal_alignment_accepts_the_same_year_and_anchors_on_income_without_revenue():
    june = _facts(_annual("Revenues", {2014: 100.0}, month_day="06-30"),
                  _annual("OperatingIncomeLoss", {2014: 10.0}, month_day="06-30"),
                  _instant("LongTermDebt", [("2014-06-30", 30.0, "2014-08-20")]))
    with edgar.fiscal_alignment():
        metrics = edgar.compute_edgar_metrics(june)
    assert metrics["operating_margin"] == pytest.approx(0.1) and metrics["latest_debt"] == 30.0
    assert metrics["stale_components"] == []
    bank = _facts(_annual("NetIncomeLoss", {2013: 5.0, 2014: 6.0}),
                  _instant("StockholdersEquity", [("2013-12-31", 50.0, "2014-02-20")]))
    with edgar.fiscal_alignment():
        metrics = edgar.compute_edgar_metrics(bank)
        reasons = edgar.fundamental_missing_reasons(bank)
    assert metrics["fiscal_anchor"] == "2014-12-31" and metrics["latest_equity"] is None
    assert reasons["equity"] == "stale_component"


def test_stale_debt_or_cash_leaves_enterprise_value_missing(monkeypatch):
    base = {"latest_net_income": 50.0, "latest_equity": 400.0, "latest_ebitda": 100.0, "latest_revenue": 500.0,
            "latest_debt": None, "latest_cash": 50.0}
    assert _classic(monkeypatch, {**base, "stale_components": ["debt"]})["enterprise_value"] is None
    never_reported = _classic(monkeypatch, {**base, "stale_components": []})
    assert never_reported["enterprise_value"] == 950.0
