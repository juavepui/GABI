"""Explicit snapshots and comparisons; ordinary reads never create events."""

from collections.abc import Callable
from datetime import date
from math import isfinite
from typing import Protocol

import pandas as pd

from gabi.application.administration.jobs import Jobs
from gabi.application.administration.model import ModelPolicy
from gabi.application.errors import QueryError
from gabi.application.market.queries import MarketRepository


class SignalRepository(Protocol):
    def snapshots(self) -> list[dict]: ...
    def snapshot(self, snapshot_id: int) -> pd.DataFrame: ...
    def save_snapshot(self, table: pd.DataFrame, as_of_date: str, name: str, top_n: int) -> int: ...
    def events(self, severity: str | None, limit: int) -> list[dict]: ...
    def record(self, events: list[dict], snapshot_id: int) -> None: ...
    def filing_facts(self, symbol: str) -> tuple[pd.DataFrame, str | None]: ...
    def record_filings(self, snapshot_id: int, results: list[dict]) -> int: ...


SignalComparator = Callable[[pd.DataFrame, pd.DataFrame, int, dict], list[dict]]
FilingsComparator = Callable[[str, pd.DataFrame, str | None], list[dict]]


class SignalMonitor:
    def __init__(self, repository: SignalRepository, market: MarketRepository,
                 policy: ModelPolicy, today: Callable[[], date], compare: SignalComparator,
                 compare_filings: FilingsComparator, jobs: Jobs):
        self.repository, self.market, self.policy, self.today, self.compare = repository, market, policy, today, compare
        self.compare_filings, self.jobs = compare_filings, jobs

    def snapshots(self) -> list[dict]:
        return self.repository.snapshots()

    def events(self, severity: str | None, limit: int) -> list[dict]:
        return self.repository.events(severity, limit)

    def save(self, name: str, top_n: int) -> int:
        name = name.strip()
        if not name or len(name) > 80 or not 1 <= top_n <= 30:
            raise QueryError("invalid_snapshot", "Indica nombre y tamaño de snapshot válidos.", 422)
        snapshot = self.market.ranking(dict(self.policy.frozen_weights), self.today())
        if snapshot.table.empty or snapshot.table["composite_score"].notna().sum() == 0:
            raise QueryError("no_candidates", "No hay candidatas con score para guardar.", 409)
        return self.repository.save_snapshot(snapshot.table, self.today().isoformat(), name, top_n)

    def run(self, snapshot_id: int, rank_change: int, score_change: float, confidence_drop: float) -> list[dict]:
        if rank_change < 1 or any(not isfinite(value) or value <= 0 or value > 100
                                  for value in (score_change, confidence_drop)):
            raise QueryError("invalid_thresholds", "Los umbrales no son válidos.", 422)
        previous = self.repository.snapshot(snapshot_id)
        if previous.empty:
            raise QueryError("snapshot_not_found", "No existe un snapshot con candidatas.", 404)
        current = self.market.ranking(dict(self.policy.frozen_weights), self.today()).table
        current = current[current["composite_score"].notna()].copy()
        current["rank"] = range(1, len(current) + 1)
        thresholds = {"rank_change": rank_change, "score_change": score_change,
                      "confidence_drop": confidence_drop}
        events = self.compare(previous, current, len(previous), thresholds)
        self.repository.record(events, snapshot_id)
        return events

    def earnings(self, snapshot_id: int) -> list[dict]:
        previous = self.repository.snapshot(snapshot_id)
        if previous.empty:
            raise QueryError("snapshot_not_found", "No existe un snapshot con candidatas.", 404)
        today = self.today()
        table = self.market.ranking(dict(self.policy.frozen_weights), today).table
        rows = []
        for symbol in previous.index:
            if symbol not in table.index:
                continue
            row = table.loc[symbol]
            event_date = row.get("next_earnings_date")
            days = row.get("next_earnings_days")
            if pd.notna(event_date) and pd.notna(days) and int(days) >= 0:
                rows.append({"symbol": symbol, "event_date": str(event_date),
                             "is_estimate": bool(row.get("next_earnings_is_estimate")),
                             "days_until": int(days)})
        return sorted(rows, key=lambda item: (item["event_date"], item["symbol"]))

    def filings(self, snapshot_id: int) -> dict:
        previous = self.repository.snapshot(snapshot_id)
        if previous.empty:
            raise QueryError("snapshot_not_found", "No existe un snapshot con candidatas.", 404)
        if len(previous) > 30:
            raise QueryError("resource_limit", "La revision SEC admite hasta 30 candidatas.", 422)
        results = []
        for symbol in previous.index:
            facts, cik = self.repository.filing_facts(str(symbol))
            results.extend(self.compare_filings(str(symbol), facts, cik))
        events = [event for result in results for event in result["events"]]
        return {"snapshot_id": snapshot_id, "checked": len(results),
                "with_comparison": sum(result["reason"] is None for result in results),
                "events": events, "results": results, "status": "EXPERIMENTAL"}

    def save_filings_job(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if job["kind"] != "filing_check":
            raise QueryError("invalid_job", "El job no contiene una revision SEC.", 422)
        result = self.jobs.result(job_id)
        snapshot_id = job["parameters"].get("snapshot_id")
        if result.get("snapshot_id") != snapshot_id or not isinstance(result.get("results"), list):
            raise QueryError("invalid_job", "El resultado SEC no corresponde al snapshot.", 422)
        self.repository.record_filings(snapshot_id, result["results"])
        return {"recorded": True, "events": result["events"]}
