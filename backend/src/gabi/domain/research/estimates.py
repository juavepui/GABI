"""Revisiones de estimaciones de consenso (EPS/revenue) y su dispersión --
nueva familia de datos de investigación, deliberadamente separada del
Composite Score hasta demostrar que aporta información incremental
(criterio explícito del objetivo que originó este módulo: "no mezclar
hasta no demostrarlo").

LIMITACIÓN DE FUENTE (documentada, no oculta -- ver docs/estimates-data.md):
Yahoo Finance (vía yfinance, sin licencia formal -- mismo uso no oficial
que el resto de datos de Yahoo en el proyecto) NO expone un archivo
histórico point-in-time de estimaciones. `Ticker.eps_trend`/`eps_revisions`/
`earnings_estimate`/`revenue_estimate` son una FOTO tomada AHORA: sus
columnas relativas ("7daysAgo", "30daysAgo"...) describen cómo cambió la
estimación *hasta hoy*, no lo que un observador habría visto en una fecha
pasada arbitraria. Por diseño, este módulo NO tiene ninguna función que
reconstruya el consenso de una fecha pasada -- hacerlo sería inventar
datos (la Nota del objetivo original: "aparcar antes que introducir un
dataset engañoso").

Lo que SÍ hace GABI es capturar esa foto en cada sincronización y
guardarla con `captured_at` (la fecha real de captura -- no la del
periodo que describe): así se construye un archivo point-in-time GENUINO,
que solo empieza a existir desde la primera vez que se ejecuta.
`evaluate_estimate_revision_signal()` mide señal SOLO sobre capturas
reales ya separadas en el tiempo -- con pocas capturas acumuladas (el caso
de hoy, recién añadido) devuelve status="insufficient_data" en vez de
forzar un resultado con datos insuficientes: es el comportamiento
correcto, no un bug ni un TODO pendiente."""
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

PERIODS = ("0q", "+1q", "0y", "+1y")
SOURCE = "Yahoo Finance (eps_trend/eps_revisions/earnings_estimate/revenue_estimate)"
MIN_BATCHES = 6
MIN_SPAN_DAYS = 60
MIN_SYMBOLS_PER_BATCH = 20


def _safe_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value) -> int | None:
    f = _safe_float(value)
    return int(f) if f is not None else None


def parse_estimate_snapshot(
    symbol: str, earnings_estimate_df: pd.DataFrame, revenue_estimate_df: pd.DataFrame,
    eps_revisions_df: pd.DataFrame, captured_at: str,
) -> list:
    """Pura: normaliza las 3 tablas ya descargadas de yfinance (o sintéticas
    con la misma forma en los tests) en una fila por periodo -- sin red ni
    base de datos. `captured_at` es el único ancla temporal fiable: no se
    usa nada de las columnas relativas de yfinance para fechar nada."""
    rows = []
    for period in PERIODS:
        eps_row = earnings_estimate_df.loc[period] if (
            earnings_estimate_df is not None and period in getattr(earnings_estimate_df, "index", [])
        ) else None
        rev_row = revenue_estimate_df.loc[period] if (
            revenue_estimate_df is not None and period in getattr(revenue_estimate_df, "index", [])
        ) else None
        rev_ok = eps_revisions_df is not None and period in getattr(eps_revisions_df, "index", [])
        revisions_row = eps_revisions_df.loc[period] if rev_ok else None

        eps_avg = _safe_float(eps_row.get("avg")) if eps_row is not None else None
        eps_low = _safe_float(eps_row.get("low")) if eps_row is not None else None
        eps_high = _safe_float(eps_row.get("high")) if eps_row is not None else None
        if eps_row is None and rev_row is None and revisions_row is None:
            continue

        dispersion = None
        if eps_avg not in (None, 0) and eps_low is not None and eps_high is not None:
            dispersion = (eps_high - eps_low) / abs(eps_avg)

        rows.append({
            "symbol": symbol, "captured_at": captured_at, "period": period,
            "eps_avg": eps_avg, "eps_low": eps_low, "eps_high": eps_high,
            "eps_analysts": _safe_int(eps_row.get("numberOfAnalysts")) if eps_row is not None else None,
            "eps_dispersion_pct": dispersion,
            "revenue_avg": _safe_float(rev_row.get("avg")) if rev_row is not None else None,
            "revenue_low": _safe_float(rev_row.get("low")) if rev_row is not None else None,
            "revenue_high": _safe_float(rev_row.get("high")) if rev_row is not None else None,
            "revised_up_7d": _safe_int(revisions_row.get("upLast7days")) if revisions_row is not None else None,
            "revised_down_7d": _safe_int(revisions_row.get("downLast7Days")) if revisions_row is not None else None,
            "revised_up_30d": _safe_int(revisions_row.get("upLast30days")) if revisions_row is not None else None,
            "revised_down_30d": _safe_int(revisions_row.get("downLast30days")) if revisions_row is not None else None,
            "source": SOURCE,
        })
    return rows


