"""Historical issuer/price audits without HTTP, threads or SQL in the facades: captured parity (#131)."""

import ast
import json
import sqlite3
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from test_sec_quarter_ingest_migration import NOMINATIONS, PERIODS, connection_factory, seed

from gabi import config, historical_issuer_evidence, historical_tiingo, sec_history
from gabi.application.research import sec_cover_downloads
from gabi.domain.market.identity import normalize_cik
from gabi.infrastructure.legacy import historical_identity_audit
from gabi.infrastructure.providers import sec_archive
from gabi.infrastructure.storage import historical_prices

REFERENCE = json.loads((Path(__file__).parent / "fixtures/historical_audits_migration.json").read_text(encoding="utf-8"))
SOURCE = historical_identity_audit.CANDIDATE_SOURCE


def captured(module: str, names: set[str], namespace: dict) -> dict:
    source = REFERENCE[module]
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            exec(ast.get_source_segment(source, node), namespace)
    return namespace


def http_error(status: int | None) -> requests.HTTPError:
    response = None
    if status is not None:
        response = requests.Response()
        response.status_code = status
    return requests.HTTPError(f"status {status}", response=response)


class Sec:
    """Scripted SEC answers per URL fragment; records every attempt and wait."""

    def __init__(self, script: dict[str, list]):
        self.script = {key: list(values) for key, values in script.items()}
        self.lock = threading.Lock()
        self.attempts: Counter = Counter()
        self.sleeps: list[float] = []

    def download(self, url, path):
        with self.lock:
            self.attempts[url] += 1
            key = next((key for key in self.script if key in url), None)
            outcome = self.script[key].pop(0) if key and self.script[key] else None
        if isinstance(outcome, BaseException):
            raise outcome
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"cover")
        return Path(path)

    def sleep(self, seconds):
        with self.lock:
            self.sleeps.append(seconds)


@pytest.fixture
def workspace(tmp_path, monkeypatch, capsys):
    path = tmp_path / "gabi.db"
    seed(path)
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(historical_identity_audit, "identity_nominations", lambda: NOMINATIONS)
    return SimpleNamespace(root=tmp_path, path=path, capsys=capsys)


SCRIPTS = {
    "transient": {"/1/": [http_error(429)], "/2/": [http_error(503), http_error(502), http_error(500)],
                  "/9/": [http_error(404)], "/3/": [requests.ConnectionError("offline")]},
    "local": {"/1/": [OSError("disk full")], "/2/": [ValueError("size")], "/9/": [http_error(None)]},
    "clean": {},
}


def run_covers(workspace, monkeypatch, label, script, limit, period, prioritize):
    data = workspace.root / label / "data"
    monkeypatch.setattr(config, "DATA_DIR", data)
    cached = data / "history_refresh" / "validation_1996_2015" / "instances" / "1-2010-02.xml"
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(b"cached")
    sec = Sec(script)
    clock = SimpleNamespace(monotonic=lambda: 0.0, sleep=sec.sleep)
    if label == "old":
        function = captured("historical_identity_audit", {"fetch_candidate_instances"}, {
            "storage": SimpleNamespace(get_connection=connection_factory(workspace.path)),
            "sec_history": SimpleNamespace(download=sec.download), "identity_nominations": lambda: NOMINATIONS,
            "identity": SimpleNamespace(normalize_cik=normalize_cik), "CANDIDATE_SOURCE": SOURCE,
            "P2010": PERIODS[0], "Period": object, "date": date, "timedelta": timedelta, "Path": Path,
            "_date": historical_identity_audit._date, "config": config, "time": clock, "threading": threading,
            "requests": requests, "ThreadPoolExecutor": ThreadPoolExecutor, "as_completed": as_completed,
        })["fetch_candidate_instances"]
    else:
        monkeypatch.setattr(historical_identity_audit, "time", clock)
        monkeypatch.setattr(sec_history, "download", sec.download)
        function = historical_identity_audit.fetch_candidate_instances
    try:
        outcome = function(limit, prioritize_unresolved=prioritize, period=period)
    except Exception as exc:  # noqa: BLE001 - the propagated type and message are compared
        outcome = ("raised", type(exc).__name__, str(exc))
    lines = sorted(workspace.capsys.readouterr().out.splitlines())
    files = sorted(path.name for path in cached.parent.iterdir())
    return outcome, dict(sec.attempts), sorted(sec.sleeps), lines, files


