"""Download and validate SEC's 2009-2015 structured archive, without inventing dates.

NUM.ddate and qtrs are rounded by SEC. Raw records are retained separately;
only original XBRL contexts supply exact dates for GABI's fact schema.
"""
import argparse
import json
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests
from lxml import etree

from gabi.application.research import sec_archive_download, sec_bulk
from gabi.application.research import sec_quarter_ingest as quarter_ingest
from gabi.domain.research import sec_bulk as bulk_rules
from gabi.infrastructure.storage import sec_bulk as bulk_storage
from gabi.infrastructure.storage import sec_quarter_ingest as ingest_storage
from gabi.infrastructure.storage.sec_archive_download import SecArchiveFiles, SqliteSecArchiveProvenance

from . import config, edgar, historical_archive

SCHEMA = bulk_storage.SCHEMA
DIRECTORY = config.DATA_DIR / "history_refresh" / "validation_1996_2015"
TRACKED = set(edgar.TRACKED_TAGS + edgar.SHARES_TAGS)


ensure_schema = bulk_storage.initialize_compatibility


def download(url: str, path: Path) -> Path:
    sec_archive_download.download(url, str(path), files=SecArchiveFiles(),
        provenance=SqliteSecArchiveProvenance(config.DB_PATH), source=_download_chunks,
        now=lambda: datetime.now(UTC))
    return path


def _download_chunks(url: str):
    time.sleep(0.15)
    with requests.get(url, headers=edgar._headers(), timeout=(20, 90), stream=True) as response:
        response.raise_for_status()
        yield from response.iter_content(1024 * 1024)


date8 = bulk_rules.date8


def import_quarter(path: Path, source_url: str, ciks: set[str], *, facts: bool = True) -> dict:
    return sec_bulk.import_quarter(bulk_storage.LocalSecQuarter(path), bulk_storage.SqliteSecQuarter(config.DB_PATH),
                                   source_url, ciks, tracked=TRACKED, shares=set(edgar.SHARES_TAGS), facts=facts)


def parse_instance(content: bytes, *, cik: str, accn: str, filed_date: str, form: str, fp: str, fy: str) -> list[dict]:
    """Consolidated standard facts only; exact XBRL context dates, never NUM dates."""
    return bulk_rules.instance_facts(*ingest_storage.decode_instance(content), cik=cik, accn=accn,
                                     filed_date=filed_date, form=form, fp=fp, fy=fy,
                                     tracked=TRACKED, shares=set(edgar.SHARES_TAGS))


def _selection() -> ingest_storage.SqliteSecIngestSelection:
    # The compatibility setting is captured per operation, never mutated.
    return ingest_storage.SqliteSecIngestSelection(config.DB_PATH)


def _download_to_directory(url: str, name: str) -> Path:
    return download(url, DIRECTORY / name)


def _import(path: Path, url: str, ciks: set[str], facts: bool) -> dict:
    return import_quarter(path, url, ciks, facts=facts)


def target_ciks() -> set[str]:
    return _selection().candidate_ciks_before("2016-01-01")


def run_bulk() -> dict:
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    ingest_storage.backup_once(config.DB_PATH, DIRECTORY / "before_validation.db")
    return quarter_ingest.ingest_quarters(
        bulk_rules.quarter_keys(range(2009, 2016)), target_ciks(), download=_download_to_directory,
        import_quarter=_import, checkpoints=ingest_storage.JsonQuarterReport(DIRECTORY / "bulk_report.json"),
        errors=(requests.RequestException, ValueError, zipfile.BadZipFile), log=_log)


def _log(*values) -> None:
    print(*values, flush=True)


def recover_instances(limit: int = 100, *, quarterly: bool = False, unmatched: bool = False) -> dict:
    """Recover original contexts for filings lacking exact facts in the local cache."""
    historical_archive.register_source("sec-original-xbrl", {
        "start": "2009-01-01", "end_exclusive": "2016-01-01",
        "quality": "exact_contexts_from_original_SEC_XBRL; ticker_identity_not_certified",
        "provenance": "sec_archive_files and instances_report.json contain URLs and file hashes",
    })
    reviewed = set(pd.read_csv(DIRECTORY / "sec-unmatched.csv").accn) if unmatched else None

    def import_facts(symbol: str, cik: str, rows: list[dict], url: str) -> None:
        # The source symbol is explicitly a CIK placeholder, never a ticker alias.
        historical_archive.import_sec_facts("sec-original-xbrl", symbol, cik, rows, source_url=url)

    return quarter_ingest.recover_instances(
        _selection(), limit=limit, quarterly=quarterly, unmatched=reviewed,
        checkpoints=ingest_storage.JsonQuarterReport(DIRECTORY / "instances_report.json"),
        fetch=lambda url, name: _download_to_directory(url, name).read_bytes(), parse=parse_instance, import_facts=import_facts,
        errors=(requests.RequestException, ValueError, etree.XMLSyntaxError), log=_log)


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
