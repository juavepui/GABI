"""Read-only evidence for the accredited SEC-facts freshness guard of the 2011-2025 revalidation."""

from pathlib import Path

from gabi.infrastructure.storage.bounded_reads import bounded_rows, read_only

REQUIRED = {"historical_identity_intervals", "entity_observations"}


class SqliteIssuerFactsFreshness:
    def __init__(self, path: Path, *, max_rows=200000, max_bytes=64 * 1024 * 1024, max_field_bytes=1024):
        if min(max_rows, max_bytes, max_field_bytes) <= 0:
            raise ValueError("Freshness limits must be positive")
        self.path = path
        self.limits = dict(max_rows=max_rows, max_bytes=max_bytes, max_field_bytes=max_field_bytes)

    def evidence(self, identity_source: str, tiers: tuple[str, ...]) -> tuple[list[tuple], dict[str, str]]:
        """Last accredited interval end per CIK and last filed SEC fact per CIK, in one read transaction."""
        with read_only(self.path, self.limits["max_field_bytes"]) as (db, tables):
            if missing := REQUIRED - tables:
                raise ValueError(f"Missing local identity tables: {sorted(missing)}")
            intervals = bounded_rows(db, "SELECT cik,MAX(valid_to) FROM historical_identity_intervals WHERE source_id=? "
                                     f"AND status IN ({','.join('?' * len(tiers))}) GROUP BY cik",
                                     (identity_source, *tiers), **self.limits)
            latest = dict(bounded_rows(db, "SELECT substr(entity_id,5),MAX(json_extract(payload_json,'$.filed_date')) "
                                       "FROM entity_observations WHERE dataset='edgar_facts' GROUP BY entity_id",
                                       (), **self.limits))
        return intervals, latest
