"""Job commands and contracts, independent of HTTP, SQLite and legacy engines."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from gabi.application.administration.data_health import normalize_data_health
from gabi.application.administration.data_update import normalize_data_update
from gabi.application.errors import QueryError
from gabi.application.market.company_research import normalize_company_sync
from gabi.application.research.backtest_factors import normalize_factor_contrast
from gabi.application.research.backtests import normalize_backtest, normalize_registration
from gabi.application.research.blind import normalize_blind_job
from gabi.application.research.experiment_analysis import normalize_bootstrap, normalize_pbo
from gabi.application.research.historical_outcomes import normalize_outcomes
from gabi.application.research.live_ledger import normalize_live_report
from gabi.application.research.portfolio_lab import normalize_portfolio_lab
from gabi.application.research.preparation import normalize_preparation
from gabi.application.research.reservations import OBSERVED_END, require_factor_period, require_observed_period

JobKind = Literal["refresh", "symbols", "quality", "backtest", "maintenance", "tiingo", "sim_result", "sim_compare", "decision_plan", "filing_check", "historical_ranking", "factor_analysis", "estimate_analysis", "backtest_v1", "backtest_v2", "backtest_register", "backtest_factors", "prepare_history", "historical_outcomes", "experiment_pbo", "experiment_bootstrap", "live_forward_report", "blind_rebalance", "blind_performance", "blind_export", "portfolio_lab", "company_sync", "data_update", "data_health", "sim_prices"]
RESEARCH_KINDS = {"factor_analysis", "estimate_analysis", "backtest_v1", "backtest_v2", "backtest_register",
                  "backtest_factors", "historical_outcomes", "experiment_pbo", "experiment_bootstrap",
                  "live_forward_report", "blind_rebalance", "blind_performance", "blind_export", "portfolio_lab"}
BLIND_KINDS = {"blind_rebalance", "blind_performance", "blind_export"}
DERIVED_SOURCES = {"backtest_factors": ("factor_contrast", {"backtest_v1", "backtest_v2"}),
                   "backtest_register": ("research_log", {"backtest_v1", "backtest_v2"}),
                   "historical_outcomes": ("outcomes", {"historical_ranking"})}
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
    backtest_options: dict | None = None
    research_log: dict | None = None
    factor_contrast: dict | None = None
    preparation: dict | None = None
    outcomes: dict | None = None
    experiment_analysis: dict | None = None
    live_report: dict | None = None
    blind: dict | None = None
    portfolio_options: dict | None = None
    company: dict | None = None
    update: dict | None = None
    health: dict | None = None

    def __post_init__(self) -> None:
        if self.kind == "symbols":
            if not 1 <= len(self.symbols) <= 10 or len(set(self.symbols)) != len(self.symbols):
                raise QueryError("invalid_job", "Indica entre 1 y 10 símbolos distintos.", 422)
            if not all(SYMBOL.fullmatch(symbol) for symbol in self.symbols):
                raise QueryError("invalid_job", "Los símbolos no son válidos.", 422)
        elif self.kind == "sim_prices":
            if len(self.symbols) > 1 or not all(SYMBOL.fullmatch(symbol) for symbol in self.symbols):
                raise QueryError("invalid_job", "Indica un símbolo válido o ninguno para toda la cartera.", 422)
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
        elif self.kind in {"backtest_v1", "backtest_v2"}:
            object.__setattr__(self, "backtest_options",
                               normalize_backtest(self.kind, self.start, self.end, self.backtest_options))
        elif self.kind == "portfolio_lab":
            pass  # Its dates are validated with its options below.
        elif self.kind == "prepare_history":
            object.__setattr__(self, "preparation", normalize_preparation(self.start, self.end, self.preparation))
        elif self.start is not None or self.end is not None:
            raise QueryError("invalid_job", "Este trabajo no admite fechas.", 422)
        if self.kind not in {"backtest_v1", "backtest_v2"} and self.backtest_options is not None:
            raise QueryError("invalid_job", "Este trabajo no admite parámetros de backtest.", 422)
        if self.kind == "backtest_register":
            object.__setattr__(self, "research_log", normalize_registration(self.research_log))
        elif self.research_log is not None:
            raise QueryError("invalid_job", "Este trabajo no admite registro en Research Lab.", 422)
        if self.kind == "backtest_factors":
            object.__setattr__(self, "factor_contrast", normalize_factor_contrast(self.factor_contrast))
        elif self.factor_contrast is not None:
            raise QueryError("invalid_job", "Este trabajo no admite contraste Fama-French.", 422)
        if self.kind != "prepare_history" and self.preparation is not None:
            raise QueryError("invalid_job", "Este trabajo no admite preparación de datos.", 422)
        if self.kind == "historical_outcomes":
            object.__setattr__(self, "outcomes", normalize_outcomes(self.outcomes))
        elif self.outcomes is not None:
            raise QueryError("invalid_job", "Este trabajo no admite evaluación posterior.", 422)
        if self.kind == "experiment_pbo":
            object.__setattr__(self, "experiment_analysis", normalize_pbo(self.experiment_analysis))
        elif self.kind == "experiment_bootstrap":
            object.__setattr__(self, "experiment_analysis", normalize_bootstrap(self.experiment_analysis))
        elif self.experiment_analysis is not None:
            raise QueryError("invalid_job", "Este trabajo no admite análisis de experimentos.", 422)
        if self.kind == "live_forward_report":
            object.__setattr__(self, "live_report", normalize_live_report(self.live_report))
        elif self.live_report is not None:
            raise QueryError("invalid_job", "Este trabajo no admite informe prospectivo.", 422)
        if self.kind in BLIND_KINDS:
            object.__setattr__(self, "blind", normalize_blind_job(self.blind))
        elif self.blind is not None:
            raise QueryError("invalid_job", "Este trabajo no admite validación ciega.", 422)
        if self.kind == "portfolio_lab":
            object.__setattr__(self, "portfolio_options",
                               normalize_portfolio_lab(self.start, self.end, self.portfolio_options))
        elif self.portfolio_options is not None:
            raise QueryError("invalid_job", "Este trabajo no admite parámetros de Portfolio Lab.", 422)
        if self.kind == "company_sync":
            object.__setattr__(self, "company", normalize_company_sync(self.company))
        elif self.company is not None:
            raise QueryError("invalid_job", "Este trabajo no admite sincronización de una empresa.", 422)
        if self.kind == "data_update":
            object.__setattr__(self, "update", normalize_data_update(self.update))
        elif self.update is not None:
            raise QueryError("invalid_job", "Este trabajo no admite parámetros de actualización.", 422)
        if self.kind == "data_health":
            object.__setattr__(self, "health", normalize_data_health(self.health))
        elif self.health is not None:
            raise QueryError("invalid_job", "Este trabajo no admite parámetros de calidad de datos.", 422)
        if self.kind != "factor_analysis" and any(value is not None for value in
                                                  (self.factor_months, self.factor_mode, self.factor_max_symbols)):
            raise QueryError("invalid_job", "Este trabajo no admite parámetros de Factor Lab.", 422)
        if self.kind in {"sim_result", "sim_prices"}:
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
            raise QueryError("research_required", "Esta investigación requiere el modo Research local.", 403)

    def submit(self, command: JobCommand, key: str, *, origin: str = "ui") -> dict:
        if command.kind in RESEARCH_KINDS:
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
        if job["kind"] in RESEARCH_KINDS:
            self._require_research()
        if job["kind"] in {"maintenance", "tiingo"}:
            raise QueryError("result_restricted", "Este resultado pertenece al seguimiento ciego.", 403)
        if job["kind"] in {"backtest", "historical_ranking", "factor_analysis", "backtest_v1", "backtest_v2",
                           "prepare_history", "portfolio_lab"}:
            parameters = job["parameters"]
            if job["kind"] == "historical_ranking" and parameters.get("end") is not None:
                raise QueryError("reserved_period", "Este resultado no corresponde a una sola fecha observada.", 403)
            if job["kind"] == "factor_analysis":
                require_factor_period(parameters.get("start"), parameters.get("end"))
            else:
                require_observed_period(parameters.get("start"), parameters.get("end"))
        if job["kind"] in DERIVED_SOURCES:
            # Derived artifacts inherit the reserved-period check of their source job.
            field, kinds = DERIVED_SOURCES[job["kind"]]
            source_id = (job["parameters"].get(field) or {}).get("source_job_id")
            source = self.repository.get(source_id) if source_id else None
            if source is None or source["kind"] not in kinds:
                raise QueryError("result_unavailable", "El trabajo de origen no existe.", 404)
            require_observed_period(source["parameters"].get("start"), source["parameters"].get("end"))
        result = self.repository.result(job_id)
        if job["kind"] == "estimate_analysis" and (
                result.get("kind") != "estimate_analysis" or
                result.get("observed_cutoff") != OBSERVED_END.isoformat() or
                result.get("horizons_months") != [1, 3]):
            raise QueryError("reserved_period", "El resultado de estimaciones no respeta el corte observado.", 403)
        return result
