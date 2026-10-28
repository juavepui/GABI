"""Non-frozen SEC readers see the whole issuer history, whichever alias stored it (#201)."""

from datetime import UTC, datetime

import pytest

from gabi.application.errors import QueryError
from gabi.domain.market import filings
from gabi.infrastructure.storage.sec_reads import SqliteSecReads
from gabi.infrastructure.storage.sec_selection import SqliteSecSelection
from gabi.infrastructure.storage.sec_xbrl import SqliteXbrl
from gabi.infrastructure.storage.signals import SqliteSignals

CIK = "0000000042"


def _now():
    return datetime(2026, 1, 1, tzinfo=UTC)


def _row(accn, year, value, *, tag="Revenues", form="10-K"):
    return {"tag": tag, "unit": "USD", "start_date": f"{year}-01-01", "end_date": f"{year}-12-31", "val": value,
            "form": form, "fp": "FY", "fy": year, "filed_date": f"{year + 1}-02-15", "accn": accn}


def _split_history(path, new_rows):
    """OLD stored the history; the sync wrote under NEW only the rows the entity did not know (PSKY → SKYD)."""
    store = SqliteXbrl(path, _now)
    store.ensure_entity(CIK)
    quarter = _row("q1", 2023, 3.0, form="10-Q") | {"end_date": "2023-06-30", "filed_date": "2023-08-01"}
    store.save("OLD", CIK, [_row("a1", 2022, 10.0), _row("a2", 2023, 11.0), quarter], {})
    store.save("NEW", CIK, new_rows, {})
    store.save("BARE", "0000000077", [], {})  # stored CIK, no facts anywhere


def test_filing_facts_read_the_issuer_history_under_the_current_symbol(tmp_path):
    _split_history(tmp_path / "gabi.db", [_row("a3", 2024, 12.0)])
    facts, cik = SqliteSignals(tmp_path).filing_facts("NEW")
    assert cik == CIK and set(facts.symbol) == {"NEW"}
    assert list(facts.accn) == ["a1", "q1", "a2", "a3"]  # end_date order
    index = filings.filings_from_facts(facts, "10-K", cik)
    assert list(index.accn) == ["a1", "a2", "a3"]  # the previous 10-K exists to compare against
    assert SqliteSignals(tmp_path).filing_facts("BARE")[0].empty


def test_filing_facts_fall_back_to_symbol_rows_and_bound_the_entity_read(tmp_path):
    path = tmp_path / "gabi.db"
    _split_history(path, [_row("a3", 2024, 12.0)])
    store = SqliteXbrl(path, _now)
    store.store_facts("LEGACY", [_row("x1", 2024, 5.0)])  # no stored CIK: symbol rows only
    assert list(SqliteSignals(tmp_path).filing_facts("LEGACY")[0].accn) == ["x1"]
    store.ensure_entity("0000000099")
    store.store_facts("HUGE", [_row("h1", 2024, 1.0) | {"tag": "T" * 20000}], entity="cik:0000000099",
                      cik="0000000099")
    store.save("HUGE", "0000000099", [], {})
    with pytest.raises(QueryError):
        SqliteSignals(tmp_path).filing_facts("HUGE")


def test_symbols_with_facts_counts_history_stored_under_another_alias(tmp_path):
    path = tmp_path / "gabi.db"
    _split_history(path, [])
    assert SqliteSecReads(path).facts("NEW").empty
    assert SqliteSecReads(path).symbols_with_facts(["OLD", "NEW", "BARE", "ABSENT"]) == {"OLD", "NEW"}


def test_sec_selection_does_not_redownload_a_symbol_covered_through_its_entity(tmp_path):
    path = tmp_path / "gabi.db"
    _split_history(path, [])
    fetched, covered, failed = SqliteSecSelection(path, _now).current(["OLD", "NEW", "BARE"])
    assert covered == {"OLD", "NEW"} and set(fetched) == {"OLD", "NEW", "BARE"} and failed == {}


def test_issuer_entities_only_when_the_entity_holds_every_fact_the_symbol_had(tmp_path):
    path = tmp_path / "gabi.db"
    _split_history(path, [_row("a3", 2024, 12.0)])
    store = SqliteXbrl(path, _now)
    store.store_facts("LEGACY", [_row("x1", 2024, 5.0)])  # no stored CIK
    reads = SqliteSecReads(path)
    entity = f"cik:{CIK}"
    assert reads.issuer_entities(["NEW", "OLD", "BARE", "LEGACY", "ABSENT"], "2025-12-31") == {"NEW": entity,
                                                                                             "OLD": entity}
    # A later row under NEW that the entity never got (e.g. a successor's filing) only blocks from its filing on.
    store.store_facts("NEW", [_row("s1", 2025, 1.0)])
    assert reads.issuer_entities(["NEW"], "2026-02-14") == {"NEW": entity}
    assert reads.issuer_entities(["NEW"], "2026-02-15") == {}


def test_issuer_entities_skip_a_symbol_whose_own_rows_were_withdrawn_from_the_ticker_table(tmp_path):
    import sqlite3
    from contextlib import closing

    path = tmp_path / "gabi.db"
    _split_history(path, [_row("a3", 2024, 12.0), _row("w1", 2008, 1.0)])
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("DELETE FROM edgar_facts WHERE accn='w1'")  # still an observation under NEW
    assert SqliteSecReads(path).issuer_entities(["NEW", "OLD"], "2025-12-31") == {"OLD": f"cik:{CIK}"}
