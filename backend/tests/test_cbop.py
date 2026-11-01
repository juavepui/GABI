"""CBOP-v1 data gate (#252): the formula, its point-in-time facts and the coverage audit, without returns."""

from datetime import date

import pytest

from gabi.application.errors import QueryError
from gabi.application.research import cbop_coverage
from gabi.domain.research import cbop


def entry(val, end, filed, start=None, accn="0001-24-1"):
    return {"val": val, "end": end, "start": start, "filed": filed, "form": "10-K", "fp": "FY", "accn": accn}


def year(values: dict, end="2023-12-31", filed="2024-02-15", accn="0001-24-1"):
    start = f"{int(end[:4])}-01-01"
    return {tag: entry(val, end, filed, None if tag == "Assets" else start, accn) for tag, val in values.items()}


def facts(*years: dict) -> dict:
    families: dict = {}
    for values in years:
        for tag, item in values.items():
            families.setdefault(tag, {"units": {"USD": []}})["units"]["USD"].append(item)
    return {"facts": {"us-gaap": families}}


BASE = {"Revenues": 1000.0, "CostOfRevenue": 600.0, "SellingGeneralAndAdministrativeExpense": 200.0,
        "ResearchAndDevelopmentExpense": 50.0, "Assets": 2000.0,
        "IncreaseDecreaseInAccountsReceivable": 30.0, "IncreaseDecreaseInInventories": 20.0,
        "IncreaseDecreaseInPrepaidDeferredExpenseAndOtherAssets": 10.0,
        "IncreaseDecreaseInContractWithCustomerLiability": 5.0, "IncreaseDecreaseInAccountsPayable": 15.0,
        "IncreaseDecreaseInAccruedLiabilities": 40.0}
SIGNAL = date(2024, 7, 1)


def test_cbop_follows_ball_et_al_with_rd_never_subtracted():
    value = cbop.cbop(facts(year(BASE)), SIGNAL, sic=3571)
    # (1000 − 600 − 200) − 30 − 20 − 10 + 5 + 15 + 40 = 200, over 2000 of assets.
    assert value.metric.state == "computed" and value.metric.value == pytest.approx(0.10)
    assert value.anchor == "2023-12-31" and value.imputed == ()
    assert "ResearchAndDevelopmentExpense" in cbop.USD_TAGS
    assert all(fact.tag != "ResearchAndDevelopmentExpense" for fact in value.metric.inputs)


def test_only_facts_filed_before_the_signal_count():
    old = year({**BASE, "Revenues": 900.0}, end="2022-12-31", filed="2023-02-15", accn="0001-23-1")
    new = year(BASE, filed="2024-07-01")  # Filed on the signal day itself: not yet usable.
    value = cbop.cbop(facts(old, new), SIGNAL, sic=None)
    assert value.anchor == "2022-12-31" and value.metric.value == pytest.approx(0.05)
    assert cbop.cbop(facts(old, new), date(2024, 7, 2), sic=None).anchor == "2023-12-31"


def test_a_line_never_reported_is_zero_and_declared_but_a_missing_year_is_not():
    never = {key: val for key, val in BASE.items() if key != "IncreaseDecreaseInInventories"}
    value = cbop.cbop(facts(year(never)), SIGNAL, sic=None)
    assert value.metric.state == "computed" and value.imputed == ("d_inventories",)
    assert value.metric.value == pytest.approx(0.11)
    old = year(BASE, end="2022-12-31", filed="2023-02-15", accn="0001-23-1")
    gap = cbop.cbop(facts(old, year(never)), SIGNAL, sic=None)
    assert gap.metric.value is None and gap.metric.reason == "d_inventories_stale"


def test_required_lines_financials_and_stale_issuers_are_not_computed():
    no_sga = {key: val for key, val in BASE.items() if key != "SellingGeneralAndAdministrativeExpense"}
    assert cbop.cbop(facts(year(no_sga)), SIGNAL, sic=None).metric.reason == "sga_absent"
    assert cbop.cbop(facts(year(BASE)), SIGNAL, sic=6021).metric.state == "not_applicable"
    assert cbop.cbop(facts(year(BASE)), date(2025, 7, 10), sic=None).metric.reason == "annual_report_too_old"
    assert cbop.cbop({"facts": {"us-gaap": {}}}, SIGNAL, sic=None).metric.reason == "no_annual_report"
    renamed = {("SalesRevenueNet" if key == "Revenues" else key): val for key, val in BASE.items()}
    assert cbop.cbop(facts(year(renamed)), SIGNAL, sic=None).metric.value == pytest.approx(0.10)


def test_the_audit_reports_coverage_per_signal_and_closes_below_the_threshold():
    complete = facts(year(BASE))
    members = {"2024-07-01": ["A", "B", "BANK", "C"]}
    stored = {"A": complete, "B": complete, "BANK": complete, "C": facts(year({"Assets": 10.0}))}
    report = cbop_coverage.audit(
        [SIGNAL], membership=lambda day: {"symbols": members[day], "is_exact": True},
        facts=lambda symbol, signal: stored[symbol], sic=lambda symbol, signal: 6021 if symbol == "BANK" else None)
    row = report["signals"][0]
    assert (row["eligible"], row["computed"], row["passes"]) == (3, 2, False)
    assert row["missing_reasons"] == {"revenue_absent": 1} and row["unknown_sic"] == 3
    assert report["decision"] == "close_unfeasible" and report["returns_read"] is False
    assert report["missing_examples"]["2024-07-01"] == ["C"]
    passing = cbop_coverage.audit(
        [SIGNAL], membership=lambda day: {"symbols": ["A", "B", "C"]}, facts=lambda symbol, signal: stored[symbol],
        sic=lambda symbol, signal: None, threshold=0.6)
    assert passing["passes"] and passing["decision"] == "continue_to_exploratory"


def test_the_audit_never_reads_the_reserved_period():
    with pytest.raises(QueryError) as error:
        cbop_coverage.audit([date(2025, 7, 1), date(2026, 7, 1)], membership=lambda day: pytest.fail("read"),
                            facts=lambda *args: pytest.fail("read"), sic=lambda *args: None)
    assert error.value.code == "reserved_period"


def test_the_sec_sync_stores_the_cbop_tags():
    from gabi.application.market.sec_xbrl import FACT_TAGS

    assert set(cbop.USD_TAGS) <= set(FACT_TAGS)
