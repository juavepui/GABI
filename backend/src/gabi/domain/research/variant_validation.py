"""Arnés reproducible para validar variantes de R3 sobre V2.

El control Composite se ejecuta siempre con los mismos parámetros de universo,
fechas y motor. Las variantes se declaran antes de llamar al backtest; el
arnés rechaza parámetros que cambiarían la muestra y comprueba que todos los
resultados tengan exactamente las mismas fechas de rebalanceo.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import exchange_calendars as xcals
import pandas as pd

from gabi.domain.portfolio import metrics as portfolio_metrics

DEFAULT_START = "2016-01-02"
DEFAULT_END = "2025-10-02"  # Los mismos 39 trimestres de full_universe_audit.
DEFAULT_WINDOWS = {
    "full_history": (DEFAULT_START, DEFAULT_END),
    "development_retrospective": (DEFAULT_START, "2021-01-02"),
    "validation_retrospective": ("2021-01-02", DEFAULT_END),
}
_LOCKED_PARAMS = {"start", "end", "months", "mode", "max_symbols"}


@dataclass(frozen=True)
class VariantSpec:
    """Configuración declarada antes de observar cualquier resultado."""

    name: str
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.name.strip():
            raise ValueError("Toda variante necesita un nombre no vacío.")
        forbidden = _LOCKED_PARAMS & set(self.params)
        if forbidden:
            raise ValueError(f"La variante no puede cambiar la muestra: {sorted(forbidden)}")


def expected_rebalance_dates(start: str, end: str, months: int) -> list[str]:
    current, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    dates = []
    while current + pd.DateOffset(months=months) <= end_ts:
        dates.append(current.date().isoformat())
        current += pd.DateOffset(months=months)
    return dates


def window_metrics(result: dict, start: str, end: str) -> dict:
    nav = result["nav_curve"]
    calendar = xcals.get_calendar("XNYS")
    entry = calendar.next_session(calendar.date_to_session(pd.Timestamp(start), direction="previous"))
    next_entry = calendar.next_session(calendar.date_to_session(pd.Timestamp(end), direction="previous"))
    # The first daily return of each window includes its entry/rebalance costs.
    # Use the previous NAV as denominator at internal boundaries; initial cash
    # for the first window. No overlapping returns or lost first-day costs.
    segment = nav[(nav.index >= entry) & (nav.index < next_entry)]
    if len(segment) < 2:
        return {"cagr_net": None, "es_95": None, "es_99": None, "drawdown": None,
                "turnover": None, "cost_total": None, "beta_spy": None, "n_obs": 0}
    previous = nav[nav.index < entry]
    base = float(previous.iloc[-1]) if len(previous) else result["initial_capital"]
    base_date = previous.index[-1] if len(previous) else entry
    years = (segment.index[-1] - base_date).days / 365.25
    cagr = float((segment.iloc[-1] / base) ** (1 / years) - 1) if years > 0 else None
    returns = segment.pct_change(fill_method=None)
    returns.iloc[0] = segment.iloc[0] / base - 1
    tail = portfolio_metrics.tail_risk_metrics(returns, horizon="una sesión")
    drawdown = float((segment / segment.cummax().clip(lower=base) - 1).min())
    periods = result["periods"]
    selected = periods[(periods["fecha"] >= start) & (periods["fecha"] < end)]
    spy = result.get("nav_curve_spy")
    beta = None
    if spy is not None:
        spy_segment = spy[(spy.index >= segment.index[0]) & (spy.index <= segment.index[-1])]
        if len(spy_segment) >= 2:
            beta = portfolio_metrics.beta_vs_benchmark(
                portfolio_metrics.returns_from_nav(segment),
                portfolio_metrics.returns_from_nav(spy_segment),
            )
    return {
        "cagr_net": cagr,
        "es_95": tail["95"]["expected_shortfall"],
        "es_99": tail["99"]["expected_shortfall"],
        "drawdown": drawdown,
        "turnover": float(selected["turnover_pct"].mean()) if not selected.empty else None,
        "commissions": float(selected["comision_pagada"].sum()),
        "spread_cost": float(selected["spread_pagado"].sum()) if "spread_pagado" in selected else None,
        "cost_total": float(selected["coste_total"].sum()) if "coste_total" in selected else None,
        "initial_value": base, "final_value": float(segment.iloc[-1]),
        "n_periods": len(selected),
        "beta_spy": beta,
        "n_obs": len(returns),
    }


