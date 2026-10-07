"""All quarterly artifacts against the original command, on temporary inputs."""

import argparse
import json
import sqlite3
import types
from contextlib import closing

import exchange_calendars as xcals
import pandas as pd
import pytest
from test_historical_data_audit_migration import REFERENCE, SOURCE_DIR, make_inputs, original_modules

from gabi.application.research.quarterly_coverage import publish
from gabi.domain.research.coverage import CoverageParameters, unique_historical_ciks
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.quarterly_coverage import FileQuarterlyCoverage, SqliteQuarterlyCoverage, read_facts
from gabi.infrastructure.storage.readonly import connect_readonly


def make_quarterly_inputs(directory):
    db, _, _ = make_inputs(directory)
    manifest = json.loads((SOURCE_DIR / "resources/historical_sources_1996_2015.json").read_text(encoding="utf-8"))
    live = directory / "sec_cik_map.csv"
    pd.DataFrame([{"symbol": "AAA", "cik": "1"}, {"symbol": "BBB", "cik": "2"}]).to_csv(live, index=False)
    with sqlite3.connect(db) as connection:
        connection.executescript("""
            CREATE TABLE entities(entity_id,cik);
            CREATE TABLE edgar_metrics(symbol,cik);
            CREATE TABLE historical_issuer_candidates(source_id,symbol,cik,date_added,observed_from);
        """)
        connection.execute("UPDATE historical_membership SET date='1995-12-31'")
        connection.execute("INSERT INTO historical_membership VALUES (?,?,?)", (manifest["membership_source_id"], "2014-01-01", "BBB,AAA,BBB"))
        connection.executemany("INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?)", [
            (manifest["issuer_source_id"], "AAA", "1", "1995-01-01", "2000-01-01"),
            (manifest["issuer_source_id"], "BBB", "2", "1995-01-01", "2000-01-01"),
            (manifest["issuer_source_id"], "BBB", "9", "1995-01-01", "2000-01-01")])
        connection.execute("INSERT INTO entities VALUES (?,?)", ("cik:0000000001", "0000000001"))
        connection.execute("UPDATE entity_aliases SET entity_id='cik:0000000001' WHERE symbol='AAA'")
        connection.execute("DELETE FROM entity_observations")
        facts = pd.read_sql_query("SELECT tag,unit,start_date,end_date,val,form,fp,fy,filed_date,accn FROM edgar_facts WHERE symbol='AAA'", connection)
        connection.executemany("INSERT INTO entity_observations VALUES (?,?,?)", [
            ("cik:0000000001", "edgar_facts", json.dumps(row)) for row in facts.to_dict("records")])
        dates = pd.bdate_range("1995-01-01", "2015-12-31")
        connection.execute("DELETE FROM historical_prices")
        connection.executemany("INSERT INTO historical_prices VALUES (?,?,?,?,?)", [
            (manifest["price_source_id"], symbol, day.date().isoformat(), 100 + i / 100, 100 + i / 100)
            for symbol in ("AAA", "BBB") for i, day in enumerate(dates)])
    before = directory / "before_validation.db"
    with closing(connect_readonly(db)) as connection, closing(sqlite3.connect(before)) as target:
        connection.backup(target)
        target.execute("DELETE FROM entity_observations")
        target.commit()
    return db, before, live


def sessions():
    return xcals.get_calendar("XNYS", start="1994-01-01", end="2016-01-01").sessions


def reader(connection, before, live, **kwargs):
    resources = SOURCE_DIR / "resources"
    return SqliteQuarterlyCoverage(connection, before, live, resources / "historical_sources_1996_2015.json",
                                   resources / "legacy_filings_pilot.json", **kwargs)


def original_command(db, before, live, output, trace=None):
    original, _ = original_modules()
    original.config = types.SimpleNamespace(DB_PATH=db, DATA_DIR=live.parent, MOMENTUM_LONG_DAYS=252,
                                            MOMENTUM_SHORT_DAYS=126, SMA_LONG=200)
    def reference_connection(path):
        connection = connect_readonly(path)
        if trace:
            connection.set_trace_callback(trace)
        return closing(connection)

    original.storage = types.SimpleNamespace(get_connection=lambda: reference_connection(db))
    original.sqlite3 = types.SimpleNamespace(connect=reference_connection)
    original.DIRECTORY = output.parent
    mapping = {"pd": pd}
    exec(compile(REFERENCE["mapping_source"], "original_unique_historical_ciks", "exec"), mapping)
    original.historical_archive = types.SimpleNamespace(unique_historical_ciks=mapping["unique_historical_ciks"])
    original_read = original.read_facts

    def read_reference(path):
        # The old command fixes the before-cache under its output directory.
        return original_read(before if path.name == "before_validation.db" else path)

    original.read_facts = read_reference
    return original.run()