def compute_revision(history: pd.DataFrame, lookback_days: int, *, as_of: date) -> dict | None:
    """Pura: cambio del EPS medio de consenso entre la captura más reciente
    (en/antes de `as_of`) y la primera captura ANTERIOR a `as_of -
    lookback_days` -- construido SOLO con capturas reales de `history`
    (el historial de capturas de GABI), nunca con las columnas relativas de yfinance.
    None si no hay una captura lo bastante antigua todavía -- es el estado
    honesto mientras el archivo propio de GABI no tenga suficiente
    profundidad, no un error."""
    if history is None or history.empty:
        return None
    h = history.copy()
    h["captured_date"] = pd.to_datetime(h["captured_at"]).dt.date
    h = h[h["captured_date"] <= as_of]
    if h.empty:
        return None
    latest = h.iloc[-1]
    cutoff = as_of - pd.Timedelta(days=lookback_days)
    older = h[h["captured_date"] <= cutoff]
    if older.empty:
        return None
    baseline = older.iloc[-1]
    if pd.isna(latest["eps_avg"]) or pd.isna(baseline["eps_avg"]) or baseline["eps_avg"] == 0:
        return None
    change = float(latest["eps_avg"] - baseline["eps_avg"])
    return {
        "current_eps_avg": float(latest["eps_avg"]), "baseline_eps_avg": float(baseline["eps_avg"]),
        "change": change, "change_pct": change / abs(baseline["eps_avg"]),
        "baseline_captured_at": baseline["captured_at"], "current_captured_at": latest["captured_at"],
        "actual_lookback_days": (latest["captured_date"] - baseline["captured_date"]).days,
    }


