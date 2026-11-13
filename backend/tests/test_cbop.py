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


def test_a_working_capital_line_missing_for_the_anchor_year_is_zero_and_declared():
    never = {key: val for key, val in BASE.items() if key != "IncreaseDecreaseInInventories"}
    value = cbop.cbop(facts(year(never)), SIGNAL, sic=None)
    assert value.metric.state == "computed" and value.imputed == ("d_inventories",)
    assert value.metric.value == pytest.approx(0.11)
    old = year(BASE, end="2022-12-31", filed="2023-02-15", accn="0001-23-1")
    gap = cbop.cbop(facts(old, year(never)), SIGNAL, sic=None)  # Amendment 1: stopped presenting it.
    assert gap.metric.value == pytest.approx(0.11) and gap.imputed == ("d_inventories",)


def test_amendment_one_rebuilds_sga_and_falls_back_to_total_operating_costs():
    split = {key: val for key, val in BASE.items() if key != "SellingGeneralAndAdministrativeExpense"}
    split |= {"SellingAndMarketingExpense": 120.0, "GeneralAndAdministrativeExpense": 80.0}
    assert cbop.cbop(facts(year(split)), SIGNAL, sic=None).metric.value == pytest.approx(0.10)
    utility = {key: val for key, val in BASE.items()
               if key not in {"CostOfRevenue", "SellingGeneralAndAdministrativeExpense"}}
    # Costs and expenses 950 − D&A 100 − R&D 50 = 800 = cost of revenue + SG&A.
    utility |= {"CostsAndExpenses": 950.0, "DepreciationDepletionAndAmortization": 100.0}
    value = cbop.cbop(facts(year(utility)), SIGNAL, sic=4911)
    assert value.metric.value == pytest.approx(0.10) and "total_costs" in value.metric.convention
    no_amortization = {key: val for key, val in utility.items() if key != "DepreciationDepletionAndAmortization"}
    assert cbop.cbop(facts(year(no_amortization)), SIGNAL, sic=None).metric.reason == "cost_of_revenue_absent"


def test_required_lines_financials_and_stale_issuers_are_not_computed():
    no_sga = {key: val for key, val in BASE.items() if key != "SellingGeneralAndAdministrativeExpense"}
    assert cbop.cbop(facts(year(no_sga)), SIGNAL, sic=None).metric.reason == "sga_absent"
    no_revenue = {key: val for key, val in BASE.items() if key != "Revenues"}
    assert cbop.cbop(facts(year(no_revenue)), SIGNAL, sic=None).metric.reason == "revenue_absent"
    assert cbop.cbop(facts(year(BASE)), SIGNAL, sic=6021).metric.state == "not_applicable"
    assert cbop.cbop(facts(year(BASE)), date(2025, 7, 10), sic=None).metric.reason == "annual_report_too_old"
    assert cbop.cbop({"facts": {"us-gaap": {}}}, SIGNAL, sic=None).metric.reason == "no_annual_report"
    renamed = {("SalesRevenueNet" if key == "Revenues" else key): val for key, val in BASE.items()}
    assert cbop.cbop(facts(year(renamed)), SIGNAL, sic=None).metric.value == pytest.approx(0.10)


def test_the_audit_reports_coverage_per_signal_and_closes_below_the_threshold():
    complete = facts(year(BASE))
    stored = {"1": complete, "2": complete, "9": complete, "3": facts(year({"Assets": 10.0}))}
    members = {SIGNAL: {"A": "1", "B": "2", "BANK": "9", "C": "3"}}
    report = cbop_coverage.audit(members, facts=stored.__getitem__, sic=lambda cik: 6021 if cik == "9" else None)
    row = report["signals"][0]
    assert (row["eligible"], row["computed"], row["passes"]) == (3, 2, False)
    assert row["missing_reasons"] == {"revenue_absent": 1} and row["unknown_sic"] == 3
    assert report["decision"] == "close_unfeasible" and report["returns_read"] is False
    assert report["missing_examples"]["2024-07-01"] == ["C:revenue_absent"]
    passing = cbop_coverage.audit({SIGNAL: {"A": "1", "B": "2", "C": "3"}}, facts=stored.__getitem__,
                                  sic=lambda cik: None, threshold=0.6)
    assert passing["passes"] and passing["decision"] == "continue_to_exploratory"


