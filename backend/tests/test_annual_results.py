"""Ingresos, beneficio neto y caja libre por ejercicio (#328, parte B): selection, alignment and the API."""

import hashlib
import sqlite3

from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.domain.market import annual_results as rules
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def fact(start, end, val, filed, form="10-K", fp="FY"):
    return {"start": start, "end": end, "val": val, "form": form, "fp": fp, "filed": filed, "accn": "a-" + filed}


def facts(**tags):
    return {"facts": {"us-gaap": {tag: {"units": {"USD": entries}} for tag, entries in tags.items()}}}


def test_bridges_revenue_tags_that_reconcile_and_reads_a_september_year():
    data = facts(
        SalesRevenueNet=[fact("2021-09-26", "2022-09-24", 100e9, "2022-10-28"),
                         fact("2022-09-25", "2023-09-30", 110e9, "2023-11-03")],
        # The new tag repeats 2023 with the same figure: same concept, so both years join.
        RevenueFromContractWithCustomerExcludingAssessedTax=[
            fact("2022-09-25", "2023-09-30", 110e9, "2024-11-01"),
            fact("2023-10-01", "2024-09-28", 121e9, "2024-11-01"),
            fact("2024-07-01", "2024-09-28", 30e9, "2024-11-01")],  # A quarter inside the 10-K is ignored.
        NetIncomeLoss=[fact("2022-09-25", "2023-09-30", -5e9, "2023-11-03"),
                       fact("2023-10-01", "2024-09-28", 20e9, "2024-11-01")],
        NetCashProvidedByUsedInOperatingActivities=[fact("2023-10-01", "2024-09-28", 30e9, "2024-11-01")],
        # Capital expenditure dated a few days apart still belongs to the same fiscal year.
        PaymentsToAcquirePropertyPlantAndEquipment=[fact("2023-10-01", "2024-09-28", 8e9, "2024-11-01")],
    )
    points = rules.rows(data)
    assert [(p["label"], p["revenue"]) for p in points] == [("sep 2022", 100e9), ("sep 2023", 110e9),
                                                           ("sep 2024", 121e9)]
    last = points[-1]
    assert last["net_income"] == 20e9 and last["free_cash_flow"] == 22e9 and last["filed"] == "2024-11-01"
    assert set(points[0]["missing"]) == {"net_income", "free_cash_flow"}
    text = rules.reading(points, has_facts=True)["text"]
    assert "de 100.000 millones de $ en sep 2022 a 121.000 millones de $ en sep 2024" in text
    assert "un 10,0 % más cada año de media" in text
    assert "Tuvo pérdidas en 1 de 2 ejercicios (sep 2023)" in text
    assert "caja libre positiva) en 1 de 1 ejercicios" in text


def test_tags_that_disagree_are_not_mixed_and_the_gap_is_explained():
    data = facts(
        RevenueFromContractWithCustomerExcludingAssessedTax=[fact("2017-01-01", "2017-12-31", 110e9, "2018-02-20")],
        Revenues=[fact("2023-01-01", "2023-12-31", 35e9, "2024-02-02")],
        NetIncomeLoss=[fact("2017-01-01", "2017-12-31", 1e9, "2018-02-20"),
                       fact("2023-01-01", "2023-12-31", 9e9, "2024-02-02")],
    )
    points = rules.rows(data)
    assert [(p["label"], p["revenue"], p["net_income"]) for p in points] == [("2017", 110e9, 1e9),
                                                                            ("2023", None, 9e9)]
    assert "etiqueta distinta" in points[-1]["missing"]["revenue"]


def test_figures_redone_later_are_shown_but_not_compared():
    data = facts(Revenues=[
        fact("2021-01-01", "2021-12-31", 18e9, "2022-02-01"),
        fact("2022-01-01", "2022-12-31", 12e9, "2023-02-01"),
        fact("2021-01-01", "2021-12-31", 18e9, "2023-02-01"),
        # After selling a business, the next reports give 2022 again, smaller.
        fact("2022-01-01", "2022-12-31", 6e9, "2024-02-01"),
        fact("2023-01-01", "2023-12-31", 7e9, "2024-02-01"),
    ])
    points = rules.rows(data)
    assert [(p["label"], p["revenue"], p["restated"]) for p in points] == [
        ("2021", 18e9, True), ("2022", 6e9, False), ("2023", 7e9, False)]
    reading = rules.reading(points, has_facts=True)
    assert "de 6.000 millones de $ en 2022 a 7.000 millones de $ en 2023" in reading["text"]
    assert reading["values"]["restated"] == ["2021"]


def test_labels_name_the_closing_month_of_52_week_years():
    assert rules.label("2024-12-31") == "2024"
    assert rules.label("2026-07-03") == "jun 2026"
    assert rules.label("2026-01-04") == "2025"
    assert rules.label("2026-01-25") == "ene 2026"


def test_without_reports_it_says_why():
    assert rules.rows(facts()) == []
    assert "todavía no se han descargado" in rules.reading([], has_facts=False)["text"]
    assert "no traen ingresos" in rules.reading([], has_facts=True)["text"]


def test_api_reads_the_stored_reports_without_writing(tmp_path):
    seed_fixture(tmp_path, companies=12)
    db = tmp_path / "gabi.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE IF NOT EXISTS edgar_facts (symbol TEXT, tag TEXT, unit TEXT, start_date TEXT, "
                    "end_date TEXT, val REAL, form TEXT, fp TEXT, fy INTEGER, filed_date TEXT, accn TEXT)")
        con.executemany("INSERT INTO edgar_facts VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
            ("T000", "Revenues", "USD", "2024-01-01", "2024-12-31", 50e6, "10-K", "FY", 2024, "2025-02-01", "x1"),
            ("T000", "Revenues", "USD", "2025-01-01", "2025-12-31", 60e6, "10-K", "FY", 2025, "2026-02-01", "x2"),
        ])
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        body = api.get("/api/v1/companies/T000/annual-results").json()
        empty = api.get("/api/v1/companies/T001/annual-results").json()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert body["currency"] == "USD" and [p["revenue"] for p in body["points"]] == [50e6, 60e6]
    assert body["points"][-1]["filed"] == "2026-02-01" and "un 20,0 % más" in body["reading"]["text"]
    assert empty["points"] == [] and "todavía no se han descargado" in empty["reading"]["text"]
