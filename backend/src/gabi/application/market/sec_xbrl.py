"""Explicit companyfacts synchronization; issuer attribution is a storage port."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

import pandas as pd

from gabi.domain.market.observations import change_status, delta_rows
from gabi.domain.market.sec_facts import (
    SHARES_TAGS,
    TRACKED_TAGS,
    _extract_raw_facts,
    compute_edgar_metrics,
    extract_latest_filings,
)
from gabi.domain.market.sec_xbrl import FIELDS, KEYS, facts_due, normalize_cik


class XbrlStore(Protocol):
    def ensure_entity(self, cik: str) -> str: ...
    def has_facts(self, entity: str) -> bool: ...
    def metrics(self, symbol: str) -> dict | None: ...
    def facts(self, entity: str) -> pd.DataFrame: ...
    def save(self, symbol: str, cik: str, rows: list[dict], metrics: dict) -> None: ...


def synchronize(symbol: str, cik: str, *, store: XbrlStore, submissions: Callable[[str], dict],
                companyfacts: Callable[[str], dict], checkpoint: Callable[[str, str, str], dict],
                attempt_factory: Callable, retry: Callable, fingerprint: Callable,
                now: Callable[[], datetime], full_refresh: bool = False,
                fiscal_alignment: bool = False) -> dict:
    entity = store.ensure_entity(cik)
    attempt = attempt_factory("sec", entity, f"facts:{symbol}")
    cp = checkpoint("sec", entity, attempt.dataset)
    try:
        filings = retry(lambda: submissions(cik), attempt)
        validate_issuer(filings, cik)
        attempt.payload(filings)
        recent = filings.get("filings", {}).get("recent", {})
        filing_hash = fingerprint(recent)
        has_facts, cached = store.has_facts(entity), store.metrics(symbol)
        need_facts = (facts_due(cp, recent, has_facts, cached, now(), full_refresh)
                      or cp.get("filings_hash") != filing_hash)
        state = {"filings_hash": filing_hash}
        links = extract_latest_filings(filings)
        if not need_facts:
            store.save(symbol, cik, [], {**(cached or {}), **links})
            return attempt.finish("unchanged", state=state,
                                  reason="filings sin cambios; auditoría XBRL semanal no vencida")
        facts = retry(lambda: companyfacts(cik), attempt)
        validate_issuer(facts, cik)
        attempt.payload(facts)
        facts_hash = fingerprint(facts)
        state.update(facts_hash=facts_hash, facts_audited_at=now().isoformat())
        if facts_hash == cp.get("facts_hash") and has_facts and cached and not full_refresh:
            store.save(symbol, cik, [], {**cached, **links})
            return attempt.finish("unchanged", state=state,
                                  reason="companyfacts idéntico; no se reprocesa el histórico")
        raw = _extract_raw_facts(facts, TRACKED_TAGS, unit="USD")
        raw += _extract_raw_facts(facts, SHARES_TAGS, unit="shares")
        if not raw:
            raise ValueError("SEC no devolvió hechos XBRL utilizables; checkpoint conservado.")
        incoming = pd.DataFrame(raw).drop_duplicates(KEYS, keep="last").set_index(KEYS)[FIELDS]
        old = store.facts(entity)
        previous = old.set_index(KEYS)[FIELDS] if not old.empty else pd.DataFrame(columns=FIELDS)
        changed, new, revised = delta_rows(previous, incoming)
        rows = [{k: None if pd.isna(v) else v for k, v in r.items()}
                for r in changed.reset_index().to_dict("records")]
        metrics = {**compute_edgar_metrics(facts, fiscal_alignment=fiscal_alignment), **links}
        store.save(symbol, cik, rows, metrics)
        filed = incoming.filed_date.dropna()
        state["watermark"] = max(cp.get("watermark", ""), str(filed.max()) if len(filed) else "")
        return attempt.finish(change_status(new, revised), state=state, new=new, revised=revised,
                              unchanged=len(incoming) - new - revised,
                              reason="companyfacts completo solicitado por filing/auditoría; sólo se escriben hechos nuevos/revisados")
    except Exception as exc:
        attempt.finish("failed", reason=str(exc))
        raise


def validate_issuer(payload: dict, cik: str) -> None:
    if "cik" in payload and normalize_cik(payload["cik"]) != normalize_cik(cik):
        raise ValueError("SEC respondió con hechos/filings de otro emisor.")
