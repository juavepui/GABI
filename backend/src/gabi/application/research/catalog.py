"""Read the published search ledger without touching operational or reserved data."""

from typing import Protocol


class PublishedLedger(Protocol):
    def read(self) -> dict: ...


class ResearchCatalog:
    def __init__(self, source: PublishedLedger):
        self.source = source

    def overview(self) -> dict:
        ledger = self.source.read()
        published = ledger["legacy_entries"] + ledger["additional_observed_records"]
        return {
            "as_of": ledger["as_of"],
            "scope": ledger["scope"],
            "counts": ledger["counts"],
            "exhaustive_search_history": ledger["exhaustive_search_history"],
            "global_error_control_established": ledger["global_error_control_established"],
            "limitations": ledger["limitations"],
            "diagnostics": ledger["diagnostics"],
            "unresolved_groups": ledger["unresolved_groups"],
            "families": sorted({row["family"] for row in published}),
        }

    def trials(self, *, offset: int, limit: int, family: str | None = None) -> dict:
        ledger = self.source.read()
        published = ledger["legacy_entries"] + ledger["additional_observed_records"]
        rows = [row for row in published if family is None or row["family"] == family]
        # Do not expose arbitrary configuration or raw artifact contents through this endpoint.
        fields = ("id", "family", "configuration_sha256", "specification_ref", "result_ref",
                  "observed_sample", "planned_sample", "state", "decision", "failures",
                  "demonstrated_superiority")
        return {
            "total": len(rows),
            "offset": offset,
            "items": [{field: row[field] for field in fields} for row in rows[offset:offset + limit]],
        }
