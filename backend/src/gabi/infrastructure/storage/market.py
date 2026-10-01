"""Read-only SQL snapshots and a small process-local ranking cache.

The persistent monitor makes data_version meaningful across requests, including
WAL/historical corrections. This revision is a cache token, never an evidence hash.
"""
import hashlib
import json
import sqlite3
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime
from io import StringIO
from threading import RLock
from time import monotonic

import pandas as pd

from gabi.application.administration.model import LocalModel, ModelPolicy
from gabi.application.errors import QueryError
from gabi.application.market.queries import RankingSnapshot
from gabi.application.market.ranking import Calculators, MarketBatch, build_ranking
from gabi.domain.market.identity import resolve_claims
from gabi.infrastructure.settings import Settings


class SqlInputs:
    def __init__(self, owner: "ReadOnlyMarket", universe: pd.DataFrame):
        self.owner, self.universe = owner, universe
        self.benchmark_symbol = owner.benchmark_symbol
        self.benchmark = owner.prices((self.benchmark_symbol,), owner.settings.max_benchmark_rows).get(
            self.benchmark_symbol, pd.DataFrame())
        self.risk_free_rate = owner.risk_free_rate
        if "macro_series" in owner.tables:
            values = owner.rows("SELECT value FROM macro_series WHERE series_id=? ORDER BY date DESC LIMIT 1", ("DGS10",))
            if values and values[0][0] is not None:
                self.risk_free_rate = float(values[0][0]) / 100

    def _spans(self) -> Iterator[tuple[int, int]]:
        """Consecutive universe slices within the symbol and price-row budgets.

        Full histories are read (the risk metrics use all of them, as the Streamlit screener did); a
        deep backfill only makes the slices smaller instead of exceeding the row budget."""
        settings = self.owner.settings
        counts = self.owner.price_counts(tuple(self.universe["symbol"]))
        start, rows = 0, 0
        for position, symbol in enumerate(self.universe["symbol"]):
            size = counts.get(str(symbol), 0)
            if size > settings.max_price_rows_per_batch:
                raise QueryError("resource_limit", "El histórico de una empresa supera el presupuesto de lectura.")
            if position > start and (position - start >= settings.batch_size
                                     or rows + size > settings.max_price_rows_per_batch):
                yield start, position
                start, rows = position, 0
            rows += size
        if start < len(self.universe):
            yield start, len(self.universe)

    def batches(self) -> Iterator[MarketBatch]:
        for start, end in self._spans():
            frame = self.universe.iloc[start:end]
            symbols = tuple(frame["symbol"])
            yield MarketBatch(frame, self.owner.fundamentals(symbols),
                              self.owner.prices(symbols, self.owner.settings.max_price_rows_per_batch),
                              self.owner.sec(symbols))


