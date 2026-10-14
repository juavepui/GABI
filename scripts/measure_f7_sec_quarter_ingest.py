"""Synthetic parity and cold/warm measurement of SEC ingestion selection reads."""

import ast
import json
import sqlite3
import statistics
import sys
import tempfile
import time
import tracemalloc
from contextlib import closing, contextmanager
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
ISSUERS, YEARS = 600, range(2009, 2016)


def main():
    from gabi.application.research import sec_quarter_ingest
    from gabi.domain.market.identity import normalize_cik
    from gabi.domain.research import sec_bulk
    from gabi.infrastructure.legacy import historical_identity_audit, sec_history
    from gabi.infrastructure.storage.sec_quarter_ingest import SqliteSecIngestSelection

    reference = json.loads((ROOT / "backend/tests/fixtures/sec_quarter_ingest_migration.json").read_text(encoding="utf-8"))
    source = historical_identity_audit.CANDIDATE_SOURCE
    with tempfile.TemporaryDirectory(prefix="gabi-sec-ingest-") as directory:
        path = Path(directory) / "gabi.db"
        counters = {"selects": 0, "schema": 0}

        def trace(statement):
            head = statement.lstrip().upper()
            counters["selects"] += head.startswith("SELECT")
            counters["schema"] += head.startswith(("CREATE", "ALTER"))

        real_connect = sqlite3.connect

        def connect(*args, **kwargs):
            db = real_connect(*args, **kwargs)
            db.set_trace_callback(trace)
            return db

        @contextmanager
        def get_connection():
            with closing(sqlite3.connect(path, timeout=30)) as db:
                yield db

        with get_connection() as db:
            db.executescript(sec_history.SCHEMA)
            db.executescript("CREATE TABLE historical_issuer_candidates (source_id TEXT, symbol TEXT, cik TEXT, "
                             "name TEXT, date_added TEXT, date_removed TEXT, observed_from TEXT);"
                             "CREATE TABLE historical_identity_intervals (source_id TEXT, symbol TEXT, cik TEXT, "
                             "valid_from TEXT, valid_to TEXT, status TEXT);"
                             "CREATE TABLE edgar_facts (symbol TEXT, accn TEXT);"
                             "CREATE TABLE historical_facts (payload_json TEXT);")
            for i in range(1, ISSUERS + 1):
                cik = str(i).zfill(10)
                db.execute("INSERT INTO historical_issuer_candidates VALUES (?,?,?,?,?,?,?)",
                           (source, f"S{i}", cik, "Issuer", "2009-01-01", None, "2009-01-01"))
                db.executemany("INSERT INTO sec_bulk_submissions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                               [(f"{i}-{year}-{q}", cik, "Issuer", "1000", "10-K" if q == 1 else "10-Q",
                                 f"{year}-{q * 3:02d}-01", "", str(year), "FY", "i.xml", "src")
                                for year in YEARS for q in range(1, 5)])
                if i % 3 == 0:
                    db.execute("INSERT INTO historical_identity_intervals VALUES (?,?,?,?,?,?)",
                               ("hist", f"S{i}", cik, "2011-01-01", "2013-01-01", "unresolved"))
                db.execute("INSERT INTO edgar_facts VALUES (?,?)", (f"S{i}", f"{i}-2010-1"))
            db.commit()
        period = SimpleNamespace(years=range(2010, 2016), start="2010-01-01", end_exclusive="2016-01-01",
                                 identity_source="hist")
        old = {"storage": SimpleNamespace(get_connection=get_connection), "pd": pd, "date": date,
               "timedelta": timedelta, "identity_nominations": lambda: [], "CANDIDATE_SOURCE": source,
               "identity": SimpleNamespace(normalize_cik=normalize_cik), "_date": historical_identity_audit._date}

        def old_covers():
            with get_connection() as conn:
                candidates = conn.execute(
                    "SELECT DISTINCT symbol,cik,date_added,date_removed FROM historical_issuer_candidates "
                    "WHERE source_id=? AND date_added<? AND (date_removed IS NULL OR date_removed='' OR date_removed>=?)",
                    (source, period.end_exclusive, period.start)).fetchall()
                filings = conn.execute(
                    "SELECT accn,cik,filed_date,instance FROM sec_bulk_submissions WHERE filed_date>=? AND filed_date<? "
                    "AND form IN ('10-K','10-Q') AND instance IS NOT NULL ORDER BY filed_date,accn",
                    (period.start, period.end_exclusive)).fetchall()
                unresolved = conn.execute("SELECT cik,valid_from,valid_to FROM historical_identity_intervals "
                                          "WHERE source_id=? AND status='unresolved'", (period.identity_source,)).fetchall()
            return historical_identity_audit.instance_rules.select_cover_filings(
                candidates, filings, unresolved, start=period.start, end_exclusive=period.end_exclusive)

        for node in ast.parse(reference["sec_history"]).body:
            if isinstance(node, ast.FunctionDef) and node.name == "target_ciks":
                exec(ast.get_source_segment(reference["sec_history"], node), old)

        def old_missing():
            with get_connection() as conn:
                submissions = pd.read_sql_query("SELECT * FROM sec_bulk_submissions WHERE form IN (?) ORDER BY filed_date,accn",
                                                conn, params=["10-K"])
                existing = {a for a, in conn.execute("SELECT DISTINCT accn FROM edgar_facts UNION SELECT DISTINCT "
                                                     "json_extract(payload_json,'$.accn') FROM historical_facts")}
            return list(submissions[~submissions.accn.isin(existing)].accn)

        reader = SqliteSecIngestSelection(path)
        flows = {
            "CIK objetivo": (old["target_ciks"], lambda: reader.candidate_ciks_before("2016-01-01")),
            "Selección de covers": (old_covers, lambda: sec_quarter_ingest.cover_filings(
                reader, source, start=period.start, end_exclusive=period.end_exclusive, nominated=[],
                identity_source="hist", prioritize_unresolved=True)),
            "Instancias pendientes": (old_missing, lambda: list(sec_bulk.missing_instances(
                reader.submissions(["10-K"]), reader.accessions_with_facts()).accn)),
        }
        sqlite3.connect = connect
        try:
            results = {}
            for name, variants in flows.items():
                outputs, row = [], {}
                for label, run in zip(("anterior", "nuevo"), variants):
                    for key in counters:
                        counters[key] = 0
                    began = time.perf_counter()
                    output = run()
                    cold = time.perf_counter() - began
                    calls = dict(counters)
                    tracemalloc.start()
                    run()
                    peak = tracemalloc.get_traced_memory()[1] / 2**20
                    tracemalloc.stop()
                    warm = []
                    for _ in range(3):
                        began = time.perf_counter()
                        run()
                        warm.append(time.perf_counter() - began)
                    outputs.append(output)
                    row[label] = {"cold_s": round(cold, 4), "warm_median_s": round(statistics.median(warm), 4),
                                  "peak_python_mib": round(peak, 2), **calls}
                assert outputs[0] == outputs[1], name
                results[name] = row
        finally:
            sqlite3.connect = real_connect
    print(json.dumps({"issuers": ISSUERS, "submissions": ISSUERS * len(YEARS) * 4, "parity": True, "downloads": 0,
                      "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
