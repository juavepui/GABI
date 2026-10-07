"""Files, SQLite and the old SEC archive for the 1996-2015 validation commands (ADR 0002)."""
import json
import sqlite3
from pathlib import Path

import pandas as pd

from gabi.domain.research.sec_reconciliation import compare, summary
from gabi.infrastructure.providers.sec_filings import extract_reviewed
from gabi.infrastructure.storage.quarterly_coverage import read_facts


def directory(data_dir: Path) -> Path:
    return data_dir / "history_refresh" / "validation_1996_2015"


def run_reconciliation(data_dir: Path) -> dict:
    database = data_dir / "gabi.db"
    with sqlite3.connect(database, timeout=30) as conn:
        bulk = pd.read_sql_query("SELECT s.cik,f.* FROM sec_bulk_facts f JOIN sec_bulk_submissions s USING(accn)", conn)
    frames = [frame.assign(cik=cik) for cik, frame in read_facts(database).items()]
    result = compare(bulk, pd.concat(frames, ignore_index=True))
    output = directory(data_dir)
    result[result.comparison != "matches"].to_csv(output / "sec-unmatched.csv", index=False)
    values = summary(result)
    (output / "reconciliation.json").write_text(json.dumps(values, indent=2) + "\n")
    return values


def run_legacy_pilot(data_dir: Path) -> dict:
    """Explicit write: downloads the three pinned filings once and imports their reviewed facts."""
    from gabi import historical_archive, sec_history

    manifest = Path(sec_history.__file__).with_name("resources") / "legacy_filings_pilot.json"
    output = directory(data_dir)
    report = {}
    for contract in json.loads(manifest.read_text(encoding="utf-8")):
        path = sec_history.download(contract["url"], output / "legacy" / contract["filename"])
        rows = extract_reviewed(path.read_bytes(), contract)
        source = "legacy-reviewed:" + contract["accn"]
        historical_archive.register_source(source, {"url": contract["url"], "sha256": contract["sha256"],
                                                    "review": "table/units/periods and transcription checks",
                                                    "start": "1996-01-01", "end_exclusive": "2009-01-01"})
        historical_archive.import_sec_facts(source, contract["symbol"], contract["cik"], rows, source_url=contract["url"])
        report[contract["symbol"]] = {"rows": len(rows), "checks": len(contract["checks"]),
                                      "filed_date": contract["filed_date"], "url": contract["url"], "status": "passed"}
    (output / "legacy_pilot_report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
