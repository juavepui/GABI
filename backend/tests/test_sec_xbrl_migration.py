"""Captured pre-migration parity, issuer attribution, boundaries and worker wiring."""

import ast
import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

from gabi.application.administration.sync_events import SyncAttempt
from gabi.application.market.sec_xbrl import download_complete, fetch_complete, synchronize
from gabi.domain.market.sec_xbrl import facts_due
from gabi.infrastructure.legacy.source_errors import fingerprint
from gabi.infrastructure.providers.sec_xbrl import SecXbrl
from gabi.infrastructure.storage.sec_xbrl import SqliteXbrl
from gabi.infrastructure.storage.sync_events import OperationSyncEvents

REFERENCE = json.loads((Path(__file__).parent / "fixtures/sec_xbrl_migration.json").read_text(encoding="utf-8"))
NOW = datetime(2024, 1, 10, 22, tzinfo=UTC)


def payload(value=100, accn="a1", filed="2020-02-01", *, count=1):
    entries = [{"start": "2019-01-01", "end": "2019-12-31", "val": value + i,
                "accn": f"{accn}-{i}", "filed": filed, "form": "10-K", "fp": "FY", "fy": 2019}
               for i in range(count)]
    return {"cik": 1, "facts": {"us-gaap": {"Revenues": {"units": {"USD": entries}}},
                               "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
                                   {"end": "2019-12-31", "val": 10, "accn": accn,
                                    "filed": filed, "form": "10-K", "fp": None, "fy": None}]}}}}}


def filings(accn="a1", filed="2020-02-01"):
    return {"cik": 1, "filings": {"recent": {"form": ["10-K"], "filingDate": [filed],
                                            "accessionNumber": [accn], "primaryDocument": ["doc.htm"]}}}


def counted(call, attempt):
    attempt.calls += 1
    return call()


def read_tables(path):
    orders = {"entities": "entity_id", "entity_observations": "entity_id,dataset,symbol,record_key",
              "edgar_facts": "symbol,tag,unit,start_date,end_date,accn", "edgar_metrics": "symbol",
              "sync_checkpoints": "source,entity,dataset", "sync_events": "id"}
    with closing(sqlite3.connect(path)) as db:
        return {table: db.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
                if db.execute("SELECT 1 FROM sqlite_schema WHERE name=?", (table,)).fetchone() else []
                for table, order in orders.items()}


def captured_functions(source, namespace, names):
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            code = ast.get_source_segment(source, node)
            code = code.replace("    from . import identity\n", "")
            code = code.replace("        from .identity import observations\n", "        observations = identity.observations\n")
            exec(code, namespace)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    exec(ast.get_source_segment(source, node), namespace)


