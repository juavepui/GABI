"""Captured EDGAR query parity, filing cutoffs, read-only boundaries and CLI."""

import ast
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from gabi.application.market.sec_reads import concept_value, issuer_facts, issuer_snapshot, metrics_as_of, stored_facts
from gabi.domain.market import sec_facts
from gabi.infrastructure.storage.sec_reads import SqliteSecReads

REFERENCE = json.loads((Path(__file__).parent / "fixtures/sec_reads_migration.json").read_text(encoding="utf-8"))


def captured(path, monkeypatch):
    from gabi import config, storage
    monkeypatch.setattr(config, "DB_PATH", path)
    names = {"FACTS_SCHEMA", "get_edgar_facts", "get_issuer_facts_as_of", "get_value_as_of",
             "get_shares_outstanding_as_of", "_facts_dict_from_stored", "compute_edgar_metrics_as_of", "get_last_filed_dates"}
    namespace = {**vars(sec_facts), "__package__": "gabi", "__spec__": None,
                 "storage": storage, "pd": pd, "json": json, "date": date}
    source = REFERENCE["edgar"]
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in names or isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in names for target in node.targets):
            exec(ast.get_source_segment(source, node), namespace)
    return namespace


def row(year, value=100, *, tag="Revenues", unit="USD", accn=None, filed=None):
    return {"tag": tag, "unit": unit, "start_date": f"{year}-01-01", "end_date": f"{year}-12-31", "val": value,
            "form": "10-K", "fp": "FY", "fy": year, "filed_date": filed or f"{year + 1}-02-01", "accn": accn or str(year)}


