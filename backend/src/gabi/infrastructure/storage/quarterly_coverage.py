"""Read-only historical coverage inputs; source hashes are not rewritten."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

from gabi.application.research.quarterly_coverage import CoverageMetadata, CoverageReport
from gabi.domain.research.coverage import unique_historical_ciks
from gabi.domain.research.quarterly_coverage import CompanyCoverageInputs
from gabi.infrastructure.storage.readonly import connect_readonly


def issuer_facts(connection: sqlite3.Connection, cik: str | None = None, *, max_rows: int = 100_000) -> dict[str, pd.DataFrame]:
    if max_rows <= 0:
        raise ValueError("Invalid issuer fact row limit")
    query = ("SELECT e.cik,o.payload_json FROM entity_observations o JOIN entities e USING(entity_id) "
             "WHERE o.dataset='edgar_facts' AND json_extract(o.payload_json,'$.filed_date')<'2016-01-01'")
    params: tuple = ()
    if cik is not None:
        query += " AND e.cik=?"
        params = (cik,)
    cursor = connection.execute(query + " LIMIT ?", (*params, max_rows + 1))
    records: dict = {}
    for index, (issuer, payload) in enumerate(cursor):
        if index == max_rows:
            raise ValueError("Issuer fact row limit exceeded")
        if issuer:
            records.setdefault(issuer, []).append(json.loads(payload))
    return {issuer: pd.DataFrame(rows).drop_duplicates(["tag", "unit", "start_date", "end_date", "accn"])
            for issuer, rows in records.items()}


def read_facts(path: Path, *, max_rows: int = 1_000_000) -> dict[str, pd.DataFrame]:
    """Compatibility input for explicit SEC reconciliation; rejects overflow."""
    with closing(connect_readonly(path)) as connection:
        return issuer_facts(connection, max_rows=max_rows)


class SqliteQuarterlyCoverage:
    def __init__(self, connection: sqlite3.Connection, before: sqlite3.Connection, live_csv: Path,
                 manifest: Path, pilot: Path, *, max_rows: int = 100_000, max_price_rows: int = 25_000,
                 max_file_bytes: int = 2_000_000):
        if min(max_rows, max_price_rows, max_file_bytes) <= 0:
            raise ValueError("Invalid quarterly coverage limits")
        self.connection = connection
        self.before = before
        self.live_csv = live_csv
        self.manifest = manifest
        self.pilot = pilot
        self.max_rows = max_rows
        self.max_price_rows = max_price_rows
        self.max_file_bytes = max_file_bytes
        self.price_source: str | None = None

    def _frame(self, query: str, params=(), *, price: bool = False):
        limit = self.max_price_rows if price else self.max_rows
        frame = pd.read_sql_query(query + " LIMIT ?", self.connection, params=(*params, limit + 1))
        if len(frame) > limit:
            raise ValueError("Quarterly coverage row limit exceeded")
        return frame

    def _file(self, path: Path):
        if path.stat().st_size > self.max_file_bytes:
            raise ValueError("Quarterly coverage file limit exceeded")

    def metadata(self) -> CoverageMetadata:
        for path in (self.manifest, self.pilot, self.live_csv):
            self._file(path)
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.price_source = manifest["price_source_id"]
        members = self._frame("SELECT date,tickers FROM historical_membership WHERE source_id=? ORDER BY date",
                              (manifest["membership_source_id"],))
        candidates = self._frame("SELECT symbol,cik,date_added,observed_from AS created_at FROM historical_issuer_candidates WHERE source_id=?",
                                 (manifest["issuer_source_id"],))
        stored = dict(self._frame("SELECT symbol,cik FROM edgar_metrics").itertuples(index=False, name=None))
        live_frame = pd.read_csv(self.live_csv, dtype=str)
        live = dict(zip(live_frame.symbol, live_frame.cik.str.zfill(10), strict=True))
        targets = {symbol for value in members.tickers for symbol in value.split(",")}
        mappings, blocked = unique_historical_ciks(candidates, targets, live, stored)
        pilot = json.loads(self.pilot.read_text(encoding="utf-8"))
        mappings.update({row["symbol"]: row["cik"] for row in pilot if row["symbol"] not in mappings})
        return CoverageMetadata(members, mappings, blocked)

    def _prices(self, symbol: str, *, archive: bool = False) -> pd.DataFrame:
        params: tuple
        if archive:
            query = ("SELECT date,close,adj_close FROM historical_prices WHERE source_id=? "
                     "AND symbol=? AND date<'2016-01-01'")
            params = (self.price_source, symbol)
        else:
            query = "SELECT date,close,adj_close FROM prices WHERE symbol=? AND date<'2016-01-01' AND adj_close>0 AND close>0"
            params = (symbol,)
        frame = self._frame(query, params, price=True)
        frame["date"] = pd.to_datetime(frame.date)
        return frame.set_index("date").sort_index()

    def benchmark(self) -> pd.DataFrame:
        return self._prices("SPY")

    def company(self, symbol: str, cik: str) -> CompanyCoverageInputs:
        facts = issuer_facts(self.connection, cik, max_rows=self.max_rows).get(cik, pd.DataFrame())
        before = issuer_facts(self.before, cik, max_rows=self.max_rows).get(cik, pd.DataFrame())
        splits = self._frame("SELECT symbol,date,ratio FROM splits WHERE symbol=?", (symbol,))
        aliases = self._frame("SELECT * FROM entity_aliases WHERE symbol=?", (symbol,))
        return CompanyCoverageInputs(self._prices(symbol), self._prices(symbol, archive=True), facts, before, splits, aliases)


class FileQuarterlyCoverage:
    def __init__(self, output: Path):
        self.output = output

    def save(self, report: CoverageReport) -> None:
        self.output.mkdir(parents=True, exist_ok=True)
        for name, frame in (("price-validation.csv", report.comparisons), ("company-quarter.csv", report.details),
                            ("quarterly.csv", report.quarters), ("missing-metrics.csv", report.missing)):
            frame.to_csv(self.output / name, index=False)
        (self.output / "summary.json").write_text(json.dumps(report.summary, indent=2) + "\n")
