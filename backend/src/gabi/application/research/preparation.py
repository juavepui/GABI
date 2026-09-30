"""Explicit download of the SEC and price history a reconstruction or backtest needs."""

from datetime import date

from gabi.application.errors import QueryError
from gabi.application.research.reservations import require_observed_period

MAX_FAILURES = 1_000


def normalize_preparation(start: str | None, end: str | None, options: dict | None) -> dict:
    """`date` prepares one reconstruction date; `backtest` every rebalance of a backtest range."""
    options = dict(options or {})
    scope = options.get("scope")
    if scope == "date":
        options.setdefault("universe_limit", None)
        if set(options) != {"scope", "universe_limit"} or options["universe_limit"] not in (15, 50, None):
            raise QueryError("invalid_job", "La preparación por fecha admite 15, 50 o todas las empresas.", 422)
        if end is not None:
            raise QueryError("invalid_job", "La preparación por fecha admite una sola fecha.", 422)
        require_observed_period(start)
        return options
    if scope == "backtest":
        options.setdefault("max_symbols", None)
        if (set(options) != {"scope", "months", "max_symbols"} or options["months"] not in (1, 3, 6, 12)
                or options["max_symbols"] not in (50, 100, 200, 500, None)):
            raise QueryError("invalid_job", "Los parámetros de preparación del backtest no son válidos.", 422)
        require_observed_period(start, end)
        if end is None or date.fromisoformat(start or "") >= date.fromisoformat(end):
            raise QueryError("invalid_job", "La preparación necesita un inicio anterior al fin.", 422)
        return options
    raise QueryError("invalid_job", "Indica si se prepara una fecha o un backtest.", 422)


def preparation_result(start: str, end: str | None, options: dict, summary: dict,
                       failures: dict[str, dict[str, str]]) -> dict:
    rows = [{"symbol": symbol, "etapa": stage, "motivo": str(reason)}
            for symbol, stages in sorted(failures.items()) for stage, reason in sorted(stages.items())]
    return {"kind": "prepare_history", "start": start, "end": end, "options": options, **summary,
            "failed_symbols": len(failures), "failures": rows[:MAX_FAILURES],
            "failures_truncated": len(rows) > MAX_FAILURES}
