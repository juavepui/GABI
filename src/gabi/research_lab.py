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
import json
import subprocess

import pandas as pd

from . import config, storage

STAGES = ["RESEARCH", "IN_SAMPLE", "OUT_OF_SAMPLE", "LIVE_FORWARD"]

STAGE_INFO = {
    "RESEARCH": {"emoji": "🔬", "label": "Research", "help": "Explorando/probando configuraciones -- la mayoría del trabajo de investigación."},
    "IN_SAMPLE": {"emoji": "📊", "label": "In-sample", "help": "Resultado sobre el rango de datos usado para diseñar la hipótesis."},
    "OUT_OF_SAMPLE": {"emoji": "🧪", "label": "Out-of-sample", "help": "Resultado sobre datos que NO se miraron al diseñar la hipótesis."},
    "LIVE_FORWARD": {"emoji": "🚀", "label": "Live forward", "help": "Seguimiento real desde hoy, sin margen para haber influido en el diseño."},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    model_id TEXT NOT NULL,
    git_commit TEXT,
    data_cutoff TEXT,
    universe TEXT,
    factors TEXT,
    weights_json TEXT,
    n_positions INTEGER,
    rebalance TEXT,
    cost_model TEXT,
    is_start TEXT,
    is_end TEXT,
    oos_start TEXT,
    oos_end TEXT,
    hypothesis_registered INTEGER NOT NULL,
    stage TEXT NOT NULL,
    family TEXT,
    sharpe REAL,
    sortino REAL,
    max_drawdown REAL,
    total_return REAL,
    annualized_return REAL,
    periods_per_year REAL,
    n_periods INTEGER,
    returns_json TEXT,
    notes TEXT,
    result_json TEXT
);
"""


def _current_git_commit() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=config.BASE_DIR,
                                capture_output=True, text=True, timeout=5)
        return result.stdout.strip() or None
    except Exception:
        return None


def log_experiment(
    model_id: str, stage: str, hypothesis_registered: bool, *,
    git_commit: str = None, data_cutoff: str = None, universe: str = None, factors: str = None,
    weights: dict = None, n_positions: int = None, rebalance: str = None, cost_model: str = None,
    is_start: str = None, is_end: str = None, oos_start: str = None, oos_end: str = None,
    family: str = None, sharpe: float = None, sortino: float = None, max_drawdown: float = None,
    total_return: float = None, annualized_return: float = None, periods_per_year: float = None,
    n_periods: int = None, returns: pd.Series = None, notes: str = None, result: dict = None,
) -> int:
    """Registra un experimento. `stage` debe ser uno de `STAGES`.
    `git_commit` se captura automáticamente (`git rev-parse --short HEAD`) si
    no se indica explícitamente -- ata cada resultado al código exacto que lo
    produjo. `returns` (opcional, `pd.Series` indexada por fecha): la serie
    de retornos real del experimento -- si se guarda, habilita PSR exacto,
    bootstrap y PBO/CSCV para este experimento en `stats_rigor.py`; si no,
    solo queda disponible la aproximación normal a partir del Sharpe resumen."""
    if stage not in STAGES:
        raise ValueError(f"stage debe ser uno de {STAGES}.")
    if git_commit is None:
        git_commit = _current_git_commit()
    returns_json = None
    if returns is not None:
        returns_json = json.dumps({str(k): float(v) for k, v in returns.dropna().items()})
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        cur = conn.execute(
            "INSERT INTO experiments (created_at, model_id, git_commit, data_cutoff, universe, factors, "
            "weights_json, n_positions, rebalance, cost_model, is_start, is_end, oos_start, oos_end, "
            "hypothesis_registered, stage, family, sharpe, sortino, max_drawdown, total_return, "
            "annualized_return, periods_per_year, n_periods, returns_json, notes, result_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pd.Timestamp.now().isoformat(), model_id, git_commit, data_cutoff, universe, factors,
             json.dumps(weights) if weights else None, n_positions, rebalance, cost_model,
             is_start, is_end, oos_start, oos_end, int(bool(hypothesis_registered)), stage, family,
             sharpe, sortino, max_drawdown, total_return, annualized_return, periods_per_year,
             n_periods, returns_json, notes, json.dumps(result) if result else None),
        )
        conn.commit()
        return cur.lastrowid


def list_experiments(family: str = None, stage: str = None) -> pd.DataFrame:
    query = "SELECT * FROM experiments"
    conditions, params = [], []
    if family is not None:
        conditions.append("family = ?")
        params.append(family)
    if stage is not None:
        conditions.append("stage = ?")
        params.append(stage)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id DESC"
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.commit()
        return pd.read_sql_query(query, conn, params=params)


def get_experiment(experiment_id: int) -> dict:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        row = conn.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,)).fetchone()
        columns = [d[0] for d in conn.execute("SELECT * FROM experiments LIMIT 0").description]
        conn.commit()
    if row is None:
        return {}
    data = dict(zip(columns, row))
    data["weights"] = json.loads(data["weights_json"]) if data.get("weights_json") else None
    data["result"] = json.loads(data["result_json"]) if data.get("result_json") else None
    if data.get("returns_json"):
        series = pd.Series(json.loads(data["returns_json"]))
        series.index = pd.to_datetime(series.index)
        data["returns"] = series.sort_index()
    else:
        data["returns"] = None
    return data


def delete_experiment(experiment_id: int) -> bool:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        cur = conn.execute("DELETE FROM experiments WHERE id = ?", (experiment_id,))
        conn.commit()
        return cur.rowcount > 0


def list_families() -> list:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        rows = conn.execute(
            "SELECT DISTINCT family FROM experiments WHERE family IS NOT NULL ORDER BY family"
        ).fetchall()
        conn.commit()
    return [r[0] for r in rows]