def test_all_four_csv_and_summary_bytes_match_original(tmp_path):
    db, before, live = make_quarterly_inputs(tmp_path)
    old_output = tmp_path / "reference/coverage"
    old_output.parent.mkdir()
    expected = original_command(db, before, live, old_output)
    db_bytes, before_bytes = db.read_bytes(), before.read_bytes()
    output = tmp_path / "migrated"
    messages = []
    with closing(connect_readonly(db)) as connection, closing(connect_readonly(before)) as old_connection:
        result = publish(reader(connection, old_connection, live), sessions(), FileQuarterlyCoverage(output), progress=messages.append)
    assert result == expected
    assert result["quarters"] == 80 and result["company_quarters"] == 168
    assert result["sector_verified"] is False
    for name in ("price-validation.csv", "company-quarter.csv", "quarterly.csv", "missing-metrics.csv", "summary.json"):
        assert (output / name).read_bytes() == (old_output / name).read_bytes()
    assert len(messages) == 80
    assert db.read_bytes() == db_bytes and before.read_bytes() == before_bytes


@pytest.mark.parametrize("limit", ["max_price_rows", "max_rows", "max_file_bytes"])
def test_limits_do_not_produce_partial_artifacts(tmp_path, limit):
    db, before, live = make_quarterly_inputs(tmp_path)
    output = tmp_path / "output"
    with closing(connect_readonly(db)) as connection, closing(connect_readonly(before)) as old_connection, pytest.raises(ValueError, match="limit"):
        publish(reader(connection, old_connection, live, **{limit: 1}), sessions(), FileQuarterlyCoverage(output))
    assert not output.exists()


def test_scoped_reads_fetch_only_one_company_and_preserve_exact_facts(tmp_path):
    db, before, live = make_quarterly_inputs(tmp_path)
    with closing(connect_readonly(db)) as connection, closing(connect_readonly(before)) as old_connection:
        adapter = reader(connection, old_connection, live)
        adapter.metadata()
        reads = []
        connection.set_trace_callback(reads.append)
        inputs = adapter.company("AAA", "0000000001")
        assert not inputs.facts.empty and inputs.before.empty
        assert all("symbol='AAA'" in sql or "e.cik='0000000001'" in sql for sql in reads)
    assert read_facts(db)["0000000001"].equals(inputs.facts)
    with pytest.raises(ValueError, match="limit"):
        read_facts(db, max_rows=1)


def test_candidate_mapping_matches_original_conflicts_and_cutoffs():
    frame = pd.DataFrame([
        {"symbol": "A.A", "cik": "1", "created_at": "2015-01-01", "date_added": "2010-01-01"},
        {"symbol": "BBB", "cik": "2", "created_at": "2015-01-01", "date_added": "2010-01-01"},
        {"symbol": "CCC", "cik": "3", "created_at": "2016-01-01", "date_added": "2010-01-01"}])
    namespace = {"pd": pd}
    exec(compile(REFERENCE["mapping_source"], "original_mapping", "exec"), namespace)
    assert unique_historical_ciks(frame, {"A-A", "BBB", "CCC"}, {"BBB": "0000000009"}, {}) == namespace["unique_historical_ciks"](
        frame, {"A-A", "BBB", "CCC"}, {"BBB": "0000000009"}, {})


def test_quarterly_metrics_receive_explicit_policy_without_global_changes(tmp_path, monkeypatch):
    from gabi.domain.research import quarterly_coverage

    db, before, live = make_quarterly_inputs(tmp_path)
    policy = CoverageParameters(fiscal_alignment=True, alignment_tolerance_days=20)
    calls = []

    def metrics(*args, **kwargs):
        calls.append(kwargs["parameters"])
        return dict.fromkeys(policy.metrics)

    monkeypatch.setattr(quarterly_coverage, "metric_row", metrics)
    with closing(connect_readonly(db)) as connection, closing(connect_readonly(before)) as old_connection:
        source = reader(connection, old_connection, live)
        source.metadata()
        inputs = source.company("AAA", "0000000001")
    row = quarterly_coverage.company_quarter(inputs, pd.DataFrame(), "AAA", "0000000001", pd.Timestamp("2015-12-31"),
                                            sessions()[-253:], "", "consistent_overlap", parameters=policy)
    assert row["metrics_available"] == 0
    assert calls == [policy, policy]


def test_cli_is_offline_and_closes_both_connections(tmp_path, monkeypatch):
    from gabi.infrastructure.storage import readonly
    from gabi_cli.research.bootstrap import quarterly_coverage

    db, before, live = make_quarterly_inputs(tmp_path)
    connections = []

    def connect(path):
        connection = connect_readonly(path)
        connections.append(connection)
        return connection

    monkeypatch.setattr(readonly, "connect_readonly", connect)
    output = tmp_path / "output"
    quarterly_coverage(Settings(tmp_path / "data"), argparse.Namespace(db=db, before=before, cik_map=live, output=output))
    assert json.loads((output / "summary.json").read_text())["quarters"] == 80
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
