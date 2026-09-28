"""SEC submissions gate companyfacts; changed facts keep accession and filed date."""

from datetime import UTC, datetime

import pandas as pd

from . import edgar, identity, storage
from . import sync_state as sync

KEYS = ["tag", "unit", "start_date", "end_date", "accn"]
FIELDS = ["val", "form", "fp", "fy", "filed_date"]


def run_one(symbol: str, cik: str, *, full_refresh: bool = False) -> dict:
    entity = identity.ensure_entity(cik)
    attempt = sync.Attempt("sec", entity, f"facts:{symbol}")
    cp = sync.get("sec", entity, attempt.dataset)
    try:
        submissions = sync.retry(lambda: edgar.fetch_submissions(cik), attempt)
        attempt.payload(submissions)
        recent = submissions.get("filings", {}).get("recent", {})
        filing_hash = sync.fingerprint(recent)
        with storage.get_connection() as conn:
            has_facts = bool(conn.execute("SELECT 1 FROM entity_observations WHERE entity_id=? "
                                          "AND dataset='edgar_facts' LIMIT 1", (entity,)).fetchone())
        cached = edgar.get_edgar_metrics([symbol]).get(symbol)
        audit_due = not cp.get("facts_audited_at") or (
            datetime.now(UTC) - datetime.fromisoformat(cp["facts_audited_at"])).total_seconds() >= 7 * 86400
        recent_dates = recent.get("filingDate", [])
        # Retry ingestion delay even if the filing-list fingerprint is unchanged.
        filing_recent = bool(recent_dates and max(recent_dates) >= (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=2)).date().isoformat())
        need_facts = (full_refresh or not has_facts or not cached or audit_due or filing_recent
                      or cp.get("status") == "failed" or cp.get("filings_hash") != filing_hash)
        state = {"filings_hash": filing_hash}
        links = edgar.extract_latest_filings(submissions)
        if not need_facts:
            edgar.upsert_edgar_metrics(symbol, cik, {**(cached or {}), **links})
            return attempt.finish("unchanged", state=state, reason="filings sin cambios; auditoría XBRL semanal no vencida")
        facts = sync.retry(lambda: edgar.fetch_company_facts(cik), attempt)
        attempt.payload(facts)
        facts_hash = sync.fingerprint(facts)
        state.update({"facts_hash": facts_hash, "facts_audited_at": datetime.now(UTC).isoformat()})
        if facts_hash == cp.get("facts_hash") and has_facts and cached and not full_refresh:
            edgar.upsert_edgar_metrics(symbol, cik, {**cached, **links})
            return attempt.finish("unchanged", state=state, reason="companyfacts idéntico; no se reprocesa el histórico")
        raw = edgar._extract_raw_facts(facts, edgar.TRACKED_TAGS, unit="USD")
        raw += edgar._extract_raw_facts(facts, edgar.SHARES_TAGS, unit="shares")
        if not raw:
            raise ValueError("SEC no devolvió hechos XBRL utilizables; checkpoint conservado.")
        # Tag lists may contain aliases repeated across families. Keep the last provider row for an observation key.
        incoming = pd.DataFrame(raw).drop_duplicates(KEYS, keep="last").set_index(KEYS)[FIELDS]
        old = edgar.get_edgar_facts(symbol, entity_id=entity)
        previous = old.set_index(KEYS)[FIELDS] if not old.empty else pd.DataFrame(columns=FIELDS)
        changed, new, revised = sync.delta_rows(previous, incoming)
        if not changed.empty:
            rows = changed.reset_index().to_dict("records")
            rows = [{k: None if pd.isna(v) else v for k, v in r.items()} for r in rows]
            edgar.upsert_edgar_facts(symbol, rows, cik=cik)
        metrics = {**edgar.compute_edgar_metrics(facts), **links}
        edgar.upsert_edgar_metrics(symbol, cik, metrics)
        filed = incoming.filed_date.dropna()
        state["watermark"] = max(cp.get("watermark", ""), str(filed.max()) if len(filed) else "")
        return attempt.finish(sync.change_status(new, revised), state=state, new=new, revised=revised,
                              unchanged=len(incoming) - new - revised,
                              reason="companyfacts completo solicitado por filing/auditoría; sólo se escriben hechos nuevos/revisados")
    except Exception as exc:
        attempt.finish("failed", reason=str(exc))
        raise