def seed(path):
    from gabi import edgar, identity
    records = [row(year, value) for year, value in [(2016, 100), (2017, 110), (2018, 121), (2019, 133.1)]]
    records += [{**row(2019, 200, accn="amend", filed="2021-03-01"), "form": "10-K/A"},
                {**row(2019, 1000000, tag="EntityCommonStockSharesOutstanding", unit="shares"), "start_date": ""},
                row(2020, 900000, tag="CommonStockSharesOutstanding", unit="shares"),
                {**row(2020, 500, accn="8k"), "form": "8-K"},
                {**row(2025, 700, filed="2020-06-01"), "accn": "future-period"},
                {**row(2019, 300, accn="undated"), "filed_date": None}]
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        db.executescript(edgar.FACTS_SCHEMA)
        identity.ensure_schema(db)
        db.executemany("INSERT INTO edgar_facts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       [("REC", *(record[key] for key in ("tag", "unit", "start_date", "end_date", "val", "form", "fp", "fy", "filed_date", "accn"))) for record in records])
        for i, record in enumerate(records):
            db.execute("INSERT INTO entity_observations VALUES (?,?,?,?,?,?)",
                       ("cik:0000000001", "edgar_facts", "OLD", str(i), json.dumps(record), f"https://sec.example/{i}"))
        db.execute("INSERT INTO entity_observations VALUES (?,?,?,?,?,?)",
                   ("cik:0000000002", "edgar_facts", "REC", "other", json.dumps(row(2019, 99999)), "other issuer"))
        db.commit()
    return records


@pytest.mark.parametrize("day", ["2016-01-01", "2019-06-01", "2020-02-01", "2020-12-31", "2021-06-01"])
def test_captured_values_metrics_versions_and_raw_rows(tmp_path, monkeypatch, day):
    path = tmp_path / "gabi.db"
    seed(path)
    old = captured(path, monkeypatch)
    reader = SqliteSecReads(path)
    for entity in (None, "cik:0000000001", "cik:0000000002", "cik:0000009999"):
        for tags in (None, [], ["Revenues"], ["absent"]):
            assert_frame_equal(reader.facts("REC", tags=tags, entity_id=entity), old["get_edgar_facts"]("REC", tags=tags, entity_id=entity))
        assert stored_facts(reader, "REC", day, entity_id=entity) == old["_facts_dict_from_stored"]("REC", day, entity_id=entity)
        assert metrics_as_of(reader, "REC", day, entity_id=entity) == old["compute_edgar_metrics_as_of"]("REC", day, entity_id=entity)
        for tags, unit in ((["Revenues"], "USD"), (sec_facts.SHARES_TAGS, "shares"), (["unknown"], "USD")):
            assert concept_value(reader, "REC", tags, day, unit, entity_id=entity) == old["get_value_as_of"]("REC", tags, day, unit, entity_id=entity)
    for tags in (None, ["Revenues"], ["absent"]):
        assert_frame_equal(issuer_facts(reader, "1", day, tags), old["get_issuer_facts_as_of"]("1", day, tags))
    assert reader.last_filed(["REC", "UNKNOWN"], day) == old["get_last_filed_dates"](["REC", "UNKNOWN"], day)


def test_duplicate_alias_is_selected_before_cutoff_and_other_cik_is_isolated(tmp_path):
    path = tmp_path / "gabi.db"
    seed(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("INSERT INTO entity_observations VALUES (?,?,?,?,?,?)", ("cik:0000000001", "edgar_facts", "ZZZ", "dup",
                   json.dumps(row(2019, 9999, filed="2019-01-01")), "duplicate"))
        db.commit()
    reader = SqliteSecReads(path)
    facts = stored_facts(reader, "REC", "2019-06-01", entity_id="cik:0000000001")
    assert all(entry["val"] != 9999 for entry in facts["facts"]["us-gaap"]["Revenues"]["units"]["USD"])
    assert metrics_as_of(reader, "REC", "2020-12-31", entity_id="cik:0000000002")["latest_revenue"] == 99999


def test_queries_do_not_create_or_mutate_database_or_contact_sources(tmp_path, monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("network in local query"))
    path = tmp_path / "absent/gabi.db"
    reader = SqliteSecReads(path)
    assert issuer_snapshot(reader, "1", "2020-01-01")["facts"] == []
    assert reader.last_filed(["REC"]) == {}
    assert not path.parent.exists()
    seed(path)
    before = path.read_bytes()
    statements = []
    actual = sqlite3.connect
    def traced(*args, **kwargs):
        connection = actual(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection
    monkeypatch.setattr(sqlite3, "connect", traced)
    snapshot = issuer_snapshot(reader, "1", "2020-12-31")
    assert snapshot["cik"] == "0000000001" and snapshot["facts"]
    assert path.read_bytes() == before
    assert not any(statement.lstrip().upper().startswith(("CREATE", "INSERT", "UPDATE", "DELETE")) for statement in statements)


@pytest.mark.parametrize("limits", [{"max_rows": 1}, {"max_bytes": 1}, {"max_row_bytes": 1}])
def test_read_limits_fail_instead_of_truncating(tmp_path, limits):
    path = tmp_path / "gabi.db"
    seed(path)
    reader = SqliteSecReads(path, **limits)
    with pytest.raises(ValueError, match="límite"):
        reader.facts("REC")
    with pytest.raises(ValueError, match="límite"):
        issuer_facts(reader, "1", "2022-01-01")


def test_bulk_last_filings_and_input_limits(tmp_path):
    path = tmp_path / "gabi.db"
    seed(path)
    reader = SqliteSecReads(path)
    assert reader.last_filed(["REC", *[f"S{i}" for i in range(205)]], "2020-12-31") == {"REC": "2020-06-01"}
    with pytest.raises(ValueError, match="símbolos"):
        reader.last_filed([str(i) for i in range(1001)])
    with pytest.raises(ValueError, match="tags"):
        reader.facts("REC", tags=[str(i) for i in range(201)])
    with pytest.raises(ValueError):
        issuer_facts(reader, "1", "not-a-date")


def test_missing_tables_and_oversized_json_never_initialize_or_decode(tmp_path, monkeypatch):
    path = tmp_path / "gabi.db"
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE unrelated(x)")
    reader = SqliteSecReads(path)
    before = path.read_bytes()
    assert reader.facts("REC").empty and issuer_facts(reader, "1", "2020-12-31").empty
    assert reader.last_filed(["REC"]) == {} and path.read_bytes() == before
    seed(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("INSERT INTO entity_observations VALUES (?,?,?,?,?,?)", ("cik:0000000001", "edgar_facts", "BIG", "large",
                   json.dumps({**row(2019), "extra": "x" * 100000}), "source"))
        db.commit()
    monkeypatch.setattr(json, "loads", lambda *a, **k: pytest.fail("decoding before size guard"))
    with pytest.raises(ValueError, match="límite"):
        issuer_facts(reader, "1", "2020-12-31")
    with pytest.raises(ValueError, match="límite"):
        reader.facts("REC", entity_id="cik:0000000001")


def test_cli_uses_explicit_database_and_no_legacy_reader(tmp_path, monkeypatch, capsys):
    from gabi import edgar
    from gabi_cli.research.bootstrap import main
    seed(tmp_path / "gabi.db")
    monkeypatch.setenv("GABI_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(edgar, "get_edgar_facts", lambda *a, **k: pytest.fail("legacy read"))
    main(["sec-facts", "--cik", "1", "--as-of", "2020-12-31", "--tag", "Revenues"])
    actual = json.loads(capsys.readouterr().out)
    assert actual["cik"] == "0000000001" and actual["shares_outstanding"] == 1000000
    assert all(record["tag"] == "Revenues" for record in actual["facts"])
    assert actual["metrics"] == issuer_snapshot(SqliteSecReads(tmp_path / "gabi.db"), "1", "2020-12-31")["metrics"]
