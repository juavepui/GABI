"""Explicit Research Lab writes: a manual experiment and the deletion of one."""

import math
from collections.abc import Callable
from datetime import date
from typing import Protocol

from gabi.application.errors import QueryError
from gabi.domain.research.experiments import STAGES

REBALANCES = ("Quarterly", "Semiannual", "Annual", "Monthly")
FACTORS = "Value/Quality/Momentum/Risk"
TEXT_LIMITS = {"model_id": 80, "universe": 200, "cost_model": 200, "family": 120, "data_fingerprint": 200,
               "notes": 4_000}


class ExperimentLog(Protocol):
    def log(self, record: dict) -> int: ...
    def delete(self, experiment_id: int) -> bool: ...


def _text(value, name: str, required: bool = False) -> str | None:
    if value is not None and not isinstance(value, str):
        raise QueryError("invalid_experiment", "Un campo de texto no es válido.", 422)
    if value is not None and len(value) > TEXT_LIMITS[name]:
        raise QueryError("invalid_experiment", "Un campo de texto es demasiado largo.", 422)
    if required and not (value or "").strip():
        raise QueryError("invalid_experiment", "Indica el identificador del modelo.", 422)
    return value


def _day(value, name: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise QueryError("invalid_experiment", f"La fecha {name} no es válida.", 422) from exc


def _optional(value: float | None) -> float | None:
    """The Streamlit form stored 0 as "no value" (`sharpe or None`)."""
    if value is not None and not math.isfinite(value):
        raise QueryError("invalid_experiment", "Las métricas deben ser finitas.", 422)
    return value or None


def manual_record(form: dict) -> dict:
    """Keyword arguments for research_lab.log_experiment, exactly as the Streamlit form built them."""
    if form.get("stage") not in STAGES or form.get("rebalance") not in REBALANCES:
        raise QueryError("invalid_experiment", "La fase o el rebalanceo no son válidos.", 422)
    n_positions, n_periods, per_year = form.get("n_positions"), form.get("n_periods"), form.get("periods_per_year")
    if (not isinstance(n_positions, int) or not 1 <= n_positions <= 100 or not isinstance(n_periods, int)
            or not 1 <= n_periods <= 100_000 or not isinstance(per_year, int | float)
            or not math.isfinite(per_year) or not 1 <= per_year <= 366):
        raise QueryError("invalid_experiment", "Posiciones, periodos o frecuencia no válidos.", 422)
    if not isinstance(form.get("hypothesis_registered"), bool):
        raise QueryError("invalid_experiment", "Indica si la hipótesis se registró antes.", 422)
    fingerprint = _text(form.get("data_fingerprint"), "data_fingerprint")
    family = _text(form.get("family"), "family")
    notes = _text(form.get("notes"), "notes")
    return {
        "model_id": _text(form.get("model_id"), "model_id", required=True),
        "stage": form["stage"], "hypothesis_registered": form["hypothesis_registered"],
        "data_cutoff": _day(form.get("data_cutoff"), "de corte"),
        "data_fingerprint": (fingerprint or "").strip() or None,
        "universe": _text(form.get("universe"), "universe"), "factors": FACTORS,
        "n_positions": n_positions, "rebalance": form["rebalance"],
        "cost_model": _text(form.get("cost_model"), "cost_model"),
        "is_start": _day(form.get("is_start"), "de inicio IS"), "is_end": _day(form.get("is_end"), "de fin IS"),
        "family": family or None, "sharpe": _optional(form.get("sharpe")),
        "sortino": _optional(form.get("sortino")), "max_drawdown": _optional(form.get("max_drawdown")),
        "n_periods": n_periods, "periods_per_year": float(per_year), "notes": notes or None,
    }


class ExperimentCommands:
    def __init__(self, log: ExperimentLog, research_mode: Callable[[], bool]):
        self.log, self.research_mode = log, research_mode

    def _require_research(self) -> None:
        if not self.research_mode():
            raise QueryError("research_required", "Research Lab requiere el modo Research local.", 403)

    def create(self, form: dict) -> int:
        self._require_research()
        return self.log.log(manual_record(form))

    def delete(self, experiment_id: int) -> dict:
        self._require_research()
        if not self.log.delete(experiment_id):
            raise QueryError("experiment_not_found", f"No existe el experimento #{experiment_id}.", 404)
        return {"deleted": experiment_id}
