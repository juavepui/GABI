"""Stored SEC metrics V2 (#245): one row per issuer, always computed from its stored facts.

The SEC sync recomputes an issuer's row when its facts change; :func:`fill` writes the
rows that are missing or belong to another metrics version, without downloading. The
active ranking reads them only when the active model version declares
``sec-metrics-v2`` (ADR 0008); the paths of the active studies keep reading V1.
"""

from collections.abc import Callable
from typing import Protocol

import pandas as pd

from gabi.domain.market import sec_metrics_v2 as v2
from gabi.domain.market.sec_reads import companyfacts
from gabi.domain.market.sec_xbrl import normalize_cik


class MetricsV2Store(Protocol):
    def facts(self, entity: str) -> pd.DataFrame: ...
    def save_metrics_v2(self, symbol: str, cik: str | None, row: dict) -> None: ...
    def metrics_v2_state(self, symbols: list[str]) -> dict[str, tuple[str | None, str | None]]: ...


def entity(cik: str) -> str:
    return f"cik:{normalize_cik(cik)}"


def from_facts(frame: pd.DataFrame) -> dict:
    """The V2 row from stored fact rows: the same reconstruction the comparison job reads."""
    return v2.snapshot(companyfacts(frame))


def refresh(store: MetricsV2Store, symbol: str, cik: str) -> dict:
    row = from_facts(store.facts(entity(cik)))
    store.save_metrics_v2(symbol, cik, row)
    return row


def fill(symbols: list[str], *, store: MetricsV2Store,
         progress: Callable[[int, int], None] = lambda done, total: None) -> dict:
    """Write the missing or outdated V2 rows from local facts; reads one query when all are current."""
    unique = list(dict.fromkeys(symbols))
    state = store.metrics_v2_state(unique)
    current = sum(version == v2.VERSION for _, version in state.values())
    due = [(symbol, cik) for symbol, (cik, version) in sorted(state.items())
           if version != v2.VERSION and cik and str(cik).strip().isdigit()]
    for done, (symbol, cik) in enumerate(due, 1):
        refresh(store, symbol, str(cik).strip())
        if done % 25 == 0 or done == len(due):
            progress(done, len(due))
    # Without V1 SEC metrics or a numeric CIK there is no issuer to read: the V2 row stays absent.
    return {"metrics_version": v2.VERSION, "computed": len(due), "current": current,
            "without_issuer": len(unique) - len(due) - current}
