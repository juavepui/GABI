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

Lo que SÍ hace este módulo es capturar esa foto en cada sincronización y
guardarla con `captured_at` (la fecha real de captura -- no la del
periodo que describe): así se construye un archivo point-in-time GENUINO,
que solo empieza a existir desde la primera vez que se ejecuta.
`evaluate_estimate_revision_signal()` mide señal SOLO sobre capturas
reales ya separadas en el tiempo -- con pocas capturas acumuladas (el caso
de hoy, recién añadido) devuelve status="insufficient_data" en vez de
forzar un resultado con datos insuficientes: es el comportamiento
correcto, no un bug ni un TODO pendiente."""
import concurrent.futures as cf
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from . import factor_lab, storage
from .data_fetch import _classify_error, normalize_symbol

SCHEMA = """
CREATE TABLE IF NOT EXISTS estimate_snapshots (
    symbol TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    period TEXT NOT NULL,
    eps_avg REAL, eps_low REAL, eps_high REAL, eps_analysts INTEGER,
    eps_dispersion_pct REAL,
    revenue_avg REAL, revenue_low REAL, revenue_high REAL,
    revised_up_7d INTEGER, revised_down_7d INTEGER,
    revised_up_30d INTEGER, revised_down_30d INTEGER,
    source TEXT NOT NULL,
    PRIMARY KEY (symbol, captured_at, period)
);
"""

PERIODS = ("0q", "+1q", "0y", "+1y")
SOURCE = "Yahoo Finance (eps_trend/eps_revisions/earnings_estimate/revenue_estimate)"


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


def store_estimate_snapshot(rows: list):
    if not rows:
        return
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO estimate_snapshots "
            "(symbol, captured_at, period, eps_avg, eps_low, eps_high, eps_analysts, eps_dispersion_pct, "
            "revenue_avg, revenue_low, revenue_high, revised_up_7d, revised_down_7d, revised_up_30d, "
            "revised_down_30d, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(r["symbol"], r["captured_at"], r["period"], r["eps_avg"], r["eps_low"], r["eps_high"],
              r["eps_analysts"], r["eps_dispersion_pct"], r["revenue_avg"], r["revenue_low"], r["revenue_high"],
              r["revised_up_7d"], r["revised_down_7d"], r["revised_up_30d"], r["revised_down_30d"], r["source"])
             for r in rows],
        )
        conn.commit()


def get_estimate_history(symbol: str, period: str = "0q") -> pd.DataFrame:
    """El archivo point-in-time REAL acumulado por GABI para `symbol` --
    empieza vacío y solo crece hacia delante desde la primera sincronización."""
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        return pd.read_sql_query(
            "SELECT * FROM estimate_snapshots WHERE symbol=? AND period=? ORDER BY captured_at ASC",
            conn, params=(symbol, period),
        )


def latest_estimate_snapshot(symbol: str, period: str = "0q") -> dict | None:
    history = get_estimate_history(symbol, period=period)
    return history.iloc[-1].to_dict() if not history.empty else None


def compute_revision(history: pd.DataFrame, lookback_days: int, *, as_of: date | None = None) -> dict | None:
    """Pura: cambio del EPS medio de consenso entre la captura más reciente
    (en/antes de `as_of`) y la primera captura ANTERIOR a `as_of -
    lookback_days` -- construido SOLO con capturas reales de `history`
    (get_estimate_history), nunca con las columnas relativas de yfinance.
    None si no hay una captura lo bastante antigua todavía -- es el estado
    honesto mientras el archivo propio de GABI no tenga suficiente
    profundidad, no un error."""
    if history is None or history.empty:
        return None
    if as_of is None:
        as_of = date.today()
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


def revision_since(symbol: str, lookback_days: int, *, period: str = "0q", as_of: date | None = None) -> dict | None:
    return compute_revision(get_estimate_history(symbol, period=period), lookback_days, as_of=as_of)


def _fetch_estimate_snapshot_attempt(symbol: str) -> dict:
    t_symbol = normalize_symbol(symbol)
    import yfinance as yf
    t = yf.Ticker(t_symbol)
    return {
        "earnings_estimate": t.earnings_estimate, "revenue_estimate": t.revenue_estimate,
        "eps_revisions": t.eps_revisions,
    }


def sync_estimates(symbols: list, max_workers: int = 6, progress_cb=None) -> dict:
    """Descarga (red) earnings_estimate/revenue_estimate/eps_revisions por
    símbolo y los persiste con un ÚNICO `captured_at` compartido por toda la
    llamada -- así todas las filas de esta sincronización forman un batch
    cross-seccional genuino (mismo instante de captura), que es lo que
    evaluate_estimate_revision_signal() necesita para comparar símbolos
    entre sí de forma honesta. Manual, no forma parte de 'Actualizar
    datos' -- mismo criterio que filing_tracker/events_calendar."""
    failed: dict = {}
    total = len(symbols)
    if total == 0:
        return failed
    captured_at = datetime.now(UTC).isoformat()
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_fetch_estimate_snapshot_attempt, s): s for s in symbols}
        done = 0
        for fut in cf.as_completed(futures):
            sym = futures[fut]
            done += 1
            try:
                raw = fut.result()
                rows = parse_estimate_snapshot(
                    sym, raw["earnings_estimate"], raw["revenue_estimate"], raw["eps_revisions"], captured_at,
                )
                store_estimate_snapshot(rows)
            except Exception as exc:
                _, reason = _classify_error(exc, service="Yahoo Finance")
                failed[sym] = reason
            if progress_cb:
                progress_cb(done, total)
    return failed


