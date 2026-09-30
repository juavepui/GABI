"""Coverage and warnings of a verified historical ranking artifact, as the Streamlit page showed them."""

from typing import Protocol

import pandas as pd

from gabi.application.administration.jobs import Jobs
from gabi.application.errors import QueryError

PREVIEW_ROWS = 100


class RankingQuality(Protocol):
    def block_coverage(self, table: pd.DataFrame) -> dict: ...
    def block_warnings(self, blocks: dict, threshold: float) -> list[str]: ...
    def ranking_warnings(self, quality: dict, threshold: float) -> list[str]: ...


def _count(table: pd.DataFrame, column: str, test) -> int:
    return int(test(table[column]).sum()) if column in table else 0


def coverage(table: pd.DataFrame, universe_info: dict, threshold: float, quality: RankingQuality) -> dict:
    historical = universe_info.get("historical_coverage") or None
    identity = None
    if "identity_status" in table and not historical:
        identity = {"ambiguous": _count(table, "identity_status", lambda s: s.eq("ambiguous")),
                    "unresolved": _count(table, "identity_status", lambda s: s.eq("unresolved"))}
    warnings = []
    if len(table):
        sector_missing = table["sector"].isna() if "sector" in table else pd.Series(True, index=table.index)
        approximate = (table["sector_is_approximate"].fillna(False).astype(bool)
                       if "sector_is_approximate" in table else pd.Series(False, index=table.index))
        bad = float((sector_missing | approximate).mean())
        if bad > 1 - threshold:
            warnings.append(
                f"**Sector**: {bad:.0%} de las empresas de esta tabla tienen sector aproximado o "
                "desconocido para esta fecha -- el color por sector y los percentiles sectoriales de una buena "
                "parte de la tabla no son point-in-time reales.")
        warnings += quality.block_warnings(quality.block_coverage(table), threshold)
    return {
        "threshold": threshold, "historical_coverage": historical, "identity": identity,
        "with_fundamentals": _count(table, "roic", lambda s: s.notna()),
        "with_price": _count(table, "market_cap", lambda s: s.notna()),
        "sector_approximate": _count(table, "sector_is_approximate", lambda s: s.fillna(False).astype(bool)),
        "no_sector": _count(table, "sector", lambda s: s.isna()), "warnings": warnings,
    }


class HistoricalQueries:
    def __init__(self, jobs: Jobs, quality: RankingQuality):
        self.jobs = jobs
        self.quality = quality

    def preview(self, job_id: str, threshold: float) -> dict:
        if not 0 <= threshold <= 1:
            raise QueryError("invalid_query", "El umbral de cobertura debe estar entre 0 y 1.", 422)
        job = self.jobs.get(job_id)
        if job["kind"] != "historical_ranking":
            raise QueryError("job_not_found", "El ranking histórico no existe.", 404)
        result = self.jobs.result(job_id)
        table = pd.DataFrame(result["rows"])
        rows = result["rows"][:PREVIEW_ROWS]
        return {
            "job_id": job_id, "as_of": result["as_of"], "status": result["status"],
            "independent_advantage_demonstrated": result["independent_advantage_demonstrated"],
            "universe_info": result["universe_info"], "total": result["total"], "shown": len(rows),
            "rows": rows, "coverage": coverage(table, result["universe_info"], threshold, self.quality),
            "result_sha256": job["result_sha256"],
        }
