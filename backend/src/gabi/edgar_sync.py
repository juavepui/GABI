"""Compatibility facade for the shared issuer companyfacts synchronization."""

from gabi.domain.market.sec_xbrl import FIELDS as FIELDS
from gabi.domain.market.sec_xbrl import KEYS as KEYS

from . import edgar


def run_one(symbol: str, cik: str, *, full_refresh: bool = False) -> dict:
    return edgar.synchronize_issuer(symbol, cik, full_refresh=full_refresh)