def _capture_batches(period: str) -> pd.DataFrame:
    """Cada `captured_at` distinto que exista en estimate_snapshots para
    `period`, con el número de símbolos que tiene esa foto -- ninguna fecha
    aquí es inventada, son literalmente los `sync_estimates()` ya
    ejecutados en el pasado."""
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        return pd.read_sql_query(
            "SELECT captured_at, COUNT(DISTINCT symbol) AS n_symbols FROM estimate_snapshots "
            "WHERE period=? GROUP BY captured_at ORDER BY captured_at ASC", conn, params=(period,),
        )


MIN_BATCHES = 6
MIN_SPAN_DAYS = 60
MIN_SYMBOLS_PER_BATCH = 20


def evaluate_estimate_revision_signal(
    period: str = "0q", horizons_months=(1, 3), n_quantiles: int = 5,
    min_batches: int = MIN_BATCHES, min_span_days: int = MIN_SPAN_DAYS,
) -> dict:
    """Rank IC cross-seccional de `net_revision_30d` (revisiones al alza
    menos a la baja en los últimos 30 días, tal cual las da Yahoo en el
    momento de cada captura) contra el retorno FUTURO real -- SOLO sobre
    `captured_at` que de verdad se ejecutaron (_capture_batches), igual que
    factor_lab.run_factor_analysis pero sin reconstruir nada del pasado.

    Devuelve {"status": "insufficient_data", ...} si todavía no hay
    suficientes capturas separadas en el tiempo -- el estado esperado
    mientras el archivo propio de GABI es joven, no un fallo."""
    batches = _capture_batches(period)
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

    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        raw = pd.read_sql_query(
            "SELECT symbol, captured_at, revised_up_30d, revised_down_30d FROM estimate_snapshots "
            "WHERE period=? AND captured_at IN ({})".format(",".join("?" * len(usable))),
            conn, params=[period] + usable["captured_at"].tolist(),
        )
    raw["net_revision_30d"] = raw["revised_up_30d"] - raw["revised_down_30d"]
    raw = raw[raw["net_revision_30d"].notna()]

    ic_rows = []
    for captured_at, group in raw.groupby("captured_at"):
        if len(group) < n_quantiles * 4:
            continue
        as_of_ts = pd.Timestamp(captured_at).tz_localize(None)
        if as_of_ts > pd.Timestamp(date.today()):
            continue
        histories = storage.get_prices_multi(group["symbol"].tolist())
        calendar = None
        for horizon in horizons_months:
            try:
                import exchange_calendars as xcals
                calendar = calendar or xcals.get_calendar(factor_lab._CALENDAR)
                entry, exit_session = factor_lab._entry_exit_sessions(calendar, as_of_ts, horizon)
            except Exception:
                continue
            if exit_session > pd.Timestamp(date.today()):
                continue
            fwd = factor_lab._forward_returns(histories, group["symbol"], entry, exit_session)
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
