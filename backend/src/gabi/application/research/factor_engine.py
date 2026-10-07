"""Explicit Factor Lab operation; readers and the observation day are injected."""
from datetime import date
from typing import Protocol

import exchange_calendars as xcals
import pandas as pd

from gabi.domain.research.factors import (
    _CALENDAR,
    DEFAULT_FACTOR_COLS,
    DEFAULT_HORIZONS,
    _entry_exit_sessions,
    analyze_period,
    summarize,
)

VALID_MODES = ("validation", "fast_dev")


class FactorInputs(Protocol):
    def membership(self, as_of: str) -> dict: ...
    def sample(self, symbols: list, maximum: int | None) -> list: ...
    def ranking(self, as_of: str, symbols: list) -> pd.DataFrame: ...
    def prices(self, symbols: list, first: str, last: str) -> dict: ...


def run_factor_analysis(
    start: str, end: str, months: int = 3, max_symbols: int | None = None, mode: str = "validation",
    factor_cols=DEFAULT_FACTOR_COLS, horizons_months=DEFAULT_HORIZONS, n_quantiles: int = 5,
    min_coverage: float = .7, min_universe_coverage: float = .5,
    *, inputs: FactorInputs, today: date, min_rows_per_quantile: int = 4,
) -> dict:
    """Read one rebalance at a time and calculate the unchanged factor evidence."""
    if mode not in VALID_MODES:
        raise ValueError(f"mode debe ser uno de {VALID_MODES}.")
    if mode == "validation" and max_symbols is not None:
        raise ValueError("mode='validation' no permite muestreo (max_symbols debe ser None) -- "
                         "usa mode='fast_dev' para pruebas rápidas con un subconjunto.")
    if mode == "fast_dev" and max_symbols is None:
        raise ValueError("mode='fast_dev' necesita max_symbols (ej. 50/100/200) -- "
                         "usa mode='validation' para el universo histórico completo.")
    if not 1 <= months <= 12:
        raise ValueError("Rebalanceo inválido.")
    if n_quantiles < 2:
        raise ValueError("n_quantiles debe ser al menos 2.")
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    if start_ts >= end_ts or end_ts > pd.Timestamp(today):
        raise ValueError("El intervalo debe terminar después del inicio y no superar hoy.")

    calendar = xcals.get_calendar(_CALENDAR)
    boundaries = []
    current = start_ts
    while current + pd.DateOffset(months=months) <= end_ts:
        boundaries.append(current)
        current += pd.DateOffset(months=months)
    if not boundaries:
        raise ValueError("El intervalo no contiene ningún rebalanceo completo.")

    ic_rows, quantile_rows, turnover_rows, skipped = [], [], [], []
    previous_quantile_members: dict = {}  # factor -> {quantil: set(symbols)}

    for as_of in boundaries:
        as_of_str = as_of.date().isoformat()
        try:
            membership = inputs.membership(as_of_str)
            if not membership["is_exact"]:
                raise ValueError(membership["note"])
            symbols = inputs.sample(membership["symbols"], max_symbols)
            ranked = inputs.ranking(as_of_str, symbols)
            eligible = ranked[ranked["composite_score"].notna() & (ranked["score_coverage"] >= min_coverage)]
            if len(eligible) / len(symbols) < min_universe_coverage:
                raise ValueError(f"cobertura insuficiente del universo ({len(eligible)}/{len(symbols)})")
        except (ValueError, RuntimeError) as exc:
            skipped.append({"fecha": as_of_str, "motivo": str(exc)})
            continue

        first_session, _ = _entry_exit_sessions(calendar, as_of, min(horizons_months))
        _, last_session = _entry_exit_sessions(calendar, as_of, max(horizons_months))
        histories = inputs.prices(eligible.index.tolist(), first_session.date().isoformat(), last_session.date().isoformat())
        period_ic, period_quantiles, period_turnover, previous_quantile_members = analyze_period(
            eligible, histories, as_of, calendar=calendar, today=today, factor_cols=factor_cols,
            horizons_months=horizons_months, n_quantiles=n_quantiles,
            min_rows_per_quantile=min_rows_per_quantile, previous_quantile_members=previous_quantile_members,
        )
        ic_rows.extend(period_ic)
        quantile_rows.extend(period_quantiles)
        turnover_rows.extend(period_turnover)
    return summarize(ic_rows, quantile_rows, turnover_rows, skipped=skipped, mode=mode)
