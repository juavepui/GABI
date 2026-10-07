"""Scheduled maintenance with explicit data sources, storage and clocks."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Protocol

import pandas as pd

from gabi.application.research.blind import BlindValidationQueries
from gabi.domain.market.freshness import MAINTENANCE_BENCHMARKS, last_completed_session, maintenance_freshness

BENCHMARKS = list(MAINTENANCE_BENCHMARKS)
SOON_DAYS = 7


class PeriodicStore(Protocol):
    def live_symbols(self) -> list[str]: ...
    def latest_prices(self, symbols: list[str]) -> dict[str, str | None]: ...
    def tiingo_queue(self) -> dict: ...
    def smallmid_state(self, today: date) -> dict: ...
    def acquire_tiingo(self, at: datetime) -> str | None: ...
    def release_tiingo(self) -> None: ...
    def queued_symbols(self) -> list[str]: ...
    def log(self, event: dict) -> None: ...


class SyncAttempt(Protocol):
    calls: int
    def payload(self, value: list[dict]) -> None: ...
    def finish(self, status: str, **options) -> None: ...


class PeriodicOperations(Protocol):
    def latest_event_id(self) -> int: ...
    def universe_checkpoint(self) -> dict | None: ...
    def universe_due(self, checkpoint: dict | None) -> bool: ...
    def universe_attempt(self) -> SyncAttempt: ...
    def universe(self, refresh: bool) -> pd.DataFrame: ...
    def fingerprint(self, records: list[dict]) -> str: ...
    def refresh_symbols(self, symbols: list[str], full_refresh: bool) -> dict: ...
    def refresh_macro(self, full_refresh: bool) -> dict: ...
    def events_since(self, event_id: int) -> list[dict]: ...
    def totals(self, events: list[dict]) -> dict: ...
    def record_rebalance(self, validation_id: int) -> dict: ...
    def smallmid_final(self) -> dict: ...
    def verify_ledger(self) -> dict: ...
    def capture_ledger(self, error: str | None, maintenance: dict) -> dict: ...
    def fetch_tiingo(self, symbols: list[str]) -> dict: ...
    def import_tiingo(self) -> dict: ...
    def mark_tiingo_complete(self, fetched: dict) -> None: ...


class PeriodicTasks:
    def __init__(self, store: PeriodicStore, operations: PeriodicOperations, blind: BlindValidationQueries,
                 now: Callable[[], datetime], wall_time: Callable[[], float], cpu_time: Callable[[], float]):
        self.store, self.operations, self.blind = store, operations, blind
        self.now, self.wall_time, self.cpu_time = now, wall_time, cpu_time

    def last_session(self, now: datetime | None = None) -> str:
        return last_completed_session(now or self.now()).isoformat()

    def latest_price(self, symbol: str) -> str | None:
        return self.store.latest_prices([symbol]).get(symbol)

    def live_symbols(self) -> list[str]:
        return self.store.live_symbols()

    def _freshness(self, now: datetime) -> tuple[str, dict, float, bool]:
        session = self.last_session(now)
        symbols = self.live_symbols()
        prices = self.store.latest_prices(list(dict.fromkeys([*symbols, *BENCHMARKS])))
        benchmarks, behind, fresh = maintenance_freshness(symbols, prices, session)
        return session, benchmarks, behind, fresh

    def stale_share(self, now: datetime | None = None) -> float:
        return self._freshness(now or self.now())[2]

    def prices_fresh(self, now: datetime | None = None) -> bool:
        return self._freshness(now or self.now())[3]

    def blind_status(self, today: date | None = None) -> list[dict]:
        today = today or self.now().date()
        rows = []
        for item in self.blind.list_status()["items"]:
            due = item["next_rebalance_due"]
            rows.append({"id": item["id"], "nombre": item["name"], "estado": item["status"], "proximo": due,
                         "vencido": bool(due and item["status"] == "locked" and today.isoformat() >= due),
                         "dias": (date.fromisoformat(due) - today).days if due else None,
                         "integridad": item["integrity"]["ok"], "periodos": item["n_periods"]})
        return rows

    def due_soon(self, days: int = SOON_DAYS, today: date | None = None) -> list[dict]:
        return [row for row in self.blind_status(today) if row["estado"] == "locked" and row["dias"] is not None
                and row["dias"] <= days]

    def status(self, now: datetime | None = None) -> dict:
        now = now or self.now()
        session, benchmarks, behind, fresh = self._freshness(now)
        return {"fecha": now.date().isoformat(), "ultima_sesion": session, "precios": benchmarks,
                "universo_sin_ultimo_cierre": behind, "precios_al_dia": fresh,
                "pruebas_ciegas": self.blind_status(now.date()), "tiingo_44": self.store.tiingo_queue(),
                "prueba_44": self.smallmid_state(now.date())}

    def smallmid_state(self, today: date | None = None) -> dict:
        return self.store.smallmid_state(today or self.now().date())

    def smallmid_step(self, today: date | None = None) -> dict:
        state = self.smallmid_state(today)
        if state["analizada"] or not state["datos_congelados"]:
            return {"lanzado": False, **state}
        try:
            return {"lanzado": True, **self.operations.smallmid_final()}
        except Exception as exc:
            return {"lanzado": True, "error": f"{type(exc).__name__}: {exc}"}

    def refresh_data(self, *, full_refresh: bool = False) -> dict:
        source = self.operations
        wall_started, cpu_started = self.wall_time(), self.cpu_time()
        event_id = source.latest_event_id()
        cp = source.universe_checkpoint()
        refresh_universe = full_refresh or source.universe_due(cp)
        attempt = source.universe_attempt()
        attempt.calls = int(refresh_universe)
        try:
            universe = source.universe(refresh_universe)
        except Exception as exc:
            attempt.finish("failed", reason=str(exc))
            raise
        if refresh_universe:
            attempt.payload(universe.to_dict("records"))
            digest = source.fingerprint(universe.sort_values("symbol").to_dict("records"))
            status = "new" if not cp else "revised" if cp.get("fingerprint") != digest else "unchanged"
            if universe.attrs.get("cache_after_error"):
                attempt.finish("failed", reason="fuentes de universo fallidas; se conserva la caché previa")
            else:
                attempt.finish(status, state={"fingerprint": digest}, new=int(not cp), revised=int(status == "revised"),
                               reason="revisión diaria de composición/sectores actuales")
        symbols = [*universe["symbol"].tolist(), *BENCHMARKS]
        result = source.refresh_symbols(symbols, full_refresh)
        macro_result = source.refresh_macro(full_refresh)
        events = source.events_since(event_id)
        failed_events = [{k: e.get(k) for k in ("source", "entity", "dataset", "reason")}
                         for e in events if e["status"] == "failed"]
        return {"simbolos": len(symbols), "fallos": len(result.get("failed", {})), "failed": result.get("failed", {}),
                "failed_events": failed_events, "macro": macro_result, "sync": source.totals(events),
                "cambios": events, "full_refresh": full_refresh,
                "seconds_total": self.wall_time() - wall_started, "cpu_seconds_total": self.cpu_time() - cpu_started}

    def record_due(self, now: datetime | None = None) -> list[dict]:
        now = now or self.now()
        outcomes = []
        session, benchmarks, behind, fresh = self._freshness(now)
        for row in self.blind_status(now.date()):
            if not row["vencido"]:
                continue
            if not fresh:
                outcomes.append({"id": row["id"], "registrado": False,
                                 "motivo": f"precios no actualizados (SPY {benchmarks['SPY']}, "
                                           f"RSP {benchmarks['RSP']}, sin último cierre "
                                           f"{behind:.1%}, última sesión {session})"})
                continue
            if not row["integridad"]:
                outcomes.append({"id": row["id"], "registrado": False, "motivo": "cadena de hashes rota; revisar"})
                continue
            result = self.operations.record_rebalance(row["id"])
            outcomes.append({"id": row["id"], "registrado": True, "fecha": result["rebalance_date"],
                             "hash": result["record_hash"], "posiciones": len(result["symbols"])})
        return outcomes

    def run(self, *, refresh: bool = True, full_refresh: bool = False) -> dict:
        integrity = self.operations.verify_ledger()
        if not integrity["ok"]:
            raise ValueError(f"Ledger no íntegro antes del mantenimiento: {integrity['reason']}")
        report: dict = {}
        try:
            report["antes"] = self.status()
            if refresh:
                report["refresco"] = self.refresh_data(**({"full_refresh": True} if full_refresh else {}))
            report["rebalanceos"] = self.record_due()
            report["prueba_44"] = self.smallmid_step()
            report["despues"] = self.status()
        except Exception as exc:
            report["error"] = f"{type(exc).__name__}: {exc}"
        maintenance = {k: v for k, v in report.get("refresco", {}).items() if k != "cambios"}
        event = self.operations.capture_ledger(report.get("error"), maintenance)
        report["ledger"] = {"seq": event["seq"], "record_hash": event["record_hash"], "status": event["payload"]["status"]}
        self.store.log({"at": self.now().astimezone(UTC).isoformat(), "accion": "run", **report})
        return report

    def resume_tiingo(self) -> dict:
        omitted = self.store.acquire_tiingo(self.now())
        if omitted:
            return {"omitido": omitted}
        try:
            fetched = self.operations.fetch_tiingo(self.store.queued_symbols())
            imported = self.operations.import_tiingo()
            self.operations.mark_tiingo_complete(fetched)
        finally:
            self.store.release_tiingo()
        report = {"descarga": fetched, "importacion": imported, "cola": self.store.tiingo_queue()}
        self.store.log({"at": self.now().astimezone(UTC).isoformat(), "accion": "tiingo", **report})
        return report
