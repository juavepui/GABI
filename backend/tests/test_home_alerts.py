"""«Qué requiere tu atención» (#183): each alert from stored data, without recomputing or writing."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture
from ranking_fixture import RankingFixture

from gabi.domain.portfolio import alerts as rules
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.holdings import SqliteHoldings
from gabi_api.bootstrap import create_app


def _epoch(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, 12, tzinfo=UTC).timestamp())


def test_results_within_the_week_are_grouped_by_scope():
    earnings = {"A": ("2026-09-30", True), "B": ("2026-10-06", False), "C": ("2026-10-07", False),
                "D": ("2026-09-28", False)}
    [alert] = rules.upcoming_earnings(earnings, ["A", "B", "C", "D", "Z"], scope="target", today=TODAY,
                                      link="/eventos")
    assert alert["symbols"] == ["A", "B"] and alert["date"] == "2026-09-30"  # C is 8 days away, D has passed.
    assert alert["detail"] == {"scope": "target", "dates": {"A": "2026-09-30", "B": "2026-10-06"},
                               "estimated": ["A"]}
    assert rules.upcoming_earnings({}, ["A"], scope="target", today=TODAY, link="/") == []


def test_dividends_entries_exits_filings_jobs_and_theses():
    events = [{"symbol": "A", "event_type": "ex_dividend", "event_date": date(2026, 10, 1)},
              {"symbol": "B", "event_type": "ex_dividend", "event_date": date(2026, 10, 1)},
              {"symbol": "A", "event_type": "dividend_payment", "event_date": date(2026, 11, 1)}]
    [dividend] = rules.upcoming_dividends(events, ["A", "B"], today=TODAY)
    assert (dividend["kind"], dividend["symbols"], dividend["date"]) == ("ex_dividend", ["A", "B"], "2026-10-01")
    [change] = rules.top_changes(["A", "HST"], ["A", "BF-B"], "2026-09-17", "Hipótesis")
    assert change["detail"] == {"entered": ["HST"], "exited": ["BF-B"], "snapshot": "Hipótesis"}
    assert rules.top_changes(["A"], ["A"], "2026-09-17", "x") == []
    filings = [{"symbol": "A", "event_type": "filing_revenue_down", "detected_at": "2026-09-25T10:00:00"},
               {"symbol": "B", "event_type": "filing_margin_up", "detected_at": "2026-09-01T10:00:00"},
               {"symbol": "C", "event_type": "rank_change", "detected_at": "2026-09-28T10:00:00"}]
    [filing] = rules.filing_changes(filings, ["A"], today=TODAY)
    assert filing["symbols"] == ["A"] and filing["detail"] == {"held": ["A"]} and filing["severity"] == "high"
    jobs = [{"kind": "data_update", "status": "failed", "finished_at": "2026-09-28T09:00:00", "error_code": "key"},
            {"kind": "data_update", "status": "failed", "finished_at": "2026-09-27T09:00:00"},
            {"kind": "quality", "status": "succeeded", "finished_at": "2026-09-27T08:00:00"},
            {"kind": "quality", "status": "failed", "finished_at": "2026-09-26T08:00:00"},
            {"kind": "refresh", "status": "failed", "finished_at": "2026-09-01T08:00:00"}]
    [job] = rules.failed_jobs(jobs, today=TODAY)  # One per kind; solved and old failures are left out.
    assert job["date"] == "2026-09-28" and job["detail"]["error_code"] == "key"
    # An unknown code reads as unclassified; the alert shows the category, never the raw code (#179).
    assert job["detail"]["failure"] == "Causa no clasificada"
    theses = [{"id": 1, "symbol": "A", "horizon": "Corto (<6 meses)", "created_at": "2026-03-15T10:00:00",
               "status": "abierta"},
              {"id": 2, "symbol": "B", "horizon": "Medio (6-12 meses)", "created_at": "2026-03-15T10:00:00",
               "status": "abierta"},
              {"id": 3, "symbol": "C", "horizon": "Largo (>12 meses)", "created_at": "2024-08-31T10:00:00",
               "status": "abierta"},
              {"id": 4, "symbol": "D", "horizon": "Corto (<6 meses)", "created_at": "2025-01-01T10:00:00",
               "status": "revisada"}]
    due = {alert["symbols"][0]: alert["date"] for alert in rules.overdue_theses(theses, today=TODAY)}
    assert due == {"A": "2026-09-15", "C": "2026-08-31"}  # The long one, at its second anniversary.
    ordered = rules.ordered([dividend, change, filing, job])
    assert [alert["severity"] for alert in ordered] == ["high", "high", "medium", "info"]


def test_home_shows_every_alert_from_stored_data_without_writing(tmp_path):
    seed_fixture(tmp_path, companies=30)
    evaluation = RankingFixture(tmp_path, TODAY)
    saved = pd.DataFrame({"composite_score": [80.0, 70.0], "score_coverage": [.9, .9], "confidence": [90.0, 80.0],
                          "sector": ["X", "Y"]}, index=["T000", "GO.NE"])
    evaluation.save_snapshot(saved, (TODAY - timedelta(days=12)).isoformat(), top_n=2, name="Foto anterior")
    with closing(sqlite3.connect(tmp_path / "gabi.db")) as db, db:
        for symbol, raw in db.execute("SELECT symbol,info_json FROM fundamentals").fetchall():
            info = json.loads(raw) | {"earningsTimestampStart": _epoch(TODAY + timedelta(days=2)),
                                      "isEarningsDateEstimate": False,
                                      "exDividendDate": _epoch(TODAY + timedelta(days=4))}
            db.execute("UPDATE fundamentals SET info_json=? WHERE symbol=?", (json.dumps(info), symbol))
        db.execute("CREATE TABLE signal_events(id INTEGER PRIMARY KEY, detected_at TEXT, from_snapshot_id INTEGER, "
                   "to_snapshot_id INTEGER, symbol TEXT, event_type TEXT, severity TEXT, previous_value TEXT, "
                   "new_value TEXT, cause TEXT)")
        db.execute("INSERT INTO signal_events VALUES(1,'2026-09-27T10:00:00',0,0,'T001','filing_revenue_down',"
                   "'MATERIAL',NULL,NULL,'Ingresos')")
        db.execute("CREATE TABLE journal_entries(id INTEGER PRIMARY KEY, symbol TEXT, created_at TEXT, horizon TEXT, "
                   "status TEXT)")
        db.execute("INSERT INTO journal_entries VALUES(1,'T002','2026-01-10T10:00:00','Corto (<6 meses)','abierta')")
    SqliteHoldings(tmp_path).add([{"symbol": "T029", "shares": 1, "price": 1, "purchase_date": "2026-06-01",
                                   "currency": "USD", "commission": 0, "fx_rate": None, "note": None}], "now")
    app = create_app(Settings(tmp_path), today=lambda: TODAY)
    with TestClient(app) as client:
        app.state.jobs.list = lambda: [{"kind": "data_update", "status": "failed", "error_code": "source_failed",
                                        "finished_at": "2026-09-28T09:00:00", "failures_total": 2}]
        before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in tmp_path.iterdir()
                  if path.is_file()}
        cold = client.get("/api/v1/home").json()  # Without a cached ranking: only what needs no ranking.
        body = client.get("/api/v1/home", params={"compute": "true"}).json()
        after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in tmp_path.iterdir()
                 if path.is_file()}
    assert {alert["kind"] for alert in cold["alerts"]} == {"job_failed", "filings", "thesis_review"}
    kinds = {alert["kind"]: alert for alert in body["alerts"]}
    assert set(kinds) == {"job_failed", "filings", "thesis_review", "earnings", "ex_dividend", "top_changes"}
    target = [row["symbol"] for row in body["target"]]
    earnings = [alert for alert in body["alerts"] if alert["kind"] == "earnings"]
    assert {alert["detail"]["scope"]: alert["symbols"] for alert in earnings} == {"target": sorted(target),
                                                                                    "holdings": ["T029"]}
    assert kinds["ex_dividend"]["symbols"] == sorted({*target, "T029"})
    assert kinds["top_changes"]["detail"]["exited"] == ["GO-NE"]  # Dotted classes, dash spelling.
    assert kinds["top_changes"]["detail"]["entered"] == [symbol for symbol in target if symbol != "T000"]
    assert kinds["thesis_review"]["date"] == "2026-07-10" and kinds["filings"]["symbols"] == ["T001"]
    assert [alert["severity"] for alert in body["alerts"]][:2] == ["high", "high"]
    assert after == before
