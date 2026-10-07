"""Whole annual inventory parity on isolated synthetic caches and CSV inputs."""

import argparse
import json
import sqlite3
import types
from contextlib import closing
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gabi.application.research.historical_data_audit import audit, publish_audit
from gabi.domain.research import coverage
from gabi.domain.research.historical_data_audit import block_counts
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.historical_data_audit import CsvAnnualAudit, SqliteAnnualAudit
from gabi.infrastructure.storage.readonly import connect_readonly

REFERENCE = json.loads((Path(__file__).parent / "fixtures/historical_data_audit_migration.json").read_text(encoding="utf-8"))
SOURCE_DIR = Path(__file__).parents[1] / "src/gabi"


def original_modules():
    modules = []
    for key, name in (("coverage_source", "historical_coverage"), ("annual_source", "historical_data_audit")):
        module = types.ModuleType(f"gabi._reference_{name}")
        module.__package__ = "gabi"
        module.__file__ = str(SOURCE_DIR / f"{name}.py")
        source = REFERENCE[key]
        if key == "annual_source":
            source = source.replace("from .historical_coverage import availability, finite, metric_row", "")
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        modules.append(module)
    old_coverage, old_annual = modules
    old_annual.metric_row = old_coverage.metric_row
    old_annual.finite = old_coverage.finite
    old_annual.availability = old_coverage.availability
    original_connect = old_annual.connect_readonly
    # SQLite's own context commits/rolls back but does not close. Close the
    # reference connection explicitly so the temporary Windows DB is releasable.
    old_annual.connect_readonly = lambda path: closing(original_connect(path))
    return old_coverage, old_annual


