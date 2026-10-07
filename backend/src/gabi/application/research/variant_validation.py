"""Run the declared retrospective protocol through an explicit backtest runner."""

from collections.abc import Callable, Mapping

import pandas as pd

from gabi.domain.research.variant_validation import (
    DEFAULT_END,
    DEFAULT_START,
    DEFAULT_WINDOWS,
    VariantSpec,
    expected_rebalance_dates,
    window_metrics,
)


def run_validation(variants: list[VariantSpec], *, start: str = DEFAULT_START,
                   end: str = DEFAULT_END, top_n: int = 20,
                   windows: Mapping[str, tuple[str, str]] = DEFAULT_WINDOWS,
                   runner: Callable[..., dict]) -> dict:
    """Ejecuta control + variantes y devuelve una tabla comparable por ventana."""
    if not variants:
        raise ValueError("Declara al menos una variante.")
    if start != DEFAULT_START or end != DEFAULT_END:
        raise ValueError("Se requieren las fechas de la auditoría: 2016-01-02 a 2025-10-02.")
    names = [v.name for v in variants]
    if len(set(names)) != len(names) or "control_composite" in names:
        raise ValueError("Los nombres deben ser únicos y control_composite está reservado.")
    specs = [VariantSpec("control_composite", {})] + list(variants)
    expected = expected_rebalance_dates(start, end, 3)
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
            metrics = window_metrics(result, window_start, window_end)
            rows.append({"variant": name, "window": window, **metrics})
    return {
        "protocol": {"start": start, "end": end, "months": 3, "top_n": top_n,
                     "mode": "validation", "max_symbols": None, "expected_periods": 39},
        "variants_declared": [spec.name for spec in specs],
        "future": {"status": "not_evaluated", "reason": "Todo el intervalo es retrospectivo; prueba ciega intacta."},
        "results": results,
        "report": pd.DataFrame(rows),
    }