def original(directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "gabi.db"
    @contextmanager
    def connection():
        with closing(sqlite3.connect(path)) as db:
            with db:
                yield db
    class FixedDatetime:
        now = staticmethod(lambda zone: NOW)
        fromisoformat = staticmethod(datetime.fromisoformat)
    fixed_date = SimpleNamespace(today=lambda: NOW.date())
    identity_ns = {"pd": pd, "json": json, "date": fixed_date,
                   "storage": SimpleNamespace(get_connection=connection)}
    captured_functions(REFERENCE["identity"], identity_ns,
                       {"SCHEMA", "DATA_KEYS", "ensure_schema", "normalize_cik", "normalize_symbol",
                        "ensure_entity", "put_observations", "_json_value", "observations"})
    identity = SimpleNamespace(**identity_ns)
    sync_ns = {"storage": SimpleNamespace(get_connection=connection), "datetime": FixedDatetime,
               "time": SimpleNamespace(perf_counter=lambda: 4., thread_time=lambda: 2.)}
    source = REFERENCE["sync_state"].replace("from . import storage", "").replace("import time\n", "")
    source = source.replace("from datetime import UTC, datetime", "from datetime import UTC")
    exec(source, sync_ns)
    sync_ns["retry"] = counted
    sync = SimpleNamespace(**sync_ns)
    from gabi.domain.market import sec_facts
    edgar_ns = {"pd": pd, "datetime": FixedDatetime, "UTC": UTC, "identity": identity,
                "storage": SimpleNamespace(get_connection=connection)}
    captured_functions(REFERENCE["edgar"], edgar_ns,
                       {"FACTS_SCHEMA", "SCHEMA", "upsert_edgar_facts", "get_edgar_facts",
                        "upsert_edgar_metrics", "get_edgar_metrics"})
    edgar_ns.update(TRACKED_TAGS=sec_facts.TRACKED_TAGS, SHARES_TAGS=sec_facts.SHARES_TAGS,
                    _extract_raw_facts=sec_facts._extract_raw_facts,
                    compute_edgar_metrics=sec_facts.compute_edgar_metrics,
                    extract_latest_filings=sec_facts.extract_latest_filings,
                    fetch_submissions=lambda cik: filings(), fetch_company_facts=lambda cik: payload())
    edgar = SimpleNamespace(**edgar_ns)
    run_ns = {"edgar": edgar, "identity": identity, "storage": SimpleNamespace(get_connection=connection),
              "sync": sync, "datetime": FixedDatetime}
    source = REFERENCE["edgar_sync"].replace("from . import edgar, identity, storage", "")
    source = source.replace("from . import sync_state as sync", "")
    source = source.replace("from datetime import UTC, datetime", "from datetime import UTC")
    exec(source, run_ns)
    return SimpleNamespace(run=run_ns["run_one"], source=edgar, events=sync, path=path)


def modern(directory):
    path = directory / "gabi.db"
    store, events = SqliteXbrl(path, lambda: NOW), OperationSyncEvents(path)
    source = SimpleNamespace(submissions=lambda cik: filings(), companyfacts=lambda cik: payload())
    def attempt(provider, entity, dataset):
        return SyncAttempt(provider, entity, dataset, events, now=lambda: NOW,
                           wall_time=lambda: 4., cpu_time=lambda: 2.)
    def run(symbol="A", cik="1", **options):
        return synchronize(symbol, cik, store=store, submissions=source.submissions, companyfacts=source.companyfacts,
                           checkpoint=events.get, attempt_factory=attempt, retry=counted,
                           fingerprint=fingerprint, now=lambda: NOW, **options)
    return SimpleNamespace(run=run, source=source, store=store, events=events, path=path)


@pytest.mark.parametrize("count", [1, 50])
def test_complete_sql_events_checkpoints_match_original(tmp_path, count):
    old, new = original(tmp_path / "old"), modern(tmp_path / "new")
    for step in range(7):
        for service in (old, new):
            service.source.fetch_company_facts = lambda cik: payload(count=count)
            service.source.companyfacts = service.source.fetch_company_facts
            if step == 3:
                service.source.fetch_company_facts = lambda cik: payload(120, count=count)
                service.source.companyfacts = service.source.fetch_company_facts
            elif step == 4:
                service.source.fetch_submissions = lambda cik: filings("a2", "2020-05-01")
                service.source.submissions = service.source.fetch_submissions
                service.source.fetch_company_facts = lambda cik: payload(130, "a2", "2020-05-01", count=count)
                service.source.companyfacts = service.source.fetch_company_facts
            elif step == 5:
                def fail(cik):
                    raise ValueError("synthetic failure")
                service.source.fetch_company_facts = fail
                service.source.companyfacts = fail
        if step == 5:
            for service in (old, new):
                with pytest.raises(ValueError, match="synthetic failure"):
                    service.run("A", "1", full_refresh=True)
        else:
            assert old.run("A", "1", full_refresh=step in (2, 3, 6)) == new.run("A", "1", full_refresh=step in (2, 3, 6))
        assert read_tables(old.path) == read_tables(new.path)


def test_hash_hit_does_not_read_or_parse_history(tmp_path, monkeypatch):
    service = modern(tmp_path)
    service.run()
    cp = service.events.get("sec", "cik:0000000001", "facts:A")
    cp["facts_audited_at"] = (NOW - timedelta(days=8)).isoformat()
    with closing(sqlite3.connect(service.path)) as db:
        db.execute("UPDATE sync_checkpoints SET state_json=?", (json.dumps(cp),))
        db.commit()
    monkeypatch.setattr(service.store, "facts", lambda _: pytest.fail("history read on hash hit"))
    event = service.run()
    assert event["calls"] == 2 and event["status"] == "unchanged"


def test_issuer_fact_revision_under_new_alias_keeps_accessions(tmp_path):
    service = modern(tmp_path)
    service.run("OLD", "1")
    service.source.companyfacts = lambda cik: payload(110)
    assert service.run("NEW", "1")["revised"] == 1
    frame = service.store.facts("cik:0000000001")
    revenue = frame[frame.tag == "Revenues"]
    assert revenue.iloc[0].val == 110 and revenue.iloc[0].source_symbol == "NEW"
    service.source.submissions = lambda cik: filings("a2", "2020-05-01")
    service.source.companyfacts = lambda cik: payload(120, "a2", "2020-05-01")
    service.run("NEW", "1")
    assert set(service.store.facts("cik:0000000001").accn) == {"a1", "a1-0", "a2", "a2-0"}
    assert service.store.facts("cik:0000000002").empty


@pytest.mark.parametrize("kind", ["submissions", "companyfacts"])
def test_wrong_issuer_does_not_advance_success_or_replace_rows(tmp_path, kind):
    service = modern(tmp_path)
    service.run()
    before = read_tables(service.path)
    setattr(service.source, kind, lambda cik: {"cik": 2})
    with pytest.raises(ValueError, match="otro emisor"):
        service.run(full_refresh=True)
    after = read_tables(service.path)
    for table in ("entity_observations", "edgar_facts", "edgar_metrics"):
        assert after[table] == before[table]
    cp = service.events.get("sec", "cik:0000000001", "facts:A")
    assert cp["status"] == "failed" and cp["watermark"] == "2020-02-01"


def test_atomic_dual_write_rolls_back_if_attribution_fails(tmp_path, monkeypatch):
    import gabi.infrastructure.storage.sec_xbrl as module
    service = modern(tmp_path)
    service.run()
    before = read_tables(service.path)
    service.source.companyfacts = lambda cik: payload(110)
    def fail(*args):
        raise RuntimeError("attribution failed")
    monkeypatch.setattr(module, "put_facts", fail)
    with pytest.raises(RuntimeError, match="attribution failed"):
        service.run(full_refresh=True)
    after = read_tables(service.path)
    for table in ("entity_observations", "edgar_facts", "edgar_metrics"):
        assert after[table] == before[table]


def test_interruption_after_commit_resumes_idempotently(tmp_path, monkeypatch):
    service = modern(tmp_path)
    original_save = service.store.save
    def interrupted(*args):
        original_save(*args)
        raise KeyboardInterrupt
    monkeypatch.setattr(service.store, "save", interrupted)
    with pytest.raises(KeyboardInterrupt):
        service.run()
    assert service.events.get("sec", "cik:0000000001", "facts:A") == {}
    before = read_tables(service.path)
    monkeypatch.setattr(service.store, "save", original_save)
    event = service.run()
    assert event["new"] == 0 and event["revised"] == 0 and event["status"] == "unchanged"
    after = read_tables(service.path)
    assert after["edgar_facts"] == before["edgar_facts"]
    assert after["entity_observations"] == before["entity_observations"]
    assert service.events.get("sec", "cik:0000000001", "facts:A")["watermark"] == "2020-02-01"


def test_source_calls_have_no_open_database_and_empty_payload_keeps_success(tmp_path):
    service = modern(tmp_path)
    service.run()
    before = read_tables(service.path)
    def empty(cik):
        # An exclusive writer can acquire the database while the source runs.
        with closing(sqlite3.connect(service.path, timeout=0)) as db:
            db.execute("BEGIN EXCLUSIVE")
            db.rollback()
        return {"cik": 1, "facts": {}}
    service.source.companyfacts = empty
    with pytest.raises(ValueError, match="utilizables"):
        service.run(full_refresh=True)
    after = read_tables(service.path)
    assert after["edgar_facts"] == before["edgar_facts"]
    assert after["edgar_metrics"] == before["edgar_metrics"]
    cp = service.events.get("sec", "cik:0000000001", "facts:A")
    assert cp["status"] == "failed" and cp["facts_hash"] == json.loads(before["sync_checkpoints"][0][3])["facts_hash"]


def test_reads_do_not_create_database_or_schema_and_enforce_limits(tmp_path):
    service = modern(tmp_path / "absent")
    assert not service.store.has_facts("cik:0000000001")
    assert service.store.facts("cik:0000000001").empty and service.store.metrics("A") is None
    assert not service.path.parent.exists()
    service.path.parent.mkdir()
    with closing(sqlite3.connect(service.path)) as db:
        db.execute("CREATE TABLE unrelated(x)")
    before = service.path.read_bytes()
    assert service.store.facts("cik:0000000001").empty and service.store.metrics("A") is None
    assert not service.store.has_facts("cik:0000000001") and service.path.read_bytes() == before
    service.run()
    for options in ({"max_rows": 1}, {"max_payload_bytes": 1}, {"max_row_bytes": 1}):
        with pytest.raises(ValueError, match="límite"):
            SqliteXbrl(service.path, lambda: NOW, **options).facts("cik:0000000001")


@pytest.mark.parametrize("days,expected", [(6.999, False), (7, True)])
def test_weekly_audit_boundary_and_recent_filings(days, expected):
    cp = {"facts_audited_at": (NOW - timedelta(days=days)).isoformat()}
    assert facts_due(cp, {}, True, {"x": 1}, NOW, False) == expected
    assert facts_due(cp, {"filingDate": [(NOW - timedelta(days=2)).date().isoformat()]},
                     True, {"x": 1}, NOW, False)


@pytest.mark.parametrize("status,payload_bytes,error", [(200, b'[]', "inválida"), (200, b'{}' * 5, "bytes"),
                                                       (404, b'', "XBRL")])
def test_http_bounds_404_and_response_closed(monkeypatch, status, payload_bytes, error):
    calls, closed = [], []
    class Response:
        status_code = status
        def __enter__(self):
            return self
        def __exit__(self, *args):
            closed.append(True)
        def raise_for_status(self):
            pass
        def iter_content(self, size):
            yield payload_bytes
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append((a, k)) or Response())
    with pytest.raises(ValueError, match=error):
        SecXbrl("contact", max_bytes=8).companyfacts("1")
    assert closed == [True]
    assert calls[0][0][0].endswith("CIK0000000001.json")
    assert calls[0][1] == {"headers": {"User-Agent": "contact"}, "timeout": 30, "stream": True}


