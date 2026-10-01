"""Read the Research Lab experiment log in Research mode, without writing or recomputing."""

from collections.abc import Callable
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.domain.research.experiments import STAGE_INFO, STAGES


class ExperimentStore(Protocol):
    def list(self, family: str | None, stage: str | None) -> tuple[list[dict], list[str]]: ...

    def get(self, experiment_id: int) -> dict | None: ...


def returns_series(returns: dict | None) -> pd.Series | None:
    """The saved series exactly as research_lab.get_experiment rebuilds it."""
    if not returns:
        return None
    series = pd.Series(returns)
    series.index = pd.to_datetime(series.index)
    return series.sort_index()


def _period_label(key: str) -> str:
    return key[:10]


class ExperimentQueries:
    def __init__(self, store: ExperimentStore, research_mode: Callable[[], bool]):
        self.store, self.research_mode = store, research_mode

    def _require_research(self) -> None:
        if not self.research_mode():
            raise QueryError("research_required", "Research Lab requiere el modo Research local.", 403)

    def list(self, family: str | None = None, stage: str | None = None, offset: int = 0, limit: int = 50) -> dict:
        self._require_research()
        if stage is not None and stage not in STAGES:
            raise QueryError("invalid_request", "La fase no es válida.", 422)
        items, families = self.store.list(family, stage)
        return {"total": len(items), "offset": offset, "items": items[offset:offset + limit],
                "families": families,
                "stages": [{"id": key, **STAGE_INFO[key]} for key in STAGES]}

    def detail(self, experiment_id: int) -> dict:
        self._require_research()
        item = self.store.get(experiment_id)
        if item is None:
            raise QueryError("experiment_not_found", "El experimento no existe.", 404)
        returns = item.pop("returns") or {}
        if not isinstance(returns, dict):
            raise QueryError("experiments_invalid", "La serie del experimento no es válida.", 503)
        dates = sorted(_period_label(str(key)) for key in returns)
        deps = item.pop("deps") or {}
        return item | {
            "deps": [{"package": name, "version": str(deps[name])} for name in sorted(deps)],
            "has_returns": bool(returns), "returns_count": len(returns),
            "returns_first": dates[0] if dates else None,
            "returns_last": dates[-1] if dates else None,
        }
