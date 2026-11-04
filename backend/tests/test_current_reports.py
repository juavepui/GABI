"""8-K current reports by SEC Item, without AI (#292): rules over real SEC rows, storage, the job and alerts."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gabi.application.administration.jobs import JobCommand
from gabi.application.market.company_research import CompanyResearch
from gabi.application.market.sec_xbrl import synchronize
from gabi.domain.market import current_reports as rules
from gabi.domain.portfolio import idea_alerts
from gabi.infrastructure.storage.current_reports import SqliteCurrentReports

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "sec_8k_submissions.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 11, 4, 9, tzinfo=UTC)


def codes(report: dict) -> list[tuple[str, str]]:
    return [(item["code"], item["category"]) for item in report["items"]]


def test_an_8k_with_several_items_keeps_each_one_in_the_sec_order():
    rows = rules.from_submissions(FIXTURE["SMCI"])
    # The 10-Q row is ignored; the 8-Ks come newest first.
    assert [row["accession"] for row in rows][:2] == ["0001375365-25-000007", "0001375365-24-000045"]
    assert all(row["form"] == "8-K" for row in rows) and len(rows) == 6
    loan = rules.describe(next(row for row in rows if row["accession"] == "0001375365-24-000042"), "1375365")
    assert codes(loan) == [("1.01", "contratos"), ("2.03", "deuda"), ("3.01", "exclusion_bolsa"),
                           ("9.01", "anexos")]
    assert loan["review"] is True  # 3.01: notice of delisting.
    assert loan["url"] == "https://www.sec.gov/Archives/edgar/data/1375365/000137536524000042/smci-20241114.htm"


def test_review_items_auditor_change_and_routine_results():
    smci = [rules.describe(row, "1375365") for row in rules.from_submissions(FIXTURE["SMCI"])]
    auditor = next(report for report in smci if report["accession"] == "0001375365-24-000036")
    assert codes(auditor)[0] == ("4.01", "auditor") and auditor["review"] is True
    apple = {row["accession"]: rules.describe(row, "320193") for row in rules.from_submissions(FIXTURE["AAPL"])}
    results = apple["0000320193-25-000055"]
    assert codes(results) == [("2.02", "resultados"), ("9.01", "anexos")] and results["review"] is False
    assert codes(apple["0001140361-25-005876"]) == [("5.07", "votaciones")]
    assert codes(apple["0001140361-25-000228"]) == [("5.02", "directivos")]
    assert apple["0001140361-25-000228"]["report_date"] == "2024-12-30"


def test_an_amendment_is_marked_and_classified_like_the_original():
    (row,) = rules.from_submissions(FIXTURE["MSFT"])
    report = rules.describe(row, "789019")
    assert report["form"] == "8-K/A" and report["amendment"] is True
    assert codes(report) == [("1.05", "ciberseguridad"), ("7.01", "comunicacion"), ("9.01", "anexos")]


@pytest.mark.parametrize("code", ["5", "2.99", "4.1", "abc", "10.01"])
def test_an_unknown_item_is_unclassified_never_guessed(code):
    item = rules.classify(code)
    assert item["category"] == "sin_clasificar" and item["review"] is False
    assert code in item["label"]


def test_items_are_split_trimmed_and_deduplicated():
    assert rules.parse_items(" 2.02, 9.01,,2.02 ") == ["2.02", "9.01"]
    assert rules.parse_items(None) == [] and rules.parse_items("") == []
    assert rules.filing_url("1", "0000000001-26-000001", None).endswith("/0000000001-26-000001-index.htm")


def test_every_item_maps_to_a_labelled_category_and_review_items_are_the_issue_ones():
    assert set(rules.ITEMS.values()) <= set(rules.CATEGORIES)
    assert rules.REVIEW_ITEMS == ("1.03", "3.01", "4.01", "4.02")
    assert rules.VERSION == "8k-items-v1"


def seed_metrics(path: Path, symbol: str, cik: str) -> None:
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS edgar_metrics(symbol TEXT PRIMARY KEY, cik TEXT)")
        db.execute("INSERT INTO edgar_metrics VALUES(?,?)", (symbol, cik))


def test_storage_is_idempotent_and_reads_never_create_the_table(tmp_path):
    database = tmp_path / "gabi.db"
    store = SqliteCurrentReports(database, lambda: NOW)
    assert store.for_symbol("SMCI") == {"cik": None, "captured_at": None, "rows": []}
    assert not database.exists()  # A read on a missing database creates nothing.
    seed_metrics(database, "SMCI", "1375365")
    assert store.for_symbol("SMCI")["cik"] == "0001375365"
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT name FROM sqlite_schema WHERE name='sec_current_reports'").fetchone() is None
    assert store.save_submissions("1375365", FIXTURE["SMCI"]) == 6
    assert store.save_submissions("1375365", FIXTURE["SMCI"]) == 0
    stored = store.for_symbol("smci")
    assert len(stored["rows"]) == 6 and stored["captured_at"] == NOW.isoformat()


def test_the_company_research_lists_classified_reports(tmp_path):
    database = tmp_path / "gabi.db"
    seed_metrics(database, "SMCI", "1375365")
    SqliteCurrentReports(database, lambda: NOW).save_submissions("1375365", FIXTURE["SMCI"])
    research = CompanyResearch(None, None, None, None, None, reports=SqliteCurrentReports(database).for_symbol)
    listing = research.current_reports("SMCI")
    assert listing["version"] == "8k-items-v1" and listing["total"] == 6
    assert listing["reports"][0]["filed_date"] == "2025-02-26"
    assert [item["code"] for item in listing["review_items"]] == ["1.03", "3.01", "4.01", "4.02"]
    assert CompanyResearch(None, None, None, None, None).current_reports("SMCI")["reports"] == []


def test_the_sec_sync_stores_the_8ks_it_already_downloaded():
    saved, calls = [], []

    class Stop(Exception):
        pass

    class Attempt:
        calls, dataset = 0, "facts:SMCI"

        def payload(self, value):
            pass

        def finish(self, status, **options):
            return {"status": status}

    class Store:
        def ensure_entity(self, cik):
            return "cik:" + cik

        def has_facts(self, entity):
            raise Stop  # Stop right after the filings step: only the 8-K hook matters here.

    def submissions(cik):
        calls.append(cik)
        return FIXTURE["SMCI"]

    with pytest.raises(Stop):
        synchronize("SMCI", "1375365", store=Store(), submissions=submissions, companyfacts=lambda cik: {},
                    checkpoint=lambda *args: {}, attempt_factory=lambda *args: Attempt(),
                    retry=lambda operation, attempt: operation(), fingerprint=lambda value: "h", now=lambda: NOW,
                    current_reports=lambda cik, payload: saved.append((cik, len(rules.from_submissions(payload)))))
    assert saved == [("1375365", 6)] and calls == ["1375365"]  # No extra request.


def test_the_company_job_downloads_the_index_of_the_stored_cik(tmp_path):
    from gabi.infrastructure.legacy.company import sync_current_reports

    database = tmp_path / "gabi.db"
    assert "datos SEC" in sync_current_reports(tmp_path, "SMCI", submissions=lambda cik: pytest.fail("no CIK"))["SMCI"]
    seed_metrics(database, "SMCI", "1375365")
    asked = []
    assert sync_current_reports(tmp_path, "SMCI", submissions=lambda cik: asked.append(cik) or FIXTURE["SMCI"]) == {}
    assert asked == ["1375365"] and len(SqliteCurrentReports(database).for_symbol("SMCI")["rows"]) == 6
    other = {**FIXTURE["AAPL"], "cik": "320193"}
    assert "otro emisor" in sync_current_reports(tmp_path, "SMCI", submissions=lambda cik: other)["SMCI"]
    JobCommand("company_sync", company={"symbol": "SMCI", "dataset": "current_reports"})


def test_review_items_after_publication_become_review_alerts_only():
    reports = [rules.describe(row, "1375365") for row in rules.from_submissions(FIXTURE["SMCI"])]
    alerts = idea_alerts.current_reports("2024-11-01", reports)
    # After 2024-11-01: three 3.01 notices and one 4.01; the 4.01 of 2024-10-30 is older than the idea.
    assert sorted((alert["evidence"]["filed"], alert["evidence"]["item"]) for alert in alerts) == [
        ("2024-11-18", "4.01"), ("2024-11-20", "3.01"), ("2024-12-06", "3.01"), ("2025-02-26", "3.01")]
    assert all(alert["kind"] == "8k" and "no es una orden" in alert["message"] for alert in alerts)
    assert len({alert["key"] for alert in alerts}) == len(alerts)
    apple = [rules.describe(row, "320193") for row in rules.from_submissions(FIXTURE["AAPL"])]
    assert idea_alerts.current_reports("2024-01-01", apple) == []  # Results, votes and officers: no alert.
