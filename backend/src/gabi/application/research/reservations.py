"""Conservative API boundary for research periods with reserved outcomes."""

from datetime import date

from gabi.application.errors import QueryError

OBSERVED_START = date(2010, 1, 1)
OBSERVED_END = date(2025, 7, 2)


def require_observed_period(start: str | None, end: str | None = None) -> None:
    try:
        first = date.fromisoformat(start or "")
        last = date.fromisoformat(end) if end is not None else first
    except ValueError as exc:
        raise QueryError("invalid_job", "Indica fechas históricas ISO válidas.", 422) from exc
    if not OBSERVED_START <= first <= last <= OBSERVED_END:
        raise QueryError("reserved_period", "Solo se permite el histórico S&P 500 observado de 2010 a julio de 2025.", 403)
