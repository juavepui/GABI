"""PBO/CSCV over saved experiment returns, as an explicit Research job."""

from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.application.research.experiments import ExperimentStore, returns_series

MAX_PBO_VARIANTS = 20
MIN_COMMON_DATES = 16


class PboMath(Protocol):
    def pbo(self, matrix: pd.DataFrame, n_splits: int) -> dict: ...


def normalize_pbo(options: dict | None) -> dict:
    ids = (options or {}).get("experiment_ids")
    if (not isinstance(ids, list) or not all(isinstance(item, int) and not isinstance(item, bool) and item >= 1
                                              for item in ids)
            or len(set(ids)) != len(ids) or not 2 <= len(ids) <= MAX_PBO_VARIANTS):
        raise QueryError("invalid_job", f"Elige entre 2 y {MAX_PBO_VARIANTS} experimentos distintos.", 422)
    if set(options or {}) != {"experiment_ids"}:
        raise QueryError("invalid_job", "Parámetros de PBO no válidos.", 422)
    return {"experiment_ids": sorted(ids)}


def _label(item: dict) -> str:
    """The option label of the Streamlit page; it names the matrix columns."""
    if item["sharpe"] is not None:
        return f"#{item['id']} · {item['model_id']} · Sharpe {item['sharpe']:.2f}"
    return f"#{item['id']} · {item['model_id']}"


def _provenance(item: dict) -> dict:
    return {key: item.get(key) for key in ("id", "model_id", "git_commit", "data_fingerprint", "stage", "family")}


def build_pbo(store: ExperimentStore, options: dict, math: PboMath) -> dict:
    series, experiments = {}, []
    for experiment_id in options["experiment_ids"]:
        item = store.get(experiment_id)
        if item is None:
            raise ValueError(f"El experimento #{experiment_id} no existe.")
        returns = returns_series(item.pop("returns"))
        if returns is None:
            raise ValueError(f"El experimento #{experiment_id} no tiene serie de retornos guardada.")
        series[_label(item)] = returns
        experiments.append(_provenance(item) | {"label": _label(item), "n_returns": len(returns)})
    matrix = pd.concat(series, axis=1).dropna()
    result = {"kind": "experiment_pbo", "experiments": experiments, "n_common_dates": len(matrix),
              "first_date": str(matrix.index[0].date()) if len(matrix) else None,
              "last_date": str(matrix.index[-1].date()) if len(matrix) else None,
              "n_splits": None, "pbo": None, "n_combinations": None, "tied_splits": None, "tie_policy": None,
              "logits": [], "logit_weights": [], "message": None,
              "status": "RETROSPECTIVE_EXPLORATORY", "independent_advantage_demonstrated": False}
    if len(matrix) < MIN_COMMON_DATES:
        return result | {"message": "Muy pocas fechas comunes entre las variantes elegidas para dividir en bloques."}
    n_splits = min(16, (len(matrix) // 10) * 2 or 2)
    try:
        pbo = math.pbo(matrix, n_splits)
    except ValueError as exc:
        return result | {"n_splits": n_splits, "message": str(exc)}
    return result | {"n_splits": n_splits, "pbo": pbo["pbo"], "n_combinations": pbo["n_combinations"],
                     "tied_splits": pbo["tied_splits"], "tie_policy": pbo["tie_policy"],
                     "logits": pbo["logits"], "logit_weights": pbo["logit_weights"]}


MIN_BOOTSTRAP_OBS = 30


class BootstrapMath(Protocol):
    def block_lengths(self) -> dict: ...
    def bootstrap(self, matrix: pd.DataFrame, periods_per_year: float) -> tuple[dict, pd.DataFrame]: ...


def normalize_bootstrap(options: dict | None) -> dict:
    options = options or {}
    strategy, benchmark = options.get("experiment_id"), options.get("benchmark_id")
    valid = (isinstance(strategy, int) and not isinstance(strategy, bool) and strategy >= 1
             and (benchmark is None or isinstance(benchmark, int) and not isinstance(benchmark, bool)
                  and benchmark >= 1 and benchmark != strategy))
    if not valid or set(options) - {"experiment_id", "benchmark_id"}:
        raise QueryError("invalid_job", "Elige un experimento y, opcionalmente, otra serie de comparación.", 422)
    return {"experiment_id": strategy, "benchmark_id": benchmark}


def _columns(distribution: pd.DataFrame) -> list[dict]:
    """Every replicate, column by column and in order (artifacts are saved with sorted keys)."""
    return [{"name": name, "values": [None if pd.isna(value) else
                                      (int(value) if name in ("block_size", "replicate") else float(value))
                                      for value in distribution[name].tolist()]} for name in distribution]


def distribution_frame(columns: list[dict]) -> pd.DataFrame:
    return pd.DataFrame({column["name"]: column["values"] for column in columns})


def build_bootstrap(store: ExperimentStore, options: dict, math: BootstrapMath) -> dict:
    """Same checks, matrix and preregistered block lengths as the Streamlit button."""
    strategy = store.get(options["experiment_id"])
    if strategy is None:
        raise ValueError("El experimento no existe.")
    returns = returns_series(strategy.pop("returns"))
    if returns is None:
        raise ValueError("El experimento no tiene serie de retornos guardada.")
    experiments = {"strategy": _provenance(strategy)}
    result = {"kind": "experiment_bootstrap", "experiments": experiments, "message": None, "audit": None,
              "block_order": None, "distribution": None, "status": "RETROSPECTIVE_EXPLORATORY",
              "independent_advantage_demonstrated": False}
    if len(returns) < MIN_BOOTSTRAP_OBS:
        return result | {"message": "Esta serie tiene menos de 30 observaciones; no es suficiente para un "
                                    "bootstrap razonable."}
    frequency = strategy["periods_per_year"]
    if frequency not in math.block_lengths():
        return result | {"message": "Falta una frecuencia válida declarada en el experimento; no se presume "
                                    "que sea diaria."}
    matrix = returns.to_frame("strategy")
    if options["benchmark_id"] is not None:
        benchmark = store.get(options["benchmark_id"])
        if benchmark is None or benchmark["periods_per_year"] != frequency:
            raise ValueError("La serie de comparación no existe o no tiene la misma frecuencia.")
        benchmark_returns = returns_series(benchmark.pop("returns"))
        if benchmark_returns is None:
            raise ValueError("La serie de comparación no tiene retornos guardados.")
        experiments["benchmark"] = _provenance(benchmark)
        if not benchmark_returns.index.equals(matrix.index):
            return result | {"message": "Las fechas no coinciden exactamente: no se recortan ni rellenan las "
                                        "series. El benchmark no está alineado."}
        matrix["benchmark"] = benchmark_returns
    try:
        audit, distribution = math.bootstrap(matrix, frequency)
    except ValueError as exc:
        return result | {"message": str(exc)}
    audit["experiments"] = {role: {key: item[key] for key in ("id", "model_id", "git_commit", "data_fingerprint")}
                            for role, item in experiments.items()}
    return result | {"audit": audit, "block_order": list(audit["runs"]), "distribution": _columns(distribution)}
