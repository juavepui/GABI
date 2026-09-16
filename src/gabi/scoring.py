"""Normaliza métricas por percentil dentro del universo y combina bloques de
score (Value / Quality / Momentum) en un score compuesto configurable."""
import numpy as np
import pandas as pd

VALUE_METRICS_LOWER_BETTER = ["pe", "peg", "pb", "ps", "ev_ebitda"]
QUALITY_METRICS_HIGHER_BETTER = [
    "roe", "roa", "operating_margin", "gross_margin", "profit_margin",
    "revenue_growth_yoy", "earnings_growth_yoy", "revenue_growth_ttm_yoy",
    "current_ratio",
]
QUALITY_METRICS_LOWER_BETTER = ["debt_to_equity"]
MOMENTUM_METRICS_HIGHER_BETTER = [
    "price_vs_sma50", "price_vs_sma200", "momentum_6m", "momentum_12m", "rel_strength_6m",
]

DEFAULT_WEIGHTS = {"value": 0.35, "quality": 0.35, "momentum": 0.30}


def _percentile(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    ranked = series.rank(pct=True, na_option="keep")
    if not higher_is_better:
        ranked = 1 - ranked
    return ranked * 100


def add_percentile_columns(df: pd.DataFrame, metric_cols, higher_is_better=True, suffix="_pct"):
    df = df.copy()
    for col in metric_cols:
        if col in df.columns:
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
    (las listadas arriba), más opcionalmente 'rsi14' y 'golden_cross_recent'.
    """
    weights = weights or DEFAULT_WEIGHTS
    df = df.copy()

    df = add_percentile_columns(df, VALUE_METRICS_LOWER_BETTER, higher_is_better=False)
    df = add_percentile_columns(df, QUALITY_METRICS_HIGHER_BETTER, higher_is_better=True)
    df = add_percentile_columns(df, QUALITY_METRICS_LOWER_BETTER, higher_is_better=False)
    df = add_percentile_columns(df, MOMENTUM_METRICS_HIGHER_BETTER, higher_is_better=True)

    momentum_pct_cols = [c + "_pct" for c in MOMENTUM_METRICS_HIGHER_BETTER]
    if "rsi14" in df.columns:
        # Zona sana ~45-65: penaliza tanto sobrecompra como debilidad, no es
        # un percentil cruzado sino una distancia a la "zona dulce".
        df["rsi14_pct"] = 100 - (df["rsi14"] - 55).abs().clip(upper=55) / 55 * 100
        momentum_pct_cols.append("rsi14_pct")

    value_pct_cols = [c + "_pct" for c in VALUE_METRICS_LOWER_BETTER]
    quality_pct_cols = [c + "_pct" for c in QUALITY_METRICS_HIGHER_BETTER + QUALITY_METRICS_LOWER_BETTER]

    df["value_score"] = compute_block_score(df, value_pct_cols)
    df["quality_score"] = compute_block_score(df, quality_pct_cols)
    df["momentum_score"] = compute_block_score(df, momentum_pct_cols)

    if "golden_cross_recent" in df.columns:
        bonus = df["golden_cross_recent"].fillna(False).astype(bool).map({True: 5.0, False: 0.0})
        df["momentum_score"] = (df["momentum_score"].fillna(0) + bonus).clip(upper=100)

    w = np.array([weights.get("value", 0), weights.get("quality", 0), weights.get("momentum", 0)])
    block_values = df[["value_score", "quality_score", "momentum_score"]].to_numpy(dtype=float)
    df["composite_score"] = [
        _weighted_row_mean(row, w) for row in block_values
    ]

    return df.sort_values("composite_score", ascending=False)


def explain_row(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Devuelve una tabla larga (métrica, valor, percentil) para explicar por
    qué una empresa concreta obtuvo el score que obtuvo."""
    if symbol not in df.index:
        return pd.DataFrame(columns=["metric", "value", "percentile"])
    row = df.loc[symbol]
    all_metric_cols = (
        VALUE_METRICS_LOWER_BETTER + QUALITY_METRICS_HIGHER_BETTER
        + QUALITY_METRICS_LOWER_BETTER + MOMENTUM_METRICS_HIGHER_BETTER
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
