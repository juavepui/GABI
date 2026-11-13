"""Read a finished Portfolio Lab artifact, with the daily tail risk the old page computed per NAV."""

from typing import Protocol

import pandas as pd

from gabi.application.administration.jobs import Jobs
from gabi.application.errors import QueryError
from gabi.application.research.backtest_diagnostics import _tail
from gabi.application.research.portfolio_lab import SPY
from gabi.application.research.reservations import require_observed_period


class TailMath(Protocol):
    def tail_risk(self, returns: pd.Series, horizon: str) -> dict: ...
    def returns_from_nav(self, nav: pd.Series) -> pd.Series: ...


class PortfolioLabQueries:
    """Typed summary of a verified artifact plus the daily tail risk the page computed from each NAV."""

    def __init__(self, jobs: Jobs, math: TailMath):
        self.jobs, self.math = jobs, math

    def preview(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if job["kind"] != "portfolio_lab":
            raise QueryError("job_not_found", "El resultado de Portfolio Lab no existe.", 404)
        result = self.jobs.result(job_id)  # Research mode, reserved dates and SHA-256 are checked here.
        require_observed_period(result["start"], result["end"])
        curve = pd.DataFrame(result["curve"])
        curve.index = pd.to_datetime(curve.pop("fecha"))
        horizon = "una sesión (NAV diario)"
        tail = []
        for name, label in [*((scheme["id"], scheme["label"]) for scheme in result["schemes"]),
                            (SPY, "SPY (buy & hold)")]:
            try:
                returns = self.math.returns_from_nav(curve[name].dropna().astype(float))
                tail.append({"name": label, "summary": _tail(self.math.tail_risk(returns, horizon)), "error": None})
            except (ValueError, TypeError) as exc:
                tail.append({"name": label, "summary": None, "error": str(exc)})
        return {key: result[key] for key in ("status", "independent_advantage_demonstrated", "start", "end",
                                             "options", "mode", "skipped", "labels", "scenario_labels",
                                             "scenario_ground", "curve")} | {
            "job_id": job_id, "result_sha256": job["result_sha256"],
            "schemes": result["schemes"],
            "scenarios": result["scenarios"], "tail": {"horizon": horizon, "message": None, "series": tail},
        }
