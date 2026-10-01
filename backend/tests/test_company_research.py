"""Company research context of the old Ficha: events, surprises, estimates, filing changes and explicit syncs."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi import config, estimates, events_calendar, filing_tracker
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app


def _epoch(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())


@pytest.fixture
def company():
    root = config.DATA_DIR
    seed_fixture(root)
    with closing(sqlite3.connect(root / "gabi.db")) as db:
        info = json.loads(db.execute("SELECT info_json FROM fundamentals WHERE symbol='T001'").fetchone()[0])
        info |= {"earningsTimestampStart": _epoch(date(2026, 10, 27)), "isEarningsDateEstimate": False,
                 "exDividendDate": _epoch(date(2026, 10, 10)), "dividendDate": _epoch(date(2026, 8, 1))}
        db.execute("UPDATE fundamentals SET info_json=? WHERE symbol='T001'", (json.dumps(info),))
        db.commit()
    events_calendar.store_earnings_surprises([
        {"symbol": "T001", "earnings_date": date(2026, 7, 28), "eps_estimate": 1.0, "eps_reported": 1.1,
         "surprise_pct": 10.0, "price_reaction_pct": 2.5},
        {"symbol": "T001", "earnings_date": date(2026, 4, 28), "eps_estimate": 0.9, "eps_reported": 0.8,
         "surprise_pct": -11.1, "price_reaction_pct": None}])
    base = {"symbol": "T001", "period": "0q", "eps_low": 1.0, "eps_high": 1.4, "eps_analysts": 12,
            "revenue_avg": None, "revenue_low": None, "revenue_high": None, "revised_up_7d": 1, "revised_down_7d": 0,
            "revised_up_30d": 3, "revised_down_30d": 1, "source": estimates.SOURCE}
    estimates.store_estimate_snapshot([
        base | {"captured_at": "2026-05-01T09:00:00+00:00", "eps_avg": 1.1, "eps_dispersion_pct": .3},
        base | {"captured_at": "2026-09-20T09:00:00+00:00", "eps_avg": 1.2, "eps_dispersion_pct": .33}])
    with TestClient(create_app(Settings(root), today=lambda: TODAY)) as client:
        yield client, root


def test_overview_matches_the_old_ficha_without_writing(company):
    client, root = company
    before = (root / "gabi.db").read_bytes()
    body = client.get("/api/v1/companies/t001/research").json()
    record = json.loads(sqlite3.connect(root / "gabi.db").execute(
        "SELECT info_json FROM fundamentals WHERE symbol='T001'").fetchone()[0])
    expected = [e for e in events_calendar.parse_corporate_events("T001", record, "2026-09-29T08:00:00+00:00",
                                                                  today=TODAY) if e["days_until"] >= 0]
    assert [(e["event_type"], e["event_date"]) for e in body["events"]] == [
        (e["event_type"], e["event_date"].isoformat()) for e in sorted(expected, key=lambda e: e["event_date"])]
    legacy = events_calendar.get_earnings_surprises("T001")
    assert [row["earnings_date"] for row in body["surprises"]] == legacy["earnings_date"].tolist()
    assert body["surprises"][1]["price_reaction_pct"] is None
    latest = estimates.latest_estimate_snapshot("T001")
    assert body["estimate"]["eps_avg"] == latest["eps_avg"] and body["estimate"]["captured_at"] == latest["captured_at"]
    assert body["revision_90d"] == estimates.revision_since("T001", 90, as_of=TODAY)
    assert (root / "gabi.db").read_bytes() == before
    empty = client.get("/api/v1/companies/T002/research").json()
    assert empty["surprises"] == [] and empty["estimate"] is None and empty["revision_90d"] is None


def test_filing_changes_match_filing_tracker(company):
    client, _ = company
    body = client.get("/api/v1/companies/T001/filing-changes").json()
    for result in body["results"]:
        legacy = filing_tracker.compare_filings("T001", result["form"])
        assert [row["metric"] for row in result["rows"]] == [row["metric"] for row in legacy["rows"]]
        assert result["reason"] is not None or result["rows"]  # An empty comparison always says why.


@pytest.mark.parametrize(("dataset", "target"), [("surprises", "sync_earnings_surprises"),
                                                 ("estimates", "sync_estimates")])
def test_syncs_are_explicit_jobs_with_their_failure_reason(company, monkeypatch, dataset, target):
    client, root = company
    module = events_calendar if dataset == "surprises" else estimates
    calls = []
    monkeypatch.setattr(module, target, lambda symbols: calls.append(symbols) or {"T001": "sin respuesta de Yahoo"})
    job = client.post("/api/v1/jobs", json={"kind": "company_sync", "idempotency_key": f"company-{dataset}-1",
                                             "company": {"symbol": "t001", "dataset": dataset}})
    assert job.status_code == 202, job.text
    assert Worker(SqliteJobs(root), LegacyExecutor(Settings(root)), root).run_once()
    result = client.get(f"/api/v1/jobs/{job.json()['id']}/result").json()
    assert calls == [["T001"]]
    assert result == {"kind": "company_sync", "symbol": "T001", "dataset": dataset, "synced": False,
                      "reason": "sin respuesta de Yahoo"}
    assert client.post("/api/v1/jobs", json={"kind": "company_sync", "idempotency_key": "company-bad-1",
                                             "company": {"symbol": "T001", "dataset": "prices"}}).status_code == 422
