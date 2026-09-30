"""Explicit Fama-French 5 + Momentum contrast of a finished V1 backtest."""

from collections.abc import Callable

import pandas as pd

from gabi.application.errors import QueryError
from gabi.application.research.historical import _json_value
from gabi.application.research.reservations import require_observed_period

FACTOR_KEYS = {"source_job_id", "hac_lags"}
PARTS = ("regression", "stability", "benchmark")


def normalize_factor_contrast(request: dict | None) -> dict:
    request = dict(request or {})
    request.setdefault("hac_lags", None)  # None: the automatic Newey-West rule used by Streamlit.
    if set(request) != FACTOR_KEYS:
        raise QueryError("invalid_job", "El contraste no corresponde a un backtest.", 422)
    source, lags = request["source_job_id"], request["hac_lags"]
    if not isinstance(source, str) or len(source) != 32 or any(c not in "0123456789abcdef" for c in source):
        raise QueryError("invalid_job", "Indica un backtest V1 terminado válido.", 422)
    if lags is not None and (isinstance(lags, bool) or not isinstance(lags, int) or not 0 <= lags <= 400):
        raise QueryError("invalid_job", "Los retardos HAC deben ser un entero no negativo.", 422)
    return request


def build_factor_contrast(artifact: dict, request: dict, source_sha256: str,
                          run: Callable[[pd.DataFrame, int | None], dict]) -> dict:
    """Serialize each legacy diagnostic separately; a failed part keeps its message, not a guess."""
    if artifact.get("kind") != "backtest_v1":
        raise ValueError("El contraste Fama-French solo se aplica al backtest V1, como en Streamlit.")
    require_observed_period(artifact["start"], artifact["end"])
    periods = pd.DataFrame(artifact["periods"])
    lags = request["hac_lags"]
    if lags is not None and lags > len(periods) - 1:
        raise ValueError(f"El máximo retardo HAC para {len(periods)} periodos es {len(periods) - 1}.")
    result = run(periods, lags)
    output = {"kind": "backtest_factors", "status": "RETROSPECTIVE_EXPLORATORY",
              "independent_advantage_demonstrated": False, "source_job_id": request["source_job_id"],
              "source_result_sha256": source_sha256, "hac_lags_requested": lags,
              "factors_source": _json_value(result["factors_source"])}
    for part in PARTS:
        value = result[part]
        output[part] = None if isinstance(value, str) else _json_value(value)
        output[f"{part}_error"] = value if isinstance(value, str) else None
    return output
