"""Offline identity audits with explicit evidence and read ports."""
from collections.abc import Callable
from typing import Protocol

from gabi.domain.market.identity import normalize_cik
from gabi.domain.research import historical_identity_audit as rules
from gabi.domain.research.periods import P2010, Period


class IdentityAuditReader(Protocol):
    def evidence_inputs(self, period: Period) -> tuple: ...
    def coverage_inputs(self, period: Period) -> tuple: ...
    def counts(self) -> dict[str, int]: ...

def build_evidence_intervals(reader: IdentityAuditReader, official_names: Callable[[str], dict | None],
                             listing_life: Callable[[str], dict | None], nominations: tuple[dict, ...],
                             period: Period = P2010, *,
                             prepare_evidence: Callable[[set[str], int | None], None] | None = None) -> list[dict]:
    history, candidates, proofs, submissions = reader.evidence_inputs(period)
    names = {cik: official_names(cik) for cik in sorted({normalize_cik(row[0]) for row in submissions})}
    memberships, by_symbol = rules.member_candidates(history, candidates, nominations, period)
    ciks = {candidate['cik'] for member in memberships for candidate in by_symbol.get(member['symbol'], [])
            if max(member['valid_from'], candidate['start'], period.start) <
               min(member['valid_to'], candidate['end'], period.end_exclusive)}
    if prepare_evidence is not None:
        prepare_evidence(ciks, None)
    lives = {cik: listing_life(cik) for cik in sorted(ciks)}
    return rules.build_evidence_intervals(history, candidates, proofs, submissions, names, lives, nominations, period)

def coverage_report(reader: IdentityAuditReader, period: Period = P2010) -> dict:
    history, candidates, aliases, intervals, names = reader.coverage_inputs(period)
    return rules.coverage_report(history, candidates, aliases, intervals, names, period)


def annual_report_symbol_evidence[Document](
        rows: Callable[[], list[tuple]], nominations, limit: int, *, extended: bool,
        listing_life: Callable[[str], dict | None], fetch_annual_report: Callable[[str, dict], tuple[str, Document]],
        text: Callable[[Document], str], digest: Callable[[Document], str],
        symbols: Callable[[str, bool], set[str]]) -> tuple[list[dict], int, int]:
    """Ticker proofs from 10-K text for intervals the XBRL covers left open.

    Early XBRL covers often omit ``dei:TradingSymbol``; the annual report's market section states
    it. A report naming exactly one symbol is a proof (URL + SHA-256); otherwise it is ignored.
    Returns the records, the number of target intervals and the reports downloaded."""
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    targets = rules.annual_report_targets(rows(), nominations)
    downloads = 0
    records = []
    for _symbol, cik, start, end, _status in targets:
        life = listing_life(cik)
        if life is None:
            continue
        for report in rules.reports_to_check(life["annual_reports"], start, end):
            if downloads >= limit:
                break
            url, path = fetch_annual_report(cik, report)
            downloads += 1
            found = symbols(text(path), extended)
            if extended and len(found) > 1:
                # Other companies' symbols (investees, spin-offs) appear in the
                # text; keep the one reviewed ticker of this CIK, if unique.
                found &= rules.reviewed_tickers(nominations, cik, report["filed"])
            if len(found) != 1:
                continue
            records.append({"symbol": next(iter(found)), "cik": cik, "accession": report["accession"],
                            "filed_date": report["filed"], "historical_name": life["name"],
                            "historical_name_source": "sec_10k_text", "sha256": digest(path), "source_url": url})
    return records, len(targets), downloads


def fetch_issuer_name_histories(read_ciks: Callable[[], list[str]], limit: int, *, cached: Callable[[str], bool],
                                download: Callable[[str], dict], errors: tuple[type[BaseException], ...],
                                log: Callable[[str], None]) -> dict:
    """Cache SEC's official name chain for still-unresolved historical CIKs."""
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    ciks = read_ciks()
    already = fetched = failed = 0
    for cik in ciks:
        if cached(cik):
            already += 1
            continue
        if fetched + failed >= limit:
            break
        try:
            if normalize_cik(download(cik)["cik"]) != cik:
                raise ValueError("SEC submissions issuer CIK mismatch")
            fetched += 1
        except errors as exc:
            failed += 1
            log(f"SEC issuer name history failed {cik}: {exc}")
    return {"candidate_ciks": len(ciks), "cached": already, "fetched": fetched, "failed": failed}