class ReadOnlyMarket:
    def __init__(self, settings: Settings, calculators: Calculators, policy: ModelPolicy,
                 benchmark_symbol: str, risk_free_rate: float):
        self.settings, self.calculators, self.policy = settings, calculators, policy
        self.benchmark_symbol, self.risk_free_rate = benchmark_symbol, risk_free_rate
        self.db = settings.data_dir / "gabi.db"
        self.connection: sqlite3.Connection | None = None
        self.file_identity: tuple | None = None
        self.tables: set[str] = set()
        self.lock = RLock()
        self.cache: OrderedDict[tuple, tuple[float, RankingSnapshot]] = OrderedDict()
        self.query_count = 0
        self.row_count = 0

    def close(self) -> None:
        with self.lock:
            if self.connection is not None:
                self.connection.close()
            self.connection = None
            self.file_identity = None
            self.cache.clear()

    def connect(self) -> None:
        identity = self.stamp(self.db)
        if identity is None:
            self.close()
            self.tables = set()
            return
        if self.connection is not None and self.file_identity == identity[:2]:
            return
        self.close()
        # No mkdir, schema initialization, migrations, journal-mode changes, or network.
        self.connection = sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True, timeout=2, check_same_thread=False)
        self.connection.execute("PRAGMA query_only=ON")
        self.file_identity = identity[:2]

    @staticmethod
    def stamp(path) -> tuple | None:
        try:
            stat = path.stat()
            return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns
        except FileNotFoundError:
            return None

    def small_file(self, name: str) -> bytes | None:
        path = self.settings.data_dir / name
        try:
            with path.open("rb") as stream:
                contents = stream.read(self.settings.max_small_file_bytes + 1)
        except FileNotFoundError:
            return None
        if len(contents) > self.settings.max_small_file_bytes:
            raise QueryError("resource_limit", "El archivo de configuración supera el límite de lectura.")
        return contents

    def rows(self, sql: str, params: tuple = (), maximum: int = 10_000) -> list[tuple]:
        if self.connection is None:
            return []
        self.query_count += 1
        cursor = self.connection.execute(sql, params)
        values = cursor.fetchmany(maximum + 1)
        self.row_count += len(values)
        if len(values) > maximum:
            raise QueryError("resource_limit", "El histórico supera el presupuesto de lectura; no se ha truncado el cálculo.")
        return values

    def discover(self) -> None:
        self.tables = {row[0] for row in self.rows("SELECT name FROM sqlite_schema WHERE type='table'")}

    def token(self, universe_bytes: bytes | None) -> str:
        version = self.rows("PRAGMA data_version")[0][0] if self.connection is not None else None
        signature = ("market-query-v1", self.stamp(self.db), self.stamp(self.db.with_name("gabi.db-wal")),
                     version, hashlib.sha256(universe_bytes or b"").hexdigest())
        return hashlib.sha256(repr(signature).encode()).hexdigest()

    def local_model(self) -> LocalModel:
        with self.lock:
            try:
                mode_bytes, weights_bytes = self.small_file("app_mode.json"), self.small_file("weights.json")
                mode = json.loads(mode_bytes).get("mode", "INVESTOR") if mode_bytes else "INVESTOR"
                if mode not in {"INVESTOR", "RESEARCH"}:
                    raise ValueError("Invalid mode")
                weights = json.loads(weights_bytes) if weights_bytes else dict(self.policy.frozen_weights)
                if not isinstance(weights, dict):
                    raise ValueError("Invalid weights")
                weights = {str(key): float(value) for key, value in weights.items()}
                self.connect()
                self.discover()
                blind_id = None
                if {"blind_validations", "blind_validation_periods"} <= self.tables:
                    # Metadata only. Never SELECT results, prices, symbols or sealed rankings.
                    candidates = self.rows("SELECT id,weights_json FROM blind_validations v WHERE status='locked' "
                                           "AND EXISTS(SELECT 1 FROM blind_validation_periods p WHERE p.validation_id=v.id)")
                    for candidate_id, raw_weights in candidates:
                        if self.policy.matches(json.loads(raw_weights)):
                            blind_id = int(candidate_id)
                            break
                weak = bool(self.rows("SELECT 1 FROM experiments WHERE stage='LIVE_FORWARD' LIMIT 1")) if "experiments" in self.tables else False
                return LocalModel(mode, weights, blind_id, weak)
            except QueryError:
                raise
            except (OSError, ValueError, TypeError, sqlite3.Error) as exc:
                raise QueryError("local_state_error", "No se puede leer el estado local del modelo.") from exc

    def universe(self, contents: bytes | None) -> pd.DataFrame:
        if not contents:
            return pd.DataFrame(columns=["symbol", "name", "sector"])
        frame = pd.read_csv(StringIO(contents.decode("utf-8")), nrows=self.settings.max_symbols + 1)
        if not {"symbol", "name", "sector"} <= set(frame.columns) or frame["symbol"].isna().any():
            raise ValueError("Invalid universe columns")
        frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper().str.replace(".", "-", regex=False)
        if len(frame) > self.settings.max_symbols:
            raise QueryError("resource_limit", "El universo supera el límite de símbolos.")
        if frame["symbol"].duplicated().any() or not frame["symbol"].str.fullmatch(r"[A-Z0-9^][A-Z0-9^\-]{0,19}").all():
            raise ValueError("Invalid or duplicate ticker")
        return frame

    def ranking(self, weights: dict[str, float], today: date) -> RankingSnapshot:
        with self.lock:
            try:
                self.connect()
                raw = self.small_file("sp500_constituents.csv")
                revision = self.token(raw)
                key = (revision, today.isoformat(), tuple(sorted(weights.items())), self.benchmark_symbol,
                       self.risk_free_rate, self.policy.frozen_id)
                existing = self.cache.get(key)
                if existing and monotonic() - existing[0] < self.settings.cache_seconds:
                    self.cache.move_to_end(key)
                    return replace(existing[1], cache_hit=True)
                universe = self.universe(raw)
                if self.connection is not None:
                    self.connection.execute("BEGIN")
                try:
                    self.discover()
                    table = build_ranking(SqlInputs(self, universe), self.calculators, weights, today=today, total=len(universe))
                    identities = self.identities(tuple(universe["symbol"]), today)
                finally:
                    if self.connection is not None:
                        self.connection.rollback()
                if self.token(self.small_file("sp500_constituents.csv")) != revision:
                    raise QueryError("data_changed", "Los datos cambiaron durante la consulta; vuelve a intentarlo.", 409)
                stamp = self.stamp(self.settings.data_dir / "sp500_constituents.csv")
                cached_at = datetime.fromtimestamp(stamp[3] / 1e9, UTC) if stamp else None
                snapshot = RankingSnapshot(table, identities, revision, datetime.now(UTC), cached_at)
                self.cache[key] = monotonic(), snapshot
                self.cache.move_to_end(key)
                while len(self.cache) > self.settings.cache_entries:
                    self.cache.popitem(last=False)
                return snapshot
            except QueryError:
                raise
            except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
                raise QueryError("data_read_error", "No se pueden consultar los datos locales cacheados.") from exc

    def price_counts(self, symbols: tuple[str, ...]) -> dict[str, int]:
        if not symbols or "prices" not in self.tables:
            return {}
        counts: dict[str, int] = {}
        for start in range(0, len(symbols), 500):  # Below SQLite's host-parameter limit.
            chunk = symbols[start:start + 500]
            placeholders = ",".join("?" * len(chunk))
            counts.update((str(symbol), int(count)) for symbol, count in self.rows(
                f"SELECT symbol,COUNT(*) FROM prices WHERE symbol IN ({placeholders}) GROUP BY symbol",
                chunk, len(chunk)))
        return counts

    def prices(self, symbols: tuple[str, ...], maximum: int) -> dict[str, pd.DataFrame]:
        if not symbols or "prices" not in self.tables:
            return {}
        columns = {row[1] for row in self.rows("PRAGMA table_info(prices)")}
        adjusted = "adj_close" if "adj_close" in columns else "NULL AS adj_close"
        placeholders = ",".join("?" * len(symbols))
        records = self.rows(f"SELECT symbol,date,open,high,low,close,volume,{adjusted} FROM prices "
                            f"WHERE symbol IN ({placeholders}) ORDER BY date ASC LIMIT ?", (*symbols, maximum + 1), maximum)
        if not records:
            return {}
        frame = pd.DataFrame(records, columns=["symbol", "date", "open", "high", "low", "close", "volume", "adj_close"])
        frame["date"] = pd.to_datetime(frame["date"])
        return {str(symbol): group.drop(columns="symbol").set_index("date") for symbol, group in frame.groupby("symbol")}

    def fundamentals(self, symbols: tuple[str, ...]) -> dict:
        if not symbols or "fundamentals" not in self.tables:
            return {}
        placeholders = ",".join("?" * len(symbols))
        bound = self.settings.max_small_file_bytes
        rows = self.rows("SELECT symbol,fetched_at,substr(CAST(info_json AS BLOB),1,?),"
                         "substr(CAST(quarterly_income_json AS BLOB),1,?),"
                         f"substr(CAST(quarterly_cashflow_json AS BLOB),1,?) FROM fundamentals WHERE symbol IN ({placeholders})",
                         (bound + 1, bound + 1, bound + 1, *symbols), len(symbols))
        if any(value is None or len(value) > bound for row in rows for value in row[2:]):
            raise QueryError("resource_limit", "Un registro fundamental supera el presupuesto de lectura.")
        return {symbol: {"fetched_at": fetched, "info": json.loads(info), "quarterly_income": json.loads(income),
                         "quarterly_cashflow": json.loads(cashflow)} for symbol, fetched, info, income, cashflow in rows}

    def sec(self, symbols: tuple[str, ...]) -> dict:
        if not symbols or "edgar_metrics" not in self.tables:
            return {}
        columns = ("revenue_cagr_3y", "fcf_cagr_3y", "roic", "latest_10k_date", "latest_10k_url",
                   "latest_10q_date", "latest_10q_url", "fetched_at")
        placeholders = ",".join("?" * len(symbols))
        records = self.rows(f"SELECT symbol,{','.join(columns)} FROM edgar_metrics WHERE symbol IN ({placeholders})", symbols, len(symbols))
        return {row[0]: dict(zip(columns, row[1:], strict=True)) for row in records}

    def identities(self, symbols: tuple[str, ...], today: date) -> dict[str, dict]:
        grouped: dict[str, list[tuple]] = {symbol: [] for symbol in symbols}
        if symbols and {"entity_aliases", "entities"} <= self.tables:
            placeholders = ",".join("?" * len(symbols))
            rows = self.rows("SELECT a.symbol,a.entity_id,e.cik,a.source,a.confidence FROM entity_aliases a "
                             f"JOIN entities e USING(entity_id) WHERE symbol IN ({placeholders}) AND valid_from<=? "
                             "AND (valid_to IS NULL OR valid_to>?)", (*symbols, today.isoformat(), today.isoformat()))
            for symbol, *claim in rows:
                grouped[symbol].append(tuple(claim))
        return {symbol: resolve_claims(claims, today) for symbol, claims in grouped.items()}

    def company_events(self, symbol: str, today: date) -> list[dict]:
        """Dated corporate events parsed from the cached fundamentals record (no download)."""
        with self.lock:
            try:
                self.connect()
                self.discover()
                record = self.fundamentals((symbol,)).get(symbol)
                if not record:
                    return []
                return self.calculators.events(symbol, record.get("info", {}), record.get("fetched_at", ""),
                                               today=today)
            except QueryError:
                raise
            except (OSError, ValueError, TypeError, sqlite3.Error) as exc:
                raise QueryError("data_read_error", "No se pueden consultar los datos de la empresa.") from exc

    def price_history(self, symbol: str, limit: int, revision: str) -> pd.DataFrame:
        with self.lock:
            try:
                self.connect()
                if self.token(self.small_file("sp500_constituents.csv")) != revision:
                    raise QueryError("data_changed", "Los datos cambiaron durante la consulta; vuelve a intentarlo.", 409)
                self.discover()
                if "prices" not in self.tables:
                    return pd.DataFrame()
                columns = {row[1] for row in self.rows("PRAGMA table_info(prices)")}
                adjusted = "adj_close" if "adj_close" in columns else "NULL AS adj_close"
                records = self.rows(f"SELECT date,close,{adjusted} FROM prices WHERE symbol=? ORDER BY date DESC LIMIT ?", (symbol, limit), limit)
                if self.token(self.small_file("sp500_constituents.csv")) != revision:
                    raise QueryError("data_changed", "Los datos cambiaron durante la consulta; vuelve a intentarlo.", 409)
                return pd.DataFrame(reversed(records), columns=["date", "close", "adj_close"])
            except QueryError:
                raise
            except (OSError, ValueError, sqlite3.Error) as exc:
                raise QueryError("data_read_error", "No se pueden consultar los precios cacheados.") from exc
