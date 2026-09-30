"""Job commands and contracts, independent of HTTP, SQLite and legacy engines."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from gabi.application.errors import QueryError
from gabi.application.research.reservations import OBSERVED_END, require_factor_period, require_observed_period

JobKind = Literal["refresh", "symbols", "quality", "backtest", "maintenance", "tiingo", "sim_result", "sim_compare", "decision_plan", "filing_check", "historical_ranking", "factor_analysis", "estimate_analysis"]
SYMBOL = re.compile(r"[A-Z0-9^][A-Z0-9^-]{0,19}\Z")


@dataclass(frozen=True)
class JobCommand:
    kind: JobKind
    symbols: tuple[str, ...] = ()
    start: str | None = None
    end: str | None = None
    portfolio_id: int | None = None
    decision_policy: dict | None = None
    holdings_text: str | None = None
    snapshot_id: int | None = None
    factor_months: int | None = None
    factor_mode: str | None = None
    factor_max_symbols: int | None = None

    def __post_init__(self) -> None:
        if self.kind == "symbols":
            if not 1 <= len(self.symbols) <= 10 or len(set(self.symbols)) != len(self.symbols):
                raise QueryError("invalid_job", "Indica entre 1 y 10 símbolos distintos.", 422)
            if not all(SYMBOL.fullmatch(symbol) for symbol in self.symbols):
                raise QueryError("invalid_job", "Los símbolos no son válidos.", 422)
        elif self.symbols:
            raise QueryError("invalid_job", "Este trabajo no admite símbolos.", 422)
        if self.kind == "backtest":
            from datetime import date

            try:
                first, last = date.fromisoformat(self.start or ""), date.fromisoformat(self.end or "")
            except ValueError as exc:
                raise QueryError("invalid_job", "Indica fechas ISO válidas.", 422) from exc
            if first >= last or last > date.today() or (last - first).days > 370:
                raise QueryError("invalid_job", "El backtest debe cubrir hasta un año cerrado en el pasado.", 422)
            require_observed_period(self.start, self.end)
        elif self.kind == "historical_ranking":
            if self.end is not None:
                raise QueryError("invalid_job", "El ranking histórico admite una sola fecha.", 422)
            require_observed_period(self.start)
        elif self.kind == "factor_analysis":
            require_factor_period(self.start, self.end)
            if self.factor_months not in (1, 3, 6, 12) or self.factor_mode not in ("validation", "fast_dev"):
                raise QueryError("invalid_job", "Parámetros de Factor Lab no válidos.", 422)
            if (self.factor_mode == "validation" and self.factor_max_symbols is not None or
                    self.factor_mode == "fast_dev" and self.factor_max_symbols not in (50, 100, 200)):
                raise QueryError("invalid_job", "La muestra no corresponde al modo de Factor Lab.", 422)
        elif self.start is not None or self.end is not None:
            raise QueryError("invalid_job", "Este trabajo no admite fechas.", 422)
        if self.kind != "factor_analysis" and any(value is not None for value in
                                                  (self.factor_months, self.factor_mode, self.factor_max_symbols)):
            raise QueryError("invalid_job", "Este trabajo no admite parámetros de Factor Lab.", 422)
        if self.kind == "sim_result":
            if self.portfolio_id is None or not 1 <= self.portfolio_id <= 1_000_000:
                raise QueryError("invalid_job", "Indica una cartera simulada válida.", 422)
        elif self.portfolio_id is not None:
            raise QueryError("invalid_job", "Este trabajo no admite cartera simulada.", 422)
        if self.kind == "decision_plan":
            if self.decision_policy is None or self.holdings_text is None or len(self.holdings_text) > 5000:
                raise QueryError("invalid_job", "Indica politica y posiciones validas.", 422)
        elif self.decision_policy is not None or self.holdings_text is not None:
            raise QueryError("invalid_job", "Este trabajo no admite politica de decisiones.", 422)
        if self.kind == "filing_check":
            if self.snapshot_id is None or not 1 <= self.snapshot_id <= 1_000_000:
                raise QueryError("invalid_job", "Indica un snapshot valido.", 422)
        elif self.snapshot_id is not None:
            raise QueryError("invalid_job", "Este trabajo no admite snapshot.", 422)


class JobRepository(Protocol):
    def enqueue(self, command: JobCommand, key: str, origin: str) -> dict: ...
    def list(self, limit: int = 30) -> list[dict]: ...
    def get(self, job_id: str) -> dict: ...
    def cancel(self, job_id: str) -> dict: ...
    def result(self, job_id: str) -> dict: ...


class Jobs:
    def __init__(self, repository: JobRepository, research_allowed: Callable[[], bool] | None = None):
        self.repository = repository
        self.research_allowed = research_allowed

    def _require_research(self) -> None:
        if self.research_allowed is None or not self.research_allowed():
            raise QueryError("research_required", "Factor Lab requiere el modo Research local.", 403)

    def submit(self, command: JobCommand, key: str, *, origin: str = "ui") -> dict:
        if command.kind in {"factor_analysis", "estimate_analysis"}:
            self._require_research()
        if origin == "ui" and command.kind in {"maintenance", "tiingo"}:
            raise QueryError("forbidden_job", "Este trabajo pertenece al programador local.", 403)
        if not 8 <= len(key) <= 100 or not re.fullmatch(r"[A-Za-z0-9._:-]+", key):
            raise QueryError("invalid_job", "La clave de repetición no es válida.", 422)
        return self.repository.enqueue(command, key, origin)

    def list(self) -> list[dict]:
        return self.repository.list()

    def get(self, job_id: str) -> dict:
        return self.repository.get(job_id)

    def cancel(self, job_id: str) -> dict:
        return self.repository.cancel(job_id)

    def result(self, job_id: str) -> dict:
        job = self.repository.get(job_id)
        if job["kind"] in {"factor_analysis", "estimate_analysis"}:
            self._require_research()
        if job["kind"] in {"maintenance", "tiingo"}:
            raise QueryError("result_restricted", "Este resultado pertenece al seguimiento ciego.", 403)
        if job["kind"] in {"backtest", "historical_ranking", "factor_analysis"}:
            parameters = job["parameters"]
            if job["kind"] == "historical_ranking" and parameters.get("end") is not None:
                raise QueryError("reserved_period", "Este resultado no corresponde a una sola fecha observada.", 403)
            if job["kind"] == "factor_analysis":
                require_factor_period(parameters.get("start"), parameters.get("end"))
            else:
                require_observed_period(parameters.get("start"), parameters.get("end"))
        result = self.repository.result(job_id)
        if job["kind"] == "estimate_analysis" and (
                result.get("kind") != "estimate_analysis" or
                result.get("observed_cutoff") != OBSERVED_END.isoformat() or
                result.get("horizons_months") != [1, 3]):
            raise QueryError("reserved_period", "El resultado de estimaciones no respeta el corte observado.", 403)
        return result
