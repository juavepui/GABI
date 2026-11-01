"""Explicit companyfacts synchronization; issuer attribution is a storage port."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import pandas as pd

from gabi.application.market import stored_metrics_v2
from gabi.domain.market.checklist import CHECKLIST_TAGS, DILUTED_SHARES_TAGS
from gabi.domain.market.observations import change_status, delta_rows
from gabi.domain.market.sec_facts import (
    SHARES_TAGS,
    TRACKED_TAGS,
    _extract_raw_facts,
    compute_edgar_metrics,
    extract_latest_filings,
)
from gabi.domain.market.sec_succession import SUCCESSIONS, Succession, files_annual_report
from gabi.domain.market.sec_xbrl import FIELDS, KEYS, facts_due, normalize_cik
from gabi.domain.market.valuation_v2 import USD_TAGS as V2_USD_TAGS

# Stored USD tags: the metric tags plus the checklist-only ones (#167) and those of
# SEC metrics V2 (#245). Metrics keep reading TRACKED_TAGS; the extra rows only feed
# the checklist and V2.
FACT_TAGS = list(dict.fromkeys(TRACKED_TAGS + list(CHECKLIST_TAGS) + list(V2_USD_TAGS)))
# Share-unit tags: outstanding shares plus the 10-K diluted average, the checklist's
# fallback for issuers that only report shares per class.
SHARE_FACT_TAGS = list(dict.fromkeys(SHARES_TAGS + DILUTED_SHARES_TAGS))


class XbrlStore(Protocol):
    def ensure_entity(self, cik: str) -> str: ...
    def has_facts(self, entity: str) -> bool: ...
    def metrics(self, symbol: str) -> dict | None: ...
    def facts(self, entity: str) -> pd.DataFrame: ...
    def save(self, symbol: str, cik: str, rows: list[dict], metrics: dict) -> None: ...
    def save_metrics_v2(self, symbol: str, cik: str | None, row: dict) -> None: ...


def synchronize(symbol: str, cik: str, *, store: XbrlStore, submissions: Callable[[str], dict],
                companyfacts: Callable[[str], dict], checkpoint: Callable[[str, str, str], dict],
                attempt_factory: Callable, retry: Callable, fingerprint: Callable,
                now: Callable[[], datetime], full_refresh: bool = False,
                fiscal_alignment: bool = False, successions: Mapping[str, Succession] = SUCCESSIONS) -> dict:
    succession = successions.get(normalize_cik(cik))
    probe, own = _Calls(), None
    if succession is not None:
        # A reviewed successor without its own 10-K reads the predecessor's statements (#202).
        try:
            own = retry(lambda: submissions(cik), probe)
            validate_issuer(own, cik)
        except Exception as exc:
            attempt_factory("sec", store.ensure_entity(cik), f"facts:{symbol}").finish("failed", reason=str(exc))
            raise
        if not files_annual_report(own):
            cik, own = succession.predecessor, None
    entity = store.ensure_entity(cik)
    attempt = attempt_factory("sec", entity, f"facts:{symbol}")
    attempt.calls += probe.calls
    cp = checkpoint("sec", entity, attempt.dataset)
    try:
        filings = own if own is not None else retry(lambda: submissions(cik), attempt)
        validate_issuer(filings, cik)
        attempt.payload(filings)
        recent = filings.get("filings", {}).get("recent", {})
        filing_hash = fingerprint(recent)
        has_facts, cached = store.has_facts(entity), store.metrics(symbol)
        # A stored history extracted with another tag set is reprocessed once,
        # even if companyfacts is unchanged, so new tags reach existing issuers.
        tags_version = fingerprint(FACT_TAGS + SHARE_FACT_TAGS)
        tags_stale = cp.get("fact_tags") != tags_version
        need_facts = (facts_due(cp, recent, has_facts, cached, now(), full_refresh)
                      or cp.get("filings_hash") != filing_hash or tags_stale)
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
        if facts_hash == cp.get("facts_hash") and has_facts and cached and not full_refresh and not tags_stale:
            store.save(symbol, cik, [], {**cached, **links})
            return attempt.finish("unchanged", state=state,
                                  reason="companyfacts idéntico; no se reprocesa el histórico")
        raw = _extract_raw_facts(facts, FACT_TAGS, unit="USD")
        raw += _extract_raw_facts(facts, SHARE_FACT_TAGS, unit="shares")
        if not raw and not has_facts:
            # New issuer before its first XBRL filing: absent coverage, not a source failure.
            return attempt.finish("unchanged", state=state,
                                  reason="emisor sin hechos XBRL rastreados todavía; cobertura ausente, sin métricas")
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
        # SEC metrics V2 (#245) from the stored history, the only source of the V2 rows.
        stored_metrics_v2.refresh(store, symbol, cik)
        state["fact_tags"] = tags_version
        filed = incoming.filed_date.dropna()
        state["watermark"] = max(cp.get("watermark", ""), str(filed.max()) if len(filed) else "")
        return attempt.finish(change_status(new, revised), state=state, new=new, revised=revised,
                              unchanged=len(incoming) - new - revised,
                              reason="companyfacts completo solicitado por filing/auditoría; sólo se escriben hechos nuevos/revisados")
    except Exception as exc:
        attempt.finish("failed", reason=str(exc))
        raise


@dataclass
class _Calls:
    """Counts the successor probe's requests; they are added to the issuer attempt."""
    source: str = "sec"
    calls: int = 0


def validate_issuer(payload: dict, cik: str) -> None:
    if "cik" in payload and normalize_cik(payload["cik"]) != normalize_cik(cik):
        raise ValueError("SEC respondió con hechos/filings de otro emisor.")


def fetch_complete(cik: str, *, companyfacts: Callable[[str], dict], submissions: Callable[[str], dict],
                   compute: Callable[[dict], dict]) -> tuple[dict, list[dict]]:
    facts = companyfacts(cik)
    validate_issuer(facts, cik)
    rows = _extract_raw_facts(facts, FACT_TAGS, unit="USD")
    rows += _extract_raw_facts(facts, SHARE_FACT_TAGS, unit="shares")
    metrics = compute(facts)
    try:
        filings = submissions(cik)
    except Exception:
        pass  # Historical nonincremental compatibility: filing links remain optional.
    else:
        validate_issuer(filings, cik)
        metrics.update(extract_latest_filings(filings))
    return metrics, rows


def download_complete(symbol: str, cik: str, *, store: XbrlStore, companyfacts: Callable[[str], dict],
                      submissions: Callable[[str], dict], compute: Callable[[dict], dict]) -> None:
    metrics, rows = fetch_complete(cik, companyfacts=companyfacts, submissions=submissions, compute=compute)
    if rows:
        store.ensure_entity(cik)
    store.save(symbol, cik, rows, metrics)