@pytest.mark.parametrize("script", sorted(SCRIPTS))
@pytest.mark.parametrize("limit", [0, 2, 50])
@pytest.mark.parametrize("period", PERIODS, ids=["2010", "2016"])
@pytest.mark.parametrize("prioritize", [False, True])
def test_cover_downloads_match_capture(workspace, monkeypatch, script, limit, period, prioritize):
    old = run_covers(workspace, monkeypatch, "old", SCRIPTS[script], limit, period, prioritize)
    new = run_covers(workspace, monkeypatch, "new", SCRIPTS[script], limit, period, prioritize)
    assert new == old


def test_unexpected_cover_errors_propagate_like_the_capture(workspace, monkeypatch):
    script = {"/1/": [RuntimeError("bug")]}
    old = run_covers(workspace, monkeypatch, "old", script, 50, PERIODS[0], False)
    new = run_covers(workspace, monkeypatch, "new", script, 50, PERIODS[0], False)
    assert new[0] == old[0] == ("raised", "RuntimeError", "bug")


def test_negative_limit_fails_before_any_read(workspace, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", workspace.root / "absent.db")
    with pytest.raises(ValueError, match="nonnegative"):
        historical_identity_audit.fetch_candidate_instances(-1)
    with pytest.raises(ValueError, match="nonnegative"):
        sec_cover_downloads.pending_covers({}, -1, cached=lambda accn: False)
    assert not (workspace.root / "absent.db").exists()


def test_pacer_is_shared_across_workers_and_counts_retries():
    now = [10.0]
    waits = []
    pace = sec_cover_downloads.Pacer(0.25, clock=lambda: now[0], wait=waits.append)
    for _ in range(4):
        pace()
    now[0] = 20.0
    pace()
    assert waits == [0.25, 0.5, 0.75]
    attempts = Counter()

    def download(url, accn):
        attempts[accn] += 1
        if attempts[accn] < 3:
            raise http_error(503)

    report = sec_cover_downloads.download_covers(
        [("a", "u")], download=download, errors=(requests.RequestException,), status=sec_archive.http_status,
        parallel=sec_archive.parallel, clock=lambda: 0.0, wait=waits.append, log=lambda message: None)
    assert report == {"fetched": 1, "failed": 0} and attempts["a"] == 3


def frame_namespace(sec, directory):
    names = {"FRAME_SPECS", "PERIODS", "ANNUAL_PERIODS", "FRAME_URL", "SUBMISSIONS_URL", "FILINGS_FROM", "FILINGS_TO"}
    namespace = {name: getattr(historical_issuer_evidence, name) for name in names}
    namespace.update(FRAMES_DIR=directory / "frames", SUBMISSIONS_DIR=directory / "submissions", Path=Path,
                     json=json, requests=requests, sec_history=SimpleNamespace(download=sec.download),
                     identity=SimpleNamespace(normalize_cik=normalize_cik))
    return captured("historical_issuer_evidence", {"_periods", "_frame_path", "fetch_frames", "fetch_submissions",
                                                   "fetch_annual_report", "fetch_report"}, namespace)


def run_evidence(tmp_path, monkeypatch, capsys, label, script, flow, seed_files):
    directory = tmp_path / label
    for name, body in seed_files.items():
        (directory / name).parent.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(body, encoding="utf-8")
    sec = Sec(script)
    if label == "old":
        module = SimpleNamespace(**frame_namespace(sec, directory))
    else:
        module = historical_issuer_evidence
        monkeypatch.setattr(module, "FRAMES_DIR", directory / "frames")
        monkeypatch.setattr(module, "SUBMISSIONS_DIR", directory / "submissions")
        monkeypatch.setattr(sec_history, "download", sec.download)
    try:
        outcome = flow(module)
    except Exception as exc:  # noqa: BLE001 - the propagated type and message are compared
        outcome = ("raised", type(exc).__name__, str(exc))
    files = sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file())
    return outcome, dict(sec.attempts), capsys.readouterr().out, files


FRAME_CASES = {
    "missing_and_cached": ({"Dividends": [http_error(404)], "EntityPublicFloat": [http_error(404)]},
                           {"frames/dei_EntityPublicFloat_USD_CY2010Q2I.json": "{}"}),
    "server_error": ({"EntityPublicFloat": [http_error(500)]}, {}),
    "transport_error": ({"EntityCommonStockSharesOutstanding": [requests.ConnectionError("down")]}, {}),
}


@pytest.mark.parametrize("case", sorted(FRAME_CASES))
def test_frame_downloads_match_capture(tmp_path, monkeypatch, capsys, case):
    script, files = FRAME_CASES[case]
    results = [run_evidence(tmp_path, monkeypatch, capsys, label, script, lambda module: module.fetch_frames(), files)
               for label in ("old", "new")]
    assert results[0] == results[1]


def submissions(cik, pages=()):
    return json.dumps({"cik": cik, "filings": {"files": list(pages)}})


