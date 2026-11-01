"""Preregistered statistics of NSI-v1 (#252): block-bootstrap lower bound, FF5+UMD alpha and the decision.

``docs/research/nsi-v1/preregistro.json`` fixes them before any return is read:

- Monthly net excess over the benchmark (both time-weighted, in EUR). One-sided
  lower bound of its annualised mean by circular block bootstrap: blocks of 12
  months, 5,000 replicas, alpha 0.05/3, for each window and for the whole.
- Alpha against Fama-French five factors plus momentum (Ken French, USD monthly),
  with Newey-West errors. "An interval centred on ≈ 0" is read as: the 95 %
  interval of the annualised alpha contains zero.
- Abandon if the BASE net excess over the whole period is ≤ 0, or the lower bound
  is negative in at least two of the three windows. If neither applies but the
  alpha interval contains zero, the result is a factor exposure: not promoted.
"""

import math

import numpy as np
import pandas as pd

from gabi.domain.research.academic_factors import _ols
from gabi.domain.research.ensemble_robustness import circular_indices

BLOCK_MONTHS = 12
REPLICAS = 5000
ALPHA = 0.05 / 3
SEED = 252
FACTORS = ("Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom")


def monthly(index: pd.Series) -> pd.Series:
    """Monthly returns of a daily index (time-weighted), labelled by month end."""
    month_end = index.resample("ME").last()
    first = pd.Series([index.iloc[0]], index=[index.index[0] - pd.offsets.MonthEnd(1)])
    return pd.concat([first, month_end]).pct_change().dropna()


def lower_bound(excess: pd.Series, *, block: int = BLOCK_MONTHS, replicas: int = REPLICAS, alpha: float = ALPHA,
                seed: int = SEED) -> dict:
    values = excess.dropna().to_numpy(dtype=float)
    if len(values) < block:
        return {"months": len(values), "mean_annual": None, "lower_bound_annual": None}
    rng = np.random.default_rng(seed)
    means = values[circular_indices(len(values), block, replicas, rng)].mean(axis=1)
    return {"months": len(values), "mean_annual": float(values.mean() * 12),
            "lower_bound_annual": float(np.quantile(means, alpha) * 12), "alpha": alpha, "block": block,
            "replicas": replicas, "seed": seed}


def factor_alpha(returns_usd: pd.Series, factors: pd.DataFrame) -> dict:
    """``returns_usd`` monthly (month end); ``factors`` monthly with a ``date`` column at the month start."""
    table = factors.assign(month=pd.to_datetime(factors["date"]).dt.to_period("M")).set_index("month")
    strategy = returns_usd.copy()
    strategy.index = strategy.index.to_period("M")
    joined = table.join(strategy.rename("strategy"), how="inner").dropna(subset=["strategy", *FACTORS, "RF"])
    if len(joined) <= len(FACTORS) + 12:
        return {"months": len(joined), "alpha_annual": None}
    y = (joined["strategy"] - joined["RF"]).to_numpy(dtype=float)
    X = np.column_stack([np.ones(len(joined)), joined[list(FACTORS)].to_numpy(dtype=float)])
    fit = _ols(y, X, ["alpha", *FACTORS])
    alpha, se = float(fit["coef"]["alpha"]), float(fit["se"]["alpha"])
    low, high = (alpha - 1.96 * se) * 12, (alpha + 1.96 * se) * 12
    return {"months": len(joined), "alpha_annual": alpha * 12, "ci95_annual": [low, high],
            "t_stat": alpha / se if se > 0 else math.nan, "contains_zero": low <= 0 <= high, "r2": fit["r2"],
            "loadings": {name: float(fit["coef"][name]) for name in FACTORS}}


def decide(overall_excess: float | None, window_bounds: list[float | None], alpha: dict) -> dict:
    negative = sum(bound is not None and bound < 0 for bound in window_bounds)
    if overall_excess is None or overall_excess <= 0:
        return {"label": "abandon", "reason": "net_excess_not_positive"}
    if negative >= 2:
        return {"label": "abandon", "reason": "lower_bound_negative_in_two_windows"}
    if alpha.get("contains_zero", True):
        return {"label": "factor_exposure", "reason": "alpha_interval_contains_zero"}
    return {"label": "continue_to_prospective", "reason": None}
