"""Research Lab: registro de experimentos de backtesting, con la metodología,
el commit exacto de código y el resultado de cada uno -- para poder aplicar
después el rigor estadístico de `stats_rigor.py` (PSR/DSR/PBO/bootstrap) sin
depender de la memoria o de re-ejecutar nada.

Nace porque esta sesión probó 10+ configuraciones sobre el mismo histórico
2016-2025 documentándolo todo a mano en `README.md`/`HIPOTESIS_CONGELADA.md`
-- esto formaliza esa disciplina como una tabla consultable en vez de prosa.

Cuatro fases, pensadas para no confundir "estoy explorando" con "esto ya está
validado":
- **RESEARCH**: explorando/probando configuraciones sobre el mismo histórico
  de siempre -- la mayoría de lo hecho esta sesión.
- **IN_SAMPLE**: el resultado sobre el rango de datos usado para diseñar la
  hipótesis (ej. 2016-07 a 2025-04 de `HIPOTESIS_CONGELADA.md`).
- **OUT_OF_SAMPLE**: el resultado sobre datos que NO se miraron al diseñar la
  hipótesis (ej. trimestres posteriores al corte, o un rango histórico
  distinto nunca explorado).
- **LIVE_FORWARD**: seguimiento real a partir de hoy, sin margen para haber
  influido en el diseño -- la prueba más honesta que existe."""
import platform

import pandas as pd

from gabi.application.research import experiment_log
from gabi.domain.research.experiments import STAGE_INFO, STAGES  # noqa: F401  (interfaz pública)
from gabi.infrastructure.providers import research_environment
from gabi.infrastructure.storage.experiment_log import SCHEMA as SCHEMA
from gabi.infrastructure.storage.experiment_log import SqliteExperimentLog
from gabi.infrastructure.storage.experiment_log import ensure_columns as _ensure_columns  # noqa: F401

from . import config

# Paquetes cuya versión exacta puede cambiar el resultado numérico de un
# backtest (cálculo, no solo I/O) -- se registran junto al commit para que un
# experimento antiguo sea reproducible sin tener que adivinar qué versión de
# pandas/numpy estaba instalada en su momento.
TRACKED_PACKAGES = [
    "pandas", "numpy", "scipy", "yfinance", "pyportfolioopt",
    "backtesting", "exchange_calendars", "quantstats",
]


def _log() -> SqliteExperimentLog:
    # The compatibility setting is read per operation, never mutated.
    return SqliteExperimentLog(config.DB_PATH)


def _dependency_versions() -> dict:
    return research_environment.dependency_versions(TRACKED_PACKAGES)


def _env_fingerprint() -> str | None:
    """Hash corto de `uv.lock` -- a diferencia de `deps_json` (una lista
    curada de paquetes que afectan el cálculo), esto fija TODO el árbol de
    dependencias resuelto (transitivas incluidas) en un único valor
    comparable: si dos experimentos tienen el mismo fingerprint, se
    instalaron exactamente los mismos paquetes, sin tener que diffear el
    lockfile entero a mano. None si no se encuentra (ej. instalación sin
    checkout del repo, sin `uv.lock` junto al código)."""
    return research_environment.lock_fingerprint(config.BASE_DIR / "uv.lock")


def _current_git_commit() -> str | None:
    return research_environment.git_commit(config.BASE_DIR)


def log_experiment(
    model_id: str, stage: str, hypothesis_registered: bool, *,
    git_commit: str = None, data_cutoff: str = None, universe: str = None, factors: str = None,
    weights: dict = None, n_positions: int = None, rebalance: str = None, cost_model: str = None,
    is_start: str = None, is_end: str = None, oos_start: str = None, oos_end: str = None,
    family: str = None, sharpe: float = None, sortino: float = None, max_drawdown: float = None,
    total_return: float = None, annualized_return: float = None, periods_per_year: float = None,
    n_periods: int = None, returns: pd.Series = None, notes: str = None, result: dict = None,
    data_fingerprint: str = None,
) -> int:
    """Registra un experimento. `stage` debe ser uno de `STAGES`.
    `git_commit` se captura automáticamente (`git rev-parse --short HEAD`) si
    no se indica explícitamente -- ata cada resultado al código exacto que lo
    produjo. `returns` (opcional, `pd.Series` indexada por fecha): la serie
    de retornos real del experimento -- si se guarda, habilita PSR exacto,
    bootstrap y PBO/CSCV para este experimento en `stats_rigor.py`; si no,
    solo queda disponible la aproximación normal a partir del Sharpe resumen.

    `data_fingerprint` (opcional, ver `data_quality.compute_data_fingerprint`):
    a diferencia de `env_fingerprint` (que fija las DEPENDENCIAS), este fija
    los DATOS concretos usados -- no se calcula aquí automáticamente porque
    research_lab no conoce el universo de símbolos de cada run; lo calcula
    el llamador, que sí lo sabe (ej. el backtest de 🕰️ Ranking histórico), y
    lo pasa ya hecho."""
    experiment_log.require_stage(stage)
    if git_commit is None:
        git_commit = _current_git_commit()
    row = experiment_log.record(
        model_id, stage, hypothesis_registered, created_at=pd.Timestamp.now().isoformat(), git_commit=git_commit,
        deps=_dependency_versions(), python_version=platform.python_version(), env_fingerprint=_env_fingerprint(),
        weights=weights, returns=returns, result=result, data_cutoff=data_cutoff, universe=universe,
        factors=factors, n_positions=n_positions, rebalance=rebalance, cost_model=cost_model, is_start=is_start,
        is_end=is_end, oos_start=oos_start, oos_end=oos_end, family=family, data_fingerprint=data_fingerprint,
        sharpe=sharpe, sortino=sortino, max_drawdown=max_drawdown, total_return=total_return,
        annualized_return=annualized_return, periods_per_year=periods_per_year, n_periods=n_periods, notes=notes)
    return _log().record(row)


def list_experiments(family: str = None, stage: str = None) -> pd.DataFrame:
    return _log().frame(family, stage)


def get_experiment(experiment_id: int) -> dict:
    return experiment_log.detail(_log().row(experiment_id))


def delete_experiment(experiment_id: int) -> bool:
    return _log().delete(experiment_id)


def list_families() -> list:
    return _log().families()
