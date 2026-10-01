"""Read the published search ledger without touching operational or reserved data."""

from typing import Protocol

from gabi.application.errors import QueryError
from gabi.domain.research.trial_presentation import rows

OVERFITTING_AUDIT = "docs/overfitting-audit/audit.json"


class PublishedLedger(Protocol):
    def read(self) -> dict: ...


class PublishedArtifacts(Protocol):
    def read(self, ref: str) -> tuple[object, bool | None]: ...


class ResearchCatalog:
    def __init__(self, source: PublishedLedger, artifacts: PublishedArtifacts | None = None):
        self.source, self.artifacts = source, artifacts

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

    def trial(self, trial_id: str) -> dict:
        """One published trial: what was tested (its configuration) and what came out (its published result)."""
        ledger = self.source.read()
        row = next((row for row in ledger["legacy_entries"] + ledger["additional_observed_records"]
                    if row["id"] == trial_id), None)
        if row is None:
            raise QueryError("trial_not_found", "El ensayo no está en el registro publicado.", 404)
        detail = {field: row[field] for field in (
            "id", "family", "specification_ref", "result_ref", "observed_sample", "planned_sample", "state",
            "decision", "failures", "demonstrated_superiority")}
        detail |= {"configuration": rows(row.get("configuration") or {}), "result": [], "series": None,
                   "statistics": [], "result_verified": None, "result_note": None}
        if not row.get("result_ref"):
            detail["result_note"] = "Ensayo prospectivo: su resultado aún no existe."
            return detail
        if self.artifacts is None:
            return detail
        try:
            value, verified = self.artifacts.read(row["result_ref"])
        except QueryError as error:  # The configuration is still worth showing.
            detail["result_note"] = error.message
            return detail
        detail["result_verified"] = verified
        if isinstance(value, list) and value and isinstance(value[0], dict) and "date" in value[0]:
            detail["series"] = value  # Published period returns (fractions), shown as they are.
        else:
            detail["result"] = rows(value)
        trial = ((row.get("configuration") or {}).get("trial") or {}).get("trial_id")
        if trial and row["specification_ref"].startswith(OVERFITTING_AUDIT):
            # The audit published PSR/Sharpe per trial; read them instead of recomputing from the series.
            stats, _ = self.artifacts.read(f"{OVERFITTING_AUDIT}#/including_cost_sensitivity/trial_statistics/{trial}")
            detail["statistics"] = rows(stats)
        return detail
