"""Captured parity of SEC quarter/instance ingestion, selection, checkpoints and read-only boundaries."""

import ast
import json
import sqlite3
import zipfile
from contextlib import closing, contextmanager
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import requests
from lxml import etree

from gabi import config
from gabi.domain.market.identity import normalize_cik
from gabi.infrastructure.legacy import historical_identity_audit, sec_history
from gabi.infrastructure.storage.backups import backup_once
from gabi.infrastructure.storage.sec_quarter_ingest import JsonQuarterReport, SqliteSecIngestSelection

REFERENCE = json.loads((Path(__file__).parent / "fixtures/sec_quarter_ingest_migration.json").read_text(encoding="utf-8"))
SOURCE = historical_identity_audit.CANDIDATE_SOURCE
NOMINATIONS = [
    {"label": "NOM", "cik": "0000000009", "valid_from": "2011-01-01", "valid_to": "2013-01-01",
     "evidence_window_days": 30, "sec_tickers": ["NOM"]},
    {"label": "LATE", "cik": "0000000010", "valid_from": "2017-01-01", "valid_to": "2019-01-01",
     "evidence_window_days": 0, "sec_tickers": ["LATE"]},
]


def captured(module: str, names: set[str], namespace: dict) -> dict:
    source = REFERENCE[module]
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            exec(ast.get_source_segment(source, node), namespace)
    return namespace


def connection_factory(path):
    @contextmanager
    def get_connection():
        with closing(sqlite3.connect(path, timeout=30)) as db:
            db.row_factory = None
            yield db
    return get_connection


def seed(path: Path) -> None:
    with closing(sqlite3.connect(path)) as db:
        db.executescript(sec_history.SCHEMA)
        db.executescript("""
            CREATE TABLE historical_issuer_candidates (source_id TEXT, symbol TEXT, cik TEXT, name TEXT,
                date_added TEXT, date_removed TEXT, observed_from TEXT);
            CREATE TABLE historical_identity_intervals (source_id TEXT, symbol TEXT, cik TEXT, valid_from TEXT,
                valid_to TEXT, status TEXT);
            CREATE TABLE edgar_facts (symbol TEXT, accn TEXT);
            CREATE TABLE historical_facts (payload_json TEXT);
        """)
        db.executemany("INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)", [
            (SOURCE, "AAA", "1", "Alpha", "2010-01-01", None, "2009-06-01"),
            (SOURCE, "BBB", "0000000002", "Beta", "2009-03-01*", "2012-06-30", "2015-12-31"),
            (SOURCE, "CCC", "0000000003", "Gamma", "2014-01-01", "", "2016-01-01"),
            (SOURCE, "OLD", "0000000004", "Old", "2001-01-01", "2009-12-31", "2001-01-01"),
            (SOURCE, "NEW", "0000000005", "New", "2017-01-01*", None, "2017-01-01"),
            ("other", "XXX", "0000000006", "Other", "2010-01-01", None, "2009-01-01"),
        ])
        filings = []
        for cik, years in (("0000000001", range(2010, 2016)), ("0000000002", (2010, 2011, 2012)),
                           ("0000000003", (2014,)), ("0000000009", (2010, 2011, 2012)), ("0000000005", (2017, 2018))):
            for year in years:
                for form, month in (("10-K", "02"), ("10-Q", "05"), ("10-K/A", "08")):
                    filings.append((f"{cik[-1]}-{year}-{month}", cik, "Issuer", "1000", form, f"{year}-{month}-01",
                                    "", str(year), "FY", f"i{year}{month}.xml" if month != "08" else None, "src"))
        db.executemany("INSERT INTO sec_bulk_submissions VALUES (?,?,?,?,?,?,?,?,?,?,?)", filings)
        db.executemany("INSERT INTO historical_identity_intervals VALUES (?,?,?,?,?,?)", [
            ("hist-2010", "AAA", "1", "2011-01-01", "2013-01-01", "unresolved"),
            ("hist-2010", "BBB", "0000000002", "2010-01-01", "2012-01-01", "corroborated_candidate"),
            ("hist-2010", "CCC", "0000000003", "2014-01-01", "2016-01-01", "unresolved"),
            ("hist-2016", "NEW", "0000000005", "2017-01-01", "2019-01-01", "unresolved"),
        ])
        db.executemany("INSERT INTO edgar_facts VALUES (?,?)", [("A", "1-2010-02"), ("A", "1-2011-05")])
        db.execute("INSERT INTO historical_facts VALUES (?)", (json.dumps({"accn": "2-2010-02"}),))
        db.commit()