def test_bootstrap_and_worker_use_injected_sync_not_legacy(tmp_path, monkeypatch):
    from gabi import config, edgar, edgar_sync
    from gabi.infrastructure.settings import Settings
    from gabi_cli.bootstrap import build_executor
    from gabi_cli.sources.bootstrap import build_xbrl_operation

    operation = build_xbrl_operation(Settings(tmp_path), "contact", now=lambda: NOW)
    assert not tmp_path.joinpath("gabi.db").exists()
    monkeypatch.setattr(SecXbrl, "submissions", lambda self, cik: filings())
    monkeypatch.setattr(SecXbrl, "companyfacts", lambda self, cik: payload())
    monkeypatch.setattr(edgar_sync, "run_one", lambda *a, **k: pytest.fail("legacy synchronization"))
    monkeypatch.setattr(edgar, "fetch_submissions", lambda *a: pytest.fail("legacy HTTP"))
    monkeypatch.setattr(edgar, "fetch_company_facts", lambda *a: pytest.fail("legacy HTTP"))
    from gabi.application.market.sec_cik import CikResolver
    monkeypatch.setattr(CikResolver, "mapping", lambda self, **k: pd.DataFrame({"symbol": ["A"], "cik": ["0000000001"], "title": ["A"]}))
    monkeypatch.setattr(edgar, "get_cik_map", lambda **k: pytest.fail("legacy map"))
    monkeypatch.setattr(edgar, "ensure_edgar_data", lambda *a, **k: pytest.fail("legacy selection"))
    executor = build_executor(Settings(config.DATA_DIR), now=lambda: NOW)
    assert executor.sec_sync(["A"], force=True)["edgar_refreshed"] == 1
    assert operation.keywords["store"].path == tmp_path / "gabi.db"


