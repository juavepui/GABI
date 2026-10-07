"""Local SEC queries over a specific read port; no implicit synchronization."""

from collections.abc import Callable
from datetime import date
from typing import Protocol

import pandas as pd

from gabi.domain.market.sec_facts import SHARES_TAGS, compute_edgar_metrics
from gabi.domain.market.sec_reads import companyfacts, issuer_versions, value_as_of
from gabi.domain.market.sec_xbrl import normalize_cik


class FactReader(Protocol):
    def facts(self, symbol: str, *, entity_id: str | None = None, tags: list[str] | None = None,
              as_of: str | None = None, unit: str | None = None) -> pd.DataFrame: ...
    def issuer(self, cik: str, as_of: str) -> pd.DataFrame: ...
    def last_filed(self, symbols: list[str], as_of: str | None = None) -> dict[str, str]: ...


class IssuerSnapshotReader(Protocol):
    def issuer_inputs(self, cik: str, as_of: str) -> tuple[pd.DataFrame, pd.DataFrame]: ...


def issuer_facts(reader: FactReader, cik: str, as_of: str, tags: list[str] | None = None) -> pd.DataFrame:
    day, normalized = date.fromisoformat(as_of).isoformat(), normalize_cik(cik)
    return issuer_versions(reader.issuer(normalized, day), normalized, tags)


def stored_facts(reader: FactReader, symbol: str, as_of: str | None = None, *, entity_id: str | None = None) -> dict:
    return companyfacts(reader.facts(symbol, entity_id=entity_id, as_of=as_of), as_of)


def metrics_as_of(reader: FactReader, symbol: str, as_of: str, *, entity_id: str | None = None,
                  compute: Callable[[dict], dict] = compute_edgar_metrics) -> dict:
    return compute(stored_facts(reader, symbol, as_of, entity_id=entity_id))


def concept_value(reader: FactReader, symbol: str, tags: list[str], as_of: str, unit: str = "USD", *,
                  entity_id: str | None = None) -> float | None:
    return value_as_of(reader.facts(symbol, entity_id=entity_id, tags=tags, as_of=as_of, unit=unit), as_of, unit)


def shares_as_of(reader: FactReader, symbol: str, as_of: str, *, entity_id: str | None = None) -> float | None:
    return concept_value(reader, symbol, SHARES_TAGS, as_of, "shares", entity_id=entity_id)


def issuer_snapshot(reader: IssuerSnapshotReader, cik: str, as_of: str, tags: list[str] | None = None) -> dict:
    day, normalized = date.fromisoformat(as_of).isoformat(), normalize_cik(cik)
    versions, raw = reader.issuer_inputs(normalized, day)
    versions = issuer_versions(versions, normalized, tags)
    # Metrics retain the legacy filing-only cutoff and form policy, independently
    # of the stricter inspectable issuer versions (filing and period cutoff).
    shares = raw[raw.tag.isin(SHARES_TAGS)] if not raw.empty else raw
    return {"cik": normalized, "as_of": day, "facts": versions.to_dict("records"),
            "metrics": compute_edgar_metrics(companyfacts(raw, day)),
            "shares_outstanding": value_as_of(shares, day, "shares")}
