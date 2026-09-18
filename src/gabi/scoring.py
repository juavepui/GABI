"""Normaliza métricas por percentil dentro del universo y combina bloques de
score (Value / Quality / Momentum) en un score compuesto configurable."""
import numpy as np
import pandas as pd

VALUE_METRICS_LOWER_BETTER = ["pe", "peg", "pb", "ps", "ev_ebitda"]
QUALITY_METRICS_HIGHER_BETTER = [
    "roe", "roa", "roic", "operating_margin", "gross_margin", "profit_margin",
    "revenue_growth_yoy", "earnings_growth_yoy", "revenue_growth_ttm_yoy",
    "revenue_cagr_3y", "fcf_cagr_3y", "current_ratio",
]
MOMENTUM_METRICS_HIGHER_BETTER = [
    "price_vs_sma50", "price_vs_sma200", "momentum_6m", "momentum_12m", "rel_strength_6m",
]
# Deuda, volatilidad y drawdown viven en Risk, no en Quality: cuánta deuda
# lleva o cuánto se mueve una empresa es un rasgo de riesgo, no de calidad
# del negocio en sí.
RISK_METRICS_LOWER_BETTER = ["debt_to_equity", "volatility"]
RISK_METRICS_HIGHER_BETTER = ["max_drawdown", "sharpe_ratio", "sortino_ratio"]

DEFAULT_WEIGHTS = {"value": 0.30, "quality": 0.35, "momentum": 0.25, "risk": 0.10}

# Nº mínimo de empresas del mismo sector con dato para esa métrica antes de
# fiarse del percentil sectorial. Por debajo de esto (típico en universos de
# prueba pequeños) una sola empresa "gana" su sector por defecto, lo que
# produce puntuaciones artificialmente perfectas o pésimas.
DEFAULT_MIN_SECTOR_GROUP = 8
MIN_SCORE_COVERAGE = 0.50

# Una métrica representativa por cada familia de métricas muy correlacionadas
# (ej. los 5 múltiplos de Value no deben votar 5 veces). El resto de métricas
# siguen visibles en el detalle de cada empresa, pero no puntúan aparte.
SCORE_METRICS = {
    "value": ["pe", "pb", "ev_ebitda"],
    "quality": ["roic", "operating_margin", "revenue_cagr_3y", "fcf_cagr_3y"],
    "momentum": ["momentum_12m", "rel_strength_6m", "price_vs_sma200"],
    "risk": ["debt_to_equity", "volatility", "max_drawdown"],
}