def test_members_map_to_their_accredited_issuer_and_unresolved_ones_count_as_missing():
    intervals = [
        {"symbol": "OLD", "cik": "0000000001", "valid_from": "2016-01-01", "valid_to": "2019-03-01",
         "status": "confirmed_historical_ticker"},
        {"symbol": "OLD", "cik": "0000000002", "valid_from": "2019-03-01", "valid_to": "2026-01-01",
         "status": "corroborated_candidate"},
        {"symbol": "AMB", "cik": "0000000003", "valid_from": "2016-01-01", "valid_to": "2026-01-01",
         "status": "ambiguous"},
    ]
    signals = [date(2018, 7, 2), date(2019, 7, 1)]
    members = cbop_coverage.issuers(signals, lambda day: {"symbols": ["OLD", "AMB", "NEW"]}, intervals)
    assert members[signals[0]] == {"OLD": "0000000001", "AMB": None, "NEW": None}
    assert members[signals[1]]["OLD"] == "0000000002"
    report = cbop_coverage.audit({signals[0]: members[signals[0]]}, facts=lambda cik: facts(year(BASE, end="2017-12-31", filed="2018-02-15")),
                                 sic=lambda cik: None)
    assert report["signals"][0]["missing_reasons"] == {"identity_unresolved": 2}


def test_the_audit_never_reads_the_reserved_period():
    with pytest.raises(QueryError) as error:
        cbop_coverage.issuers([date(2025, 7, 1), date(2026, 7, 1)], lambda day: pytest.fail("read"), [])
    assert error.value.code == "reserved_period"
    with pytest.raises(QueryError):
        cbop_coverage.audit({date(2026, 7, 1): {"A": "1"}}, facts=lambda cik: pytest.fail("read"),
                            sic=lambda cik: None)


def test_the_download_is_resumable_keeps_only_cbop_tags_and_records_absent_issuers(tmp_path):
    from gabi.infrastructure.storage.cbop_facts import SqliteCbopFacts

    store = SqliteCbopFacts(tmp_path / "cbop" / "facts.db")
    payload = facts(year({**BASE, "NetIncomeLoss": 7.0}))

    def companyfacts(cik):
        if cik == "0000000002":
            raise ValueError("SEC EDGAR no tiene datos XBRL estructurados para esta empresa")
        return payload

    calls = []
    result = cbop_coverage.download(["0000000001", "0000000002"], done=set(store.downloaded(cbop_coverage.tags_sha256())), save=store.save,
                                    companyfacts=companyfacts, submissions=lambda cik: calls.append(cik) or {"sic": "3571"},
                                    now=lambda: "2026-11-01T12:00:00+00:00")
    assert result == {"pending": 2, "ok": 1, "absent": 1}
    assert store.downloaded() == {"0000000001": "ok", "0000000002": "absent"} and store.sic("0000000001") == 3571
    stored = store.facts("0000000001")
    assert "NetIncomeLoss" not in stored["facts"]["us-gaap"]
    assert cbop.cbop(stored, SIGNAL, sic=3571).metric.value == pytest.approx(0.10)
    again = cbop_coverage.download(["0000000001", "0000000002", "0000000003"], done=set(store.downloaded()),
                                   save=store.save, companyfacts=companyfacts,
                                   submissions=lambda cik: calls.append(cik) or {}, now=lambda: "x")
    assert again["pending"] == 1 and calls[-1] == "0000000003" and store.sic("0000000003") is None
    assert set(store.downloaded(cbop_coverage.tags_sha256())) == {"0000000001", "0000000002", "0000000003"}
    assert store.downloaded("another tag set") == {}  # A new tag set downloads everything again.
    summary = store.downloaded_summary()
    assert (summary["issuers"], summary["ok"], summary["absent"]) == (3, 2, 1) and len(summary["manifest_sha256"]) == 64


def test_the_sec_sync_stores_the_cbop_tags():
    from gabi.application.market.sec_xbrl import FACT_TAGS

    assert set(cbop.USD_TAGS) <= set(FACT_TAGS)
