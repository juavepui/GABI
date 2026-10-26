"""The home page: data state, today's frozen target, last data update and first steps; never computes by default."""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Protocol

import pandas as pd

from gabi.application.administration.model import ModelPolicy
from gabi.application.errors import QueryError
from gabi.application.market.queries import RankingSnapshot, describe_data
from gabi.domain.market.identity import normalize_symbol
from gabi.domain.portfolio import alerts as rules
from gabi.domain.portfolio.selection import target_portfolio

FROZEN_POSITIONS = 20
UPDATE_KINDS = {"data_update", "refresh", "symbols"}


class HomeMarket(Protocol):
    def cached_ranking(self, weights: dict[str, float], today: date) -> RankingSnapshot | None: ...
    def ranking(self, weights: dict[str, float], today: date) -> RankingSnapshot: ...


class HomeJobs(Protocol):
    def list(self) -> list[dict]: ...


@dataclass(frozen=True)
class AlertSources:
    """Cheap reads of data already stored; none recomputes the ranking or compares filings (#183)."""

    latest_snapshot: Callable[[], tuple[dict, list[str]] | None]  # (meta, symbols by rank)
    signal_events: Callable[[str], list[dict]]  # detected since the ISO date
    open_theses: Callable[[], list[dict]]
    held: Callable[[], list[str]]  # Mi cartera
    events: Callable[[list[str], date], list[dict] | None]  # cached corporate events; None while busy


def _no_alerts() -> AlertSources:
    return AlertSources(lambda: None, lambda since: [], list, list, lambda symbols, today: [])


class HomeQueries:
    def __init__(self, market: HomeMarket, policy: ModelPolicy, jobs: HomeJobs,
                 configured_keys: Callable[[], dict[str, bool]], universe_present: Callable[[], bool],
                 today: Callable[[], date], last_session: Callable[[], date] | None = None,
                 alerts: AlertSources | None = None):
        self.market, self.policy, self.jobs, self.last_session = market, policy, jobs, last_session
        self.sources = alerts or _no_alerts()
        self.configured_keys, self.universe_present, self.today = configured_keys, universe_present, today

    def summary(self, compute: bool = False) -> dict:
        """`compute=False` answers at once from the cache; `compute=True` builds the frozen ranking if needed."""
        today = self.today()
        weights = dict(self.policy.frozen_weights)
        snapshot = self.market.ranking(weights, today) if compute else self.market.cached_ranking(weights, today)
        jobs = self.jobs.list()
        last_update = next((job for job in jobs if job["kind"] in UPDATE_KINDS
                            and job["status"] == "succeeded"), None)
        keys = self.configured_keys()
        result: dict = {
            "as_of": today.isoformat(), "model_id": self.policy.frozen_id, "ranking_ready": snapshot is not None,
            "data": None, "target": [], "target_positions": FROZEN_POSITIONS, "alerts": [],
            "last_update": None if last_update is None else {
                "kind": last_update["kind"], "finished_at": last_update["finished_at"]},
            "steps": {"fred_key": bool(keys.get("fred")), "universe": self.universe_present(),
                      "data_loaded": None, "updated": last_update is not None},
        }
        held = self.sources.held()
        alerts = rules.failed_jobs(jobs, today=today) + rules.overdue_theses(self.sources.open_theses(), today=today)
        alerts += rules.filing_changes(
            self.sources.signal_events((today - timedelta(days=rules.FILING_DAYS)).isoformat()), held, today=today)
        if snapshot is None:
            result["alerts"] = rules.ordered(alerts)
            return result
        data = describe_data(snapshot, today, self.last_session() if self.last_session else None)
        result["data"] = asdict(data)
        result["steps"]["data_loaded"] = data.scored_count > 0
        # The same data without the ranking's large attrs, which pandas deep-copies on every operation (#183).
        table = pd.DataFrame(snapshot.table)
        target = target_portfolio(table, FROZEN_POSITIONS)
        result["target"] = [
            {"symbol": str(symbol), "name": None if row.get("name") is None else str(row.get("name")),
             "sector": None if row.get("sector") is None else str(row.get("sector")),
             "composite_score": float(row["composite_score"]), "weight_pct": float(row["weight_pct"])}
            for symbol, row in target.to_dict("index").items()]
        result["alerts"] = rules.ordered(alerts + self._ranking_alerts(table, target, held, today))
        return result

    def _ranking_alerts(self, table: pd.DataFrame, target: pd.DataFrame, held: list[str],
                        today: date) -> list[dict]:
        """Alerts that need the cached ranking: results, dividends and changes of the Top-20."""
        candidates = [str(symbol) for symbol in target.index]
        columns = [column for column in ("next_earnings_date", "next_earnings_is_estimate") if column in table]
        rows = table.loc[table.index.isin([*candidates, *held]), columns].to_dict("index")
        earnings = {str(symbol): (row.get("next_earnings_date"), bool(row.get("next_earnings_is_estimate")))
                    for symbol, row in rows.items()}
        alerts = rules.upcoming_earnings(earnings, candidates, scope="target", today=today, link="/cartera/seguimiento")
        alerts += rules.upcoming_earnings(earnings, held, scope="holdings", today=today, link="/cartera/mi-cartera")
        try:
            events = self.sources.events(list(dict.fromkeys([*candidates, *held])), today)
        except QueryError:  # An oversized cached record must not break the home page.
            events = []
        alerts += rules.upcoming_dividends(events or [], [*candidates, *held], today=today)
        saved = self.sources.latest_snapshot()
        if saved is not None:
            meta, symbols = saved
            # Older snapshots kept BRK.B/BF.B; the ranking uses the dash spelling (#172).
            saved_top = [normalize_symbol(symbol) for symbol in symbols[:rules.TOP_N]]
            alerts += rules.top_changes(candidates, saved_top, meta["as_of_date"], meta["name"])
        return alerts
