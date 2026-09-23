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

import pandas as pd

from . import portfolio_backtest, portfolio_metrics

DEFAULT_START = "2016-07-02"
DEFAULT_END = "2026-04-02"  # 39 rebalanceos trimestrales desde DEFAULT_START
DEFAULT_WINDOWS = {
    "development": ("2016-07-02", "2021-07-02"),
    "validation": ("2021-07-02", "2025-07-02"),
    "future": ("2025-07-02", "2026-04-02"),
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
    segment = nav[(nav.index >= pd.Timestamp(start)) & (nav.index <= pd.Timestamp(end))]
    if len(segment) < 2:
        return {"cagr_net": None, "es_95": None, "es_99": None, "drawdown": None,
                "turnover": None, "cost_total": 0.0, "beta_spy": None, "n_obs": 0}
    years = (segment.index[-1] - segment.index[0]).days / 365.25
    cagr = float((segment.iloc[-1] / segment.iloc[0]) ** (1 / years) - 1) if years > 0 else None
    returns = portfolio_metrics.returns_from_nav(segment)
    tail = portfolio_metrics.tail_risk_metrics(returns, horizon="una sesión")
    drawdown = float((segment / segment.cummax() - 1).min())
    periods = result["periods"]
    selected = periods[(periods["fecha"] >= start) & (periods["hasta"] <= end)]
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
        "cost_total": float(selected["comision_pagada"].sum()) if not selected.empty else 0.0,
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
        if period_dates != expected:
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
        "results": results,
        "report": pd.DataFrame(rows),
    }