def test_complete_download_optional_links_and_source_failure_do_not_open_sql(tmp_path):
    path = tmp_path / "gabi.db"
    store = SqliteXbrl(path, lambda: NOW)
    def source(cik):
        assert not path.exists()
        return payload()
    def unavailable(cik):
        assert not path.exists()
        raise OSError("optional filing links unavailable")
    download_complete("OLD", "0000000001", store=store, companyfacts=source,
                      submissions=unavailable, compute=lambda facts: {"roic": 0.1})
    tables = read_tables(path)
    assert len(tables["edgar_facts"]) == len(tables["entity_observations"]) == 2
    assert tables["entity_observations"][0][0] == "cik:0000000001"
    assert store.metrics("OLD")["roic"] == 0.1
    assert not tables["sync_checkpoints"] and not tables["sync_events"]
    before = path.read_bytes()
    def failed(cik):
        raise OSError("companyfacts unavailable")
    with pytest.raises(OSError):
        download_complete("OLD", "1", store=store, companyfacts=failed,
                          submissions=unavailable, compute=lambda facts: {})
    assert path.read_bytes() == before


@pytest.mark.parametrize("source", ["facts", "filings"])
def test_complete_download_rejects_another_issuer_before_storage(tmp_path, source):
    facts, submissions = payload(), filings()
    (facts if source == "facts" else submissions)["cik"] = 2
    path = tmp_path / "gabi.db"
    with pytest.raises(ValueError, match="otro emisor"):
        download_complete("A", "1", store=SqliteXbrl(path, lambda: NOW),
                          companyfacts=lambda cik: facts, submissions=lambda cik: submissions,
                          compute=lambda facts: {})
    assert not path.exists()


