"""Stored SEC metrics V2 (#245) and the model's metrics version, over temporary databases only."""

import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from gabi.application.administration.sync_events import SyncAttempt
from gabi.application.market import stored_metrics_v2
from gabi.application.market.sec_xbrl import synchronize
from gabi.domain.market import sec_metrics_v2 as v2
from gabi.domain.market.model_version import SEC_METRICS_V1
from gabi.domain.market.sec_facts import _extract_raw_facts
from gabi.infrastructure.legacy.source_errors import fingerprint
from gabi.infrastructure.model_versions import GABI_MF_V1
from gabi.infrastructure.storage.sec_xbrl import SqliteXbrl
from gabi.infrastructure.storage.sync_events import OperationSyncEvents

NOW = datetime(2026, 11, 1, 12, tzinfo=UTC)
FY24, FY23 = ("2024-01-01", "2024-12-31"), ("2023-01-01", "2023-12-31")


def flow(value, period=FY24, accn="0001-24", filed="2025-02-15"):
    return {"start": period[0], "end": period[1], "val": value, "form": "10-K", "fp": "FY", "fy": 2024,
            "accn": accn, "filed": filed}


def stock(value, end="2024-12-31", accn="0001-24", filed="2025-02-15"):
    return {"end": end, "val": value, "form": "10-K", "fp": "FY", "fy": 2024, "accn": accn, "filed": filed}


def companyfacts(cik=1, debt=True, operating=200.0):
    tags = {
        "OperatingIncomeLoss": [flow(operating)],
        "IncomeTaxExpenseBenefit": [flow(45.0)],
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": [flow(180.0)],
        "StockholdersEquity": [stock(900.0, "2023-12-31", "0001-23", "2024-02-15"), stock(1100.0)],
        "CashAndCashEquivalentsAtCarryingValue": [stock(150.0, "2023-12-31", "0001-23", "2024-02-15"),
                                                  stock(200.0)],
    }
    if debt:
        tags["LongTermDebt"] = [stock(450.0, "2023-12-31", "0001-23", "2024-02-15"), stock(420.0)]
    return {"cik": cik, "facts": {"us-gaap": {tag: {"units": {"USD": rows}} for tag, rows in tags.items()}}}


def filings(accn="0001-24"):
    return {"cik": 1, "filings": {"recent": {"form": ["10-K"], "filingDate": ["2025-02-15"],
                                            "accessionNumber": [accn], "primaryDocument": ["doc.htm"]}}}


