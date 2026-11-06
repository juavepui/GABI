"""Accounting warning signs of tenk-flags-v1 (#293): hand-computed values, absences and point in time."""

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime

import pytest

from gabi.application.market.company_research import CompanyResearch
from gabi.domain.market import tenk_flags as flags
from gabi.domain.market.sec_reads import companyfacts
from gabi.domain.portfolio import idea_alerts
from gabi.infrastructure.storage.current_reports import SqliteCurrentReports

FY24, FY23 = ("2024-01-01", "2024-12-31"), ("2023-01-01", "2023-12-31")
AS_OF = date(2025, 6, 30)


def flow(value, period, accn="0000000001-25-000010", filed="2025-02-15"):
    return {"start": period[0], "end": period[1], "val": value, "form": "10-K", "fp": "FY", "accn": accn,
            "filed": filed}


def stock(value, end, accn="0000000001-25-000010", filed="2025-02-15"):
    return {"end": end, "val": value, "form": "10-K", "fp": "FY", "accn": accn, "filed": filed}


def facts(**tags):
    return {"facts": {"us-gaap": {tag: {"units": {"shares" if "Shares" in tag else "USD": rows}}
                                  for tag, rows in tags.items()}}}


def by_key(result):
    return {flag["key"]: flag for flag in result["flags"]}


def test_receivables_growing_faster_than_sales_by_hand():
    # Receivables 100 → 130 (+30 %), sales 1 000 → 1 100 (+10 %): gap 20 points > 15.
    data = facts(Revenues=[flow(1000.0, FY23), flow(1100.0, FY24)],
                 AccountsReceivableNetCurrent=[stock(100.0, "2023-12-31"), stock(130.0, "2024-12-31")])
    flag = flags.receivables(data)
    assert flag["status"] == "alerta"
    assert flag["values"]["receivables_growth"] == pytest.approx(0.30)
    assert flag["values"]["revenue_growth"] == pytest.approx(0.10)
    assert flag["values"]["gap"] == pytest.approx(0.20) and flag["threshold"] == 0.15
    assert flag["source"] == {"form": "10-K", "accession": "0000000001-25-000010", "filed_date": "2025-02-15",
                              "period_end": "2024-12-31"}
    # Receivables 100 → 120 (+20 %): gap 10 points, no sign.
    calm = facts(Revenues=[flow(1000.0, FY23), flow(1100.0, FY24)],
                 AccountsReceivableNetCurrent=[stock(100.0, "2023-12-31"), stock(120.0, "2024-12-31")])
    assert flags.receivables(calm)["status"] == "sin_alerta"


def test_accruals_by_hand():
    # (90 − 30) / ((500 + 700) / 2) = 60 / 600 = 0.10 → not above 0.10; with OCF 20 it is 70 / 600 ≈ 0.117.
    base = {"NetIncomeLoss": [flow(90.0, FY24)], "Assets": [stock(500.0, "2023-12-31"), stock(700.0, "2024-12-31")]}
    edge = flags.accruals(facts(**base, NetCashProvidedByUsedInOperatingActivities=[flow(30.0, FY24)]))
    assert edge["status"] == "sin_alerta" and edge["values"]["ratio"] == pytest.approx(0.10)
    high = flags.accruals(facts(**base, NetCashProvidedByUsedInOperatingActivities=[flow(20.0, FY24)]))
    assert high["status"] == "alerta" and high["values"]["ratio"] == pytest.approx(70 / 600)
    assert high["values"]["average_assets"] == pytest.approx(600.0)


def test_dilution_by_hand():
    rows = [flow(100.0, FY23), flow(106.0, FY24)]
    flag = flags.dilution(facts(WeightedAverageNumberOfDilutedSharesOutstanding=rows))
    assert flag["status"] == "alerta" and flag["values"]["growth"] == pytest.approx(0.06)
    rows[1] = flow(104.0, FY24)
    assert flags.dilution(facts(WeightedAverageNumberOfDilutedSharesOutstanding=rows))["status"] == "sin_alerta"


def test_missing_data_is_not_evaluable_never_clear():
    empty = facts()
    for sign in (flags.receivables, flags.accruals, flags.dilution):
        flag = sign(empty)
        assert flag["status"] == "no_evaluable" and flag["reason"]
    # One year only, or two years that are not consecutive, cannot be compared.
    one = facts(WeightedAverageNumberOfDilutedSharesOutstanding=[flow(100.0, FY24)])
    assert flags.dilution(one)["status"] == "no_evaluable"
    gap = facts(WeightedAverageNumberOfDilutedSharesOutstanding=[flow(100.0, ("2021-01-01", "2021-12-31")),
                                                                 flow(150.0, FY24)])
    assert flags.dilution(gap)["status"] == "no_evaluable"
    result = flags.evaluate(empty, None, AS_OF)
    assert result["counts"] == {"alerta": 0, "sin_alerta": 0, "no_evaluable": 7}
    assert result["version"] == "tenk-flags-v1"


