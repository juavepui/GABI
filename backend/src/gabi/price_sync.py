"""Incremental Yahoo prices, with overlap and explicit adjustment repair (compatibility facade)."""

from datetime import UTC, datetime

from gabi.application.market import cached_data
from gabi.application.market.price_sync import run as run_use_case
from gabi.domain.market.freshness import last_completed_session
from gabi.domain.market.price_sync import COLS as COLS
from gabi.domain.market.source_errors import classify
from gabi.infrastructure.providers import yahoo
from gabi.infrastructure.storage.cache_reads import SqliteCacheReads
from gabi.infrastructure.storage.cache_writes import SqliteCacheWrites

from . import identity, storage
from . import sync_state as sync


class _Store:
    def __init__(self, reads: SqliteCacheReads, writes: SqliteCacheWrites):
        self.reads, self.writes = reads, writes

    def adjusted_span(self, symbol):
        return self.reads.adjusted_span(symbol)

    def prices_from(self, symbol, start):
        return cached_data.prices_from(self.reads, symbol, start)

    def prices(self, symbol):
        return cached_data.prices(self.reads, symbol)

    def write(self, symbol, frame, entity_id):
        self.writes.prices(symbol, frame, entity_id=entity_id)


def run(symbols: list, *, force: bool = False, full_refresh: bool = False, now=None) -> dict:
    now = now or datetime.now(UTC)
    # The compatibility path is captured per operation, never mutated.
    path = storage.database_path()
    store = _Store(SqliteCacheReads(path), SqliteCacheWrites(path, lambda: datetime.now(UTC)))
    return run_use_case(symbols, store=store, owner=lambda symbol, day: identity.resolve(symbol, day)["entity_id"],
                        attempt=sync.Attempt, checkpoint=sync.get, due=sync.due, retry=sync.retry,
                        download=yahoo.download, classify=lambda exc: classify(str(exc))[1],
                        payload_size=lambda frame: len(frame.to_csv().encode()), now=now,
                        session=last_completed_session(now).isoformat(), force=force, full_refresh=full_refresh)
