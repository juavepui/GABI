"""Bounded read-only queries over the operational price/fundamental cache tables."""

from pathlib import Path

from gabi.infrastructure.storage.bounded_reads import bounded_rows, read_only


class SqliteCacheReads:
    # The multi-symbol price budget sits above the documented 5.3M-row `prices` snapshot
    # (docs/historical-prices-2010-2015.md) so universe-wide facades fail rather than truncate.
    def __init__(self, path: Path, *, max_rows: int = 8_000_000, max_bytes: int = 1024 * 1024 * 1024,
                 max_series_rows: int = 50_000, max_field_bytes: int = 4 * 1024 * 1024, batch_size: int = 500):
        if min(max_rows, max_bytes, max_series_rows, max_field_bytes, batch_size) < 1 or batch_size > 500:
            raise ValueError("Invalid cache read limits")
        self.path = path
        self.max_rows, self.max_bytes, self.max_series_rows = max_rows, max_bytes, max_series_rows
        self.max_field_bytes, self.batch_size = max_field_bytes, batch_size

    def _rows(self, db, query, params=(), *, max_rows=None):
        return bounded_rows(db, query, params, max_rows=self.max_rows if max_rows is None else max_rows,
                            max_bytes=self.max_bytes, max_field_bytes=self.max_field_bytes)

    def _batched(self, db, template, symbols, params=()):
        rows: list[tuple] = []
        symbols = list(dict.fromkeys(symbols))
        for start in range(0, len(symbols), self.batch_size):
            chunk = symbols[start:start + self.batch_size]
            rows += self._rows(db, template.format(marks=",".join("?" for _ in chunk)), (*chunk, *params),
                               max_rows=self.max_rows - len(rows))
        return rows

    @staticmethod
    def _adjusted(db) -> str:
        # Databases older than the adj_close column read it as absent instead of being altered.
        return "adj_close" if "adj_close" in {row[1] for row in db.execute("PRAGMA table_info(prices)")} else "NULL"

    def prices(self, symbol: str) -> list[tuple]:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "prices" not in tables:
                return []
            return self._rows(db, f"SELECT date,open,high,low,close,volume,{self._adjusted(db)} AS adj_close FROM prices "
                              "WHERE symbol=? ORDER BY date ASC", (symbol,), max_rows=self.max_series_rows)

    def prices_multi(self, symbols: list[str]) -> list[tuple]:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "prices" not in tables:
                return []
            # Primary-key order keeps per-symbol date order; a bounded ORDER BY date needs a slow top-N sort.
            return self._batched(db, f"SELECT symbol,date,open,high,low,close,volume,{self._adjusted(db)} AS adj_close "
                                 "FROM prices WHERE symbol IN ({marks}) ORDER BY symbol,date", symbols)

    def price_coverage(self, symbols: list[str]) -> list[tuple]:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "prices" not in tables:
                return []
            adjusted = self._adjusted(db)
            return self._batched(db, f"SELECT symbol,COUNT({adjusted}),MAX(CASE WHEN {adjusted} IS NOT NULL "
                                 "THEN date END) FROM prices WHERE symbol IN ({marks}) GROUP BY symbol", symbols)

    def last_price(self, symbol: str, as_of: str) -> tuple | None:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "prices" not in tables:
                return None
            rows = self._rows(db, f"SELECT * FROM (SELECT close,{self._adjusted(db)} FROM prices WHERE symbol=? "
                              "AND date<=? ORDER BY date DESC LIMIT 1)", (symbol, as_of), max_rows=1)
            return rows[0] if rows else None

    def adjusted_span(self, symbol: str) -> tuple[str | None, str | None]:
        """First and last session with a positive adjusted close."""
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "prices" not in tables or self._adjusted(db) == "NULL":
                return None, None
            first, last = db.execute("SELECT MIN(date),MAX(date) FROM prices WHERE symbol=? AND adj_close>0",
                                     (symbol,)).fetchone()
            return first, last

    def prices_from(self, symbol: str, start: str) -> list[tuple]:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "prices" not in tables:
                return []
            return self._rows(db, f"SELECT date,open,high,low,close,{self._adjusted(db)} AS adj_close,volume FROM prices "
                              "WHERE symbol=? AND date>=? ORDER BY date", (symbol, start), max_rows=self.max_series_rows)

    def table_coverage(self) -> dict:
        """Row counts and date span per cached table, and per macro series; absent tables count as empty."""
        spans = (("prices", "date"), ("edgar_facts", "filed_date"), ("macro_series", "date"))
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            result = {}
            for table, column in spans:
                row = (db.execute(f"SELECT COUNT(*),MIN({column}),MAX({column}) FROM {table}").fetchone()
                       if db is not None and table in tables else (0, None, None))
                result[table] = dict(zip(["rows", "first", "last"], row, strict=True))
            series = self._rows(db, "SELECT series_id,MIN(date),MAX(date),COUNT(*) FROM macro_series GROUP BY series_id") \
                if db is not None and "macro_series" in tables else []
            result["macro_by_series"] = {sid: {"first": lo, "last": hi, "rows": count} for sid, lo, hi, count in series}
            return result

    def latest_adjusted(self, symbols: list[str], as_of: str | None = None) -> dict[str, tuple]:
        """Newest (date, close, adj_close) with a positive adjusted close, per symbol, in one snapshot.

        ``as_of`` bounds the session (inclusive). One indexed backward lookup per symbol stops at the
        first match; a set-wide MAX would scan histories."""
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "prices" not in tables or self._adjusted(db) == "NULL":
                return {}
            found = {}
            bound, extra = (" AND date<=?", (as_of,)) if as_of else ("", ())
            for symbol in dict.fromkeys(symbols):
                rows = self._rows(db, "SELECT * FROM (SELECT date,close,adj_close FROM prices WHERE symbol=? "
                                  f"AND adj_close>0{bound} ORDER BY date DESC LIMIT 1)", (symbol, *extra), max_rows=1)
                if rows:
                    found[symbol] = rows[0]
            return found

    def split_ratios_after(self, symbol: str, as_of: str) -> list[float]:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "splits" not in tables:
                return []
            return [ratio for ratio, in self._rows(db, "SELECT ratio FROM splits WHERE symbol=? AND date>?",
                                                   (symbol, as_of), max_rows=self.max_series_rows)]

    def fundamentals(self, symbols: list[str]) -> list[tuple]:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "fundamentals" not in tables:
                return []
            return self._batched(db, "SELECT symbol,fetched_at,info_json,quarterly_income_json,quarterly_cashflow_json "
                                 "FROM fundamentals WHERE symbol IN ({marks})", symbols)

    def fundamentals_fetched_at(self, symbols: list[str]) -> list[tuple]:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "fundamentals" not in tables:
                return []
            return self._batched(db, "SELECT symbol,fetched_at FROM fundamentals WHERE symbol IN ({marks})", symbols)

    def update_errors(self, since: str, source: str | None = None) -> list[tuple]:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "update_errors" not in tables:
                return []
            query = "SELECT source,symbol,reason,occurred_at FROM update_errors WHERE occurred_at>=?"
            params: tuple = (since,)
            if source:
                query += " AND source=?"
                params += (source,)
            return self._rows(db, query + " ORDER BY occurred_at DESC", params, max_rows=self.max_series_rows)
