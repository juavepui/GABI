"""Métricas de cartera sobre curvas NAV diarias alineadas (estrategia vs
benchmark) — completa lo que ni risk.py (pensado para una sola empresa) ni
multifactor_backtest.daily_risk_metrics (CAGR/vol/Sharpe/Sortino/max
drawdown, que no se duplican aquí) tienen: Calmar, tiempo de recuperación,
beta, tracking error, Information Ratio, capture ratios, Sharpe rodante y
riesgo de cola histórico (VaR/ES, asimetría y exceso de curtosis).

Opera sobre pd.Series genéricas (curva NAV o retornos diarios), no depende
de portfolio_backtest.py ni de ningún formato propio — reutilizable donde
haga falta comparar dos curvas de capital (ej. Carteras Simuladas)."""
from numbers import Real

import numpy as np
import pandas as pd

from . import config

TRADING_DAYS_PER_YEAR = 252


def _finite_returns(returns: pd.Series) -> np.ndarray:
    """No elimina/imputa observaciones ausentes en una distribución de pérdidas."""
    values = np.asarray(returns, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("Se requiere una serie unidimensional de retornos finitos, sin NaN ni infinitos.")
    return values


def historical_tail_risk(returns: pd.Series, confidence: float = .95) -> dict:
    """VaR y Expected Shortfall/CVaR empíricos de pérdidas L=-retorno.

    VaR es la inversa de la CDF empírica (sin interpolación). ES integra
    exactamente la masa superior 1-confidence, con peso fraccionario en la
    observación frontera, también cuando hay empates. Un resultado positivo
    es pérdida; uno negativo es ganancia (no se recorta a cero).

    Horizonte: UNA observación original, sin anualizar ni usar sqrt(t).
    `tail_mass` = n*(1-confidence), no número de eventos independientes.
    <1: cola inferior a resolución muestral; <5: cola escasa (regla de aviso,
    no test de precisión). Incluso >=5 no garantiza fiabilidad predictiva.
    """
    if isinstance(confidence, (bool, np.bool_)) or not isinstance(confidence, Real):
        raise ValueError("confidence debe estar estrictamente entre 0 y 1.")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence debe estar estrictamente entre 0 y 1.") from exc
    if not np.isfinite(confidence) or not 0 < confidence < 1:
        raise ValueError("confidence debe estar estrictamente entre 0 y 1.")
    values = _finite_returns(returns)
    n = len(values)
    mass = n * (1 - confidence)
    # Evita que 100*(1-.95)=5.000000000000004 cuente una sexta fila.
    if round(mass) > 0 and abs(mass - round(mass)) < 1e-12:
        mass = float(round(mass))
    result: dict = {"confidence": confidence, "n_obs": n, "tail_mass": mass,
              "tail_observations": int(np.ceil(mass)), "var": None, "expected_shortfall": None,
              "status": "empty" if not n else "below_resolution" if mass < 1 else "sparse" if mass < 5 else "descriptive"}
    if not n:
        return result
    losses = np.sort(-values)
    var = float(np.quantile(losses, confidence, method="inverted_cdf"))
    worst = losses[::-1]
    whole = int(np.floor(mass))
    fraction = mass - whole
    # Normaliza pesos antes de sumar, evitando sumas innecesariamente grandes.
    es = float((worst[:whole] / mass).sum())
    if fraction > 0:
        es += float(worst[whole] * (fraction / mass))
    result.update(var=var, expected_shortfall=es)
    return result


def historical_var(returns: pd.Series, confidence: float = .95) -> float | None:
    """Cuantil histórico de pérdidas de una observación; ver historical_tail_risk."""
    return historical_tail_risk(returns, confidence)["var"]


def expected_shortfall(returns: pd.Series, confidence: float = .95) -> float | None:
    """ES/CVaR histórico de una observación, con masa fraccionaria exacta."""
    return historical_tail_risk(returns, confidence)["expected_shortfall"]


def return_distribution(returns: pd.Series) -> dict:
    """Asimetría Fisher-Pearson ajustada y exceso de curtosis corregido.

    Equivalen a scipy.stats.skew(bias=False) y kurtosis(fisher=True,
    bias=False) cuando son estimables. No son momentos de pérdidas sino de
    RETORNOS: asimetría negativa indica cola izquierda. Curtosis normal=0
    (exceso); curtosis Pearson normal=3. None si n<3/n<4 o serie constante.
    La corrección de muestra finita no corrige dependencia temporal.
    """
    values = _finite_returns(returns)
    n = len(values)
    result: dict = {"n_obs": n, "skewness": None, "excess_kurtosis": None,
                    "kurtosis_convention": "Fisher excess (normal=0), finite-sample corrected"}
    if n < 2 or np.all(values == values[0]):
        return result
    # Escala previa para evitar overflow de potencias y detectar constante
    # antes de la resta (pandas devuelve cero para algunas constantes).
    scaled = values / np.max(np.abs(values))
    centered = scaled - scaled.mean()
    m2 = float(np.mean(centered ** 2))
    if m2 <= 0:
        return result
    g1 = float(np.mean(centered ** 3) / m2 ** 1.5)
    g2 = float(np.mean(centered ** 4) / m2 ** 2 - 3)
    if n >= 3:
        result["skewness"] = float(np.sqrt(n * (n - 1)) / (n - 2) * g1)
    if n >= 4:
        result["excess_kurtosis"] = float((n - 1) / ((n - 2) * (n - 3)) * ((n + 1) * g2 + 6))
    return result


def tail_risk_metrics(returns: pd.Series, *, horizon: str = "una observación") -> dict:
    """Resumen JSON serializable; el llamante declara la frecuencia real.

    No transforma retornos trimestrales en diarios ni añade un cero inicial.
    Vacío produce None en métricas; NaN/inf se rechazan explícitamente.
    """
    if not isinstance(horizon, str) or not horizon.strip():
        raise ValueError("Se requiere un horizonte explícito no vacío.")
    distribution = return_distribution(returns)
    return {**distribution, "horizon": horizon, "method": "historical empirical losses=-returns; fractional-tail ES",
            "annualized": False, "95": historical_tail_risk(returns, .95),
            "99": historical_tail_risk(returns, .99)}


def returns_from_nav(nav: pd.Series) -> pd.Series:
    """Retornos simples entre valores NAV consecutivos, sin forward-fill.

    Solo descarta la primera diferencia no definida; una NAV ausente se
    rechaza. No certifica la frecuencia del calendario. Cero se admite solo
    al final (pérdida total); un divisor cero o NAV negativo es inválido.
    """
    values = _finite_returns(nav)
    if nav.index.has_duplicates or not nav.index.is_monotonic_increasing or nav.index.hasnans:
        raise ValueError("NAV requiere fechas ordenadas, únicas y no ausentes.")
    if (values < 0).any() or (values[:-1] <= 0).any() or (len(values) == 1 and values[0] == 0):
        raise ValueError("NAV requiere capital positivo salvo una pérdida total terminal.")
    result = nav.pct_change(fill_method=None).iloc[1:]
    _finite_returns(result)
    return result


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
