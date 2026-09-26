"""Download and validate SEC's 2009-2015 structured archive, without inventing dates.

NUM.ddate and qtrs are rounded by SEC. Raw records are retained separately;
only original XBRL contexts supply exact dates for GABI's fact schema.
"""
import argparse
import hashlib
import json
import math
import sqlite3
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests
from lxml import etree

from . import config, edgar, historical_archive, storage

SCHEMA = """
CREATE TABLE IF NOT EXISTS sec_archive_files (
 url TEXT PRIMARY KEY, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sec_bulk_submissions (
 accn TEXT PRIMARY KEY, cik TEXT NOT NULL, name TEXT, sic TEXT, form TEXT,
 filed_date TEXT, accepted TEXT, fy TEXT, fp TEXT, instance TEXT, source_url TEXT
);
CREATE TABLE IF NOT EXISTS sec_bulk_facts (
 accn TEXT, tag TEXT, version TEXT, end_month TEXT, qtrs INTEGER, unit TEXT, val REAL,
 PRIMARY KEY(accn,tag,version,end_month,qtrs,unit,val)
);
CREATE INDEX IF NOT EXISTS idx_sec_bulk_cik ON sec_bulk_submissions(cik,filed_date);
"""
DIRECTORY = config.DATA_DIR / "history_refresh" / "validation_1996_2015"
TRACKED = set(edgar.TRACKED_TAGS + edgar.SHARES_TAGS)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    columns = conn.execute("PRAGMA table_info(sec_bulk_facts)").fetchall()
    if not next(column[5] for column in columns if column[1] == "val"):
        # Rounded NUM keys can contain distinct values. Retain all alternatives
        # for reconciliation instead of silently choosing the last one.
        conn.executescript("""
        BEGIN IMMEDIATE;
        ALTER TABLE sec_bulk_facts RENAME TO sec_bulk_facts_old;
        CREATE TABLE sec_bulk_facts (
         accn TEXT, tag TEXT, version TEXT, end_month TEXT, qtrs INTEGER, unit TEXT, val REAL,
         PRIMARY KEY(accn,tag,version,end_month,qtrs,unit,val)
        );
        INSERT INTO sec_bulk_facts SELECT * FROM sec_bulk_facts_old;
        DROP TABLE sec_bulk_facts_old;
        COMMIT;
        """)


