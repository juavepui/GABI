"""CSV of the filtered Ranking (#196): the visible columns, with query date, model and units in its header."""

import csv
import io
import math

from gabi.application.errors import QueryError
from gabi.application.market.queries import RankingResult
from gabi.domain.market.units import BASE_METRICS, metric_unit

EARNINGS = ("next_earnings_date", "next_earnings_days")
COLUMNS = (*BASE_METRICS, *EARNINGS)
DEFAULT_COLUMNS = ("price", "composite_score", "confidence", "market_cap", "pe")
UNITS = {"fraction": "fracción (0.05 = 5 %)", "percent": "porcentaje (30 = 30 %)", "points_0_100": "puntos 0-100",
         "USD": "USD", "ratio": "múltiplo", "count": "recuento"}


def _unit(column: str) -> str:
    if column == "next_earnings_date":
        return "fecha"
    if column == "next_earnings_days":
        return "días"
    return UNITS[metric_unit(column)]


def _cell(value) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return ""
    return str(value)


def ranking_csv(result: RankingResult, columns: list[str], query: str) -> str:
    """Every filtered row in the backend order (no pagination); values in their wire units, never rounded."""
    unknown = sorted(set(columns) - set(COLUMNS))
    if unknown:
        raise QueryError("invalid_columns", "Columnas desconocidas: " + ", ".join(unknown), 422)
    chosen = list(dict.fromkeys(columns)) or list(DEFAULT_COLUMNS)
    model = result.model
    buffer = io.StringIO()
    buffer.write(f"# GABI · Ranking consultado el {result.snapshot.generated_at.isoformat()}\n")
    buffer.write(f"# Modelo {model.model_id} ({model.status}, modo {model.mode}); "
                 f"sin ventaja independiente demostrada frente a SPY\n")
    buffer.write(f"# Filtros y orden: {query or 'por defecto'}\n")
    buffer.write(f"# Filas: {len(result.rows)} de {result.total}\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["posicion", "simbolo", "nombre", "sector", *[f"{column} [{_unit(column)}]" for column in chosen]])
    # Only the chosen columns, read once; a column absent from the table is written empty.
    frame = result.rows.reindex(columns=["name", "sector", *chosen])
    ranks = result.snapshot.table.index.get_indexer(frame.index) + 1
    for rank, (symbol, *values) in zip(ranks, frame.itertuples(name=None), strict=True):
        writer.writerow([int(rank), symbol, *[_cell(value) for value in values]])
    return buffer.getvalue()
