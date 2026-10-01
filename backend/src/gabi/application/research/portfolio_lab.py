"""Portfolio Lab: six weighting schemes over the same point-in-time candidates, as an explicit Research job."""

from collections.abc import Callable
from datetime import date

import pandas as pd

from gabi.application.errors import QueryError
from gabi.application.research.historical import _json_value
from gabi.application.research.reservations import require_observed_period

SCHEMES = ("equal_weight", "inverse_vol", "min_variance", "score_weighted", "score_constrained", "risk_parity")
KEYS = {"months", "top_n", "initial_capital", "schemes", "mode", "max_symbols"}
MAX_PERIODS = 200
MAX_CURVE_POINTS = 5_000
SPY = "spy"


def normalize_portfolio_lab(start: str | None, end: str | None, options: dict | None) -> dict:
    """The Streamlit form, restricted to the observed S&P 500 history like the V1/V2 backtests."""
    require_observed_period(start, end)
    if end is None or date.fromisoformat(start or "") >= date.fromisoformat(end):
        raise QueryError("invalid_job", "Portfolio Lab necesita un inicio anterior al fin.", 422)
    options = dict(options or {})
    options.setdefault("max_symbols", None)
    if set(options) != KEYS:
        raise QueryError("invalid_job", "Los parámetros no corresponden a Portfolio Lab.", 422)
    months, top_n, capital = options["months"], options["top_n"], options["initial_capital"]
    schemes, mode, sample = options["schemes"], options["mode"], options["max_symbols"]
    if (months not in (1, 3, 6, 12) or isinstance(months, bool) or not isinstance(top_n, int)
            or isinstance(top_n, bool) or not 2 <= top_n <= 50
            or isinstance(capital, bool) or not isinstance(capital, int | float) or not 1_000 <= capital <= 10_000_000):
        raise QueryError("invalid_job", "Rebalanceo, posiciones o capital no válidos.", 422)
    if (not isinstance(schemes, list) or not schemes or len(set(schemes)) != len(schemes)
            or not set(schemes) <= set(SCHEMES)):
        raise QueryError("invalid_job", "Selecciona al menos un esquema conocido.", 422)
    if mode not in ("validation", "fast_dev") or (mode == "validation") != (sample is None) \
            or mode == "fast_dev" and sample not in (50, 100, 200):
        raise QueryError("invalid_job", "La muestra no corresponde al modo de Portfolio Lab.", 422)
    return {"months": months, "top_n": top_n, "initial_capital": float(capital),
            "schemes": [scheme for scheme in SCHEMES if scheme in schemes], "mode": mode, "max_symbols": sample}


def _records(table: pd.DataFrame, name: str) -> list[dict]:
    if len(table) > MAX_PERIODS:
        raise ValueError(f"Portfolio Lab supera el límite del artefacto ({name}).")
    return [{str(key): _json_value(value) for key, value in row.items()} for row in table.to_dict(orient="records")]


def build_portfolio_lab(start: str, end: str, options: dict, run: Callable[[str, str, dict], dict]) -> dict:
    options = normalize_portfolio_lab(start, end, options)
    result = run(start, end, options)
    schemes = result["schemes"]
    curve = pd.DataFrame({name: data["nav_curve"] for name, data in schemes.items()} | {SPY: result["nav_curve_spy"]})
    if len(curve) > MAX_CURVE_POINTS:
        raise ValueError("La curva de Portfolio Lab supera el límite del artefacto.")
    curve.index = [pd.Timestamp(value).date().isoformat() for value in curve.index]
    return {
        "kind": "portfolio_lab", "status": "RETROSPECTIVE_EXPLORATORY", "independent_advantage_demonstrated": False,
        "start": start, "end": end, "options": options, "mode": result["mode"],
        "skipped": _json_value(result["skipped"]),
        "labels": result["labels"], "scenario_labels": result["scenario_labels"],
        "scenario_ground": result["scenario_ground"],
        # A list: artifacts are stored with sorted keys and the schemes keep the engine's order.
        "schemes": [{
            "id": name, "label": data["label"], "periods": _records(data["periods"], f"{name} periods"),
            "daily": _json_value(data["daily"]), "turnover_medio": _json_value(data["turnover_medio"]),
            "comision_total": _json_value(data["comision_total"]), "hhi": _json_value(data["hhi"]),
            "tracking_error": _json_value(data["tracking_error"]),
            "top3_contribution_to_risk": _json_value(data["top3_contribution_to_risk"]),
            "last_weights": _json_value(data["last_weights"]),
            "contribution_to_risk": _json_value(data["contribution_to_risk"]),
        } for name, data in schemes.items()],
        "scenarios": _json_value(result["scenarios"]),
        "curve": [{"fecha": index, **{key: _json_value(value) for key, value in row.items()}}
                  for index, row in curve.iterrows()],
    }