def test_only_what_was_filed_by_the_analysis_date_counts():
    # The FY2024 10-K was filed on 2025-02-15: before that date only FY2023 and FY2022 are known.
    rows = [{**flow(100.0, ("2022-01-01", "2022-12-31")), "filed": "2023-02-15", "accn": "a22"},
            {**flow(101.0, FY23), "filed": "2024-02-15", "accn": "a23"},
            {**flow(120.0, FY24), "filed": "2025-02-15", "accn": "a24"}]
    import pandas as pd

    frame = pd.DataFrame([{"tag": "WeightedAverageNumberOfDilutedSharesOutstanding", "unit": "shares",
                           "start_date": row["start"], "end_date": row["end"], "val": row["val"], "form": "10-K",
                           "fp": "FY", "fy": None, "filed_date": row["filed"], "accn": row["accn"]} for row in rows])
    before = flags.dilution(companyfacts(frame, "2025-01-31"))
    after = flags.dilution(companyfacts(frame, "2025-03-31"))
    assert before["status"] == "sin_alerta" and before["values"]["period_end"] == "2023-12-31"
    assert after["status"] == "alerta" and after["source"]["accession"] == "a24"
    # A later 10-K that restates a year replaces the earlier value only once it is filed.
    restated = [*rows, {**flow(110.0, FY23), "filed": "2025-02-15", "accn": "a24"}]
    data = facts(WeightedAverageNumberOfDilutedSharesOutstanding=restated)
    assert flags.dilution(data)["values"]["previous_shares"] == 110.0


def index(rows, forms=("8-K", "8-K/A", "10-K/A", "NT 10-K"), captured="2025-06-01T00:00:00+00:00"):
    return {"cik": "0000000001", "captured_at": captured, "forms": list(forms) if forms else None, "rows": rows}


def row(form, filed, accession, items=""):
    return {"form": form, "filed_date": filed, "accession": accession, "items": items, "report_date": None}


def test_filing_signs_within_the_last_year_and_before_the_date():
    rows = [row("10-K/A", "2025-03-01", "a1"), row("NT 10-K", "2024-03-01", "a2"),
            row("8-K", "2025-01-10", "a3", "4.01,9.01"), row("8-K", "2025-07-15", "a4", "4.02")]
    found = by_key({"flags": flags.filing_flags(index(rows), AS_OF)})
    assert found["amended_10k"]["status"] == "alerta" and found["amended_10k"]["source"]["accession"] == "a1"
    assert found["late_10k"]["status"] == "sin_alerta"  # More than 365 days before.
    assert found["auditor_change"]["status"] == "alerta"
    assert found["restatement"]["status"] == "sin_alerta"  # Filed after the analysis date.


def test_filing_signs_without_an_index_or_with_an_older_capture_are_not_evaluable():
    assert {flag["status"] for flag in flags.filing_flags(None, AS_OF)} == {"no_evaluable"}
    old = by_key({"flags": flags.filing_flags(index([], forms=None), AS_OF)})
    assert old["amended_10k"]["status"] == "no_evaluable" and old["late_10k"]["status"] == "no_evaluable"
    assert old["auditor_change"]["status"] == "sin_alerta"  # 8-Ks were already captured (#292).


def test_storage_keeps_the_annual_forms_and_the_research_reads_them(tmp_path):
    database = tmp_path / "gabi.db"
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE edgar_metrics(symbol TEXT PRIMARY KEY, cik TEXT)")
        db.execute("INSERT INTO edgar_metrics VALUES('ACME','1')")
    recent = {"accessionNumber": ["a1", "a2", "a3"], "filingDate": ["2025-03-01", "2025-02-01", "2025-01-10"],
              "reportDate": ["", "", ""], "form": ["10-K/A", "10-Q", "8-K"], "items": ["", "", "4.01"],
              "primaryDocument": ["x.htm", "y.htm", "z.htm"]}
    store = SqliteCurrentReports(database, lambda: datetime(2025, 6, 1, tzinfo=UTC))
    assert store.save_submissions("1", {"cik": "1", "filings": {"recent": recent}}) == 2
    assert [r["form"] for r in store.for_symbol("ACME")["rows"]] == ["8-K"]  # The ficha's 8-K list is unchanged.
    data = facts(Revenues=[flow(1000.0, FY23), flow(1100.0, FY24)],
                 AccountsReceivableNetCurrent=[stock(100.0, "2023-12-31"), stock(130.0, "2024-12-31")])
    research = CompanyResearch(None, None, None, None, lambda: AS_OF, reports=store.for_symbol,
                               facts=lambda symbol, day: data)
    result = research.accounting_flags("acme")
    found = by_key(result)
    assert found["amended_10k"]["status"] == "alerta" and found["auditor_change"]["status"] == "alerta"
    assert found["late_10k"]["status"] == "sin_alerta" and found["receivables"]["status"] == "alerta"
    assert result["counts"]["alerta"] == 3 and "no dice que haya que vender" in result["note"]


def test_idea_alerts_for_signs_filed_after_the_idea_skip_those_the_8k_alerts_raise():
    result = flags.evaluate(
        facts(Revenues=[flow(1000.0, FY23), flow(1100.0, FY24)],
              AccountsReceivableNetCurrent=[stock(100.0, "2023-12-31"), stock(130.0, "2024-12-31")]),
        index([row("10-K/A", "2025-03-01", "a1"), row("8-K", "2025-03-05", "a3", "4.01")]), AS_OF)
    alerts = idea_alerts.accounting_flags("2025-01-01", result["flags"])
    assert sorted(alert["evidence"]["flag"] for alert in alerts) == ["amended_10k", "receivables"]
    assert all(alert["kind"] == "contable" and "no significa que haya que vender" in alert["message"]
               for alert in alerts)
    assert idea_alerts.accounting_flags("2025-03-02", result["flags"]) == []  # Both filed before the idea.
