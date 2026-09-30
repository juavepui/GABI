"""Tail risk and Spanish tax drag of a verified backtest artifact, as Streamlit showed them."""

from collections.abc import Callable
from typing import Protocol

import pandas as pd

from gabi.application.administration.jobs import Jobs
from gabi.application.errors import QueryError
from gabi.application.research.historical import _json_value

SERIES_V1 = (("Estrategia", "retorno"), ("Universo EW", "universo_ew"), ("SPY", "spy"))
SERIES_V2 = (("Estrategia", "estrategia"), ("SPY", "spy"))


class BacktestMath(Protocol):
    def tail_risk(self, returns: pd.Series, horizon: str) -> dict: ...
    def returns_from_nav(self, nav: pd.Series) -> pd.Series: ...
    def tax_drag(self, periods: pd.DataFrame, initial_capital: float) -> dict: ...
    def zero_turnover(self, periods: pd.DataFrame, return_column: str) -> pd.DataFrame: ...
    def tax_limitations(self) -> list[str]: ...
    def ranking_warnings(self, quality: dict, threshold: float) -> list[str]: ...


def _tail(summary: dict) -> dict:
    levels = {f"level_{level}": {key: _json_value(value) for key, value in summary[level].items()}
              for level in ("95", "99")}
    return {key: _json_value(value) for key, value in summary.items() if key not in {"95", "99"}} | levels


def _tax(result: dict) -> dict:
    keys = ("initial_capital", "final_value_pretax", "final_value_aftertax", "pretax_return",
            "aftertax_return", "tax_drag_pct_points", "total_tax_paid", "unrealized_gain_remaining",
            "n_periods", "n_years")
    return {key: _json_value(result[key]) for key in keys} | {
        "tax_by_year": [{"year": int(year)} | {key: _json_value(value) for key, value in row.items()}
                        for year, row in sorted(result["tax_by_year"].items())]}


class BacktestDiagnostics:
    def __init__(self, jobs: Jobs, math: BacktestMath):
        self.jobs = jobs
        self.math = math

    def _series(self, columns: tuple[tuple[str, str], ...], build: Callable[[str], pd.Series],
                horizon: str) -> list[dict]:
        rows = []
        for name, column in columns:
            try:
                rows.append({"name": name, "summary": _tail(self.math.tail_risk(build(column), horizon)),
                             "error": None})
            except (ValueError, TypeError) as exc:
                rows.append({"name": name, "summary": None, "error": str(exc)})
        return rows

    def _tail_v1(self, periods: pd.DataFrame) -> dict:
        durations = set(pd.PeriodIndex(periods["hasta"], freq="M").asi8
                        - pd.PeriodIndex(periods["fecha"], freq="M").asi8)
        if len(durations) != 1 or next(iter(durations)) <= 0:
            return {"horizon": None, "series": [],
                    "message": "No se mezclan retornos de distinta duración en una distribución de cola."}
        horizon = f"{next(iter(durations))} meses (rebalanceo V1)"
        return {"horizon": horizon, "series": self._series(SERIES_V1, lambda column: periods[column], horizon),
                "message": "Solo periodos disponibles del backtest; no mide caídas dentro de cada periodo. "
                           "Los periodos saltados no se imputan como retornos cero."}

    def _tail_v2(self, curve: pd.DataFrame) -> dict:
        horizon = "una sesión (NAV diario)"
        series = self._series(SERIES_V2, lambda column: self.math.returns_from_nav(curve[column].dropna()), horizon)
        return {"horizon": horizon, "series": series, "message": None}

    def _quality(self, artifact: dict, threshold: float) -> list[dict]:
        rows = []
        for fecha, quality in sorted((artifact.get("data_quality") or {}).items()):
            messages = self.math.ranking_warnings(quality, threshold)
            if messages:
                rows.append({"fecha": fecha, "messages": messages})
        return rows

    def diagnostics(self, job_id: str, tax_capital: float, threshold: float = 0.7) -> dict:
        job = self.jobs.get(job_id)
        if job["kind"] not in {"backtest_v1", "backtest_v2"}:
            raise QueryError("job_not_found", "El backtest no existe.", 404)
        if not 0 <= threshold <= 1:
            raise QueryError("invalid_query", "El umbral de cobertura debe estar entre 0 y 1.", 422)
        if not 1_000 <= tax_capital <= 100_000_000:
            raise QueryError("invalid_query", "El capital de la simulación fiscal no es válido.", 422)
        artifact = self.jobs.result(job_id)  # Research mode, reserved dates and SHA-256 are checked here.
        periods = pd.DataFrame(artifact["periods"])
        if job["kind"] == "backtest_v2":
            curve = pd.DataFrame(artifact["curve"])
            curve.index = pd.to_datetime(curve.pop("fecha"))
            return {"job_id": job_id, "kind": job["kind"], "tail": self._tail_v2(curve.astype(float)),
                    "tax": None, "quality_threshold": threshold,
                    "quality_warnings": self._quality(artifact, threshold), "result_sha256": job["result_sha256"]}
        tax = None
        try:
            tax = {"capital": tax_capital,
                   "strategy": _tax(self.math.tax_drag(periods, tax_capital)),
                   "spy_buy_and_hold": _tax(self.math.tax_drag(self.math.zero_turnover(periods, "spy"),
                                                               tax_capital)),
                   "limitations": self.math.tax_limitations(), "error": None}
        except (ValueError, KeyError) as exc:
            tax = {"capital": tax_capital, "strategy": None, "spy_buy_and_hold": None,
                   "limitations": self.math.tax_limitations(), "error": str(exc)}
        return {"job_id": job_id, "kind": job["kind"], "tail": self._tail_v1(periods), "tax": tax,
                "quality_threshold": threshold, "quality_warnings": self._quality(artifact, threshold),
                "result_sha256": job["result_sha256"]}
