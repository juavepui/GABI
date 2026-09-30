"""Explicit V1/V2 multifactor backtests with complete, bounded, hashed artifacts."""

from collections.abc import Callable
from datetime import date

import pandas as pd

from gabi.application.errors import QueryError
from gabi.application.research.historical import _json_value
from gabi.application.research.reservations import require_observed_period

MAX_PERIODS = 200
MAX_CURVE_POINTS = 5_000
V1_KEYS = {"months", "top_n", "cost_bps", "universe_size", "rotation_hurdle_points"}
V2_KEYS = {"months", "top_n", "mode", "max_symbols", "initial_capital", "commission_usd",
           "spread_bps", "rotation_hurdle_points"}


def _number(options: dict, key: str, low: float, high: float) -> float:
    value = options.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise QueryError("invalid_job", f"El parámetro {key} del backtest no es válido.", 422)
    return float(value)


def _choice(options: dict, key: str, allowed: tuple) -> object:
    value = options.get(key)
    if isinstance(value, bool) or value not in allowed:
        raise QueryError("invalid_job", f"El parámetro {key} del backtest no es válido.", 422)
    return value


def normalize_backtest(kind: str, start: str | None, end: str | None, options: dict | None) -> dict:
    """Validate a backtest command before it reaches the queue; unknown keys are rejected."""
    require_observed_period(start, end)
    if end is None or date.fromisoformat(start or "") >= date.fromisoformat(end):
        raise QueryError("invalid_job", "El backtest necesita un inicio anterior al fin.", 422)
    options = dict(options or {})
    if kind == "backtest_v2":
        options.setdefault("max_symbols", None)  # The universe mode is sent without a sample.
    expected = V1_KEYS if kind == "backtest_v1" else V2_KEYS
    if set(options) != expected:
        raise QueryError("invalid_job", "Los parámetros no corresponden al motor del backtest.", 422)
    common = {"months": _choice(options, "months", (1, 3, 6, 12)),
              "top_n": int(_number(options, "top_n", 1, 50)),
              "rotation_hurdle_points": _number(options, "rotation_hurdle_points", 0, 100)}
    if options["top_n"] != common["top_n"]:
        raise QueryError("invalid_job", "El número de empresas debe ser entero.", 422)
    if kind == "backtest_v1":
        return common | {"cost_bps": _number(options, "cost_bps", 0, 500),
                         "universe_size": _choice(options, "universe_size", (50, 100, 500))}
    mode = _choice(options, "mode", ("validation", "fast_dev"))
    max_symbols = options.get("max_symbols")
    if mode == "validation" and max_symbols is not None or mode == "fast_dev" and max_symbols not in (50, 100, 200):
        raise QueryError("invalid_job", "La muestra no corresponde al modo del backtest V2.", 422)
    capital = _number(options, "initial_capital", 1_000, 100_000_000)
    commission = _number(options, "commission_usd", 0, 100)
    if capital <= commission:
        raise QueryError("invalid_job", "El capital inicial debe superar la comisión.", 422)
    return common | {"mode": mode, "max_symbols": max_symbols, "initial_capital": capital,
                     "commission_usd": commission, "spread_bps": _number(options, "spread_bps", 0, 500)}


def _records(table: object, limit: int, name: str) -> list[dict]:
    if not isinstance(table, pd.DataFrame) or len(table) > limit:
        raise ValueError(f"El backtest supera el límite del artefacto ({name}).")
    return [{str(key): _json_value(value) for key, value in row.items()}
            for row in table.to_dict(orient="records")]


def _curve(series: dict[str, pd.Series]) -> list[dict]:
    frame = pd.DataFrame(series)
    if len(frame) > MAX_CURVE_POINTS:
        raise ValueError("La curva del backtest supera el límite del artefacto.")
    frame.index = [pd.Timestamp(value).date().isoformat() for value in frame.index]
    return [{"fecha": index, **{key: _json_value(value) for key, value in row.items()}}
            for index, row in frame.iterrows()]


