"""The home page: data state, today's frozen target, last data update and first steps; never computes by default."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from typing import Protocol

from gabi.application.administration.model import ModelPolicy
from gabi.application.market.queries import RankingSnapshot, describe_data
from gabi.domain.portfolio.selection import target_portfolio

FROZEN_POSITIONS = 20
UPDATE_KINDS = {"data_update", "refresh", "symbols"}


class HomeMarket(Protocol):
    def cached_ranking(self, weights: dict[str, float], today: date) -> RankingSnapshot | None: ...
    def ranking(self, weights: dict[str, float], today: date) -> RankingSnapshot: ...


class HomeJobs(Protocol):
    def list(self) -> list[dict]: ...


class HomeQueries:
    def __init__(self, market: HomeMarket, policy: ModelPolicy, jobs: HomeJobs,
                 configured_keys: Callable[[], dict[str, bool]], universe_present: Callable[[], bool],
                 today: Callable[[], date], last_session: Callable[[], date] | None = None):
        self.market, self.policy, self.jobs, self.last_session = market, policy, jobs, last_session
        self.configured_keys, self.universe_present, self.today = configured_keys, universe_present, today

    def summary(self, compute: bool = False) -> dict:
        """`compute=False` answers at once from the cache; `compute=True` builds the frozen ranking if needed."""
        today = self.today()
        weights = dict(self.policy.frozen_weights)
        snapshot = self.market.ranking(weights, today) if compute else self.market.cached_ranking(weights, today)
        last_update = next((job for job in self.jobs.list() if job["kind"] in UPDATE_KINDS
                            and job["status"] == "succeeded"), None)
        keys = self.configured_keys()
        result: dict = {
            "as_of": today.isoformat(), "model_id": self.policy.frozen_id, "ranking_ready": snapshot is not None,
            "data": None, "target": [], "target_positions": FROZEN_POSITIONS,
            "last_update": None if last_update is None else {
                "kind": last_update["kind"], "finished_at": last_update["finished_at"]},
            "steps": {"fred_key": bool(keys.get("fred")), "universe": self.universe_present(),
                      "data_loaded": None, "updated": last_update is not None},
        }
        if snapshot is None:
            return result
        data = describe_data(snapshot, today, self.last_session() if self.last_session else None)
        result["data"] = asdict(data)
        result["steps"]["data_loaded"] = data.scored_count > 0
        target = target_portfolio(snapshot.table, FROZEN_POSITIONS)
        result["target"] = [
            {"symbol": str(symbol), "name": None if row.get("name") is None else str(row.get("name")),
             "sector": None if row.get("sector") is None else str(row.get("sector")),
             "composite_score": float(row["composite_score"]), "weight_pct": float(row["weight_pct"])}
            for symbol, row in target.iterrows()]
        return result
