"""The research data refresh (``gabi_cli research history-refresh``) over the existing sources.

Composes the use case with SQLite, the CSV caches, Yahoo, Wikipedia/SEC, EDGAR and FRED. Paths
and keys come from ``config`` on each call (ADR 0005).
"""

import hashlib
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from gabi.application.market import cached_data
from gabi.application.research.history_refresh import RefreshPorts, refresh
from gabi.domain.market import fred, freshness
from gabi.domain.research import history_refresh as rules
from gabi.infrastructure.providers import yahoo
from gabi.infrastructure.providers.fred import FredSource
from gabi.infrastructure.providers.sp500_sources import SP500Sources
from gabi.infrastructure.storage.backups import backup_once
from gabi.infrastructure.storage.cache_reads import SqliteCacheReads
from gabi.infrastructure.storage.cache_writes import SqliteCacheWrites
from gabi.infrastructure.storage.fred import SqliteFred
from gabi.infrastructure.storage.reviewed_resources import MEMBERSHIP_LEDGER as LEDGER_PATH
from gabi.infrastructure.storage.sec_reads import SqliteSecReads


def _cache() -> SqliteCacheReads:
    from gabi import config

    return SqliteCacheReads(config.DB_PATH)


def _writes() -> SqliteCacheWrites:
    from gabi import config

    return SqliteCacheWrites(config.DB_PATH, lambda: datetime.now(UTC))


def database_coverage() -> dict:
    return _cache().table_coverage()


def restore_share_class_spelling(end: str) -> dict:
    """Reuse existing Yahoo rows for BRK.B/BF.B under Yahoo's dash spelling (rule in the domain)."""
    restored = {}
    for original in rules.SHARE_CLASS_SPELLINGS:
        canonical = original.replace(".", "-")
        cache = _cache()
        rows = rules.share_class_rows(cached_data.prices(cache, original), cached_data.prices(cache, canonical), end)
        if rows is None:
            continue
        _writes().prices(canonical, rows)
        restored[canonical] = {"source_symbol": original, "dates": rows.index.strftime("%Y-%m-%d").tolist()}
    return restored


def refresh_prices(symbol: str, download_symbol: str, end: str, valid_to: str | None = None) -> int:
    """Replace a complete provider series, excluding incomplete sessions.

    Former tickers may use an explicitly reviewed successor, only before the
    ticker change. Never copy an acquired company's acquirer series.
    """
    from gabi import identity

    frame, splits = rules.complete_series(yahoo.history(download_symbol, period="max", end=end, auto_adjust=False),
                                          end, valid_to)
    owner = identity.resolve(symbol, datetime.now(UTC).date().isoformat())["entity_id"]
    writes = _writes()
    writes.prices(symbol, frame, entity_id=owner)
    # Later splits also adjust earlier prices, even after a ticker rename.
    writes.splits(symbol, splits, entity_id=owner)
    return len(frame)


class RefreshRun:
    """The run folder: report, backups, fetched page and the published membership caches."""

    def __init__(self, data_dir: Path, database: Path, membership: Path, constituents: Path, cik_map: Path):
        self.data_dir, self.database = data_dir, database
        self.membership_path, self.constituents_path, self.cik_map = membership, constituents, cik_map
        self.directory = data_dir / "history_refresh"

    def start(self, stamp: str) -> str:
        self.directory = self.data_dir / "history_refresh" / stamp
        self.directory.mkdir(parents=True, exist_ok=False)
        yahoo.use_timezone_cache(self.data_dir / "history_refresh" / "yfinance_cache")
        return str(self.directory)

    def save(self, report: dict) -> None:
        (self.directory / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                                    encoding="utf-8")

    def backup(self) -> None:
        # A SQLite backup includes committed WAL pages, unlike a plain file copy.
        backup_once(self.database, self.directory / "gabi_before.db")
        for path in [self.membership_path, self.constituents_path, self.cik_map]:
            if path.exists():
                shutil.copy2(path, self.directory / path.name)

    def membership(self) -> pd.DataFrame:
        return pd.read_csv(self.membership_path, dtype=str)

    def write_page(self, page: bytes) -> None:
        (self.directory / "current.html").write_bytes(page)

    def publish_membership(self, extended: pd.DataFrame, current: pd.DataFrame) -> None:
        temporary = self.membership_path.with_suffix(".csv.tmp")
        extended.to_csv(temporary, index=False)
        temporary.replace(self.membership_path)
        current.to_csv(self.constituents_path, index=False)

    def report_path(self) -> str:
        return str(self.directory / "report.json")


def run() -> dict:
    from gabi import config, data_fetch, edgar, universe

    sources = SP500Sources(config.SEC_USER_AGENT)
    series = SqliteFred(config.DB_PATH, lambda: datetime.now(UTC))

    def live_ciks() -> dict:
        live = edgar.get_cik_map(force_refresh=True)
        return dict(zip(live["symbol"], live["cik"], strict=True))

    return refresh(RefreshPorts(
        files=RefreshRun(config.DATA_DIR, config.DB_PATH, universe.HISTORICAL_MEMBERSHIP_CACHE, config.SP500_CACHE,
                         edgar.CIK_CACHE),
        now=lambda: datetime.now(UTC), today=lambda: date.today(), session=freshness.market_date,
        ledger=lambda: json.loads(LEDGER_PATH.read_text(encoding="utf-8")),
        ledger_sha256=lambda: hashlib.sha256(LEDGER_PATH.read_bytes()).hexdigest(),
        former_issuers=lambda: json.loads(
            LEDGER_PATH.with_name("former_issuers_2025_2026.json").read_text(encoding="utf-8")),
        page=sources.wikipedia_page,
        constituents=lambda page: universe._normalize(sources.wikipedia_tables(page)[0]),
        coverage=database_coverage, price_coverage=lambda symbols: cached_data.price_coverage(_cache(), symbols),
        live_ciks=live_ciks, stored_ciks=lambda: SqliteSecReads(config.DB_PATH).stored_ciks(),
        refresh_prices=refresh_prices, classify=lambda exc: data_fetch._classify_error(exc)[1],
        restore_share_classes=restore_share_class_spelling,
        edgar_batch=lambda symbols, ciks, progress: edgar.fetch_edgar_batch(
            symbols, ciks, max_workers=1, progress_cb=progress, incremental=False),
        fundamentals_fetched_at=lambda symbols: cached_data.fundamentals_fetched_at(_cache(), symbols),
        fetch_fundamentals=lambda symbols: data_fetch.fetch_fundamentals_batch(symbols, max_workers=2),
        fred_key=config.load_fred_key, fred_series=fred.SERIES,
        fetch_fred=lambda sid, key, units: FredSource().fetch(sid, key, units, 10000, require_complete=False),
        store_fred=series.upsert, benchmark=config.BENCHMARK_SYMBOL,
        log=lambda message: print(message, flush=True)))
