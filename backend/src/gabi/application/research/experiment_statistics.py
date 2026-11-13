"""PSR/DSR and tail risk of logged experiments, with the inputs the Streamlit page used."""

from collections.abc import Callable
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.application.research.backtest_diagnostics import _tail
from gabi.application.research.experiments import ExperimentStore, returns_series

# Horizon of one saved observation, from the registered frequency (Research Lab wording).
TAIL_HORIZONS = {252: "una sesión", 12: "un mes", 4: "un trimestre", 2: "un semestre", 1: "un año"}
UNKNOWN_HORIZON = "una observación (frecuencia no identificada)"


class SharpeMath(Protocol):
    def psr_from_returns(self, returns: pd.Series, periods_per_year: float) -> dict: ...
    def deflated_sharpe(self, sharpe: float, trial_sharpes: list[float], n_obs: int, periods_per_year: float,
                        skew: float, kurtosis: float) -> dict: ...
    def psr_annualized(self, sharpe: float, n_obs: int, periods_per_year: float, skew: float,
                       kurtosis: float) -> float: ...
    def tail_risk(self, returns: pd.Series, horizon: str) -> dict: ...


class ExperimentStatistics:
    def __init__(self, store: ExperimentStore, research_mode: Callable[[], bool], math: SharpeMath):
        self.store, self.research_mode, self.math = store, research_mode, math

    def _require_research(self) -> None:
        if not self.research_mode():
            raise QueryError("research_required", "Research Lab requiere el modo Research local.", 403)

    def _experiment(self, experiment_id: int) -> dict:
        item = self.store.get(experiment_id)
        if item is None:
            raise QueryError("experiment_not_found", "El experimento no existe.", 404)
        return item

    def deflated_sharpe(self, experiment_id: int, family: str | None) -> dict:
        """N = experiments with a Sharpe in the chosen family (all of them when no family exists)."""
        self._require_research()
        rows, families = self.store.list(None, None)
        if family is not None and family not in families:
            raise QueryError("invalid_request", "La familia no existe.", 422)
        if family is None and families:
            raise QueryError("invalid_request", "Indica la familia de intentos.", 422)
        trials = [row for row in rows if row["sharpe"] is not None and (family is None or row["family"] == family)]
        if len(trials) < 2:
            raise QueryError("insufficient_trials",
                             "Esta familia tiene menos de 2 experimentos con Sharpe; no se puede calcular DSR.", 422)
        if experiment_id not in {row["id"] for row in trials}:
            raise QueryError("invalid_request", "El experimento no pertenece a esa familia o no tiene Sharpe.", 422)
        selected = self._experiment(experiment_id)
        periods_per_year = float(selected["periods_per_year"] or 4)
        n_obs = int(selected["n_periods"] or 36)
        returns = returns_series(selected["returns"])
        if returns is not None:
            exact = self.math.psr_from_returns(returns, selected["periods_per_year"] or 4)
            skew, kurtosis, moments = exact["skew"], exact["kurtosis"], "returns"
        else:
            skew, kurtosis, moments = 0.0, 3.0, "normal_approximation"
        result = self.math.deflated_sharpe(selected["sharpe"], [row["sharpe"] for row in trials], n_obs,
                                           periods_per_year, skew, kurtosis)
        psr = self.math.psr_annualized(selected["sharpe"], n_obs, periods_per_year, skew, kurtosis)
        return {"experiment_id": experiment_id, "model_id": selected["model_id"], "family": family,
                "sharpe": selected["sharpe"], "n_obs": n_obs, "periods_per_year": periods_per_year,
                "skew": skew, "kurtosis": kurtosis, "moments": moments, "psr": psr,
                "dsr": result["dsr"], "sr0_benchmark": result["sr0_benchmark"], "n_trials": result["n_trials"],
                "trial_ids": [row["id"] for row in trials]}

    def tail_risk(self, experiment_id: int) -> dict:
        self._require_research()
        selected = self._experiment(experiment_id)
        returns = returns_series(selected["returns"])
        if returns is None:
            raise QueryError("returns_missing", "Este experimento no tiene serie de retornos guardada.", 422)
        horizon = TAIL_HORIZONS.get(selected["periods_per_year"], UNKNOWN_HORIZON)
        name = f"#{experiment_id} · {selected['model_id']}"
        try:
            series = {"name": name, "summary": _tail(self.math.tail_risk(returns, horizon)), "error": None}
        except (ValueError, TypeError) as exc:
            series = {"name": name, "summary": None, "error": str(exc)}
        return {"experiment_id": experiment_id, "horizon": horizon,
                "message": "Horizonte según la frecuencia registrada del experimento; "
                           "no se convierte ni anualiza la serie.",
                "series": [series]}
