"""Blind forward validation: immutable rebalances and the sealed performance (HIPOTESIS_CONGELADA.md).

Each rebalance records its picks, entry prices, chained hash and code commit; the return against
SPY stays hidden until the unlock date. A local app cannot stop its owner reading the database, so
``break_seal_early`` leaves an honest, permanent record that the test was broken and why.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd

from gabi.domain.research import blind as rules


class DuplicatePeriodError(Exception):
    """Raised by the store when the validation already sealed that date."""


class BlindLedgerStore(Protocol):
    def create(self, record: dict) -> int: ...
    def validation(self, validation_id: int) -> dict: ...
    def periods(self, validation_id: int) -> list[dict]: ...
    def seal(self, period: dict, ranking: Callable[[], tuple[str, str]]) -> None: ...
    def enable_ranking(self, validation_id: int) -> bool: ...
    def break_seal(self, validation_id: int, at: str, reason: str) -> None: ...
    def validations(self) -> pd.DataFrame: ...


@dataclass(frozen=True)
class BlindLedger:
    store: BlindLedgerStore
    ranking: Callable[[str, dict], pd.DataFrame]  # (as_of, weights) -> table ordered by score
    prices: Callable[[list], dict]  # symbols -> cached daily history with adj_close
    git_commit: Callable[[], str | None]
    today: Callable[[], date]
    timestamp: Callable[[], str]  # local wall-clock ISO stamp, as the ledger always stored
    log_experiment: Callable[..., int]
    duplicate: type[Exception] = DuplicatePeriodError

    def _validation(self, validation_id: int) -> dict:
        validation = self.store.validation(validation_id)
        if not validation:
            raise ValueError(f"No existe la validación #{validation_id}.")
        return validation

    def create_validation(self, name: str, weights: dict, n_positions: int, rebalance_months: int,
                          start_date: str, unlock_date: str, model_id: str = "GABI-MF-v1") -> int:
        if pd.Timestamp(unlock_date) <= pd.Timestamp(start_date):
            raise ValueError("La fecha de desbloqueo debe ser posterior a la de inicio.")
        if n_positions < 1:
            raise ValueError("n_positions debe ser al menos 1.")
        return self.store.create({"created_at": self.timestamp(), "name": name, "model_id": model_id,
                                  "weights_json": json.dumps(weights), "n_positions": n_positions,
                                  "rebalance_months": rebalance_months, "start_date": start_date,
                                  "unlock_date": unlock_date, "git_commit_created": self.git_commit()})

    def record_rebalance(self, validation_id: int, as_of: str | None = None) -> dict:
        """Seal the picks and entry prices of a real rebalance; retrying the same date raises.

        ``as_of`` defaults to today; another date is allowed for tests but flagged in
        ``as_of_is_today``. Entry price is the last adjusted close on or before ``as_of``."""
        validation = self._validation(validation_id)
        periods = self.store.periods(validation_id)
        as_of = as_of or self.today().isoformat()
        as_of_ts = pd.Timestamp(as_of)
        # The validation's recorded weights, not the current defaults.
        ranked = self.ranking(as_of, json.loads(validation["weights_json"]))
        eligible = rules.eligible(ranked)
        n_positions = validation["n_positions"]
        if len(eligible) < n_positions:
            raise ValueError(f"Solo {len(eligible)}/{n_positions} candidatas con cobertura suficiente hoy.")
        picks = eligible.index.tolist()[:n_positions]
        entry, missing = rules.entry_prices(self.prices(picks), picks, as_of_ts)
        if missing:
            raise ValueError(f"Faltan precios recientes para: {', '.join(missing)}")
        prev_hash = periods[-1]["record_hash"] if periods else None
        record_hash = rules.record_hash(prev_hash, rules.canonical_payload(as_of, picks, entry))
        try:
            self.store.seal({"validation_id": validation_id, "rebalance_date": as_of,
                             "recorded_at": self.timestamp(), "symbols_json": json.dumps(picks),
                             "weights_json": json.dumps({s: 1.0 / n_positions for s in picks}),
                             "entry_prices_json": json.dumps(entry), "git_commit": self.git_commit(),
                             "prev_hash": prev_hash, "record_hash": record_hash},
                            lambda: rules.ranking_snapshot(ranked, eligible.index))
        except self.duplicate as exc:
            raise ValueError(f"Ya existe un rebalanceo registrado para {as_of} en esta validación — "
                             "es inmutable, no se puede repetir ni sobrescribir.") from exc
        return {"rebalance_date": as_of, "symbols": picks, "entry_prices": entry,
                "record_hash": record_hash, "as_of_is_today": as_of == self.today().isoformat()}

    def enable_ranking_snapshots(self, validation_id: int) -> None:
        """Store the full universe score in this validation's future rebalances."""
        if not self.store.enable_ranking(validation_id):
            raise ValueError(f"No existe la validación #{validation_id}.")

    def verify_integrity(self, validation_id: int) -> dict:
        return rules.verify_chain(self.store.periods(validation_id))

    def mark_to_market_return(self, symbols: list, entry: dict, as_of_ts: pd.Timestamp) -> float | None:
        return rules.mark_to_market_return(self.prices(symbols), symbols, entry, as_of_ts)

    def get_status(self, validation_id: int, reveal: bool = False, as_of: str | None = None) -> dict:
        """No return keys while locked before the unlock date, unless ``reveal`` is explicit.

        ``as_of`` (default today) cuts performance there: only earlier rebalances count and the
        last period is valued on that date, so a preregistered review shows nothing later."""
        validation = self._validation(validation_id)
        periods = self.store.periods(validation_id)
        today = self.today()
        base = {
            "id": validation_id, "name": validation["name"], "status": validation["status"],
            "unlock_date": validation["unlock_date"], "n_periods": len(periods),
            "next_rebalance_due": rules.next_rebalance_due(validation, periods),
            "days_to_unlock": max(0, (pd.Timestamp(validation["unlock_date"]) - pd.Timestamp(today)).days),
            "integrity": rules.verify_chain(periods),
            "revealed": rules.is_revealed(validation, today) or reveal,
        }
        if not base["revealed"]:
            return base
        if not periods:
            base["performance"] = None
            return base
        end = as_of or today.isoformat()
        shown = periods if as_of is None else [period for period in periods if period["rebalance_date"] < as_of]
        spy_history = self.prices(["SPY"]).get("SPY", pd.DataFrame())
        period_returns = []
        for i, period in enumerate(shown):
            as_of_ts = pd.Timestamp(shown[i + 1]["rebalance_date"] if i + 1 < len(shown) else end)
            spy_entry = rules.last_price_on_or_before(spy_history, pd.Timestamp(period["rebalance_date"]))
            period_returns.append({
                "rebalance_date": period["rebalance_date"],
                "retorno": self.mark_to_market_return(json.loads(period["symbols_json"]),
                                                      json.loads(period["entry_prices_json"]), as_of_ts),
                "retorno_spy": (self.mark_to_market_return(["SPY"], {"SPY": spy_entry}, as_of_ts)
                                if spy_entry is not None else None)})
        base["performance"] = {"periods": period_returns}
        return base

    def break_seal_early(self, validation_id: int, reason: str) -> None:
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("Hace falta un motivo para romper el sello antes de tiempo.")
        self.store.break_seal(validation_id, self.timestamp(), reason)

    def list_validations(self) -> pd.DataFrame:
        return self.store.validations()

    def export_to_research_lab(self, validation_id: int, as_of: str | None = None) -> int:
        validation = self._validation(validation_id)
        if not rules.is_revealed(validation, self.today()):
            raise ValueError("Esta validación sigue bloqueada -- no se puede exportar sin desbloquear antes.")
        status = self.get_status(validation_id, reveal=True, as_of=as_of)
        perf = status.get("performance")
        returns = None
        if perf and perf["periods"]:
            rets = {p["rebalance_date"]: p["retorno"] for p in perf["periods"] if p["retorno"] is not None}
            if rets:
                returns = pd.Series(rets)
                returns.index = pd.to_datetime(returns.index)
        return self.log_experiment(
            validation["model_id"], "LIVE_FORWARD", True, git_commit=validation["git_commit_created"],
            universe="S&P 500 en vivo (hoy)", factors="Value/Quality/Momentum/Risk",
            weights=json.loads(validation["weights_json"]), n_positions=validation["n_positions"],
            rebalance=f"Every {validation['rebalance_months']}mo",
            cost_model="Sin coste (mark-to-market de precios reales, no una cartera ejecutada)",
            is_start=validation["start_date"], is_end=as_of or self.today().isoformat(),
            family=f"blind_validation_{validation_id}",
            n_periods=status["n_periods"] if as_of is None else len(perf["periods"]) if perf else 0,
            returns=returns,
            notes=f"Blind Forward Validation '{validation['name']}' -- estado {validation['status']}, "
                  f"desbloqueo {validation['unlock_date']}.",
            result={"broken_early_reason": validation.get("broken_early_reason")})
