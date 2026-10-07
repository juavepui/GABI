"""Scoped SQLite/CSV inputs for the annual inventory; no schema or cache writes."""

import json
import sqlite3
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import exchange_calendars as xcals
import pandas as pd

from gabi.application.research.historical_data_audit import AuditMetadata
from gabi.domain.research.coverage import CoverageParameters
from gabi.domain.research.historical_data_audit import TickerInputs, annual_metrics


class SqliteAnnualAudit:
    """Connection lifetime belongs to the caller; each read rejects overflow."""

    def __init__(self, connection: sqlite3.Connection, membership_csv: Path, old_detail: Path,
                 manifest: Path, *, max_rows: int = 100_000, max_price_rows: int = 25_000,
                 max_file_bytes: int = 32_000_000, batch_size: int = 50, max_symbols: int = 1000):
        if min(max_rows, max_price_rows, max_file_bytes, batch_size, max_symbols) <= 0 or batch_size > 500:
            raise ValueError("Invalid annual audit resource limits")
        self.connection = connection
        self.membership_csv = membership_csv
        self.old_detail = old_detail
        self.manifest = manifest
        self.max_rows = max_rows
        self.max_price_rows = max_price_rows
        self.max_file_bytes = max_file_bytes
        self.batch_size = batch_size
        self.max_symbols = max_symbols
        self.archive_price_source: str | None = None

    def _file(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size > self.max_file_bytes:
            raise ValueError(f"Annual audit file exceeds limit: {path.name}")

    def _frame(self, query: str, params=(), *, price: bool = False) -> pd.DataFrame:
        limit = self.max_price_rows if price else self.max_rows
        frame = pd.read_sql_query(query + " LIMIT ?", self.connection, params=(*params, limit + 1))
        if len(frame) > limit:
            raise ValueError("Annual audit row limit exceeded; no truncated report produced")
        return frame

    def metadata(self) -> AuditMetadata:
        self._file(self.membership_csv)
        if not self.old_detail.is_file():
            raise FileNotFoundError(f"{self.old_detail}: run python -m gabi_cli research quarterly-coverage first")
        self._file(self.old_detail)
        self._file(self.manifest)
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.archive_price_source = manifest["price_source_id"]
        operational = pd.read_csv(self.membership_csv, dtype=str).sort_values("date")
        old = pd.read_csv(self.old_detail, dtype={"date": str, "missing_metrics": str})
        archive = self._frame("SELECT date,tickers FROM historical_membership WHERE source_id=? ORDER BY date",
                              (manifest["membership_source_id"],))
        aliases = self._frame("SELECT symbol,entity_id,valid_from,valid_to,confidence FROM entity_aliases "
                              "WHERE valid_from<='2026-12-31' AND (valid_to IS NULL OR valid_to>'2008-01-01')")
        issuer_entities = dict(self.connection.execute(
            "SELECT substr(json_extract(payload_json,'$.filed_date'),1,4),COUNT(DISTINCT entity_id) "
            "FROM entity_observations WHERE dataset='edgar_facts' "
            "AND json_extract(payload_json,'$.filed_date') BETWEEN '2008-01-01' AND '2026-12-31' GROUP BY 1"))
        last_spy = self.connection.execute("SELECT MAX(date) FROM prices WHERE symbol='SPY' AND adj_close>0").fetchone()[0]
        return AuditMetadata(operational, old, archive, aliases, issuer_entities, last_spy)

    def _prices(self, symbol: str, day: str) -> pd.DataFrame:
        frame = self._frame("SELECT date,close,adj_close FROM prices WHERE symbol=? AND date<=? ORDER BY date",
                            (symbol, day), price=True)
        frame["date"] = pd.to_datetime(frame.date)
        return frame.set_index("date")

    def _symbols(self, symbols: list[str]):
        if len(symbols) > self.max_symbols:
            raise ValueError("Annual audit symbol limit exceeded")
        for start in range(0, len(symbols), self.batch_size):
            yield symbols[start:start + self.batch_size]

    def _ticker_inputs(self, symbols: list[str], day: str) -> Iterator[TickerInputs]:
        for symbol in symbols:
            facts = self._frame(
                "SELECT tag,unit,start_date,end_date,val,form,fp,fy,filed_date,accn FROM edgar_facts "
                "WHERE symbol=? AND filed_date<=? AND end_date<=? ORDER BY filed_date,end_date,accn",
                (symbol, day, day))
            splits = self.connection.execute("SELECT ratio FROM splits WHERE symbol=? AND date>? LIMIT ?",
                                              (symbol, day, self.max_rows + 1)).fetchall()
            if len(splits) > self.max_rows:
                raise ValueError("Annual audit row limit exceeded; no truncated report produced")
            yield TickerInputs(symbol, facts, self._prices(symbol, day), tuple(row[0] for row in splits))

    def annual_metrics(self, symbols: list[str], day: str, parameters: CoverageParameters) -> dict[str, int]:
        benchmark = self._prices("SPY", day)
        sessions = xcals.get_calendar("XNYS", start="1994-01-01", end="2027-01-01").sessions
        expected = sessions[sessions <= pd.Timestamp(day)][-253:]
        totals: dict[str, int] = {}
        for batch in self._symbols(symbols):
            counts = annual_metrics(self._ticker_inputs(batch, day), benchmark, expected, day, parameters=parameters)
            for key, value in counts.items():
                totals[key] = totals.get(key, 0) + value
        return totals if totals else annual_metrics([], benchmark, expected, day, parameters=parameters)

    def year_counts(self, symbols: list[str], year: int, day: str) -> dict[str, int]:
        start = f"{year}-01-01"
        fresh_since = (date.fromisoformat(day) - timedelta(days=460)).isoformat()
        price_cutoff = (date.fromisoformat(day) - timedelta(days=10)).isoformat()
        adjusted, recent, price_year, price_recent, archive_prices, archive_adjusted = 0, 0, 0, 0, 0, 0
        for batch in self._symbols(symbols):
            marks = ",".join("?" for _ in batch)
            latest = dict(self.connection.execute(
                f"SELECT symbol,MAX(filed_date) FROM edgar_facts WHERE symbol IN ({marks}) AND filed_date<=? GROUP BY symbol",
                (*batch, day)))
            prices = dict((row[0], row[1:]) for row in self.connection.execute(
                "SELECT symbol,MAX(date),SUM(CASE WHEN adj_close>0 THEN 1 ELSE 0 END),"
                f"MAX(CASE WHEN adj_close>0 THEN date END) FROM prices WHERE symbol IN ({marks}) "
                "AND date>=? AND date<=? GROUP BY symbol", (*batch, start, day)))
            for symbol in batch:
                filed = latest.get(symbol)
                recent += bool(filed and filed >= fresh_since)
                last = prices.get(symbol, (None, None, None))
                price_year += bool(last[0])
                adjusted += bool(last[1])
                price_recent += bool(last[2] and last[2] >= price_cutoff)
            if year <= 2015:
                archived = dict(self.connection.execute(
                    "SELECT symbol,SUM(CASE WHEN adj_close>0 THEN 1 ELSE 0 END) FROM historical_prices "
                    f"WHERE source_id=? AND symbol IN ({marks}) AND date>=? AND date<=? GROUP BY symbol",
                    (self.archive_price_source, *batch, start, day)))
                archive_prices += sum(symbol in archived for symbol in batch)
                archive_adjusted += sum(bool(archived.get(symbol)) for symbol in batch)
        split_events = self.connection.execute("SELECT COUNT(*) FROM splits WHERE date>=? AND date<=?", (start, day)).fetchone()[0]
        archive_ciks = self.connection.execute("SELECT COUNT(DISTINCT cik) FROM historical_facts WHERE filed_date>=? AND filed_date<=?",
                                               (start, day)).fetchone()[0]
        return {"prices_year": price_year, "adjusted_prices_year": adjusted, "adjusted_price_recent_10d": price_recent,
                "archive_prices_year": archive_prices, "archive_adjusted_year": archive_adjusted,
                "split_events_year": split_events, "legacy_sec_recent": recent, "archive_ciks_filed_year": archive_ciks}


class CsvAnnualAudit:
    def __init__(self, output: Path):
        self.output = output

    def save(self, frame: pd.DataFrame) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(self.output, index=False)
