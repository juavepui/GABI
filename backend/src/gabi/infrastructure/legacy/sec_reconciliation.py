"""Files and SQLite for `gabi_cli research sec-reconciliation`; exact facts still come from the old coverage reader."""
import json
import sqlite3
from pathlib import Path

import pandas as pd

from gabi.domain.research.sec_reconciliation import compare, summary


def directory(data_dir: Path) -> Path:
    return data_dir / "history_refresh" / "validation_1996_2015"


def run(data_dir: Path) -> dict:
    from gabi.historical_coverage import read_facts

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
