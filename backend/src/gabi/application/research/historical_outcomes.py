"""Later return of a reconstructed ranking's leaders, only where the whole window was observed."""

from collections.abc import Callable
from datetime import date, timedelta

import pandas as pd

from gabi.application.errors import QueryError
from gabi.application.research.historical import _json_value
from gabi.application.research.reservations import OBSERVED_END, require_observed_period

HORIZONS = (6, 12)
BLOCKS = (("Value", "value_score"), ("Quality", "quality_score"),
          ("Momentum", "momentum_score"), ("Risk", "risk_score"))
PRICE_TOLERANCE = timedelta(days=7)  # evaluation._adjusted_at looks up to 7 days after the horizon.
Evaluate = Callable[[list[str], str, int, float], dict]


def normalize_outcomes(request: dict | None) -> dict:
    request = dict(request or {})
    request.setdefault("cost_bps", 0.0)
    if set(request) != {"source_job_id", "top_n", "cost_bps"}:
        raise QueryError("invalid_job", "La evaluación no corresponde a un ranking histórico.", 422)
    source, top_n, cost = request["source_job_id"], request["top_n"], request["cost_bps"]
    if not isinstance(source, str) or len(source) != 32 or any(c not in "0123456789abcdef" for c in source):
        raise QueryError("invalid_job", "Indica un ranking histórico terminado válido.", 422)
    if isinstance(top_n, bool) or not isinstance(top_n, int) or not 1 <= top_n <= 50:
        raise QueryError("invalid_job", "Las primeras candidatas deben ser entre 1 y 50.", 422)
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not 0 <= cost <= 100:
        raise QueryError("invalid_job", "El coste por operación debe estar entre 0 y 100 pb.", 422)
    return request | {"cost_bps": float(cost)}


def horizon_end(as_of: str, months: int) -> date:
    return (pd.Timestamp(as_of) + pd.DateOffset(months=months)).date()


def _outcome(symbols: list[str], as_of: str, months: int, cost: float, evaluate: Evaluate) -> dict:
    end = horizon_end(as_of, months)
    if end + PRICE_TOLERANCE > OBSERVED_END:
        # The legacy page called this "pending"; here the prices exist but belong to the reserved period.
        return {"months": months, "status": "reserved", "end_date": end.isoformat(), "requested": len(set(symbols)),
                "available": None, "portfolio_return": None, "benchmark_return": None,
                "excess_return": None, "missing": []}
    return {"months": months} | {key: _json_value(value) for key, value in
                                 evaluate(symbols, as_of, months, cost).items()}


def build_outcomes(ranking: dict, request: dict, source_sha256: str, evaluate: Evaluate) -> dict:
    """Same candidate and block selection as the old page, evaluated with the unchanged formula."""
    as_of = ranking["as_of"]
    require_observed_period(as_of)
    table = pd.DataFrame(ranking["rows"])
    if not table.empty:
        table = table.set_index("symbol")
    top_n, cost = request["top_n"], request["cost_bps"]
    scored = table[table["composite_score"].notna()] if "composite_score" in table else table.iloc[:0]
    candidates = scored.head(top_n).index.tolist()
    blocks = []
    for label, column in BLOCKS:
        leaders: list[str] = []
        if column in table and "score_coverage" in table:
            eligible = table[table[column].notna() & (table["score_coverage"] >= .5)]
            leaders = eligible.nlargest(top_n, column).index.tolist()
        blocks.append({"block": label, "column": column, "symbols": leaders,
                       "outcome": _outcome(leaders, as_of, 12, cost, evaluate)})
    return {"kind": "historical_outcomes", "status": "RETROSPECTIVE_EXPLORATORY",
            "independent_advantage_demonstrated": False, "as_of": as_of,
            "source_job_id": request["source_job_id"], "source_result_sha256": source_sha256,
            "top_n": top_n, "cost_bps": cost, "observed_cutoff": OBSERVED_END.isoformat(),
            "candidates": candidates,
            "horizons": [_outcome(candidates, as_of, months, cost, evaluate) for months in HORIZONS],
            "blocks": blocks}
