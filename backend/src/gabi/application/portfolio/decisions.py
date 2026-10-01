"""Experimental decision plans over frozen scores and bounded cached histories."""

import re
from collections.abc import Callable
from datetime import date, timedelta
from math import isfinite
from typing import Protocol

import pandas as pd

from gabi.application.administration.jobs import Jobs
from gabi.application.administration.model import ModelPolicy
from gabi.application.errors import QueryError
from gabi.application.market.queries import RankingSnapshot, describe_data
from gabi.domain.portfolio.decision_progress import progress


class DecisionMarket(Protocol):
    def ranking(self, weights: dict[str, float], today: date) -> RankingSnapshot: ...


class DecisionRepository(Protocol):
    def histories(self, symbols: list[str]) -> dict[str, pd.DataFrame]: ...
    def progress_histories(self, symbols: list[str], start: str) -> dict[str, pd.DataFrame]: ...
    def list(self) -> list[dict]: ...
    def get(self, plan_id: int) -> dict | None: ...
    def save(self, result: dict, name: str, job_id: str) -> int: ...
    def rename(self, plan_id: int, name: str) -> bool: ...
    def delete(self, plan_id: int) -> bool: ...


def parse_holdings(raw: str) -> dict[str, float]:
    if len(raw) > 5000:
        raise QueryError("invalid_holdings", "Las posiciones superan el límite de lectura.", 422)
    result = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 2:
            raise QueryError("invalid_holdings", "Usa SÍMBOLO,porcentaje por línea.", 422)
        symbol = parts[0].upper().replace(".", "-")
        try:
            value = float(parts[1])
        except ValueError as exc:
            raise QueryError("invalid_holdings", "Los porcentajes deben ser numéricos.", 422) from exc
        if not re.fullmatch(r"[A-Z0-9^][A-Z0-9^\-]{0,19}", symbol) or symbol in result or \
                not isfinite(value) or value < 0 or value > 100:
            raise QueryError("invalid_holdings", "Símbolo o porcentaje duplicado o no válido.", 422)
        result[symbol] = value
    if len(result) > 100 or sum(result.values()) > 100.001:
        raise QueryError("invalid_holdings", "Las posiciones no pueden superar el 100 %.", 422)
    return result


# decision_engine._finish column order: the old «Descargar decisiones CSV» file.
CSV_COLUMNS = ("symbol", "action", "current_pct", "target_pct", "change_pct", "reason", "score")


def decisions_frame(rows: list[dict]) -> pd.DataFrame:
    """The columns of plan["decisions"], whatever the key order the stored JSON kept."""
    return pd.DataFrame([{key: row.get(key) for key in CSV_COLUMNS} for row in rows], columns=list(CSV_COLUMNS))


class Decisions:
    def __init__(self, market: DecisionMarket, repository: DecisionRepository, model: ModelPolicy,
                 today: Callable[[], date], calculate: Callable[[pd.DataFrame, dict[str, pd.DataFrame],
                                                                  dict[str, float], dict, str], dict],
                 jobs: Jobs):
        self.market, self.repository, self.model = market, repository, model
        self.today, self.calculate, self.jobs = today, calculate, jobs

    def generate(self, options: dict, holdings_text: str) -> dict:
        holdings = parse_holdings(holdings_text)
        day = self.today()
        snapshot = self.market.ranking(dict(self.model.frozen_weights), day)
        table = snapshot.table
        if table.empty or len(table) > 1000:
            raise QueryError("data_unavailable", "No hay un universo local válido para decisiones.", 503)
        histories = self.repository.histories(table.index.astype(str).tolist())
        try:
            plan = self.calculate(table, histories, holdings, options, day.isoformat())
        except (ValueError, KeyError, TypeError) as exc:
            raise QueryError("decision_unavailable", str(exc), 422) from exc
        state = describe_data(snapshot, day)
        return plan | {"as_of": day.isoformat(), "model_id": self.model.frozen_id,
                       "revision": snapshot.revision, "data_status": state.status,
                       "coverage": {"universe": state.universe_count, "prices": state.prices_available,
                                    "scored": state.scored_count}}

    def list(self) -> list[dict]:
        return self.repository.list()

    def get(self, plan_id: int) -> dict:
        result = self.repository.get(plan_id)
        if result is None:
            raise QueryError("plan_not_found", "El plan no existe.", 404)
        return result

    def progress(self, plan_id: int) -> dict:
        plan = self.get(plan_id)
        rows = [row for row in plan["decisions"] if float(row.get("target_pct", 0)) > 0]
        symbols = list(dict.fromkeys([str(row["symbol"]) for row in rows] + ["SPY"]))
        start = (date.fromisoformat(plan["created_at"][:10]) - timedelta(days=7)).isoformat()
        histories = self.repository.progress_histories(symbols, start)
        return progress(plan["created_at"], plan["decisions"], histories, self.today())

    def job_plan(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if job["kind"] != "decision_plan":
            raise QueryError("invalid_job", "El job no contiene decisiones.", 422)
        plan = self.jobs.result(job_id)
        if plan.get("status") != "EXPERIMENTAL" or not isinstance(plan.get("decisions"), list):
            raise QueryError("invalid_job", "El resultado del job no es un plan válido.", 422)
        return plan

    def save_job(self, job_id: str, name: str) -> dict:
        name = name.strip()
        if not name or len(name) > 80:
            raise QueryError("invalid_name", "El nombre debe tener entre 1 y 80 caracteres.", 422)
        return self.get(self.repository.save(self.job_plan(job_id), name, job_id))

    def rename(self, plan_id: int, name: str) -> dict:
        name = name.strip()
        if not name or len(name) > 80:
            raise QueryError("invalid_name", "El nombre debe tener entre 1 y 80 caracteres.", 422)
        if not self.repository.rename(plan_id, name):
            raise QueryError("plan_not_found", "El plan no existe.", 404)
        return self.get(plan_id)

    def delete(self, plan_id: int) -> bool:
        return self.repository.delete(plan_id)