def test_complete_extraction_preserves_rows_metrics_and_filing_links():
    from gabi.domain.market.sec_facts import compute_edgar_metrics
    actual = fetch_complete("1", companyfacts=lambda cik: payload(), submissions=lambda cik: filings(),
                            compute=compute_edgar_metrics)
    namespace = {"fetch_company_facts": lambda cik: payload(), "fetch_submissions": lambda cik: filings()}
    from gabi.domain.market import sec_facts
    namespace.update(vars(sec_facts))
    captured_functions(REFERENCE["edgar"], namespace, {"_fetch_one"})
    assert actual == namespace["_fetch_one"]("A", "1")


def test_historical_bootstrap_uses_dated_issuer_and_explicit_database(tmp_path, monkeypatch):
    from gabi import config, edgar, identity
    from gabi.application.market.sec_cik import CikResolver
    from gabi.infrastructure.settings import Settings
    from gabi_cli.sources.bootstrap import build_xbrl_operation

    path = tmp_path / "gabi.db"
    with closing(sqlite3.connect(path)) as db:
        identity.ensure_schema(db)
        db.execute("INSERT INTO entities VALUES ('cik:0000000001','0000000001','Old','2010-01-01')")
        db.execute("INSERT INTO entity_aliases VALUES ('cik:0000000001','REC','2010-01-01','2020-01-01','dated',1)")
        db.commit()
    assert path != config.DB_PATH
    monkeypatch.setattr(CikResolver, "mapping", lambda *a, **k: pytest.fail("current map in historical route"))
    monkeypatch.setattr(edgar, "ensure_edgar_data", lambda *a, **k: pytest.fail("legacy selection"))
    calls = []
    monkeypatch.setattr(SecXbrl, "companyfacts", lambda self, cik: calls.append(cik) or payload())
    monkeypatch.setattr(SecXbrl, "submissions", lambda self, cik: filings())
    operation = build_xbrl_operation(Settings(tmp_path), "contact", now=lambda: NOW)
    assert operation(["REC"], as_of="2012-01-01") == {"edgar_refreshed": 1, "failed": {}}
    assert calls == ["0000000001"]
    assert operation(["REC"], as_of="2012-01-01") == {"edgar_refreshed": 0, "failed": {}}
    assert calls == ["0000000001"]
    assert len(read_tables(path)["entity_observations"]) == 2