def stored(path, symbol):
    with closing(sqlite3.connect(path)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM sec_metrics_v2 WHERE symbol=?", (symbol,)).fetchone()
    return dict(row) if row else None


def comparable(row):
    """A stored row as the domain snapshot returns it."""
    return {**{key: value for key, value in row.items() if key not in {"symbol", "cik", "computed_at"}},
            "roic_inputs": json.loads(row["roic_inputs"])}


def seed(path, symbol, cik, facts):
    store = SqliteXbrl(path, lambda: NOW)
    store.ensure_entity(cik)
    rows = _extract_raw_facts(facts, list(facts["facts"]["us-gaap"]))
    store.save(symbol, cik, rows, {"roic": 0.1})
    return store


def test_snapshot_states_absences_and_leaves_the_sector_rule_to_the_reader():
    row = v2.snapshot(companyfacts())
    assert (row["metrics_version"], row["anchor"], row["roic_state"]) == ("sec-metrics-v2", "2024-12-31", "computed")
    # NOPAT = 200 × (1 − 45/180); capital = ((900+450−150) + (1100+420−200)) / 2.
    assert row["roic"] == pytest.approx(150 / 1260)
    assert {item["accession"] for item in row["roic_inputs"]} == {"0001-23", "0001-24"}
    assert (row["total_debt"], row["total_debt_state"], row["cash"]) == (420.0, "reported", 200.0)
    missing = v2.snapshot(companyfacts(debt=False))
    assert (missing["roic"], missing["roic_reason"], missing["total_debt_state"]) == (None, "debt_absent", "absent")
    empty = v2.snapshot({"facts": {"us-gaap": {}}})
    assert (empty["anchor"], empty["roic_reason"]) == (None, "no_annual_report")
    assert v2.stored_roic(row, sector="Financials") is None and v2.stored_roic(row, sector="Real Estate") is None
    assert v2.stored_roic(row, sector="Industrials") == row["roic"]
    assert v2.stored_roic({**row, "metrics_version": "sec-metrics-v1"}, sector=None) is None
    assert v2.stored_roic(missing, sector=None) is None and v2.stored_roic(None, sector=None) is None


def test_stored_facts_give_the_same_row_as_the_downloaded_companyfacts(tmp_path):
    path = tmp_path / "gabi.db"
    store = seed(path, "AAA", "1", companyfacts())
    row = stored_metrics_v2.refresh(store, "AAA", "1")
    assert row == v2.snapshot(companyfacts())
    assert comparable(stored(path, "AAA")) == row


def test_the_sync_recomputes_v2_only_when_facts_change(tmp_path):
    path = tmp_path / "gabi.db"
    store, events = SqliteXbrl(path, lambda: NOW), OperationSyncEvents(path)
    source = {"facts": companyfacts()}

    def run():
        def attempt(provider, entity, dataset):
            return SyncAttempt(provider, entity, dataset, events, now=lambda: NOW,
                               wall_time=lambda: 1., cpu_time=lambda: 1.)
        return synchronize("AAA", "1", store=store, submissions=lambda cik: filings(),
                           companyfacts=lambda cik: source["facts"], checkpoint=events.get,
                           attempt_factory=attempt, retry=lambda call, attempt: call(),
                           fingerprint=fingerprint, now=lambda: NOW, full_refresh=True)

    run()
    assert comparable(stored(path, "AAA")) == v2.snapshot(companyfacts())
    source["facts"] = companyfacts(operating=260.0)
    run()
    assert stored(path, "AAA")["roic"] == pytest.approx(260 * .75 / 1260)


def test_fill_writes_missing_or_outdated_rows_from_local_facts_only(tmp_path):
    path = tmp_path / "gabi.db"
    store = seed(path, "AAA", "1", companyfacts())
    seed(path, "BBB", "2", companyfacts(cik=2, debt=False))
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("INSERT INTO edgar_metrics (symbol,cik,fetched_at) VALUES ('NOCIK',NULL,'x')")
    progress = []
    first = stored_metrics_v2.fill(["AAA", "BBB", "NOCIK", "NOSEC", "AAA"], store=store,
                                   progress=lambda done, total: progress.append((done, total)))
    assert first == {"metrics_version": "sec-metrics-v2", "computed": 2, "current": 0, "without_issuer": 2}
    assert progress == [(2, 2)] and stored(path, "BBB")["roic_reason"] == "debt_absent"
    assert stored_metrics_v2.fill(["AAA", "BBB"], store=store)["computed"] == 0
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE sec_metrics_v2 SET metrics_version='sec-metrics-v0' WHERE symbol='AAA'")
    assert stored_metrics_v2.fill(["AAA", "BBB"], store=store) == {
        "metrics_version": "sec-metrics-v2", "computed": 1, "current": 1, "without_issuer": 0}


def test_fill_on_a_database_without_sec_tables_writes_nothing(tmp_path):
    assert stored_metrics_v2.fill(["AAA"], store=SqliteXbrl(tmp_path / "gabi.db", lambda: NOW))["computed"] == 0
    assert not (tmp_path / "gabi.db").exists()


def test_model_versions_declare_their_sec_metrics():
    assert GABI_MF_V1.metrics_version == SEC_METRICS_V1
    new = replace(GABI_MF_V1, model_id="GABI-MF-v2", label="V2", sealed_hypothesis=False,
                  metrics_version=v2.VERSION)
    assert new.metrics_version == "sec-metrics-v2"
    with pytest.raises(ValueError, match="Unknown SEC metrics"):
        replace(new, metrics_version="sec-metrics-v9")
    with pytest.raises(ValueError, match="sealed hypothesis"):
        replace(GABI_MF_V1, metrics_version=v2.VERSION)


def _market(root, metrics_version=None):
    from gabi.infrastructure.legacy.market import calculators, model_policy
    from gabi.infrastructure.settings import Settings
    from gabi.infrastructure.storage.market import ReadOnlyMarket

    options = {} if metrics_version is None else {"metrics_version": metrics_version}
    return ReadOnlyMarket(Settings(root), calculators(GABI_MF_V1.technical), model_policy(GABI_MF_V1),
                          GABI_MF_V1.benchmark_symbol, GABI_MF_V1.risk_free_rate, **options)


def test_the_ranking_reads_the_roic_of_its_model_metrics_version(tmp_path):
    from market_fixture import TODAY, seed_fixture

    seed_fixture(tmp_path)
    store = SqliteXbrl(tmp_path / "gabi.db", lambda: NOW)
    row = v2.snapshot(companyfacts())
    store.save_metrics_v2("T000", "1", row)
    store.save_metrics_v2("T001", "1", v2.snapshot(companyfacts(debt=False)))
    store.save_metrics_v2("BRK-A", "1", row)
    weights = dict(GABI_MF_V1.weights)
    tables = {}
    for label, version in (("default", None), ("v1", SEC_METRICS_V1), ("v2", v2.VERSION)):
        market = _market(tmp_path, version)
        try:
            tables[label] = market.ranking(weights, TODAY).table
        finally:
            market.close()
    assert tables["v1"].equals(tables["default"])
    assert tables["v1"].loc["T000", "roic"] == pytest.approx(.10)
    roic = tables["v2"]["roic"]
    assert roic["T000"] == pytest.approx(row["roic"])
    # Absent V2, a missing row and a financial sector leave the ROIC missing, never the V1 value.
    assert roic[["T001", "T002", "BRK-A"]].isna().all()
    assert tables["v2"]["revenue_cagr_3y"].sort_index().equals(tables["v1"]["revenue_cagr_3y"].sort_index())
    with pytest.raises(ValueError, match="Unknown SEC metrics"):
        _market(tmp_path, "sec-metrics-v9")
