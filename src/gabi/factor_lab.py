"""Factor Lab: en vez de "¿el Top-20 ganó al SPY?", ¿el score contiene
información predictiva de forma gradual y consistente? Divide el universo en
quintiles por score cada rebalanceo y mide si el retorno FUTURO real
(1/3/6/12 meses) sube con el quintil -- Rank IC (Spearman), ICIR, decay por
horizonte, spread Q5−Q1, turnover de cada quintil, y una versión
sector-neutral que aísla si el score predice ganadores DENTRO de su sector o
solo capta qué sector estuvo de moda ese periodo.

Reutiliza la misma reconstrucción point-in-time que `portfolio_backtest.py`
(`universe.get_sp500_constituents_asof` + `screener_asof.build_ranking_as_of`,
mismo contrato `mode="validation"`/`"fast_dev"`) y el mismo patrón de sesión
de entrada que `multifactor_backtest._period_returns` -- no se reinventa
nada, solo se mide algo distinto: información del score, no el resultado de
una cartera concreta (por eso el retorno futuro aquí NUNCA lleva coste)."""
from datetime import date

import exchange_calendars as xcals
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from . import multifactor_backtest as v1
from . import portfolio_backtest as v2
from . import screener_asof, storage, universe

_CALENDAR = "XNYS"

DEFAULT_FACTOR_COLS = ("value_score", "quality_score", "momentum_score", "risk_score", "composite_score")
DEFAULT_HORIZONS = (1, 3, 6, 12)

# Con menos filas que esto no tiene sentido partir en n_quantiles grupos --
# cada grupo acabaría con 1-2 empresas y el resultado sería ruido, no señal.
_MIN_ROWS_PER_QUANTILE = 4


def _entry_exit_sessions(calendar, as_of_ts: pd.Timestamp, horizon_months: int):
    signal_session = calendar.date_to_session(as_of_ts, direction="previous")
    entry = calendar.next_session(signal_session)
    exit_session = calendar.date_to_session(as_of_ts + pd.DateOffset(months=horizon_months), direction="next")
    return entry, exit_session


def _forward_returns(histories: dict, symbols, entry_session, exit_session) -> dict:
    """{symbol: retorno}, SIN coste (esto mide información del score, no una
    cartera) -- omite símbolos sin precio válido en entrada o salida."""
    returns = {}
    for symbol in symbols:
        h = histories.get(symbol, pd.DataFrame())
        if (h.empty or entry_session not in h.index or exit_session not in h.index
                or pd.isna(h.loc[entry_session, "adj_close"]) or pd.isna(h.loc[exit_session, "adj_close"])
                or h.loc[entry_session, "adj_close"] <= 0):
            continue
        returns[symbol] = float(h.loc[exit_session, "adj_close"] / h.loc[entry_session, "adj_close"] - 1)
    return returns


def _quantile_labels(scores: pd.Series, n_quantiles: int) -> pd.Series:
    """Códigos 1..k (k<=n_quantiles si hay empates que colapsan bins,
    `duplicates="drop"`) -- 1 = score más bajo, k = score más alto, mismo
    sentido que Q1 (peor) .. Q5 (mejor) del usuario."""
    codes = pd.qcut(scores, n_quantiles, labels=False, duplicates="drop")
    return codes + 1