def _percentile(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    ranked = series.rank(pct=True, na_option="keep")
    if not higher_is_better:
        ranked = 1 - ranked
    return ranked * 100


def _percentile_within_sector(
    df: pd.DataFrame, col: str, higher_is_better: bool, min_group_size: int,
) -> pd.Series:
    """Percentil de cada empresa dentro de su propio sector GICS, en vez de
    contra todo el universo: el EV/EBITDA de un fabricante de semiconductores
    no es comparable al de una aseguradora. Si el sector tiene muy pocas
    empresas con dato, cae de vuelta al percentil sobre todo el universo —
    igual que si el sector es directamente desconocido (NaN), típico de
    empresas ya deslistadas en un ranking histórico (screener_asof.py), para
    las que no hay fuente gratuita de sector histórico."""
    global_pct = _percentile(df[col], higher_is_better)
    if "sector" not in df.columns:
        return global_pct
    # reindex explícito: si TODAS las filas de un grupo tienen sector NaN,
    # pandas (dropna=True por defecto en groupby) devuelve una Series vacía
    # en vez de una alineada con NaN — sin este reindex, el .where() de abajo
    # compararía índices desalineados y el resultado saldría NaN para todo.
    group_sizes = df.groupby("sector")[col].transform(lambda s: s.notna().sum()).reindex(df.index)
    within_pct = df.groupby("sector")[col].transform(lambda s: _percentile(s, higher_is_better)).reindex(df.index)
    use_global = group_sizes.isna() | (group_sizes < min_group_size)
    return within_pct.where(~use_global, global_pct)


def add_percentile_columns(
    df: pd.DataFrame, metric_cols, higher_is_better=True, suffix="_pct",
    by_sector=True, min_group_size=DEFAULT_MIN_SECTOR_GROUP,
):
    df = df.copy()
    for col in metric_cols:
        if col in df.columns:
            if by_sector:
                df[col + suffix] = _percentile_within_sector(df, col, higher_is_better, min_group_size)
            else:
                df[col + suffix] = _percentile(df[col], higher_is_better=higher_is_better)
    return df


def compute_block_score(df: pd.DataFrame, pct_cols) -> pd.Series:
    available = [c for c in pct_cols if c in df.columns]
    if not available:
        return pd.Series(np.nan, index=df.index)
    return df[available].mean(axis=1, skipna=True)


def _weighted_row_mean(row_values, weights):
    mask = ~np.isnan(row_values)
    if not mask.any():
        return np.nan
    ww = weights[mask]
    if ww.sum() == 0:
        return np.nan
    return float(np.dot(row_values[mask], ww) / ww.sum())


def build_scores(df: pd.DataFrame, weights: dict = None) -> pd.DataFrame:
    """df: DataFrame indexado por símbolo con las columnas de métricas crudas
    (las listadas arriba), más opcionalmente 'sector', 'rsi14' y 'golden_cross_recent'.

    Los percentiles se calculan dentro del sector de cada empresa cuando hay
    suficientes empresas de ese sector con dato (ver DEFAULT_MIN_SECTOR_GROUP);
    si no, caen de vuelta al percentil sobre todo el universo analizado.
    """
    weights = weights or DEFAULT_WEIGHTS
    df = df.copy()

    df = add_percentile_columns(df, VALUE_METRICS_LOWER_BETTER, higher_is_better=False)
    df = add_percentile_columns(df, QUALITY_METRICS_HIGHER_BETTER, higher_is_better=True)
    df = add_percentile_columns(df, MOMENTUM_METRICS_HIGHER_BETTER, higher_is_better=True)
    df = add_percentile_columns(df, RISK_METRICS_LOWER_BETTER, higher_is_better=False)
    df = add_percentile_columns(df, RISK_METRICS_HIGHER_BETTER, higher_is_better=True)

    momentum_pct_cols = [c + "_pct" for c in SCORE_METRICS["momentum"]]
    if "rsi14" in df.columns:
        # Zona sana ~45-65: penaliza tanto sobrecompra como debilidad, no es
        # un percentil cruzado sino una distancia a la "zona dulce".
        df["rsi14_pct"] = 100 - (df["rsi14"] - 55).abs().clip(upper=55) / 55 * 100
        # El RSI se queda como diagnóstico; su "zona sana" es una heurística propia sin respaldo académico validado.

    value_pct_cols = [c + "_pct" for c in SCORE_METRICS["value"]]
    quality_pct_cols = [c + "_pct" for c in SCORE_METRICS["quality"]]
    risk_pct_cols = [c + "_pct" for c in SCORE_METRICS["risk"]]

    df["value_score"] = compute_block_score(df, value_pct_cols)
    df["quality_score"] = compute_block_score(df, quality_pct_cols)
    df["momentum_score"] = compute_block_score(df, momentum_pct_cols)
    df["risk_score"] = compute_block_score(df, risk_pct_cols)

    selected = [c for cols in SCORE_METRICS.values() for c in cols]
    df["metrics_available"] = df.reindex(columns=selected).notna().sum(axis=1)
    df["metrics_possible"] = len(selected)
    df["score_coverage"] = df["metrics_available"] / len(selected)

    w = np.array([
        weights.get("value", 0), weights.get("quality", 0),
        weights.get("momentum", 0), weights.get("risk", 0),
    ])
    block_values = df[["value_score", "quality_score", "momentum_score", "risk_score"]].to_numpy(dtype=float)
    df["composite_score"] = [
        _weighted_row_mean(row, w) for row in block_values
    ]
    core_missing = df[["value_score", "quality_score", "momentum_score"]].isna().any(axis=1)
    df.loc[(df["score_coverage"] < MIN_SCORE_COVERAGE) | core_missing, "composite_score"] = np.nan

    return df.sort_values("composite_score", ascending=False)


def compute_confidence(df: pd.DataFrame, weights: dict = None) -> pd.Series:
    """Confidence: cuánto nos podemos fiar del `composite_score` de cada
    fila -- una dimensión DISTINTA de cuánto de atractiva es la empresa
    (eso ya lo dice el score). Pensado para el caso señalado por el
    usuario: una empresa con 1 de 4 métricas de Quality en percentil 95
    obtiene `quality_score = 95` (la media de esa única métrica) exactamente
    igual que una con las 4 métricas en percentil 95 — `build_scores` no
    distingue "score alto con mucho dato detrás" de "score alto con casi
    ningún dato detrás". Esta función no cambia `build_scores` ni ningún
    score existente (V1/`HIPOTESIS_CONGELADA.md` siguen exactamente igual) —
    es aditiva: una columna nueva y opcional, pensada para mostrarse junto
    al score, no para filtrar ni reordenar el ranking.

    Por bloque: fracción de las métricas de `SCORE_METRICS[bloque]` con dato
    disponible (0.0 si el bloque entero falta, 1.0 si están todas). La
    confidence global es la media de las confidence por bloque, ponderada
    con los MISMOS pesos que el composite score (`weights`, por defecto
    `DEFAULT_WEIGHTS`) — si el bloque con más peso es el que más falta,
    Confidence cae más que si es el de menos peso. Escala 0-100, igual que
    los scores, para que sean directamente comparables en una tabla.

    Requiere llamarse DESPUÉS de `build_scores` (o de
    `add_percentile_columns`), que es quien crea las columnas `_pct` que
    esta función cuenta."""
    weights = weights or DEFAULT_WEIGHTS
    w = np.array([weights.get(b, 0) for b in SCORE_METRICS])
    if w.sum() == 0:
        return pd.Series(0.0, index=df.index)
    block_fracs = []
    for block, cols in SCORE_METRICS.items():
        pct_cols = [c + "_pct" for c in cols]
        available = [c for c in pct_cols if c in df.columns]
        if not available:
            block_fracs.append(pd.Series(0.0, index=df.index))
        else:
            block_fracs.append(df.reindex(columns=available).notna().sum(axis=1) / len(cols))
    matrix = np.column_stack([s.to_numpy(dtype=float) for s in block_fracs])
    return pd.Series(matrix @ w / w.sum() * 100, index=df.index)


def explain_row(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Devuelve una tabla larga (métrica, valor, percentil) para explicar por
    qué una empresa concreta obtuvo el score que obtuvo."""
    if symbol not in df.index:
        return pd.DataFrame(columns=["metric", "value", "percentile"])
    row = df.loc[symbol]
    all_metric_cols = (
        VALUE_METRICS_LOWER_BETTER + QUALITY_METRICS_HIGHER_BETTER
        + MOMENTUM_METRICS_HIGHER_BETTER + RISK_METRICS_LOWER_BETTER + RISK_METRICS_HIGHER_BETTER
    )
    records = []
    for col in all_metric_cols:
        if col in row.index:
            records.append({
                "metric": col,
                "value": row.get(col),
                "percentile": row.get(col + "_pct"),
            })
    if "rsi14" in row.index:
        records.append({"metric": "rsi14", "value": row.get("rsi14"), "percentile": row.get("rsi14_pct")})
    return pd.DataFrame(records)
