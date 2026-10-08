"""Explicit, atomic import of a local SEC quarter through bounded batch ports."""

from collections.abc import Iterator
from contextlib import AbstractContextManager
from typing import Protocol

import pandas as pd

from gabi.domain.research import sec_bulk as rules


class QuarterArchive(Protocol):
    def batches(self, member: str) -> AbstractContextManager[Iterator[pd.DataFrame]]: ...


class QuarterWrites(Protocol):
    def submissions(self, records: list[tuple]) -> None: ...
    def facts(self, records: list[tuple]) -> None: ...


class QuarterRepository(Protocol):
    def transaction(self) -> AbstractContextManager[QuarterWrites]: ...


def import_quarter(archive: QuarterArchive, repository: QuarterRepository, source_url: str, ciks: set[str],
                   *, tracked: set[str], shares: set[str], facts: bool = True,
                   max_ciks: int = 10000, max_accessions: int = 500000) -> dict:
    if min(max_ciks, max_accessions) <= 0 or len(ciks) > max_ciks:
        raise ValueError('SEC bulk issuer budget exceeded')
    result = dict(submissions=0, facts=0, excluded_segment_or_coreg=0, invalid=0)
    accessions: set[str] = set()
    with archive.batches('sub.txt') as batches, repository.transaction() as writes:
        for frame in batches:
            records = rules.submissions(frame, ciks, source_url)
            accessions.update(row[0] for row in records)
            if len(accessions) > max_accessions:
                raise ValueError('SEC bulk accession budget exceeded')
            writes.submissions(records)
            result['submissions'] += len(records)
        if facts:
            with archive.batches('num.txt') as batches:
                for frame in batches:
                    records, excluded, invalid = rules.facts(frame, accessions, tracked, shares)
                    writes.facts(records)
                    result['facts'] += len(records)
                    result['excluded_segment_or_coreg'] += excluded
                    result['invalid'] += invalid
    return result
