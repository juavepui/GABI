"""Métricas de cartera sobre curvas NAV diarias alineadas (estrategia vs
benchmark) — completa lo que ni risk.py (pensado para una sola empresa) ni
multifactor_backtest.daily_risk_metrics (CAGR/vol/Sharpe/Sortino/max
drawdown, que no se duplican aquí) tienen: Calmar, tiempo de recuperación,
beta, tracking error, Information Ratio, capture ratios y Sharpe rodante.

Opera sobre pd.Series genéricas (curva NAV o retornos diarios), no depende
de portfolio_backtest.py ni de ningún formato propio — reutilizable donde
haga falta comparar dos curvas de capital (ej. Carteras Simuladas)."""
import numpy as np
import pandas as pd

from . import config

TRADING_DAYS_PER_YEAR = 252


def calmar_ratio(cagr: float, max_drawdown: float):
    """CAGR / |máximo drawdown|. None si no hay drawdown (división por cero
    no tiene una respuesta razonable: "riesgo cero" no es 0, es indefinido)."""
    if cagr is None or max_drawdown is None or max_drawdown == 0:
        return None
    return float(cagr / abs(max_drawdown))


def recovery_time(curve: pd.Series):
    """Días de calendario desde el pico previo al máximo drawdown hasta que
    la curva vuelve a superar ese pico. None si no hay drawdown real, o si
    la curva no se ha recuperado todavía dentro del rango disponible (no se
    puede saber cuánto habría tardado)."""
    if curve is None or curve.empty:
        return None
    running_max = curve.cummax()
    drawdown = curve / running_max - 1
    trough_idx = drawdown.idxmin()
    if pd.isna(trough_idx) or drawdown.loc[trough_idx] == 0:
        return None
    pre_trough_dd = drawdown.loc[:trough_idx]
    at_peak = pre_trough_dd[pre_trough_dd == 0]
    peak_date = at_peak.index[-1] if not at_peak.empty else curve.index[0]
    peak_value = curve.loc[peak_date]
    recovered = curve.loc[trough_idx:][curve.loc[trough_idx:] >= peak_value]
    if recovered.empty:
        return None
    return int((recovered.index[0] - peak_date).days)


def beta_vs_benchmark(returns: pd.Series, bench_returns: pd.Series):
    """cov/var sobre retornos diarios alineados — misma fórmula que
    risk.py::_beta_vs_benchmark, generalizada para no depender de un
    DataFrame de precios de una sola empresa. Requiere >=30 observaciones
    alineadas (mismo umbral que risk.py, para que un tramo corto no dé un
    beta espurio)."""
    aligned = pd.concat([returns, bench_returns], axis=1, join="inner").dropna()
    if len(aligned) < 30:
        return None
    r, b = aligned.iloc[:, 0], aligned.iloc[:, 1]
    bench_var = b.var()
    if not bench_var:
        return None
    return float(r.cov(b) / bench_var)


def tracking_error(returns: pd.Series, bench_returns: pd.Series):
    """Desviación estándar anualizada de (retorno estrategia - retorno
    benchmark)."""
    aligned = pd.concat([returns, bench_returns], axis=1, join="inner").dropna()
    if len(aligned) < 2:
        return None
    diff = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    return float(diff.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def information_ratio(returns: pd.Series, bench_returns: pd.Series):
    """Exceso de retorno anualizado medio / tracking error."""
    aligned = pd.concat([returns, bench_returns], axis=1, join="inner").dropna()
    if len(aligned) < 2:
        return None
    diff = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    te = float(diff.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
    # Umbral, no cero exacto: incluso una serie "constante" rara vez da una
    # std exactamente 0.0 por redondeo de punto flotante (comprobado con
    # datos reales de test) -- comparar contra 0 exacto deja pasar un IR
    # absurdamente inflado en vez de reconocer que no hay tracking error real.
    if te < 1e-9:
        return None
    ann_excess = float(diff.mean() * TRADING_DAYS_PER_YEAR)
    return ann_excess / te


def capture_ratios(returns: pd.Series, bench_returns: pd.Series) -> dict:
    """Upside/downside capture sobre retornos MENSUALES (convención
    estándar, más estable que a diario): cuánto se mueve la estrategia en
    promedio, como fracción del movimiento del benchmark, separando meses
    en los que el benchmark sube de meses en los que baja. 1.0 = se mueve
    exactamente igual; >1.0 en upside y <1.0 en downside sería lo ideal
    (participa más de las subidas que de las bajadas)."""
    aligned = pd.concat([returns, bench_returns], axis=1, join="inner").dropna()
    if aligned.empty:
        return {"upside": None, "downside": None}
    monthly = (1 + aligned).resample("ME").prod() - 1
    strat_m, bench_m = monthly.iloc[:, 0], monthly.iloc[:, 1]
    up, down = bench_m > 0, bench_m < 0
    upside = (float(strat_m[up].mean() / bench_m[up].mean())
              if up.any() and bench_m[up].mean() else None)
    downside = (float(strat_m[down].mean() / bench_m[down].mean())
                if down.any() and bench_m[down].mean() else None)
    return {"upside": upside, "downside": downside}


def rolling_sharpe(returns: pd.Series, window: int = TRADING_DAYS_PER_YEAR,
                   risk_free_rate: float = None) -> pd.Series:
    """Sharpe con ventana móvil de `window` sesiones (por defecto ~1 año) —
    para inspeccionar/graficar cómo varía en el tiempo, no un único número
    resumen. Serie vacía si no hay suficientes observaciones."""
    if risk_free_rate is None:
        risk_free_rate = config.RISK_FREE_RATE
    if returns is None or returns.empty or len(returns) < window:
        return pd.Series(dtype=float)
    daily_rf = (1 + risk_free_rate) ** (1 / TRADING_DAYS_PER_YEAR) - 1
    roll_mean = (returns - daily_rf).rolling(window).mean()
    roll_std = returns.rolling(window).std(ddof=1)
    sharpe = (roll_mean * TRADING_DAYS_PER_YEAR) / (roll_std * np.sqrt(TRADING_DAYS_PER_YEAR))
    return sharpe.dropna()
