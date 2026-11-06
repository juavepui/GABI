"""Revenue growth revenue-growth-v1 (#339): the rule, its stored rows and the model that reads them."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime

import pytest

from gabi.application.market import stored_revenue_growth
from gabi.domain.market import revenue_growth as rules
from gabi.domain.market.sec_facts import _extract_raw_facts, compute_edgar_metrics
from gabi.infrastructure.model_versions import ACTIVE_MODEL_ID, GABI_MF_V1, GABI_MF_V3, GABI_MF_V4, active_model
from gabi.infrastructure.storage.sec_xbrl import SqliteXbrl

NOW = datetime(2026, 11, 6, 12, tzinfo=UTC)


def year(y, value, filed=None, end_month_day="12-31"):
    return {"start": f"{y}-01-01", "end": f"{y}-{end_month_day}", "val": value, "form": "10-K", "fp": "FY",
            "fy": y, "accn": f"a-{y}", "filed": filed or f"{y + 1}-02-15"}


def facts(cik=1, **tags):
    return {"cik": cik, "facts": {"us-gaap": {tag: {"units": {"USD": rows}} for tag, rows in tags.items()}}}


def switched_tag():
    """GE-like: a contract-revenue tag until 2018, total `Revenues` from 2020, no year in common."""
    return facts(
        RevenueFromContractWithCustomerExcludingAssessedTax=[year(y, v) for y, v in
                                                            ((2015, 100.0), (2016, 104.0), (2017, 108.0),
                                                             (2018, 112.0))],
        Revenues=[year(y, v) for y, v in ((2020, 50.0), (2021, 55.0), (2022, 60.5), (2023, 66.55))],
        NetIncomeLoss=[year(y, 5.0) for y in range(2015, 2024)],
    )


def test_starts_from_the_tag_with_the_latest_year_where_v1_keeps_an_old_series():
    data = switched_tag()
    row = rules.snapshot(data)
    assert row["state"] == "computed" and row["tag"] == "Revenues"
    assert (row["first_end"], row["last_end"]) == ("2020-12-31", "2023-12-31")
    assert row["revenue_cagr_3y"] == pytest.approx(0.10)
    # V1 is untouched: it still reads the series that stopped in 2018 (the sealed studies use it).
    assert compute_edgar_metrics(data)["revenue_cagr_3y"] == pytest.approx((112 / 100) ** (1 / 3) - 1)


def test_tags_that_reconcile_are_still_joined():
    data = facts(
        Revenues=[year(2020, 50.0), year(2021, 55.0)],
        RevenueFromContractWithCustomerExcludingAssessedTax=[year(2021, 55.0), year(2022, 60.5), year(2023, 66.55)],
        NetIncomeLoss=[year(2023, 1.0)],
    )
    row = rules.snapshot(data)
    assert row["tag"] == "RevenueFromContractWithCustomerExcludingAssessedTax" and row["first_end"] == "2020-12-31"
    assert row["revenue_cagr_3y"] == pytest.approx(0.10)


def test_a_series_behind_the_latest_annual_report_is_stale_not_old_growth():
    # A bank: total revenue reported until 2019, net income until 2025.
    data = facts(Revenues=[year(y, 80.0 + y - 2016) for y in range(2016, 2020)],
                 NetIncomeLoss=[year(y, 10.0) for y in range(2016, 2026)])
    row = rules.snapshot(data)
    assert (row["state"], row["reason"], row["revenue_cagr_3y"]) == (
        "stale", "revenue_behind_latest_annual_report", None)
    assert rules.stored_growth(row) is None
    # A 52/53-week year a few days apart is the same year, not stale.
    close = facts(Revenues=[year(y, 100.0 * 1.1 ** (y - 2020), end_month_day="12-28") for y in range(2020, 2024)],
                  NetIncomeLoss=[year(2023, 1.0, end_month_day="12-31")])
    assert rules.snapshot(close)["state"] == "computed"


def test_absences_say_why():
    assert rules.snapshot(facts(NetIncomeLoss=[year(2024, 1.0)]))["reason"] == "no_annual_revenue"
    short = rules.snapshot(facts(Revenues=[year(2023, 10.0), year(2024, 11.0)]))
    assert (short["state"], short["reason"]) == ("absent", "not_four_consecutive_positive_years")
    assert rules.stored_growth({"rule_version": "revenue-growth-v0", "state": "computed",
                                "revenue_cagr_3y": 0.1}) is None


def seed(path, symbol, cik, data):
    store = SqliteXbrl(path, lambda: NOW)
    store.ensure_entity(cik)
    store.save(symbol, cik, _extract_raw_facts(data, list(data["facts"]["us-gaap"])), {"roic": 0.1})
    return store


def growth_row(path, symbol):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM sec_revenue_growth WHERE symbol=?", (symbol,)).fetchone()
    return dict(row) if row else None


def test_fill_writes_missing_or_outdated_rows_from_local_facts_only(tmp_path):
    path = tmp_path / "gabi.db"
    store = seed(path, "AAA", "1", switched_tag())
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("INSERT INTO edgar_metrics (symbol,cik,fetched_at) VALUES ('NOCIK',NULL,'x')")
    first = stored_revenue_growth.fill(["AAA", "NOCIK", "NOSEC", "AAA"], store=store)
    assert first == {"rule_version": "revenue-growth-v1", "computed": 1, "current": 0, "without_issuer": 2}
    assert growth_row(path, "AAA")["revenue_cagr_3y"] == pytest.approx(0.10)
    assert stored_revenue_growth.fill(["AAA"], store=store)["computed"] == 0
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE sec_revenue_growth SET rule_version='revenue-growth-v0'")
    assert stored_revenue_growth.fill(["AAA"], store=store)["computed"] == 1


def test_fill_on_a_database_without_sec_tables_writes_nothing(tmp_path):
    assert stored_revenue_growth.fill(["AAA"], store=SqliteXbrl(tmp_path / "gabi.db", lambda: NOW))["computed"] == 0
    assert not (tmp_path / "gabi.db").exists()


def test_v4_is_the_active_model_and_differs_from_v3_only_in_the_sec_metrics():
    assert ACTIVE_MODEL_ID == "GABI-MF-v4" and active_model() is GABI_MF_V4
    assert GABI_MF_V4.metrics_version == "sec-metrics-v2.2" and GABI_MF_V3.metrics_version == "sec-metrics-v2.1"
    assert (GABI_MF_V4.weights, GABI_MF_V4.technical, GABI_MF_V4.input_checks) == (
        GABI_MF_V3.weights, GABI_MF_V3.technical, GABI_MF_V3.input_checks)


def test_only_a_v2_2_ranking_reads_the_new_growth(tmp_path):
    from market_fixture import TODAY, seed_fixture

    from gabi.infrastructure.legacy.market import calculators, model_policy
    from gabi.infrastructure.settings import Settings
    from gabi.infrastructure.storage.market import ReadOnlyMarket

    seed_fixture(tmp_path)
    store = SqliteXbrl(tmp_path / "gabi.db", lambda: NOW)
    store.save_revenue_growth("T000", "1", rules.snapshot(switched_tag()))
    store.save_revenue_growth("T001", "1", rules.snapshot(facts(
        Revenues=[year(y, 80.0) for y in range(2016, 2020)], NetIncomeLoss=[year(2025, 1.0)])))
    tables = {}
    for version in ("sec-metrics-v2.1", "sec-metrics-v2.2"):
        market = ReadOnlyMarket(Settings(tmp_path), calculators(GABI_MF_V1.technical), model_policy(GABI_MF_V1),
                                "SPY", 0.04, metrics_version=version)
        try:
            tables[version] = market.ranking(dict(GABI_MF_V1.weights), TODAY).table
        finally:
            market.close()
    old, new = tables["sec-metrics-v2.1"]["revenue_cagr_3y"], tables["sec-metrics-v2.2"]["revenue_cagr_3y"]
    assert old["T000"] != pytest.approx(0.10) and new["T000"] == pytest.approx(0.10)
    # A stale series and an issuer without a row score as missing under V2.2, never with the V1 value.
    assert new[["T001", "T002"]].isna().all() and old[["T001", "T002"]].notna().all()
    assert tables["sec-metrics-v2.2"]["roic"].sort_index().equals(tables["sec-metrics-v2.1"]["roic"].sort_index())