def build_backtest(kind: str, start: str, end: str, options: dict,
                   run: Callable[[str, str, dict], dict]) -> dict:
    options = normalize_backtest(kind, start, end, options)
    result = run(start, end, options)
    artifact = {
        "kind": kind, "status": "RETROSPECTIVE_EXPLORATORY",
        "independent_advantage_demonstrated": False, "start": start, "end": end,
        "options": options, "periods": _records(result["periods"], MAX_PERIODS, "periods"),
        "skipped": _json_value(result["skipped"]),
        "data_quality": _json_value(result.get("data_quality", {})),
        "rotation_hurdle_points": _json_value(result["rotation_hurdle_points"]),
        "turnover_medio": _json_value(result["turnover_medio"]),
    }
    if kind == "backtest_v1":
        periods = result["periods"]
        return artifact | {
            "return": _json_value(result["return"]), "spy_return": _json_value(result["spy_return"]),
            "universo_ew_return": _json_value(result["universo_ew_return"]),
            "drawdown": _json_value(result["drawdown"]), "metrics": _json_value(result["metrics"]),
            "curve": _curve({"estrategia": periods.set_index("hasta")["capital"],
                             "universo_ew": periods.set_index("hasta")["universo_capital"],
                             "spy": periods.set_index("hasta")["spy_capital"]}),
        }
    return artifact | {
        "mode": result["mode"], "exit_events": _json_value(result["exit_events"]),
        "strict_result": bool(result["strict_result"]),
        "initial_capital": _json_value(result["initial_capital"]),
        "capital_final": _json_value(result["capital_final"]),
        "comision_total": _json_value(result["comision_total"]),
        "spread_total": _json_value(result["spread_total"]),
        "coste_total": _json_value(result["coste_total"]),
        "metrics": _json_value(result["metrics"]),
        "curve": _curve({"estrategia": result["nav_curve"], "spy": result["nav_curve_spy"]}),
    }


def _series(name: str, metrics: dict, total_return: object) -> dict:
    keys = ("anualizado", "vol_anualizada", "sharpe", "sortino", "max_drawdown")
    return {"name": name, "total_return": total_return, **{key: metrics.get(key) for key in keys}}


def backtest_preview(result: dict) -> dict:
    """Typed summary of an already verified artifact; it never recalculates the backtest."""
    if result.get("kind") not in {"backtest_v1", "backtest_v2"}:
        raise QueryError("job_not_found", "El backtest no existe.", 404)
    metrics = result["metrics"]
    preview = {
        "kind": result["kind"], "status": result["status"],
        "independent_advantage_demonstrated": result["independent_advantage_demonstrated"],
        "start": result["start"], "end": result["end"], **result["options"],
        "turnover_medio": result["turnover_medio"], "skipped": result["skipped"],
        "curve": result["curve"],
        "periods": [{("cobertura_universo" if key == "cobertura universo" else key): value
                     for key, value in row.items() if key not in {"capital", "spy_capital", "universo_capital"}}
                    for row in result["periods"]],
    }
    if result["kind"] == "backtest_v1":
        return preview | {"exit_events": [], "series": [
            _series("estrategia", metrics["estrategia"], result["return"]),
            _series("universo_ew", metrics["universo_ew"], result["universo_ew_return"]),
            _series("spy", metrics["spy"], result["spy_return"]),
        ]}
    curve = result["curve"]

    def total(name: str) -> float | None:
        first, last = curve[0][name] if curve else None, curve[-1][name] if curve else None
        return last / first - 1 if first and last is not None else None

    return preview | {
        "series": [_series("estrategia", metrics["estrategia"], total("estrategia")),
                   _series("spy", metrics["spy"], total("spy"))],
        "exit_events": result["exit_events"], "strict_result": result["strict_result"],
        "capital_final": result["capital_final"], "comision_total": result["comision_total"],
        "spread_total": result["spread_total"], "coste_total": result["coste_total"],
        "calmar": metrics["calmar"], "recovery_days": metrics["recovery_days"],
        "beta": metrics["beta"], "information_ratio": metrics["information_ratio"],
        "capture_upside": metrics["capture"]["upside"], "capture_downside": metrics["capture"]["downside"],
    }
