"""Coverage and warnings of a verified historical ranking artifact, as the Streamlit page showed them."""

from typing import Protocol

import pandas as pd

from gabi.application.administration.jobs import Jobs
from gabi.application.errors import QueryError
from gabi.application.research.historical import _json_value

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

    def table(self, job_id: str, *, hide_no_data: bool, sort: str | None, descending: bool,
              offset: int, limit: int) -> dict:
        job = self.jobs.get(job_id)
        if job["kind"] != "historical_ranking":
            raise QueryError("job_not_found", "El ranking histórico no existe.", 404)
        result = self.jobs.result(job_id)
        return {"job_id": job_id, "result_sha256": job["result_sha256"]} | historical_table(
            result, hide_no_data=hide_no_data, sort=sort, descending=descending, offset=offset, limit=limit)


# Columns, labels and wire units of the old reconstruction table (app/pages/8_Ranking_Historico.py).
# Streamlit printed shares_dilution_yoy, buyback_yield and capex_to_ocf raw although they are fractions
# labelled "(%)", and acquisitions_latest raw although it is USD; here they carry their real unit.
TABLE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("resolved_title", "Empresa (nombre SEC)", "text"), ("sector", "Sector", "text"),
    ("market_cap", "Cap. mercado (mil M$)", "USD"), ("price", "Precio", "USD"), ("pe", "PER", "ratio"),
    ("pb", "P/VC", "ratio"), ("roic", "ROIC (%)", "fraction"), ("gross_margin", "Margen bruto (%)", "fraction"),
    ("operating_margin", "Margen operativo (%)", "fraction"), ("debt_to_equity", "Deuda/Patrimonio", "ratio"),
    ("net_debt_to_ebitda", "Deuda neta/EBITDA", "ratio"),
    ("revenue_growth_yoy", "Crec. ingresos YoY (%)", "fraction"),
    ("revenue_cagr_3y", "Crec. ingresos 3A CAGR (%)", "fraction"),
    ("fcf_cagr_3y", "Crec. FCF 3A CAGR (%)", "fraction"),
    ("fundamentals_period_end", "Cierre del ejercicio usado", "text"),
    ("quality_persistence_score", "Persistencia calidad", "fraction"),
    ("roic_persistence_mean", "ROIC medio histórico", "fraction"),
    ("roic_persistence_std", "Variabilidad ROIC", "fraction"), ("roic_years", "Años ROIC", "count"),
    ("operating_margin_persistence_mean", "Margen operativo medio", "fraction"),
    ("operating_margin_persistence_std", "Variabilidad margen", "fraction"),
    ("operating_margin_years", "Años margen", "count"),
    ("fcf_conversion_mean", "Conversión FCF media", "fraction"), ("fcf_years", "Años FCF", "count"),
    ("revenue_per_share_cagr", "Ventas por acción CAGR", "fraction"),
    ("implied_fcf_growth", "Crecimiento FCF implícito", "fraction"),
    ("historical_fcf_cagr", "historical_fcf_cagr", "fraction"),
    ("expectations_gap", "Brecha expectativas", "fraction"),
    ("shares_dilution_yoy", "Dilución acciones YoY (%)", "fraction"),
    ("buyback_yield", "Rentabilidad recompra (%)", "fraction"),
    ("capex_to_ocf", "CAPEX / flujo operativo (%)", "fraction"),
    ("acquisitions_latest", "Adquisiciones último año", "USD"),
    ("capital_allocation_coverage", "Cobertura asignación", "text"), ("metrics_available", "Datos", "count"),
    ("metrics_possible", "Datos posibles", "count"), ("score_coverage", "Cobertura %", "fraction"),
    ("value_score", "Value", "points_0_100"), ("quality_score", "Quality", "points_0_100"),
    ("momentum_score", "Momentum", "points_0_100"), ("risk_score", "Risk", "points_0_100"),
    ("composite_score", "Composite", "points_0_100"),
)
SCORE_COLUMNS = {"value_score", "quality_score", "momentum_score", "risk_score", "composite_score", "confidence"}
MAX_TABLE_ROWS = 200


def _cell(value):
    return _json_value(value)


def historical_table(result: dict, *, hide_no_data: bool, sort: str | None, descending: bool,
                     offset: int, limit: int) -> dict:
    """Rows in the engine order (or sorted by one column) with the percentile that colours each cell."""
    keys = {key for key, _, _ in TABLE_COLUMNS}
    if sort is not None and sort not in keys:
        raise QueryError("invalid_query", "No se puede ordenar por esa columna.", 422)
    if not 1 <= limit <= MAX_TABLE_ROWS or offset < 0:
        raise QueryError("invalid_query", "La página de la tabla no es válida.", 422)
    table = pd.DataFrame(result["rows"])
    if table.empty:
        return {"columns": [], "total": 0, "offset": offset, "rows": []}
    if "resolved_title" not in table:
        table["resolved_title"] = None
    table["resolved_title"] = table["resolved_title"].where(table["resolved_title"].notna(),
                                                            table.get("name", table["symbol"]))
    table["resolved_title"] = table["resolved_title"].where(table["resolved_title"].notna(), table["symbol"])
    if hide_no_data:
        keep = pd.Series(False, index=table.index)
        for column in ("roic", "market_cap"):
            if column in table:
                keep |= table[column].notna()
        table = table[keep]
    if sort is not None and sort in table:
        table = table.sort_values(sort, ascending=not descending, na_position="last", kind="stable")
    present = [(key, label, unit) for key, label, unit in TABLE_COLUMNS if key in table]
    rows = []
    for _, row in table.iloc[offset:offset + limit].iterrows():
        values = {key: _cell(row[key]) for key, _, _ in present}
        colors = {}
        for key, _, unit in present:
            basis = row[key] if key in SCORE_COLUMNS else row.get(f"{key}_pct") if unit != "text" else None
            colors[key] = _cell(basis)
        rows.append({"symbol": row["symbol"], "values": values, "colors": colors})
    return {"columns": [{"key": key, "label": label, "unit": unit,
                         "colored": key in SCORE_COLUMNS or f"{key}_pct" in table} for key, label, unit in present],
            "total": len(table), "offset": offset, "rows": rows}
