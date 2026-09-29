"""Contraste externo del backtest de GABI contra las series de factores
académicos de Kenneth French (Fama-French 5 factores + Momentum, Dartmouth
Data Library, gratis y sin API key) — la comprobación que pedía la revisión
externa: ¿el Composite de GABI aporta algo por encima de las primas de
factor ya documentadas en la literatura, o es la misma exposición conocida
con otro nombre? Se responde con una regresión: retorno_GABI = alfa +
beta·factores + error — si alfa no es distinguible de 0, no hay evidencia
de que GABI bata a una simple combinación de factores académicos."""
import io
import zipfile

import numpy as np
import pandas as pd
import requests

from . import config

FF5_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip"
MOM_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_CSV.zip"
_HEADERS = {"User-Agent": "GABI (herramienta personal de análisis, uso no comercial)"}

DEFAULT_FACTOR_COLS = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]


def _parse_monthly_csv(text: str, value_cols: list) -> pd.DataFrame:
    """Cada CSV de Kenneth French mezcla cabecera descriptiva, tabla mensual
    (fecha 'YYYYMM') y tabla anual (fecha 'YYYY') en el mismo fichero — hay
    que quedarse solo con las filas mensuales, ignorando el resto."""
    rows = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 1 + len(value_cols):
            continue
        token = parts[0]
        if len(token) != 6 or not token.isdigit():
            continue
        try:
            values = [float(p) for p in parts[1:1 + len(value_cols)]]
        except ValueError:
            continue
        rows.append((token, *values))
    if not rows:
        return pd.DataFrame(columns=value_cols)
    df = pd.DataFrame(rows, columns=["month"] + value_cols)
    df["date"] = pd.to_datetime(df["month"], format="%Y%m")
    return df.set_index("date")[value_cols] / 100  # el CSV viene en % (ej. 1.23 = 1.23%)


def _download_zip_csv(url: str) -> str:
    resp = requests.get(url, timeout=30, headers=_HEADERS)
    resp.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    with z.open(z.namelist()[0]) as f:
        return f.read().decode("utf-8", errors="replace")


