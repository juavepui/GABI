"""Captured parity of EDGAR fact/metric writes, CIK cache and resolutions, update errors and Company Facts
recovery by CIK after their SQL moved to explicit infrastructure adapters."""

import ast
import json
import sqlite3
import sys
from contextlib import closing, contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

from gabi import config, identity

REFERENCE = json.loads((Path(__file__).parent / "fixtures/edgar_writes_migration.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 4, 1, 9, 30, tzinfo=UTC)


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


class FixedDate(date):
    @classmethod
    def today(cls):
        return NOW.date()


def captured(module: str, names: set[str], namespace: dict) -> dict:
    source = REFERENCE[module]
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names or isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in names for target in node.targets):
            code = ast.get_source_segment(source, node).replace("    from . import identity\n", "")
            exec(code, namespace)
    return namespace


def connection(path: Path):
    @contextmanager
    def get_connection():
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=30)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            yield db
    return get_connection


def dump(path: Path) -> dict:
    if not path.exists():
        return {}
    with closing(sqlite3.connect(path)) as db:
        tables = sorted(n for n, in db.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name<>'sqlite_sequence'"))
        return {t: sorted(map(repr, db.execute(f"SELECT * FROM {t}").fetchall())) for t in tables}


def legacy_edgar(path: Path) -> SimpleNamespace:
    from gabi.domain.market import sec_facts
    storage = SimpleNamespace(get_connection=connection(path))
    storage.__dict__.update(captured("storage", {"SCHEMA", "UPDATE_ERRORS_RETENTION_DAYS", "record_update_errors"}, {
        "get_connection": storage.get_connection, "datetime": FixedDatetime, "UTC": UTC, "timedelta": timedelta}))
    namespace = {"storage": storage, "identity": identity, "datetime": FixedDatetime, "UTC": UTC, "pd": pd,
                 "_sec_facts": sec_facts, "config": config, "requests": requests,
                 "resolve_cik": __import__("gabi.application.market.sec_cik", fromlist=["resolve"]).resolve}
    captured("edgar", {"SCHEMA", "FACTS_SCHEMA", "RESOLUTIONS_SCHEMA", "upsert_edgar_facts", "upsert_edgar_metrics",
                       "_remember_cik_resolution", "_get_cached_cik_resolution", "get_resolved_title",
                       "get_cik_for_symbol", "_CikResolutions"}, namespace)
    return SimpleNamespace(**namespace)


def fact(i, *, accn=None, unit="USD", tag="Revenues"):
    return {"tag": tag, "unit": unit, "start_date": "2023-01-01", "end_date": "2023-12-31", "val": 100. + i,
            "form": "10-K", "fp": "FY", "fy": 2023, "filed_date": "2024-02-01", "accn": accn or f"a-{i}"}


def write_sequence(target):
    target.upsert_edgar_facts("AAA", [fact(i) for i in range(3)])
    target.upsert_edgar_facts("AAA", [fact(1, accn="a-1"), fact(9, tag="Assets")], cik="1")
    target.upsert_edgar_facts("BBB", [fact(2, unit="shares", tag="EntityCommonStockSharesOutstanding")], cik="0000000001")
    target.upsert_edgar_facts("CCC", [], cik="2")
    target.upsert_edgar_metrics("AAA", "0000000001", {"revenue_cagr_3y": .1, "roic": None, "latest_10k_date": "2024-02-01"})
    target.upsert_edgar_metrics("AAA", "0000000001", {"revenue_cagr_3y": .2, "latest_10q_url": "u"})
    target.upsert_edgar_metrics("BBB", "x", {})


def test_fact_and_metric_writes_match_capture(tmp_path, monkeypatch):
    from gabi import edgar, storage

    monkeypatch.setattr(identity, "date", FixedDate)
    results = []
    for label in ("old", "new"):
        path = tmp_path / label / "gabi.db"
        monkeypatch.setattr(config, "DB_PATH", path)
        if label == "old":
            target = legacy_edgar(path)
        else:
            monkeypatch.setattr(edgar, "_now", lambda: NOW)
            monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("legacy connection"))
            target = edgar
        write_sequence(target)
        results.append(dump(path))
    assert results[0] == results[1]
    assert len(results[1]["entity_observations"]) == 3 and results[1]["edgar_metrics"]