class Calls:
    def __init__(self, directory: Path, failing: set[str] = frozenset()):
        self.directory, self.failing, self.log = directory, failing, []

    def download(self, url, path):
        self.log.append(("download", url, Path(path).relative_to(self.directory).as_posix()))
        if any(key in url for key in self.failing):
            raise requests.HTTPError(f"fail {url}")
        return Path(path)

    def import_quarter(self, path, url, ciks, *, facts=True):
        self.log.append(("import", Path(path).name, url, tuple(sorted(ciks)), facts))
        if "2011q2" in url:
            raise zipfile.BadZipFile("bad zip")
        return {"submissions": len(ciks), "facts": int(facts), "excluded_segment_or_coreg": 0, "invalid": 0}


@pytest.fixture
def workspace(tmp_path, monkeypatch, capsys):
    path = tmp_path / "gabi.db"
    seed(path)
    monkeypatch.setattr(config, "DB_PATH", path)
    return SimpleNamespace(root=tmp_path, path=path, capsys=capsys)


def test_target_ciks_and_resumable_bulk_match_capture(workspace, monkeypatch):
    results = []
    for label in ("old", "new"):
        directory = workspace.root / label
        directory.mkdir()
        (directory / "bulk_report.json").write_text(json.dumps({"2009q1": {"status": "complete", "submissions": 7},
                                                                 "2009q2": {"status": "failed", "error": "x"}}))
        calls = Calls(directory, failing={"2012q3"})
        if label == "old":
            namespace = captured("sec_history", {"target_ciks", "run_bulk"}, {
                "storage": SimpleNamespace(get_connection=connection_factory(workspace.path)), "DIRECTORY": directory,
                "sqlite3": sqlite3, "json": json, "requests": requests, "zipfile": zipfile,
                "download": calls.download, "import_quarter": calls.import_quarter})
            ciks, report = namespace["target_ciks"](), namespace["run_bulk"]()
        else:
            monkeypatch.setattr(sec_history, "DIRECTORY", directory)
            monkeypatch.setattr(sec_history, "download", calls.download)
            monkeypatch.setattr(sec_history, "import_quarter", calls.import_quarter)
            ciks, report = sec_history.target_ciks(), sec_history.run_bulk()
        backup = directory / "before_validation.db"
        with closing(sqlite3.connect(backup)) as db:
            tables = sorted(name for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'"))
        results.append((ciks, report, calls.log, (directory / "bulk_report.json").read_bytes(),
                        workspace.capsys.readouterr().out, tables))
    assert results[0] == results[1]
    assert results[1][0] == {"1", "0000000002", "0000000006", "0000000004"}
    assert results[1][1]["2011q2"]["status"] == "failed" and results[1][1]["2012q3"]["status"] == "failed"


def test_backup_is_taken_once_and_an_absent_source_leaves_an_empty_copy(tmp_path):
    target = tmp_path / "backup" / "before.db"
    assert backup_once(tmp_path / "absent.db", target) is True
    assert not (tmp_path / "absent.db").exists()
    with closing(sqlite3.connect(target)) as db:
        assert db.execute("SELECT count(*) FROM sqlite_schema").fetchone() == (0,)
    assert backup_once(tmp_path / "absent.db", target) is False


INSTANCE = b'''<xbrl xmlns="http://www.xbrl.org/2003/instance" xmlns:g="http://fasb.org/us-gaap/2009"
  xmlns:d="http://xbrl.us/dei/2009" xmlns:iso="http://www.xbrl.org/2003/iso4217">
  <!-- comment nodes are skipped -->
  <context id="a"><entity><identifier scheme="sec">{cik}</identifier></entity>
  <period><startDate> 2009-01-01 </startDate><endDate>2009-12-31</endDate></period></context>
  <context id="i"><entity><identifier scheme="sec">{cik}</identifier></entity><period><instant>2009-12-31</instant></period></context>
  <context id="n"><entity><identifier scheme="sec">{cik}</identifier></entity></context>
  <context id="sc"><entity><identifier scheme="sec">{cik}</identifier></entity><period><instant>2009-12-31</instant></period>
  <scenario>x</scenario></context>
  <context id="blank"><entity><identifier scheme="sec"></identifier></entity><period><instant>2009-12-31</instant></period></context>
  <unit id="usd"><measure>iso:USD</measure></unit><unit id="sh"><measure>shares</measure></unit>
  <unit id="ratio"><divide><unitNumerator><measure>iso:USD</measure></unitNumerator>
  <unitDenominator><measure>shares</measure></unitDenominator></divide></unit>
  <g:Revenues contextRef="a" unitRef="usd">100</g:Revenues>
  <g:Revenues contextRef="sc" unitRef="usd">5</g:Revenues>
  <g:Revenues contextRef="blank" unitRef="usd">6</g:Revenues>
  <g:NetIncomeLoss contextRef="a" unitRef="usd">INF</g:NetIncomeLoss>
  <g:NetIncomeLoss contextRef="a" unitRef="ratio">3</g:NetIncomeLoss>
  <g:NetIncomeLoss contextRef="n" unitRef="usd">4</g:NetIncomeLoss>
  <g:Assets contextRef="i" unitRef="usd">abc</g:Assets>
  <d:EntityCommonStockSharesOutstanding contextRef="i" unitRef="sh">1000</d:EntityCommonStockSharesOutstanding>
  <d:EntityCommonStockSharesOutstanding contextRef="i" unitRef="usd">1000</d:EntityCommonStockSharesOutstanding>
  <g:StockholdersEquity contextRef="i" unitRef="usd">1</g:StockholdersEquity>
  <g:StockholdersEquity contextRef="i" unitRef="usd">2</g:StockholdersEquity>
  <g:StockholdersEquity contextRef="i" unitRef="usd">1</g:StockholdersEquity>
</xbrl>'''


def old_parse():
    from gabi import edgar
    return captured("sec_history", {"parse_instance"}, {"etree": etree, "datetime": __import__("datetime").datetime,
                                                        "math": __import__("math"), "TRACKED": sec_history.TRACKED,
                                                        "edgar": edgar})["parse_instance"]


@pytest.mark.parametrize("cik", ["0000000123", "0000000999"])
@pytest.mark.parametrize("fy", ["2009", ""])
def test_instance_parsing_matches_capture(cik, fy):
    content = INSTANCE.replace(b"{cik}", b"123")
    arguments = dict(cik=cik, accn="a-1", filed_date="2010-02-01", form="10-K", fp="FY", fy=fy)
    assert sec_history.parse_instance(content, **arguments) == old_parse()(content, **arguments)


@pytest.mark.parametrize("content", [
    INSTANCE.replace(b"{cik}", b"123").replace(b"2009-12-31</endDate>", b"2009-13-31</endDate>"),
    INSTANCE.replace(b"{cik}", b"123").replace(b"</xbrl>", b""),
])
def test_invalid_instances_fail_like_the_capture(content):
    arguments = dict(cik="0000000123", accn="a", filed_date="2010-02-01", form="10-K", fp="FY", fy="2009")
    with pytest.raises((ValueError, etree.XMLSyntaxError)) as old:
        old_parse()(content, **arguments)
    with pytest.raises(old.type):
        sec_history.parse_instance(content, **arguments)


@pytest.mark.parametrize("mode", [{"quarterly": False}, {"quarterly": True}, {"unmatched": True}])
def test_instance_recovery_matches_capture(workspace, monkeypatch, mode):
    results = []
    for label in ("old", "new"):
        directory = workspace.root / label
        directory.mkdir()
        pd.DataFrame({"accn": ["1-2012-05", "2-2010-02", "missing"]}).to_csv(directory / "sec-unmatched.csv", index=False)
        (directory / "instances_report.json").write_text(json.dumps({"1-2010-05": {"status": "complete"},
                                                                     "1-2012-02": {"status": "complete"}}))
        imported, sources, log = [], [], []

        def download(url, path, log=log):
            log.append((url, Path(path).relative_to(directory).as_posix()))
            if "i201205" in url:
                raise requests.ConnectionError("offline")
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            cik = url.split("/data/")[1].split("/")[0]
            Path(path).write_bytes(b"<bad" if "i201402" in url else INSTANCE.replace(b"{cik}", cik.encode()))
            return Path(path)

        archive = SimpleNamespace(register_source=lambda *a: sources.append(a),
                                  import_sec_facts=lambda *a, **k: imported.append((a, k)))
        if label == "old":
            namespace = captured("sec_history", {"recover_instances"}, {
                "storage": SimpleNamespace(get_connection=connection_factory(workspace.path)), "DIRECTORY": directory,
                "historical_archive": archive, "pd": pd, "json": json, "requests": requests, "etree": etree,
                "download": download, "parse_instance": sec_history.parse_instance})
            report = namespace["recover_instances"](7, **mode)
        else:
            monkeypatch.setattr(sec_history, "DIRECTORY", directory)
            monkeypatch.setattr(sec_history, "download", download)
            monkeypatch.setattr(sec_history, "historical_archive", archive)
            report = sec_history.recover_instances(7, **mode)
        results.append((report, imported, sources, log, (directory / "instances_report.json").read_bytes(),
                        workspace.capsys.readouterr().out))
    assert results[0] == results[1]
    assert results[1][3]


def audit_namespace(workspace, calls, directory):
    sec = SimpleNamespace(download=calls.download, import_quarter=calls.import_quarter, DIRECTORY=directory,
                          ensure_schema=sec_history.ensure_schema)
    return captured("historical_identity_audit", {"import_nominated_filings", "import_period_filings",
                                                  "fetch_candidate_instances", "annual_report_symbol_evidence",
                                                  "fetch_issuer_name_histories"}, {
        "storage": SimpleNamespace(get_connection=connection_factory(workspace.path)), "sec_history": sec,
        "identity_nominations": lambda: NOMINATIONS, "identity": SimpleNamespace(normalize_cik=normalize_cik),
        "CANDIDATE_SOURCE": SOURCE, "P2010": PERIODS[0], "Period": object, "date": date, "timedelta": timedelta, "Path": Path,
        "_date": historical_identity_audit._date, "config": config, "time": SimpleNamespace(
            monotonic=lambda: 0.0, sleep=lambda seconds: None), "threading": __import__("threading"),
        "requests": requests, "ThreadPoolExecutor": __import__("concurrent.futures").futures.ThreadPoolExecutor,
        "as_completed": __import__("concurrent.futures").futures.as_completed, "json": json})


PERIODS = [SimpleNamespace(years=range(2010, 2016), start="2010-01-01", end_exclusive="2016-01-01",
                           identity_source="hist-2010"),
           SimpleNamespace(years=range(2016, 2020), start="2016-01-01", end_exclusive="2020-01-01",
                           identity_source="hist-2016")]


@pytest.mark.parametrize("period", PERIODS)
@pytest.mark.parametrize("flow", ["import_nominated_filings", "import_period_filings"])
def test_identity_quarter_imports_match_capture(workspace, monkeypatch, period, flow):
    monkeypatch.setattr(historical_identity_audit, "P2010", PERIODS[0])
    monkeypatch.setattr(historical_identity_audit, "identity_nominations", lambda: NOMINATIONS)
    results = []
    for label in ("old", "new"):
        directory = workspace.root / label
        calls = Calls(directory)
        if label == "old":
            function = audit_namespace(workspace, calls, directory)[flow]
        else:
            monkeypatch.setattr(sec_history, "DIRECTORY", directory)
            monkeypatch.setattr(sec_history, "download", calls.download)
            monkeypatch.setattr(sec_history, "import_quarter", calls.import_quarter)
            function = getattr(historical_identity_audit, flow)
        try:
            outcome = function(period)
        except zipfile.BadZipFile as exc:
            outcome = ("raised", str(exc))
        results.append((outcome, calls.log, workspace.capsys.readouterr().out))
    assert results[0] == results[1]


@pytest.mark.parametrize("period", PERIODS)
@pytest.mark.parametrize("prioritize", [False, True])
def test_cover_selection_matches_capture(workspace, monkeypatch, period, prioritize):
    monkeypatch.setattr(historical_identity_audit, "identity_nominations", lambda: NOMINATIONS)
    monkeypatch.setattr(historical_identity_audit.time, "sleep", lambda seconds: None)
    results = []
    for label in ("old", "new"):
        data = workspace.root / label / "data"
        monkeypatch.setattr(config, "DATA_DIR", data)
        cached = data / "history_refresh" / "validation_1996_2015" / "instances" / "1-2010-02.xml"
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(b"cached")
        seen = []

        def download(url, path, seen=seen):
            seen.append(url)
            if "0000000003" in url or "/3/" in url:
                raise requests.ConnectionError("offline")
            return path

        calls = SimpleNamespace(download=download, import_quarter=None)
        if label == "old":
            function = audit_namespace(workspace, calls, data)["fetch_candidate_instances"]
        else:
            monkeypatch.setattr(sec_history, "download", download)
            function = historical_identity_audit.fetch_candidate_instances
        report = function(50, prioritize_unresolved=prioritize, period=period)
        results.append((report, sorted(seen)))
        workspace.capsys.readouterr()
    assert results[0] == results[1]


def test_interval_and_name_history_selection_match_capture(workspace):
    reader = SqliteSecIngestSelection(workspace.path)
    with closing(sqlite3.connect(workspace.path)) as db:
        for source in ("hist-2010", "hist-2016", "absent"):
            assert reader.intervals(source, ("unresolved", "corroborated_candidate")) == db.execute(
                "SELECT symbol,cik,valid_from,valid_to,status FROM historical_identity_intervals "
                "WHERE source_id=? AND status IN ('unresolved','corroborated_candidate')", (source,)).fetchall()
            assert reader.unresolved_ciks_with_filings(source) == [row[0] for row in db.execute(
                "SELECT DISTINCT cik FROM historical_identity_intervals WHERE source_id=? AND status='unresolved' "
                "AND cik IN (SELECT cik FROM sec_bulk_submissions GROUP BY cik HAVING COUNT(*)>=2) ORDER BY cik",
                (source,))]


def test_selection_is_read_only_and_absent_storage_is_absent_evidence(tmp_path, workspace):
    before = workspace.path.read_bytes()
    reader = SqliteSecIngestSelection(workspace.path)
    reader.candidate_ciks_before("2016-01-01")
    reader.period_filings("2010-01-01", "2016-01-01")
    reader.submissions(["10-K"])
    reader.accessions_with_facts()
    assert workspace.path.read_bytes() == before
    missing = SqliteSecIngestSelection(tmp_path / "absent" / "gabi.db")
    assert missing.candidate_ciks_before("2016-01-01") == set()
    assert missing.bulk_ciks_filed("2010-01-01", "2016-01-01") == set()
    assert missing.accessions_with_facts() == set()
    assert missing.period_filings("2010-01-01", "2016-01-01") == []
    with pytest.raises(ValueError, match="presentaciones"):
        missing.submissions(["10-K"])
    assert not (tmp_path / "absent").exists()


def test_selection_limits_fail_instead_of_truncating(workspace):
    with pytest.raises(ValueError, match="límite"):
        SqliteSecIngestSelection(workspace.path, max_rows=3).period_filings("2010-01-01", "2016-01-01")


def test_checkpoint_report_replaces_atomically(tmp_path, monkeypatch):
    report = JsonQuarterReport(tmp_path / "nested" / "report.json")
    assert report.load() == {}
    report.save({"2010q1": {"status": "complete"}})
    assert (tmp_path / "nested" / "report.json").read_text(encoding="utf-8") == \
        json.dumps({"2010q1": {"status": "complete"}}, indent=2) + "\n"

    def broken(*args):
        raise OSError("disk full")

    monkeypatch.setattr("gabi.infrastructure.storage.sec_quarter_ingest.os.replace", broken)
    with pytest.raises(OSError):
        report.save({"other": 1})
    assert report.load() == {"2010q1": {"status": "complete"}}
    assert [path.name for path in (tmp_path / "nested").iterdir()] == ["report.json"]


def annual_report_sources(directory: Path, imported: list):
    """Synthetic issuer evidence: one or several symbols per 10-K, and an archive that records proofs."""
    texts = {"2011": "AAA", "2012": "AAA ZZZ", "2014": "CCC", "2017": "NEW OTHER", "2018": "NEW"}
    lives = {"1": [2010, 2011, 2012, 2014], "0000000003": None, "0000000005": [2017, 2018]}

    def listing_life(cik):
        years = lives.get(cik)
        return None if years is None else {"name": f"Issuer {cik}", "annual_reports": [
            {"filed": f"{year}-03-01", "accession": f"{cik}-{year}"} for year in years]}

    def fetch_annual_report(cik, report):
        path = directory / f"{report['accession']}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(texts[report["filed"][:4]], encoding="utf-8")
        return f"https://www.sec.gov/{report['accession']}", path

    evidence = SimpleNamespace(listing_life=listing_life, fetch_annual_report=fetch_annual_report,
                               annual_report_symbols=lambda text, extended=False: set(text.split()))
    archive = SimpleNamespace(import_filing_identity_evidence=lambda records: imported.extend(records) or len(records))
    return evidence, archive


@pytest.mark.parametrize("period", PERIODS)
@pytest.mark.parametrize("limit", [0, 1, 10])
def test_annual_report_symbols_match_capture(workspace, monkeypatch, period, limit):
    import hashlib

    monkeypatch.setattr(historical_identity_audit, "P2010", PERIODS[0])
    monkeypatch.setattr(historical_identity_audit, "identity_nominations", lambda: NOMINATIONS)
    results = []
    for label in ("old", "new"):
        imported = []
        evidence, archive = annual_report_sources(workspace.root / label, imported)
        if label == "old":
            namespace = audit_namespace(workspace, Calls(workspace.root / label), workspace.root / label)
            namespace.update(issuer_evidence=evidence, historical_archive=archive, hashlib=hashlib)
            function = namespace["annual_report_symbol_evidence"]
        else:
            monkeypatch.setattr(historical_identity_audit, "issuer_evidence", evidence)
            monkeypatch.setattr(historical_identity_audit, "historical_archive", archive)
            function = historical_identity_audit.annual_report_symbol_evidence
        results.append((function(limit, period), imported))
    assert results[0] == results[1]
    if limit != 1:  # no report read, or room for every report: each period then stores a proof
        assert bool(results[1][1]) is (limit == 10)
    with pytest.raises(ValueError, match="nonnegative"):
        historical_identity_audit.annual_report_symbol_evidence(-1, PERIODS[0])


@pytest.mark.parametrize("period", PERIODS)
@pytest.mark.parametrize("limit", [0, 1, 5])
def test_issuer_name_histories_match_capture(workspace, monkeypatch, period, limit):
    results = []
    for label in ("old", "new"):
        data = workspace.root / label / "data"
        monkeypatch.setattr(config, "DATA_DIR", data)
        seen = []

        def download(url, path, seen=seen):
            seen.append(url)
            if "CIK0000000005" in url:
                raise requests.ConnectionError("offline")
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(json.dumps({"cik": 3}), encoding="utf-8")
            return path

        if label == "old":
            function = audit_namespace(workspace, SimpleNamespace(download=download, import_quarter=None),
                                       data)["fetch_issuer_name_histories"]
        else:
            monkeypatch.setattr(sec_history, "download", download)
            function = historical_identity_audit.fetch_issuer_name_histories
        report = function(limit, period)
        files = sorted(path.relative_to(data).as_posix() for path in data.rglob("*.json")) if data.exists() else []
        results.append((report, seen, files, workspace.capsys.readouterr().out))
    assert results[0] == results[1]
    assert results[1][0]["fetched"] + results[1][0]["failed"] == min(limit, 1)
    with pytest.raises(ValueError, match="nonnegative"):
        historical_identity_audit.fetch_issuer_name_histories(-1, PERIODS[0])