SUBMISSION_FILES = {
    "submissions/CIK0000000001.json": submissions("1", [
        {"name": "CIK0000000001-submissions-001.json", "filingFrom": "2001-01-01", "filingTo": "2009-12-31"},
        {"name": "CIK0000000001-submissions-002.json", "filingFrom": "1994-01-01", "filingTo": "2000-12-31"},
        {"name": "CIK0000000001-submissions-003.json", "filingFrom": "2030-01-01", "filingTo": "2031-12-31"},
        {"name": "CIK0000000001-submissions-004.json"},
        # Pages touching the filing window bounds are read.
        {"name": "CIK0000000001-submissions-005.json", "filingFrom": "2027-01-01", "filingTo": "2027-06-30"},
        {"name": "CIK0000000001-submissions-006.json", "filingFrom": "2007-01-01", "filingTo": "2008-01-01"}]),
    "submissions/CIK0000000002.json": submissions("0000000099"),
    "submissions/CIK0000000003.json": "{not json",
    "submissions/CIK0000000004.json": json.dumps({"filings": {}}),
    "submissions/CIK0000000005.json": submissions("5", [{"filingFrom": "2010-01-01", "filingTo": "2011-01-01"}]),
}


@pytest.mark.parametrize("script", [{}, {"CIK0000000006.json": [requests.ConnectionError("down")],
                                         "submissions-004": [OSError("disk")]},
                                    {"CIK0000000006.json": [RuntimeError("bug")]}])
def test_submission_downloads_match_capture(tmp_path, monkeypatch, capsys, script):
    ciks = {"1", "0000000002", "3", "4", "5", "6"}
    results = [run_evidence(tmp_path, monkeypatch, capsys, label, script,
                            lambda module: module.fetch_submissions(ciks), SUBMISSION_FILES) for label in ("old", "new")]
    assert results[0] == results[1]
    assert results[1][1] or "RuntimeError" in str(results[1][0])


@pytest.mark.parametrize("flow", ["fetch_annual_report", "fetch_report"])
def test_document_urls_and_paths_match_capture(tmp_path, monkeypatch, flow):
    report = {"accession": "0000950123-10-012345", "primary": "dir/d10k.htm"}
    seen = []
    old = frame_namespace(SimpleNamespace(download=lambda url, path: seen.append((url, path)) or path), tmp_path)
    old.update(ANNUAL_DIR=historical_issuer_evidence.ANNUAL_DIR, TERMINAL_DIR=historical_issuer_evidence.TERMINAL_DIR)
    monkeypatch.setattr(sec_history, "download", lambda url, path: seen.append((url, path)) or path)
    assert getattr(historical_issuer_evidence, flow)("0000000042", report) == old[flow]("0000000042", report)
    assert seen[0] == seen[1]


def old_pinned(path, source_id):
    namespace = {"json": json, "storage": SimpleNamespace(get_connection=connection_factory(path)),
                 "historical_archive": SimpleNamespace(SCHEMA=historical_prices.SCHEMA)}
    return captured("historical_tiingo", {"_Archive"}, namespace)["_Archive"]().pinned(source_id)


def test_pinned_tiingo_files_match_capture_without_creating_schema(tmp_path, monkeypatch):
    path = tmp_path / "gabi.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    assert historical_tiingo._Archive().pinned("tiingo") == {} and not path.exists()
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE unrelated (x)")
        db.commit()
    before = path.read_bytes()
    assert historical_tiingo._Archive().pinned("tiingo") == {} and path.read_bytes() == before
    with closing(sqlite3.connect(path)) as db:
        db.executescript(historical_prices.SCHEMA)
        db.executemany("INSERT INTO historical_sources VALUES (?,?)", [
            ("tiingo", json.dumps({"files_sha256": {"AAA": "1" * 64, "BBB": "2" * 64}})),
            ("bare", json.dumps({"start": "2010-01-01"}))])
        db.commit()
    before = path.read_bytes()
    for source in ("tiingo", "bare", "absent"):
        assert historical_tiingo._Archive().pinned(source) == old_pinned(path, source)
    assert path.read_bytes() == before


def test_facades_no_longer_import_http_threads_or_sql():
    for module in (historical_identity_audit, historical_issuer_evidence, historical_tiingo, sec_history):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                    for alias in node.names}
        imported |= {node.module.split(".")[0] for node in ast.walk(tree)
                     if isinstance(node, ast.ImportFrom) and node.module and node.level == 0}
        assert not imported & {"requests", "lxml", "sqlite3", "threading", "concurrent"}, module.__name__
    assert not (Path(historical_tiingo.__file__).with_name("historical_data_audit.py")).exists()