def test_wrong_issuer_attribution_keeps_previous_rows(tmp_path, monkeypatch):
    from gabi import edgar

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    edgar.upsert_edgar_facts("AAA", [fact(0)], cik="1")
    before = dump(tmp_path / "gabi.db")
    monkeypatch.setattr(identity, "ensure_entity", lambda cik: "cik:0000000404")
    with pytest.raises(ValueError, match="Unknown entity"):
        edgar.upsert_edgar_facts("AAA", [fact(5, accn="z")], cik="404")
    assert dump(tmp_path / "gabi.db") == before


def test_cik_resolutions_match_capture(tmp_path, monkeypatch):
    from gabi import edgar

    mapping = pd.DataFrame({"symbol": ["AAA", "BRK-B"], "cik": ["0000000001", "0000000002"], "title": ["Alpha", "Berk"]})
    results = []
    for label in ("old", "new"):
        path = tmp_path / label / "gabi.db"
        monkeypatch.setattr(config, "DB_PATH", path)
        if label == "old":
            target = legacy_edgar(path)
        else:
            monkeypatch.setattr(edgar, "_now", lambda: NOW)
            target = edgar
        outcomes = [target.get_resolved_title("AAA"), target._get_cached_cik_resolution("AAA"),
                    target.get_cik_for_symbol("AAA", cik_map=mapping), target.get_cik_for_symbol("BRK.B", cik_map=mapping),
                    target.get_cik_for_symbol("ZZZ", cik_map=mapping)]
        target._remember_cik_resolution("OLD", "0000000009", "Former Corp")
        outcomes += [target.get_cik_for_symbol("OLD", cik_map=mapping), target.get_resolved_title("AAA"),
                     target._get_cached_cik_resolution("OLD")]
        results.append((outcomes, dump(path)))
    assert results[0] == results[1]


def test_cik_map_cache_matches_capture(tmp_path, monkeypatch):
    import sync_checkpoints as sync_state

    from gabi import edgar
    from gabi.infrastructure.providers import source_retry

    payload = {"0": {"cik_str": 1, "ticker": "AAA", "title": "Alpha"}, "1": {"cik_str": 22, "ticker": "BRK-B", "title": "B"}}

    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def raise_for_status(self):
            return None

        def json(self):
            return payload

        def iter_content(self, size):
            yield json.dumps(payload).encode()

    monkeypatch.setattr(requests, "get", lambda *a, **k: Response())
    monkeypatch.setattr(source_retry, "_pace", lambda *a: None)
    # The captured get_cik_map imported the flat sync_state retired in F7.29.
    monkeypatch.setitem(sys.modules, "gabi.sync_state", sync_state)
    results = []
    for label in ("old", "new"):
        directory = tmp_path / label
        monkeypatch.setattr(config, "DATA_DIR", directory)
        monkeypatch.setattr(config, "DB_PATH", directory / "gabi.db")
        cache = directory / "sec_cik_map.csv"
        monkeypatch.setattr(edgar, "CIK_CACHE", cache)
        if label == "old":
            namespace = captured("edgar", {"_CikCache", "get_cik_map", "_headers"}, {
                "CIK_CACHE": cache, "config": config, "pd": pd, "requests": requests, "TICKER_CIK_URL": edgar.TICKER_CIK_URL,
                "current_map": edgar.current_map, "datetime": datetime, "UTC": UTC, "__package__": "gabi",
                "__name__": "gabi.captured_edgar"})
            get_map = namespace["get_cik_map"]
        else:
            get_map = edgar.get_cik_map
        frames = [get_map(force_refresh=True), get_map()]
        results.append(([frame.to_dict("records") for frame in frames], cache.read_bytes(),
                        sync_state.get("sec", "all", "ticker-map")["fingerprint"]))
    assert results[0] == results[1]


def test_update_errors_from_selection_match_capture(tmp_path, monkeypatch):
    from gabi import edgar, storage

    results = []
    for label in ("old", "new"):
        path = tmp_path / label / "gabi.db"
        monkeypatch.setattr(config, "DB_PATH", path)
        if label == "old":
            legacy_edgar(path).storage.record_update_errors("sec_edgar", {"AAA": "boom", "BBB": ValueError("x")})
        else:
            monkeypatch.setattr(edgar, "_now", lambda: NOW)
            monkeypatch.setattr(storage, "get_connection", lambda: pytest.fail("legacy connection"))
            edgar._SelectionStore().errors({"AAA": "boom", "BBB": ValueError("x")})
        results.append(dump(path))
    assert results[0] == results[1]


