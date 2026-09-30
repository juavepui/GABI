"""Job commands and contracts, independent of HTTP, SQLite and legacy engines."""

import re
from dataclasses import dataclass
from typing import Literal, Protocol

from gabi.application.errors import QueryError

JobKind = Literal["refresh", "symbols", "quality", "backtest", "maintenance", "tiingo", "sim_result", "sim_compare", "decision_plan", "filing_check", "historical_ranking"]
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
        elif self.kind == "historical_ranking":
            from datetime import date

            try:
                as_of = date.fromisoformat(self.start or "")
            except ValueError as exc:
                raise QueryError("invalid_job", "Indica una fecha histórica ISO válida.", 422) from exc
            if self.end is not None or not date(2010, 1, 1) <= as_of <= date(2025, 7, 2):
                raise QueryError("reserved_period", "Solo se permite el histórico S&P 500 observado de 2010 a julio de 2025.", 403)
        elif self.start is not None or self.end is not None:
            raise QueryError("invalid_job", "Este trabajo no admite fechas.", 422)
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
    def __init__(self, repository: JobRepository):
        self.repository = repository

    def submit(self, command: JobCommand, key: str, *, origin: str = "ui") -> dict:
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
        if job["kind"] in {"maintenance", "tiingo"}:
            raise QueryError("result_restricted", "Este resultado pertenece al seguimiento ciego.", 403)
        return self.repository.result(job_id)
