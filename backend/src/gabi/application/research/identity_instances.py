"""Offline SEC cover scan with explicit metadata and local document ports."""

from dataclasses import dataclass
from typing import Protocol

from gabi.domain.market.identity import normalize_cik
from gabi.domain.research import historical_membership
from gabi.domain.research import identity_instances as rules
from gabi.domain.research.periods import P2010, Period


@dataclass(frozen=True)
class InstanceResult:
    proof: dict | None = None
    rejection: str | None = None


class InstanceMetadata(Protocol):
    def scan_inputs(self, period: Period) -> tuple: ...


class InstanceFiles(Protocol):
    def accessions(self, allowed: set[str]) -> list[str]: ...
    def proof(self, accession: str, *, cik: str, common_stock_only: bool,
              multi_class: frozenset[str]) -> InstanceResult: ...


def scan(reader: InstanceMetadata, files: InstanceFiles, nominations: tuple[dict, ...],
         period: Period = P2010, *, max_records: int = 100000) -> tuple[list[dict], dict]:
    if max_records <= 0:
        raise ValueError('Instance record budget must be positive')
    filings, candidates, history = reader.scan_inputs(period)
    snapshots = historical_membership._snapshots(history)
    snapshot_dates = [row[0] for row in snapshots]
    reviewed = [row for row in nominations if row['reason'] == 'multi_class_issuer']
    records: list[dict] = []
    failures: dict[str, int] = {}
    for accession in files.accessions(set(filings)):
        metadata = filings[accession]
        cik, filed_date, _instance, _name = metadata
        multi_class = frozenset(ticker for row in reviewed
            if row['cik'] == normalize_cik(cik) and row['valid_from'] <= filed_date < row['valid_to']
            for ticker in row['sec_tickers']) if period is not P2010 else frozenset()
        result = files.proof(accession, cik=cik, common_stock_only=period is not P2010, multi_class=multi_class)
        if result.rejection is not None:
            failures[result.rejection] = failures.get(result.rejection, 0) + 1
            continue
        if result.proof is None:
            raise ValueError('Instance reader returned neither proof nor rejection')
        records.extend(rules.dated_proofs(result.proof, accession, metadata, candidates, snapshots, snapshot_dates))
        if len(records) > max_records:
            raise ValueError('Instance record budget exceeded')
    return records, rules.summary(records, failures)