def evaluate_estimate_revision_signal(
    period: str = "0q", horizons_months=(1, 3), n_quantiles: int = 5,
    min_batches: int = MIN_BATCHES, min_span_days: int = MIN_SPAN_DAYS,
    *, cutoff: date, batch_loader, snapshot_loader, price_loader, sessions, forward_returns,
) -> dict:
    """Rank IC cross-seccional de `net_revision_30d` (revisiones al alza
    menos a la baja en los últimos 30 días, tal cual las da Yahoo en el
    momento de cada captura) contra el retorno FUTURO real -- SOLO sobre
    `captured_at` que de verdad se ejecutaron (``batch_loader``), igual que
    factor_lab.run_factor_analysis pero sin reconstruir nada del pasado.

    Los lectores, el calendario (``sessions(as_of, meses) -> (entrada, salida)``) y
    los retornos (``forward_returns(precios, símbolos, entrada, salida)``) se inyectan.

    Devuelve {"status": "insufficient_data", ...} si todavía no hay
    suficientes capturas separadas en el tiempo -- el estado esperado
    mientras el archivo propio de GABI es joven, no un fallo."""
    batches = batch_loader(period)
    batches = batches[batches["captured_at"].str[:10] <= cutoff.isoformat()]
    usable = batches[batches["n_symbols"] >= MIN_SYMBOLS_PER_BATCH]
    span_days = 0
    if len(usable) >= 2:
        span_days = (pd.Timestamp(usable["captured_at"].iloc[-1]) - pd.Timestamp(usable["captured_at"].iloc[0])).days
    if len(usable) < min_batches or span_days < min_span_days:
        return {
            "status": "insufficient_data", "batches_available": int(len(usable)), "span_days": int(span_days),
            "batches_needed": min_batches, "span_days_needed": min_span_days,
            "reason": (
                f"Solo hay {len(usable)} capturas con >= {MIN_SYMBOLS_PER_BATCH} símbolos (span de {span_days} "
                f"días) -- hacen falta {min_batches} capturas y {min_span_days} días de margen para medir señal "
                "sin ruido. Esto crece solo con el tiempo, sincronizando estimaciones periódicamente."
            ),
        }

    raw = snapshot_loader(period, usable["captured_at"].tolist())
    raw["net_revision_30d"] = raw["revised_up_30d"] - raw["revised_down_30d"]
    raw = raw[raw["net_revision_30d"].notna()]

    ic_rows = []
    for captured_at, group in raw.groupby("captured_at"):
        if len(group) < n_quantiles * 4:
            continue
        # Captures have a real wall-clock time; the exchange calendar expects a session date.
        as_of_ts = pd.Timestamp(captured_at).tz_localize(None).normalize()
        if as_of_ts > pd.Timestamp(cutoff):
            continue
        windows = []
        for horizon in horizons_months:
            try:
                entry, exit_session = sessions(as_of_ts, horizon)
            except Exception:
                continue
            if exit_session > pd.Timestamp(cutoff):
                continue
            windows.append((horizon, entry, exit_session))
        if not windows:
            continue
        first = min(entry for _, entry, _ in windows).date().isoformat()
        last = max(exit_session for _, _, exit_session in windows).date().isoformat()
        histories = price_loader(group["symbol"].tolist(), first, last)
        for horizon, entry, exit_session in windows:
            fwd = forward_returns(histories, group["symbol"], entry, exit_session)
            if len(fwd) < n_quantiles * 4:
                continue
            merged = group.set_index("symbol").loc[group.set_index("symbol").index.isin(fwd)].copy()
            merged["retorno"] = merged.index.map(fwd)
            ic = scipy_stats.spearmanr(merged["net_revision_30d"], merged["retorno"]).correlation
            ic_rows.append({"captured_at": captured_at, "horizonte": horizon, "ic": ic, "n": len(merged)})

    ic_series = pd.DataFrame(ic_rows)
    if ic_series.empty:
        return {
            "status": "insufficient_data", "batches_available": int(len(usable)), "span_days": int(span_days),
            "batches_needed": min_batches, "span_days_needed": min_span_days,
            "reason": "Hay capturas suficientes pero ninguna con horizonte ya cumplido y precios "
                     "disponibles -- vuelve a intentarlo cuando haya pasado el primer horizonte.",
        }
    summary_rows = []
    for horizon, group in ic_series.groupby("horizonte"):
        ic_values = group["ic"].dropna()
        if ic_values.empty:
            continue
        ic_mean = float(ic_values.mean())
        ic_std = float(ic_values.std(ddof=1)) if len(ic_values) > 1 else np.nan
        summary_rows.append({
            "horizonte": horizon, "ic_mean": ic_mean, "ic_std": ic_std,
            "icir": ic_mean / ic_std if ic_std else np.nan,
            "pct_ic_positive": float((ic_values > 0).mean()), "n_periods": len(ic_values),
        })
    return {
        "status": "ok", "summary": pd.DataFrame(summary_rows), "ic_series": ic_series,
        "batches_available": int(len(usable)), "span_days": int(span_days),
    }