def companyfacts(cik: int, *, filed="2012-02-01"):
    return {"cik": cik, "facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {"start": "2011-01-01", "end": "2011-12-31", "val": 10., "accn": f"r{cik}", "filed": filed, "form": "10-K",
         "fp": "FY", "fy": 2011},
        {"start": "2016-01-01", "end": "2016-12-31", "val": 11., "accn": f"s{cik}", "filed": "2017-02-01",
         "form": "10-K", "fp": "FY", "fy": 2016},
        {"start": "2015-01-01", "end": "2015-12-31", "val": 12., "accn": f"t{cik}", "filed": "2016-01-01",
         "form": "10-K", "fp": "FY", "fy": 2015}]}}},
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"end": "2011-12-31", "val": 5., "accn": f"r{cik}", "filed": filed, "form": "10-K", "fp": "FY", "fy": 2011}]}}}}}


PAYLOADS = {"0000000001": companyfacts(1), "0000000002": companyfacts(3), "0000000004": companyfacts(4, filed="2008-01-01")}


def download_factory(directory: Path, log: list):
    def download(url, path):
        log.append((url, Path(path).relative_to(directory).as_posix()))
        cik = url.split("CIK")[1][:10]
        if cik == "0000000005":
            raise requests.ConnectionError("offline")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(PAYLOADS.get(cik, {"facts": {}})), encoding="utf-8")
        return Path(path)
    return download


@pytest.mark.parametrize("flow", ["gaps", "issuers"])
def test_companyfacts_recovery_matches_capture(tmp_path, monkeypatch, capsys, flow):
    from gabi import edgar
    from gabi.domain.market import sec_facts
    from gabi.infrastructure.legacy import sec_history

    monkeypatch.setattr(identity, "date", FixedDate)
    ciks = ["0000000001", "0000000002", "0000000004", "0000000005", "0000000006"]
    results = []
    for label in ("old", "new"):
        directory = tmp_path / label
        directory.mkdir()
        path = directory / "gabi.db"
        monkeypatch.setattr(config, "DB_PATH", path)
        pd.DataFrame({"cik": ciks[:-1]}).to_csv(directory / "sec-unmatched.csv", index=False)
        calls, imported = [], []
        archive = SimpleNamespace(register_source=lambda *a: imported.append(("source", a)),
                                  import_sec_facts=lambda *a, **k: imported.append((a, k)))
        download = download_factory(directory, calls)
        if label == "old":
            old_edgar = legacy_edgar(path)
            old_edgar.TRACKED_TAGS, old_edgar.SHARES_TAGS = edgar.TRACKED_TAGS, edgar.SHARES_TAGS
            old_edgar._extract_raw_facts, old_edgar.COMPANYFACTS_URL = sec_facts._extract_raw_facts, edgar.COMPANYFACTS_URL
            namespace = captured("sec_history", {"recover_companyfacts_gaps", "ingest_issuer_companyfacts"}, {
                "historical_archive": archive, "DIRECTORY": directory, "pd": pd, "json": json, "requests": requests,
                "download": download, "edgar": old_edgar})
            run = namespace["recover_companyfacts_gaps"] if flow == "gaps" else \
                (lambda: namespace["ingest_issuer_companyfacts"](set(ciks)))
        else:
            monkeypatch.setattr(sec_history, "DIRECTORY", directory)
            monkeypatch.setattr(sec_history, "download", download)
            monkeypatch.setattr(sec_history, "historical_archive", archive)
            monkeypatch.setattr(edgar, "_now", lambda: NOW)
            run = sec_history.recover_companyfacts_gaps if flow == "gaps" else \
                (lambda: sec_history.ingest_issuer_companyfacts(set(ciks)))
        try:
            outcome = run()
        except KeyError as exc:
            outcome = ("KeyError", str(exc))
        report = directory / "companyfacts_gaps_report.json"
        results.append((outcome, calls, imported, dump(path), report.read_bytes() if report.exists() else None,
                        capsys.readouterr().out))
    assert results[0] == results[1]
