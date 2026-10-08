"""Bounded read-only evidence for retrospective identity audits."""

from pathlib import Path

import pandas as pd

from gabi.domain.research.historical_identity_audit import CANDIDATE_SOURCE
from gabi.infrastructure.storage.bounded_reads import bounded_rows, read_only


class SqliteIdentityAuditReads:
    def __init__(self, path: Path, *, max_rows=100000, max_bytes=32 * 1024 * 1024,
                 max_field_bytes=1024 * 1024):
        if min(max_rows, max_bytes, max_field_bytes) <= 0:
            raise ValueError('Identity audit limits must be positive')
        self.path = path
        self.limits = dict(max_rows=max_rows, max_bytes=max_bytes, max_field_bytes=max_field_bytes)

    def _inputs(self, period, *, coverage):
        with read_only(self.path, self.limits['max_field_bytes']) as (db, tables):
            if coverage:
                required = {'historical_membership', 'historical_issuer_candidates', 'entity_aliases', 'entities'}
                if missing := required - tables:
                    raise ValueError(f'Missing local identity tables: {sorted(missing)}')

            def rows(table, query, params=()):
                return bounded_rows(db, query, params, **self.limits) if table in tables else []

            history = pd.DataFrame(rows('historical_membership',
                'SELECT date,tickers FROM historical_membership WHERE source_id=? AND date<? ORDER BY date',
                (period.membership_source, period.end_exclusive)), columns=['date', 'tickers'])
            candidates = rows('historical_issuer_candidates',
                'SELECT symbol,cik,name,date_added,date_removed,observed_from '
                'FROM historical_issuer_candidates WHERE source_id=?', (CANDIDATE_SOURCE,))
            if coverage:
                aliases = rows('entity_aliases', 'SELECT a.symbol,a.entity_id,e.cik,a.valid_from,a.valid_to,'
                    'a.confidence FROM entity_aliases a JOIN entities e USING(entity_id)')
                intervals = rows('historical_identity_intervals',
                    'SELECT symbol,cik,valid_from,valid_to,status FROM historical_identity_intervals WHERE source_id=?',
                    (period.identity_source,))
                names = rows('sec_bulk_submissions', "SELECT cik,name,filed_date FROM sec_bulk_submissions "
                    "WHERE name IS NOT NULL AND name<>'' AND filed_date<=?", (period.last_day,))
                return history, candidates, aliases, intervals, names
            proofs = rows('entity_observations',
                "SELECT symbol,entity_id,payload_json FROM entity_observations WHERE dataset='filing_identity' "
                "AND json_extract(payload_json,'$.filed_date')>=? AND json_extract(payload_json,'$.filed_date')<?",
                (period.evidence_from, period.end_exclusive))
            submissions = rows('sec_bulk_submissions',
                'SELECT s.cik,s.accn,s.filed_date,s.name,s.form,s.source_url,a.sha256 '
                'FROM sec_bulk_submissions s LEFT JOIN sec_archive_files a ON a.url=s.source_url '
                "WHERE s.filed_date>=? AND s.filed_date<? AND s.form IN ('10-K','10-Q')",
                (period.evidence_from, period.end_exclusive)) if 'sec_archive_files' in tables else []
            return history, candidates, proofs, submissions

    def evidence_inputs(self, period):
        return self._inputs(period, coverage=False)

    def coverage_inputs(self, period):
        return self._inputs(period, coverage=True)

    def counts(self):
        with read_only(self.path, self.limits['max_field_bytes']) as (db, tables):
            return {key: db.execute(query).fetchone()[0] if table in tables else 0
                    for key, table, query in (
                        ('stored_observations', 'entity_observations',
                         "SELECT COUNT(*) FROM entity_observations WHERE dataset='filing_identity'"),
                        ('active_alias_rows', 'entity_aliases', 'SELECT COUNT(*) FROM entity_aliases'))}
