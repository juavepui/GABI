"""Explicit Form 4 ingestion and freshness decisions over supplied ports."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from gabi.domain.market.insiders import parse_form4_xml


class Form4Documents(Protocol):
    def submissions(self, cik: str) -> dict: ...
    def xml(self, url: str) -> str: ...


def fetch_transactions(symbol: str, cik: str, source: Form4Documents, limit_filings: int = 20) -> list[dict]:
    recent = source.submissions(cik).get("filings", {}).get("recent", {})
    accessions, documents = recent.get("accessionNumber", []), recent.get("primaryDocument", [])
    dates = recent.get("filingDate", [])
    rows: list[dict] = []
    count = 0
    for i, form in enumerate(recent.get("form", [])):
        if form != "4" or count >= limit_filings:
            continue
        count += 1
        accession = accessions[i].replace("-", "")
        filename = documents[i].split("/")[-1]
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{filename}"
        try:
            parsed = parse_form4_xml(source.xml(url))
        except Exception:
            continue  # Preserve the historical per-filing failure policy.
        for transaction in parsed["transactions"]:
            rows.append({"symbol": symbol, "cik": cik, "accn": accessions[i],
                         "owner_name": parsed["owner_name"], "owner_title": parsed["owner_title"],
                         "is_officer": parsed["is_officer"], "is_director": parsed["is_director"],
                         "is_ten_pct_owner": parsed["is_ten_pct_owner"], "is_10b5_1_plan": parsed["is_10b5_1_plan"],
                         "filed_date": dates[i] if i < len(dates) else None, **transaction})
    return rows


@dataclass(frozen=True)
class InsiderAttempt:
    symbol: str
    rows: list[dict] | None = None
    error: Exception | None = None


class InsiderSource(Protocol):
    def mapping(self): ...
    def resolve(self, symbol: str, mapping) -> str | None: ...
    def attempts(self, ciks: dict[str, str], max_workers: int) -> Iterable[InsiderAttempt]: ...


class InsiderStore(Protocol):
    def fetched_at(self, symbols: list[str]) -> dict[str, datetime | None]: ...
    def save(self, symbol: str, rows: list[dict]) -> None: ...
    def errors(self, failed: dict[str, str]) -> None: ...


def sync_insiders(symbols: list[str], source: InsiderSource, store: InsiderStore,
                  classify_error: Callable[[Exception], str], *, now: Callable[[], datetime],
                  max_age_hours: int | None = None, max_workers: int = 4, progress_cb=None) -> dict:
    # 0 historically means the default 24 h, not a forced refresh; retain that rule.
    hours = max_age_hours or 24
    symbols = list(dict.fromkeys(symbols))
    failed: dict[str, str]
    try:
        mapping = source.mapping()
    except Exception as exc:
        reason = classify_error(exc)
        failed = {symbol: reason for symbol in symbols}
        store.errors(failed)
        return {"refreshed": 0, "failed": failed}
    fetched_at = store.fetched_at(symbols)
    checked_at = now()
    stale = []
    for symbol in symbols:
        fetched = fetched_at.get(symbol)
        if fetched is None or (checked_at - fetched).total_seconds() > hours * 3600:
            stale.append(symbol)
    if not stale:
        return {"refreshed": 0, "failed": {}}
    ciks: dict[str, str] = {}
    failed = {}
    for symbol in stale:
        cik = source.resolve(symbol, mapping)
        if cik:
            ciks[symbol] = cik
        else:
            failed[symbol] = "Símbolo no encontrado en el mapeo ticker→CIK de la SEC"
    for done, attempt in enumerate(source.attempts(ciks, max_workers), start=1):
        try:
            if attempt.error is not None:
                raise attempt.error
            store.save(attempt.symbol, attempt.rows or [])
        except Exception as exc:
            failed[attempt.symbol] = classify_error(exc)
        if progress_cb:
            progress_cb(done, len(stale), attempt.symbol)
    store.errors(failed)
    return {"refreshed": len(stale) - len(failed), "failed": failed}