def run_factor_analysis(
    start: str, end: str, months: int = 3, max_symbols: int | None = None, mode: str = "validation",
    factor_cols=DEFAULT_FACTOR_COLS, horizons_months=DEFAULT_HORIZONS, n_quantiles: int = 5,
    min_coverage: float = .7, min_universe_coverage: float = .5,
) -> dict:
    """Analiza si cada columna de `factor_cols` (Value/Quality/Momentum/Risk/
    Composite por defecto) ordena el retorno FUTURO real de las empresas, no
    solo si una cesta top-N ganó al índice.

    `mode`/`max_symbols`: mismo contrato que `portfolio_backtest.run()`
    (`"validation"` = universo histórico completo sin muestreo, el único
    citable como evidencia; `"fast_dev"` exige `max_symbols`, para iterar
    rápido) -- reutilizado tal cual, no reimplementado.

    Devuelve `{"summary": DataFrame, "ic_series": DataFrame, "quantile_returns": DataFrame,
    "turnover": DataFrame, "skipped": [...]}`:
    - `summary`: una fila por (factor, horizonte, sector_neutral) con
      `ic_mean`, `ic_std`, `icir`, `pct_ic_positive`, `q_spread` (Qmax−Q1),
      `n_periods`.
    - `ic_series`/`quantile_returns`: el detalle por periodo, para graficar
      decay/estabilidad.
    - `turnover`: turnover medio de cada quantil, por factor (no depende del
      horizonte -- el quantil se asigna una vez por fecha y factor, con el
      score de esa fecha)."""
    if mode not in v2.VALID_MODES:
        raise ValueError(f"mode debe ser uno de {v2.VALID_MODES}.")
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
    if start_ts >= end_ts or end_ts > pd.Timestamp(date.today()):
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
    previous_quantile_members = {}  # factor -> {quantil: set(symbols)}

    for as_of in boundaries:
        as_of_str = as_of.date().isoformat()
        try:
            membership = universe.get_sp500_constituents_asof(as_of_str)
            if not membership["is_exact"]:
                raise ValueError(membership["note"])
            symbols = v1._sample_symbols(membership["symbols"], max_symbols)
            ranked = screener_asof.build_ranking_as_of(as_of_str, symbols=symbols)["table"]
            eligible = ranked[ranked["composite_score"].notna() & (ranked["score_coverage"] >= min_coverage)]
            if len(eligible) / len(symbols) < min_universe_coverage:
                raise ValueError(f"cobertura insuficiente del universo ({len(eligible)}/{len(symbols)})")
        except (ValueError, RuntimeError) as exc:
            skipped.append({"fecha": as_of_str, "motivo": str(exc)})
            continue

        histories = storage.get_prices_multi(eligible.index.tolist())
        sectors = eligible["sector"] if "sector" in eligible.columns else pd.Series(dtype=object)

        for factor in factor_cols:
            if factor not in eligible.columns:
                continue
            factor_df = eligible[[factor]].copy()
            factor_df["sector"] = sectors if not sectors.empty else np.nan
            factor_df = factor_df[factor_df[factor].notna()]
            if len(factor_df) < n_quantiles * _MIN_ROWS_PER_QUANTILE:
                continue
            factor_df = factor_df.copy()
            factor_df["quantil"] = _quantile_labels(factor_df[factor], n_quantiles)

            current_members = {q: set(g.index) for q, g in factor_df.groupby("quantil")}
            prev_members = previous_quantile_members.get(factor, {})
            for q, members in current_members.items():
                prev = prev_members.get(q)
                if prev:
                    turnover = 1 - len(members & prev) / len(members)
                    turnover_rows.append({"factor": factor, "quantil": int(q), "fecha": as_of_str,
                                          "turnover": turnover})
            previous_quantile_members[factor] = current_members

            for horizon in horizons_months:
                entry, exit_session = _entry_exit_sessions(calendar, as_of, horizon)
                if exit_session > pd.Timestamp(date.today()):
                    continue
                fwd = _forward_returns(histories, factor_df.index, entry, exit_session)
                if len(fwd) < n_quantiles * _MIN_ROWS_PER_QUANTILE:
                    continue
                merged = factor_df.loc[factor_df.index.isin(fwd)].copy()
                merged["retorno"] = merged.index.map(fwd)
                if "sector" in merged.columns and merged["sector"].notna().any():
                    sector_mean = merged.groupby("sector")["retorno"].transform("mean")
                    merged["retorno_neutral"] = merged["retorno"] - sector_mean
                else:
                    merged["retorno_neutral"] = np.nan

                ic_raw = scipy_stats.spearmanr(merged[factor], merged["retorno"]).correlation
                # Un simbolo suelto sin sector (delistado antes de que existiera
                # entity_master.py, ver README "Paso 3") no debe tirar el periodo
                # entero -- se excluyen solo esas filas del calculo sector-neutral,
                # no todas las demas que si tienen sector valido.
                neutral_rows = merged[merged["retorno_neutral"].notna()]
                ic_neutral = (scipy_stats.spearmanr(neutral_rows[factor], neutral_rows["retorno_neutral"]).correlation
                             if len(neutral_rows) >= n_quantiles * 2 else np.nan)
                ic_rows.append({"fecha": as_of_str, "factor": factor, "horizonte": horizon,
                                "ic_raw": ic_raw, "ic_neutral": ic_neutral, "n": len(merged)})

                q_raw = merged.groupby("quantil")["retorno"].mean()
                q_neutral = merged.groupby("quantil")["retorno_neutral"].mean()
                for q in q_raw.index:
                    quantile_rows.append({"fecha": as_of_str, "factor": factor, "horizonte": horizon,
                                          "quantil": int(q), "retorno_medio": q_raw[q],
                                          "retorno_medio_neutral": q_neutral.get(q, np.nan)})

    ic_series = pd.DataFrame(ic_rows)
    quantile_returns = pd.DataFrame(quantile_rows)
    turnover = pd.DataFrame(turnover_rows)

    summary_rows = []
    if not ic_series.empty:
        for (factor, horizon), group in ic_series.groupby(["factor", "horizonte"]):
            for flavor, col in (("raw", "ic_raw"), ("sector_neutral", "ic_neutral")):
                ic_values = group[col].dropna()
                if ic_values.empty:
                    continue
                ic_mean = float(ic_values.mean())
                ic_std = float(ic_values.std(ddof=1)) if len(ic_values) > 1 else np.nan
                icir = ic_mean / ic_std if ic_std else np.nan
                q_col = "retorno_medio" if flavor == "raw" else "retorno_medio_neutral"
                q_group = quantile_returns[(quantile_returns["factor"] == factor)
                                           & (quantile_returns["horizonte"] == horizon)]
                q_spread = np.nan
                if not q_group.empty:
                    by_q = q_group.groupby("quantil")[q_col].mean()
                    if len(by_q) >= 2:
                        q_spread = float(by_q.iloc[-1] - by_q.iloc[0])
                summary_rows.append({
                    "factor": factor, "horizonte": horizon, "sector_neutral": flavor == "sector_neutral",
                    "ic_mean": ic_mean, "ic_std": ic_std, "icir": icir,
                    "pct_ic_positive": float((ic_values > 0).mean()), "q_spread": q_spread,
                    "n_periods": len(ic_values),
                })
    summary = pd.DataFrame(summary_rows)

    turnover_summary = (turnover.groupby(["factor", "quantil"])["turnover"].mean().reset_index()
                        if not turnover.empty else pd.DataFrame(columns=["factor", "quantil", "turnover"]))

    return {"summary": summary, "ic_series": ic_series, "quantile_returns": quantile_returns,
           "turnover": turnover_summary, "skipped": skipped, "mode": mode}
