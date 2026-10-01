"""Blind validations: sealed status, preregistered rules and the explicit commands that touch them."""

import calendar
import math
from collections.abc import Callable
from datetime import date
from typing import Protocol

from gabi.application.errors import QueryError
from gabi.domain.research.blind import disclosure, verify_chain

BLOCKS = ("value", "quality", "momentum", "risk")


class BlindStore(Protocol):
    def read_status(self) -> list[tuple[dict, list[dict]]]: ...


class BlindPlans(Protocol):
    def plans(self) -> dict[int, dict]: ...


class BlindWriter(Protocol):
    def create(self, record: dict) -> int: ...
    def break_seal(self, validation_id: int, reason: str) -> None: ...


def _add_months(day: date, months: int) -> date:
    year, month = divmod(day.year * 12 + day.month - 1 + months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _plan(plan: dict | None) -> dict | None:
    if plan is None:
        return None
    return {"issue": plan["issue"], "looks": plan["looks"], "sha256": plan["sha256"], "source": plan["source"]}


class BlindValidationQueries:
    def __init__(self, store: BlindStore, today: Callable[[], date], plans: BlindPlans | None = None):
        self.store, self.today, self.plans = store, today, plans

    def _plans(self) -> dict[int, dict]:
        return self.plans.plans() if self.plans is not None else {}

    def list_status(self) -> dict:
        current = self.today()
        plans = self._plans()
        items = []
        for validation, periods in self.store.read_status():
            try:
                integrity = verify_chain(periods)
                unlock = date.fromisoformat(validation["unlock_date"])
                due = (_add_months(date.fromisoformat(periods[-1]["rebalance_date"]),
                                   validation["rebalance_months"])
                       if periods else date.fromisoformat(validation["start_date"]))
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise QueryError("blind_data_invalid", "No se puede verificar el registro ciego.", 503) from exc
            plan = plans.get(validation["id"])
            shown = disclosure(validation["status"], unlock.isoformat(), plan["looks"] if plan else None,
                               current.isoformat())
            items.append({
                "id": validation["id"], "name": validation["name"], "status": validation["status"],
                "unlock_date": unlock.isoformat(), "n_periods": len(periods),
                "next_rebalance_due": due.isoformat(), "days_to_unlock": max(0, (unlock - current).days),
                "integrity": integrity, "revealed": shown["revealed"], "revealed_through": shown["through"],
                "next_look": shown["next_look"], "rebalance_due": current >= due and integrity["ok"],
                "preregistered": _plan(plan),
            })
        return {"items": items}

    def item(self, validation_id: int) -> dict:
        found = next((item for item in self.list_status()["items"] if item["id"] == validation_id), None)
        if found is None:
            raise QueryError("blind_not_found", f"No existe la validación #{validation_id}.", 404)
        return found


def new_validation(form: dict) -> dict:
    """The Streamlit creation form: percentage weights per block, 1-50 positions, 1/3/6/12 months."""
    name = form.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise QueryError("invalid_blind", "Indica un nombre de hasta 200 caracteres.", 422)
    weights = form.get("weights_pct") or {}
    if set(weights) != set(BLOCKS) or not all(
            isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)
            and 0 <= value <= 100 for value in weights.values()):
        raise QueryError("invalid_blind", "Los pesos deben estar entre 0 y 100 % para los cuatro bloques.", 422)
    positions, months = form.get("n_positions"), form.get("rebalance_months")
    if not isinstance(positions, int) or not 1 <= positions <= 50 or months not in (1, 3, 6, 12):
        raise QueryError("invalid_blind", "Posiciones o rebalanceo no válidos.", 422)
    try:
        start, unlock = date.fromisoformat(form.get("start_date") or ""), date.fromisoformat(form.get("unlock_date") or "")
    except ValueError as exc:
        raise QueryError("invalid_blind", "Indica fechas ISO válidas.", 422) from exc
    if unlock <= start:
        raise QueryError("invalid_blind", "La fecha de desbloqueo debe ser posterior a la de inicio.", 422)
    return {"name": name, "weights": {block: weights[block] / 100 for block in BLOCKS},
            "n_positions": positions, "rebalance_months": months,
            "start_date": start.isoformat(), "unlock_date": unlock.isoformat()}


class BlindCommands:
    def __init__(self, queries: BlindValidationQueries, writer: BlindWriter, research_mode: Callable[[], bool]):
        self.queries, self.writer, self.research_mode = queries, writer, research_mode

    def _require_research(self) -> None:
        if not self.research_mode():
            raise QueryError("research_required", "Las validaciones ciegas requieren el modo Research local.", 403)

    def create(self, form: dict) -> dict:
        self._require_research()
        record = new_validation(form)
        self.queries._plans()  # Unverifiable plans block every blind write.
        return self.queries.item(self.writer.create(record))

    def break_seal(self, validation_id: int, reason: str) -> dict:
        """Recorded permanently with its reason; refused for preregistered tests (their plan forbids early looks)."""
        self._require_research()
        reason = (reason or "").strip()
        if not reason:
            raise QueryError("invalid_blind", "Hace falta un motivo para romper el sello antes de tiempo.", 422)
        item = self.queries.item(validation_id)
        if item["preregistered"] is not None:
            raise QueryError("preregistered_seal",
                             f"La validación #{validation_id} sigue el preregistro del #{item['preregistered']['issue']}: "
                             "solo se miran resultados en sus revisiones fijadas.", 403)
        if item["status"] == "broken_early" or item["revealed"]:
            raise QueryError("seal_not_locked", "Esta validación ya no está bloqueada.", 409)
        self.writer.break_seal(validation_id, reason)
        return self.queries.item(validation_id)
