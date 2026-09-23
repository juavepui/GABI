"""Arnés reproducible para validar variantes de R3 sobre V2.

El control Composite se ejecuta siempre con los mismos parámetros de universo,
fechas y motor. Las variantes se declaran antes de llamar al backtest; el
arnés rechaza parámetros que cambiarían la muestra y comprueba que todos los
resultados tengan exactamente las mismas fechas de rebalanceo.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import exchange_calendars as xcals
import pandas as pd

from . import portfolio_backtest, portfolio_metrics

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


def _expected_rebalance_dates(start: str, end: str, months: int) -> list[str]:
    current, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    dates = []
    while current + pd.DateOffset(months=months) <= end_ts:
        dates.append(current.date().isoformat())
        current += pd.DateOffset(months=months)
    return dates


def _window_metrics(result: dict, start: str, end: str) -> dict:
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


def run_validation(variants: list[VariantSpec], *, start: str = DEFAULT_START,
                   end: str = DEFAULT_END, top_n: int = 20,
                   windows: Mapping[str, tuple[str, str]] = DEFAULT_WINDOWS,
                   runner: Callable[..., dict] = portfolio_backtest.run) -> dict:
    """Ejecuta control + variantes y devuelve una tabla comparable por ventana."""
    if not variants:
        raise ValueError("Declara al menos una variante.")
    if start != DEFAULT_START or end != DEFAULT_END:
        raise ValueError("Se requieren las fechas de la auditoría: 2016-01-02 a 2025-10-02.")
    names = [v.name for v in variants]
    if len(set(names)) != len(names) or "control_composite" in names:
        raise ValueError("Los nombres deben ser únicos y control_composite está reservado.")
    specs = [VariantSpec("control_composite", {})] + list(variants)
    expected = _expected_rebalance_dates(start, end, 3)
    if len(expected) != 39:
        raise ValueError(f"El rango debe producir 39 rebalanceos; produce {len(expected)}.")
    results = {}
    for spec in specs:
        params = dict(spec.params)
        result = runner(start, end, months=3, top_n=top_n, max_symbols=None,
                        mode="validation", **params)
        period_dates = result["periods"]["fecha"].tolist()
        if period_dates != expected or result.get("skipped"):
            raise ValueError(f"{spec.name}: las fechas no coinciden con los 39 rebalanceos esperados.")
        results[spec.name] = result

    rows = []
    for name, result in results.items():
        for window, (window_start, window_end) in windows.items():
            metrics = _window_metrics(result, window_start, window_end)
            rows.append({"variant": name, "window": window, **metrics})
    return {
        "protocol": {"start": start, "end": end, "months": 3, "top_n": top_n,
                     "mode": "validation", "max_symbols": None, "expected_periods": 39},
        "variants_declared": [spec.name for spec in specs],
        "future": {"status": "not_evaluated", "reason": "Todo el intervalo es retrospectivo; prueba ciega intacta."},
        "results": results,
        "report": pd.DataFrame(rows),
    }