def make_inputs(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    db = directory / "cache.db"
    manifest = json.loads((SOURCE_DIR / "resources/historical_sources_1996_2015.json").read_text(encoding="utf-8"))
    membership = directory / "membership.csv"
    old_detail = directory / "old.csv"
    pd.DataFrame([{"date": "2016-01-01", "tickers": "AAA,BBB,AAA,"},
                  {"date": "2020-01-01", "tickers": "AAA,CCC"},
                  {"date": "2026-09-22", "tickers": "AAA,CCC"}]).to_csv(membership, index=False)
    pd.DataFrame([{"date": f"{year}-12-31", "symbol": symbol,
                   "missing_metrics": "pe;pb;ev_ebitda" if symbol == "BBB" else "",
                   "prices_253_recent": symbol == "AAA"}
                  for year in range(2008, 2016) for symbol in ("AAA", "BBB")]).to_csv(old_detail, index=False)
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE historical_membership(source_id,date,tickers);
            CREATE TABLE entity_aliases(symbol,entity_id,valid_from,valid_to,confidence);
            CREATE TABLE entity_observations(entity_id,dataset,payload_json);
            CREATE TABLE historical_facts(cik,filed_date);
            CREATE TABLE historical_prices(source_id,symbol,date,close,adj_close);
            CREATE TABLE prices(symbol,date,close,adj_close);
            CREATE TABLE splits(symbol,date,ratio);
            CREATE TABLE edgar_facts(symbol,tag,unit,start_date,end_date,val,form,fp,fy,filed_date,accn);
        """)
        conn.execute("INSERT INTO historical_membership VALUES (?,?,?)", (manifest["membership_source_id"], "2007-12-31", "AAA,BBB"))
        conn.executemany("INSERT INTO entity_aliases VALUES (?,?,?,?,?)", [
            ("AAA", "cik:1", "2000-01-01", None, .95), ("BBB", "cik:2", "2000-01-01", "2020-01-01", .8),
            ("BBB", "cik:2", "2000-01-01", "2020-01-01", .95),
            ("CCC", "cik:3", "2020-01-01", None, .99), ("CCC", "cik:4", "2020-01-01", None, .99)])
        for year in range(2008, 2027):
            day = f"{year}-02-01"
            conn.execute("INSERT INTO entity_observations VALUES (?,?,?)", ("cik:1", "edgar_facts", json.dumps({"filed_date": day})))
            conn.execute("INSERT INTO historical_facts VALUES (?,?)", ("1", day))
            conn.executemany("INSERT INTO historical_prices VALUES (?,?,?,?,?)", [
                (manifest["price_source_id"], "AAA", day, 10, 10),
                (manifest["price_source_id"], "BBB", day, 10, 0)])
        dates = pd.bdate_range("2014-01-01", "2026-09-22")
        conn.executemany("INSERT INTO prices VALUES (?,?,?,?)", [
            (symbol, day.date().isoformat(), 100 + i * .1, (100 + i * .1) * (1 + .03 * np.sin(i / 20)))
            for symbol in ("SPY", "AAA", "BBB", "CCC") for i, day in enumerate(dates)
            if not (symbol == "BBB" and i % 13 == 0)])
        conn.executemany("INSERT INTO splits VALUES (?,?,?)", [("AAA", "2027-01-01", 2), ("AAA", "2027-02-01", 0),
                                                               ("AAA", "2027-03-01", None), ("BBB", "2010-01-01", .5)])
        for year in range(2010, 2026):
            for tag, value in (("Revenues", 1000 + year), ("NetIncomeLoss", 100), ("OperatingIncomeLoss", 150),
                               ("NetCashProvidedByUsedInOperatingActivities", 200),
                               ("PaymentsToAcquirePropertyPlantAndEquipment", 50), ("StockholdersEquity", 500),
                               ("LongTermDebtNoncurrent", 100), ("CashAndCashEquivalentsAtCarryingValue", 70),
                               ("DepreciationDepletionAndAmortization", 30), ("CommonStockSharesOutstanding", 10)):
                conn.execute("INSERT INTO edgar_facts VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                    "AAA", tag, "shares" if "Shares" in tag else "USD", f"{year}-01-01", f"{year}-12-31", value,
                    "10-K", "FY", year, f"{year+1}-02-01", str(year)))
    return db, membership, old_detail


def reader_for(connection, membership, old_detail, **kwargs):
    return SqliteAnnualAudit(connection, membership, old_detail, SOURCE_DIR / "resources/historical_sources_1996_2015.json", **kwargs)


def test_whole_annual_audit_and_csv_bytes_match_original(tmp_path):
    db, membership, old_detail = make_inputs(tmp_path)
    old_coverage, old_annual = original_modules()
    expected = old_annual.audit(db, membership, old_detail)
    before = db.read_bytes()
    messages = []
    with closing(connect_readonly(db)) as connection:
        actual = publish_audit(reader_for(connection, membership, old_detail, batch_size=1),
                               CsvAnnualAudit(tmp_path / "new.csv"), progress=messages.append)
    pd.testing.assert_frame_equal(actual, expected)
    expected.to_csv(tmp_path / "old-output.csv", index=False)
    assert (tmp_path / "new.csv").read_bytes() == (tmp_path / "old-output.csv").read_bytes()
    assert db.read_bytes() == before
    assert len(messages) == 19
    assert actual.iloc[-1].as_of == "2026-09-22"
    with closing(connect_readonly(db)) as connection:
        frames = pd.read_sql_query("SELECT tag,unit,start_date,end_date,val,form,fp,fy,filed_date,accn FROM edgar_facts", connection)
        prices = reader_for(connection, membership, old_detail)._prices("AAA", "2026-09-22")
    assert coverage.metric_row(frames, prices, prices, "2026-09-22", nominal_price=200) == old_coverage.metric_row(
        frames, prices, prices, "2026-09-22", nominal_price=200)


@pytest.mark.parametrize("mutation,error", [("DELETE FROM prices WHERE symbol='SPY'", "SPY has no adjusted close"),
                                            ("UPDATE historical_membership SET tickers='AAA'", "membership changed")])
def test_incomplete_inventory_is_rejected_without_publishing(tmp_path, mutation, error):
    db, membership, old_detail = make_inputs(tmp_path)
    with sqlite3.connect(db) as connection:
        connection.execute(mutation)
    output = tmp_path / "output.csv"
    with closing(connect_readonly(db)) as connection, pytest.raises(ValueError, match=error):
        publish_audit(reader_for(connection, membership, old_detail), CsvAnnualAudit(output))
    assert not output.exists()


@pytest.mark.parametrize("limits", [{"max_price_rows": 5}, {"max_rows": 1}, {"max_file_bytes": 1}, {"max_symbols": 1}])
def test_limits_reject_overflow_instead_of_silently_truncating(tmp_path, limits):
    db, membership, old_detail = make_inputs(tmp_path)
    with closing(connect_readonly(db)) as connection, pytest.raises(ValueError, match="limit"):
        audit(reader_for(connection, membership, old_detail, **limits))


def test_missing_database_is_not_created_and_connection_rejects_writes(tmp_path):
    absent = tmp_path / "absent.db"
    with pytest.raises(FileNotFoundError):
        connect_readonly(absent)
    assert not absent.exists()
    db, _, _ = make_inputs(tmp_path)
    with closing(connect_readonly(db)) as connection, pytest.raises(sqlite3.OperationalError):
        connection.execute("DELETE FROM prices")


def test_domain_counts_have_no_io_and_policy_is_explicit(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("I/O in domain")

    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    full = dict.fromkeys(coverage.METRICS, 1)
    assert block_counts([full])["all_13"] == 1
    altered = coverage.CoverageParameters(min_score_coverage=1.0)
    assert not coverage.availability(dict(full, pe=None), parameters=altered)[1]


def test_cli_composes_readonly_inputs_and_explicit_csv_export(tmp_path, capsys, monkeypatch):
    from gabi.infrastructure.storage import readonly
    from gabi_cli.research.bootstrap import historical_data_audit

    db, membership, old_detail = make_inputs(tmp_path)
    before = db.read_bytes()
    output = tmp_path / "out/report.csv"
    connections = []

    def capture_connection(path):
        connection = connect_readonly(path)
        connections.append(connection)
        return connection

    monkeypatch.setattr(readonly, "connect_readonly", capture_connection)
    historical_data_audit(Settings(tmp_path / "data"), argparse.Namespace(db=db, membership=membership, old_detail=old_detail, output=output))
    assert len(pd.read_csv(output)) == 19
    assert db.read_bytes() == before
    assert str(output) in capsys.readouterr().out
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")