def download(url: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        time.sleep(0.15)
        with requests.get(url, headers=edgar._headers(), timeout=(20, 90), stream=True) as response:
            response.raise_for_status()
            tmp = path.with_suffix(path.suffix + ".part")
            with tmp.open("wb") as f:
                for chunk in response.iter_content(1024 * 1024):
                    f.write(chunk)
            tmp.replace(path)
    with path.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    with storage.get_connection() as conn:
        ensure_schema(conn)
        prior = conn.execute("SELECT sha256 FROM sec_archive_files WHERE url=?", (url,)).fetchone()
        if prior and prior[0] != digest:
            raise ValueError("Cached source changed; review before replacing its provenance")
        conn.execute("INSERT OR IGNORE INTO sec_archive_files VALUES (?,?,?,?)",
                     (url, digest, path.stat().st_size, datetime.now(UTC).isoformat()))
        conn.commit()
    return path


def date8(value: str) -> str:
    return datetime.strptime(value, "%Y%m%d").date().isoformat()


def import_quarter(path: Path, source_url: str, ciks: set[str]) -> dict:
    result = {"submissions": 0, "facts": 0, "excluded_segment_or_coreg": 0, "invalid": 0}
    with zipfile.ZipFile(path) as z, storage.get_connection() as conn:
        ensure_schema(conn)
        with z.open("sub.txt") as f:
            sub = pd.read_csv(f, sep="\t", dtype=str, keep_default_na=False)
        sub["cik"] = sub["cik"].str.zfill(10)
        sub = sub[sub.cik.isin(ciks) & sub.form.isin(["10-K", "10-Q", "10-K/A", "10-Q/A"])]
        records = [(r.adsh, r.cik, r.name, r.sic, r.form, date8(r.filed), r.accepted,
                    r.fy, r.fp, r.instance, source_url) for r in sub.itertuples(index=False)]
        conn.executemany("INSERT OR REPLACE INTO sec_bulk_submissions VALUES (?,?,?,?,?,?,?,?,?,?,?)", records)
        result["submissions"] = len(records)
        accessions = set(sub.adsh)
        with z.open("num.txt") as f:
            for chunk in pd.read_csv(f, sep="\t", dtype=str, keep_default_na=False, chunksize=200000):
                selected = chunk[chunk.adsh.isin(accessions) & chunk.tag.isin(TRACKED)
                                 & chunk.version.str.match(r"^(us-gaap|dei)/")]
                consolidated = (selected.coreg == "") & (selected.get("segments", "") == "")
                result["excluded_segment_or_coreg"] += int((~consolidated).sum())
                fact_records = []
                for r in selected[consolidated].itertuples(index=False):
                    try:
                        val, qtrs = float(r.value), int(r.qtrs)
                        if not math.isfinite(val) or qtrs < 0 or r.uom != ("shares" if r.tag in edgar.SHARES_TAGS else "USD"):
                            raise ValueError("invalid value or unit")
                        fact_records.append((r.adsh, r.tag, r.version, date8(r.ddate), qtrs, r.uom, val))
                    except ValueError:
                        result["invalid"] += 1
                conn.executemany("INSERT OR REPLACE INTO sec_bulk_facts VALUES (?,?,?,?,?,?,?)", fact_records)
                result["facts"] += len(fact_records)
        conn.commit()
    return result


def parse_instance(content: bytes, *, cik: str, accn: str, filed_date: str, form: str, fp: str, fy: str) -> list[dict]:
    """Consolidated standard facts only; exact XBRL context dates, never NUM dates."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    root = etree.fromstring(content, parser)
    ns = {"x": "http://www.xbrl.org/2003/instance"}
    contexts = {}
    for context in root.findall("x:context", ns):
        identifier = context.find("x:entity/x:identifier", ns)
        if identifier is None or (identifier.text or "").strip().zfill(10) != cik:
            continue
        if context.find("x:entity/x:segment", ns) is not None or context.find("x:scenario", ns) is not None:
            continue
        period = context.find("x:period", ns)
        if period is None:
            continue
        instant, start, end = (period.findtext(f"x:{tag}", namespaces=ns) for tag in ["instant", "startDate", "endDate"])
        instant, start, end = ((value.strip() if value else None) for value in (instant, start, end))
        end = instant or end
        if end:
            datetime.fromisoformat(end)
            if start:
                datetime.fromisoformat(start)
            contexts[context.get("id")] = (start or "", end)
    units = {}
    for unit in root.findall("x:unit", ns):
        measures = unit.findall("x:measure", ns)
        if len(measures) == 1 and unit.find("x:divide", ns) is None:
            units[unit.get("id")] = (measures[0].text or "").strip().split(":")[-1]
    records: dict = {}
    conflicts = set()
    for node in root:
        if not isinstance(node.tag, str):
            continue
        qname = etree.QName(node)
        tag = qname.localname
        if tag not in TRACKED or not any(f"/{part}/" in (qname.namespace or "") for part in ["us-gaap", "dei"]):
            continue
        context = contexts.get(node.get("contextRef"))
        unit = units.get(node.get("unitRef"))
        if not context or unit != ("shares" if tag in edgar.SHARES_TAGS else "USD"):
            continue
        try:
            val = float(node.text or "")
        except ValueError:
            continue
        if not math.isfinite(val):
            continue
        key = (tag, unit, *context)
        if key in records and records[key]["val"] != val:
            conflicts.add(key)
        records[key] = dict(tag=tag, unit=unit, start_date=context[0], end_date=context[1], val=val,
                            form=form, fp=fp, fy=int(fy) if fy else None, filed_date=filed_date, accn=accn)
    return [row for key, row in records.items() if key not in conflicts]


def target_ciks() -> set[str]:
    with storage.get_connection() as conn:
        return {r[0] for r in conn.execute("SELECT DISTINCT cik FROM historical_issuer_candidates WHERE observed_from<'2016-01-01'")}


def run_bulk() -> dict:
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    backup_path = DIRECTORY / "before_validation.db"
    if not backup_path.exists():
        with storage.get_connection() as conn, sqlite3.connect(backup_path) as backup:
            conn.backup(backup)
    report_path = DIRECTORY / "bulk_report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    ciks = target_ciks()
    for year in range(2009, 2016):
        for quarter in range(1, 5):
            key = f"{year}q{quarter}"
            if report.get(key, {}).get("status") == "complete":
                continue
            url = f"https://www.sec.gov/files/dera/data/financial-statement-data-sets/{key}.zip"
            try:
                path = download(url, DIRECTORY / f"{key}.zip")
                report[key] = {"status": "complete", **import_quarter(path, url, ciks)}
            except (requests.RequestException, ValueError, zipfile.BadZipFile) as exc:
                report[key] = {"status": "failed", "error": str(exc)[:180]}
            report_path.write_text(json.dumps(report, indent=2) + "\n")
            print(key, report[key], flush=True)
    return report


def recover_instances(limit: int = 100, *, quarterly: bool = False, unmatched: bool = False) -> dict:
    """Recover original contexts for filings lacking exact facts in the local cache."""
    historical_archive.register_source("sec-original-xbrl", {
        "start": "2009-01-01", "end_exclusive": "2016-01-01",
        "quality": "exact_contexts_from_original_SEC_XBRL; ticker_identity_not_certified",
        "provenance": "sec_archive_files and instances_report.json contain URLs and file hashes",
    })
    with storage.get_connection() as conn:
        forms = ["10-Q", "10-Q/A", "10-K/A", "10-K"] if unmatched else ["10-Q", "10-Q/A", "10-K/A"] if quarterly else ["10-K"]
        placeholders = ",".join("?" for _ in forms)
        submissions = pd.read_sql_query(f"SELECT * FROM sec_bulk_submissions WHERE form IN ({placeholders}) ORDER BY filed_date,accn", conn, params=forms)
        existing = {a for a, in conn.execute("SELECT DISTINCT accn FROM edgar_facts UNION SELECT DISTINCT json_extract(payload_json,'$.accn') FROM historical_facts")}
    report_path = DIRECTORY / "instances_report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    if unmatched:
        accessions = set(pd.read_csv(DIRECTORY / "sec-unmatched.csv").accn)
        missing = submissions[submissions.accn.isin(accessions)]
    else:
        missing = submissions[~submissions.accn.isin(existing)]
    for r in missing.head(limit).itertuples(index=False):
        if report.get(r.accn, {}).get("status") == "complete" and not unmatched:
            continue
        url = f"https://www.sec.gov/Archives/edgar/data/{int(r.cik)}/{r.accn.replace('-', '')}/{r.instance}"
        try:
            path = download(url, DIRECTORY / "instances" / f"{r.accn}.xml")
            rows = parse_instance(path.read_bytes(), cik=r.cik, accn=r.accn, filed_date=r.filed_date,
                                  form=r.form, fp=r.fp, fy=r.fy)
            # The source symbol is explicitly a CIK placeholder, never a ticker alias.
            historical_archive.import_sec_facts("sec-original-xbrl", f"CIK{r.cik}", r.cik, rows, source_url=url)
            report[r.accn] = {"status": "complete", "cik": r.cik, "rows": len(rows), "url": url}
        except (requests.RequestException, ValueError, etree.XMLSyntaxError) as exc:
            report[r.accn] = {"status": "failed", "error": str(exc)[:180], "url": url}
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(r.accn, report[r.accn]["status"], flush=True)
    return report


def recover_companyfacts_gaps() -> dict:
    """Resolve unmatched bulk issuers directly by CIK; no ticker mapping needed."""
    historical_archive.register_source("sec-companyfacts-gap-recovery", {
        "start": "2009-01-01", "end_exclusive": "2016-01-01",
        "quality": "SEC issuer facts; historical ticker identity not certified",
        "provenance": "companyfacts_gaps_report.json and sec_archive_files",
    })
    gaps = pd.read_csv(DIRECTORY / "sec-unmatched.csv", dtype={"cik": str})
    report = {}
    for cik in sorted(set(gaps.cik)):
        url = edgar.COMPANYFACTS_URL.format(cik=cik)
        try:
            path = download(url, DIRECTORY / "companyfacts" / f"CIK{cik}.json")
            payload = json.loads(path.read_text(encoding="utf-8"))
            if str(payload["cik"]).zfill(10) != cik:
                raise ValueError("Company Facts issuer mismatch")
            rows = edgar._extract_raw_facts(payload, edgar.TRACKED_TAGS)
            rows += edgar._extract_raw_facts(payload, edgar.SHARES_TAGS, unit="shares")
            rows = [r for r in rows if r.get("filed_date") and "2009-01-01" <= r["filed_date"] < "2016-01-01"]
            historical_archive.import_sec_facts("sec-companyfacts-gap-recovery", f"CIK{cik}", cik, rows, source_url=url)
            report[cik] = {"status": "complete", "rows": len(rows), "url": url}
        except (requests.RequestException, ValueError) as exc:
            report[cik] = {"status": "failed", "error": str(exc)[:180], "url": url}
        (DIRECTORY / "companyfacts_gaps_report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(cik, report[cik]["status"], flush=True)
    return report


def ingest_issuer_companyfacts(ciks: set[str]) -> dict:
    """Company Facts for historical issuers, attributed by CIK only (#32).

    Rows go to ``entity_observations`` under a ``CIK##########`` placeholder
    symbol, never under a ticker, so the legacy ticker-keyed table cannot mix
    a predecessor's facts with a later company reusing the symbol.
    """
    report = {}
    for cik in sorted(str(value).zfill(10) for value in ciks):
        url = edgar.COMPANYFACTS_URL.format(cik=cik)
        try:
            path = download(url, DIRECTORY / "companyfacts" / f"CIK{cik}.json")
            payload = json.loads(path.read_text(encoding="utf-8"))
            if str(payload["cik"]).zfill(10) != cik:
                raise ValueError("Company Facts issuer mismatch")
            rows = edgar._extract_raw_facts(payload, edgar.TRACKED_TAGS)
            rows += edgar._extract_raw_facts(payload, edgar.SHARES_TAGS, unit="shares")
            edgar.upsert_edgar_facts(f"CIK{cik}", rows, cik=cik)
            report[cik] = {"status": "complete", "rows": len(rows)}
        except (requests.RequestException, ValueError, KeyError) as exc:
            report[cik] = {"status": "failed", "error": str(exc)[:180]}
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instances", type=int, default=0)
    parser.add_argument("--quarterly", action="store_true")
    parser.add_argument("--companyfacts-gaps", action="store_true")
    parser.add_argument("--unmatched", action="store_true")
    args = parser.parse_args()
    if args.companyfacts_gaps:
        recover_companyfacts_gaps()
    elif args.instances:
        recover_instances(args.instances, quarterly=args.quarterly, unmatched=args.unmatched)
    else:
        run_bulk()
