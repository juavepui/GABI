"""Factor Lab calculations over explicit rankings, sessions and price windows."""
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

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


def analyze_period(eligible: pd.DataFrame, histories: dict, as_of: pd.Timestamp, *, calendar,
                   today: date, factor_cols=DEFAULT_FACTOR_COLS, horizons_months=DEFAULT_HORIZONS,
                   n_quantiles: int = 5, min_rows_per_quantile: int = _MIN_ROWS_PER_QUANTILE,
                   previous_quantile_members: dict | None = None) -> tuple[list, list, list, dict]:
    previous_quantile_members = dict(previous_quantile_members or {})
    ic_rows, quantile_rows, turnover_rows = [], [], []
    as_of_str = as_of.date().isoformat()
    sectors = eligible["sector"] if "sector" in eligible.columns else pd.Series(dtype=object)

    for factor in factor_cols:
        if factor not in eligible.columns:
            continue
        factor_df = eligible[[factor]].copy()
        factor_df["sector"] = sectors if not sectors.empty else np.nan
        factor_df = factor_df[factor_df[factor].notna()]
        if len(factor_df) < n_quantiles * min_rows_per_quantile:
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
            if exit_session > pd.Timestamp(today):
                continue
            fwd = _forward_returns(histories, factor_df.index, entry, exit_session)
            if len(fwd) < n_quantiles * min_rows_per_quantile:
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

    return ic_rows, quantile_rows, turnover_rows, previous_quantile_members


def summarize(ic_rows: list, quantile_rows: list, turnover_rows: list, *, skipped: list, mode: str) -> dict:
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
