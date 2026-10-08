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