def fetch_ff_factors(force_refresh: bool = False) -> pd.DataFrame:
    """Mkt-RF, SMB, HML, RMW, CMA, Mom, RF mensuales, como fracción (no %).
    Cacheado en disco — Kenneth French actualiza esto mensualmente, no hace
    falta volver a descargar en cada arranque de la app."""
    cache_path = config.DATA_DIR / "ff_factors.csv"
    if not force_refresh and cache_path.exists():
        return pd.read_csv(cache_path, index_col=0, parse_dates=True)

    five = _parse_monthly_csv(_download_zip_csv(FF5_URL), ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"])
    mom = _parse_monthly_csv(_download_zip_csv(MOM_URL), ["Mom"])
    merged = five.join(mom, how="inner")

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(cache_path)
    return merged


def quarterly_period_return(factors: pd.DataFrame, column: str, start: str, end: str):
    """Retorno compuesto de un factor entre dos fechas — mismo criterio de
    ventana (mes de inicio incluido, mes de fin excluido) para poder alinear
    exactamente con los periodos que usa multifactor_backtest.run()."""
    if column not in factors.columns:
        return None
    start_ts, end_ts = pd.Timestamp(start).replace(day=1), pd.Timestamp(end).replace(day=1)
    window = factors.loc[(factors.index >= start_ts) & (factors.index < end_ts), column]
    if window.empty:
        return None
    return float((1 + window).prod() - 1)


def _ols(y: np.ndarray, X: np.ndarray, names: list, *, hac_lags: int | None = None) -> dict:
    """Coeficientes OLS con inferencia HAC/Newey-West (Bartlett).

    Las filas deben estar ordenadas y equiespaciadas. Por defecto se usan
    floor(4*(n/100)**(2/9)) retardos y corrección de muestra pequeña n/(n-k),
    como statsmodels.stats.sandwich_covariance.cov_hac(use_correction=True).
    Un retardo es un periodo de la regresión, no un mes; 0 equivale a HC1.
    `se`/`t_stat` son HAC; los homocedásticos quedan en `se_ols`/`t_stat_ols`
    solo como diagnóstico. HAC no garantiza errores mayores que OLS.
    """
    n, k = X.shape
    if n <= k or not np.isfinite(X).all() or not np.isfinite(y).all():
        raise ValueError("La regresión requiere datos finitos y más observaciones que coeficientes.")
    if hac_lags is None:
        hac_lags = min(int(np.floor(4 * (n / 100) ** (2 / 9))), n - 1)
    if isinstance(hac_lags, (bool, np.bool_)) or not isinstance(hac_lags, (int, np.integer)) or not 0 <= hac_lags < n:
        raise ValueError(f"hac_lags debe ser un entero entre 0 y {n - 1}.")
    hac_lags = int(hac_lags)
    beta, _, rank, _ = np.linalg.lstsq(X, y, rcond=None)
    if rank < k:
        raise ValueError("La matriz de factores no tiene rango completo; no se puede interpretar la inferencia.")
    resid = y - X @ beta
    sse = float(resid @ resid)
    dof = n - k
    sigma2 = sse / dof
    x_pinv = np.linalg.pinv(X)
    xtx_inv = x_pinv @ x_pinv.T
    se_ols = np.sqrt(np.maximum(np.diag(sigma2 * xtx_inv), 0))
    scores = X * resid[:, None]
    meat = scores.T @ scores
    for lag in range(1, hac_lags + 1):
        cross = scores[lag:].T @ scores[:-lag]
        meat += (1 - lag / (hac_lags + 1)) * (cross + cross.T)
    covariance = (n / dof) * (xtx_inv @ meat @ xtx_inv)
    se = np.sqrt(np.maximum(np.diag(covariance), 0))
    t_stat = np.divide(beta, se, out=np.full_like(beta, np.nan), where=se > 0)
    t_stat_ols = np.divide(beta, se_ols, out=np.full_like(beta, np.nan), where=se_ols > 0)
    sst = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - sse / sst if sst > 0 else None
    return {
        "n_obs": n, "dof": dof, "r2": r2,
        "coef": dict(zip(names, beta.tolist())),
        "se": dict(zip(names, se.tolist())),
        "t_stat": dict(zip(names, t_stat.tolist())),
        "se_ols": dict(zip(names, se_ols.tolist())),
        "t_stat_ols": dict(zip(names, t_stat_ols.tolist())),
        "cov_type": "HAC", "hac_lags": hac_lags, "hac_kernel": "bartlett",
        "hac_small_sample_correction": True,
    }


def regress_returns_on_factors(period_returns: pd.DataFrame, factors: pd.DataFrame,
                               factor_cols: list = None, *, hac_lags: int | None = None) -> dict:
    """period_returns: DataFrame con columnas ['fecha','hasta','retorno'] —
    el mismo formato que devuelve multifactor_backtest.run()['periods'].
    Alinea cada periodo de GABI con el retorno compuesto de cada factor
    académico en su ventana mensual (inicio incluido, fin excluido), y regresiona:

        retorno_GABI − RF = alfa + Σ(beta_i · factor_i) + error

    `alfa` (por periodo, anualizado también en el resultado) es lo que GABI
    aporta por encima de las exposiciones a factores ya documentadas — si no
    es distinguible de 0 (t-stat bajo), no hay evidencia de que el Composite
    bata a una simple combinación de primas de factor académicas conocidas.

    La inferencia es HAC/Newey-West; `hac_lags` permite fijar el máximo
    retardo en periodos (None: regla automática, 3 para 36 observaciones).
    Ordena por fecha y exige ventanas mensuales consecutivas de igual duración:
    saltarse un periodo interior no puede convertirlo en un vecino temporal.
    La alineación mensual es una aproximación a las fechas bursátiles de V1.
    Con ~30-40 trimestres y 6 factores, incluso HAC tiene poca potencia y
    no proporciona una prueba concluyente ni corrige el multiple testing."""
    factor_cols = factor_cols or DEFAULT_FACTOR_COLS
    rows = []
    for _, row in period_returns.iterrows():
        factor_rets = {c: quarterly_period_return(factors, c, row["fecha"], row["hasta"]) for c in factor_cols}
        if any(v is None for v in factor_rets.values()):
            continue
        rf = quarterly_period_return(factors, "RF", row["fecha"], row["hasta"]) or 0.0
        rows.append({"fecha": pd.Timestamp(row["fecha"]), "hasta": pd.Timestamp(row["hasta"]),
                     "y": row["retorno"] - rf, **factor_rets})
    aligned = pd.DataFrame(rows)
    if len(aligned) < len(factor_cols) + 2:
        raise ValueError(f"Solo {len(aligned)} periodos con datos de factor académico alineados — "
                         f"insuficientes para una regresión con {len(factor_cols)} factores.")

    aligned = aligned.sort_values("fecha")
    starts = pd.PeriodIndex(aligned["fecha"], freq="M").asi8
    ends = pd.PeriodIndex(aligned["hasta"], freq="M").asi8
    months = int(ends[0] - starts[0])
    if months <= 0 or not np.all(ends - starts == months) or not np.all(starts[1:] == ends[:-1]):
        raise ValueError("HAC requiere periodos consecutivos de igual duración, sin huecos ni solapamientos.")
    y = aligned["y"].to_numpy()
    X = np.column_stack([np.ones(len(aligned))] + [aligned[c].to_numpy() for c in factor_cols])
    result = _ols(y, X, ["alpha"] + factor_cols, hac_lags=hac_lags)
    result["periods_per_year"] = 12 / months
    result["alpha_anualizado"] = (1 + result["coef"]["alpha"]) ** result["periods_per_year"] - 1
    result["periodos_alineados"] = len(aligned)
    result["periodos_totales"] = len(period_returns)
    return result
