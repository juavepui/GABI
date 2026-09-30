"""Conservative API boundary for research periods with reserved outcomes."""

from datetime import date

from gabi.application.errors import QueryError

OBSERVED_START = date(2010, 1, 1)
OBSERVED_END = date(2025, 7, 2)
FACTOR_END = date(2024, 7, 1)  # Default Factor Lab includes 12-month forward returns.


def require_observed_period(start: str | None, end: str | None = None) -> None:
    try:
        first = date.fromisoformat(start or "")
        last = date.fromisoformat(end) if end is not None else first
    except ValueError as exc:
        raise QueryError("invalid_job", "Indica fechas históricas ISO válidas.", 422) from exc
    if not OBSERVED_START <= first <= last <= OBSERVED_END:
        raise QueryError("reserved_period", "Solo se permite el histórico S&P 500 observado de 2010 a julio de 2025.", 403)


def require_factor_period(start: str | None, end: str | None) -> None:
    if end is None:
        raise QueryError("invalid_job", "Indica inicio y fin de Factor Lab.", 422)
    require_observed_period(start, end)
    first, last = date.fromisoformat(start or ""), date.fromisoformat(end or "")
    if last > FACTOR_END:
        raise QueryError("reserved_period", "El Factor Lab de 12 meses solo admite cierres hasta julio de 2024.", 403)
    if first >= last or (last - first).days > 2192:
        raise QueryError("invalid_job", "El Factor Lab necesita un intervalo positivo de hasta seis años.", 422)
