"""Compatibility facade for the shared issuer companyfacts synchronization."""

from datetime import UTC, datetime

from gabi.application.market.sec_xbrl import synchronize
from gabi.domain.market.sec_xbrl import FIELDS as FIELDS
from gabi.domain.market.sec_xbrl import KEYS as KEYS

from . import edgar, identity, storage
from . import sync_state as sync


class _Store:
    def ensure_entity(self, cik):
        return identity.ensure_entity(cik)

    def has_facts(self, entity):
        with storage.get_connection() as db:
            return bool(db.execute("SELECT 1 FROM entity_observations WHERE entity_id=? "
                                   "AND dataset='edgar_facts' LIMIT 1", (entity,)).fetchone())

    def metrics(self, symbol):
        return edgar.get_edgar_metrics([symbol]).get(symbol)

    def facts(self, entity):
        return edgar.get_edgar_facts("", entity_id=entity)

    def save(self, symbol, cik, rows, metrics):
        if rows:
            edgar.upsert_edgar_facts(symbol, rows, cik=cik)
        edgar.upsert_edgar_metrics(symbol, cik, metrics)


def run_one(symbol: str, cik: str, *, full_refresh: bool = False) -> dict:
    return synchronize(symbol, cik, store=_Store(), submissions=edgar.fetch_submissions,
                       companyfacts=edgar.fetch_company_facts, checkpoint=sync.get,
                       attempt_factory=sync.Attempt, retry=sync.retry, fingerprint=sync.fingerprint,
                       now=lambda: datetime.now(UTC), full_refresh=full_refresh,
                       fiscal_alignment=edgar.fiscal_alignment_enabled())
