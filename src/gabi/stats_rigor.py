"""Rigor estadístico para no confundir ruido de muestreo con una estrategia
mejor cuando se han probado varias configuraciones sobre el mismo histórico
-- exactamente el problema que `HIPOTESIS_CONGELADA.md` reconoce ("10+
configuraciones distintas comparadas sobre el mismo rango 2016-2025... eso es
*data snooping* por diseño") y que `multifactor_backtest.sharpe_standard_error`
ya empezó a abordar con una aproximación normal simple.

Fórmulas de Bailey & López de Prado:
- "The Sharpe Ratio Efficient Frontier" (2012) -- Probabilistic Sharpe Ratio.
- "The Probability of Backtest Overfitting" (Bailey, Borwein, López de Prado,
  Zhu, 2015/2017) -- Deflated Sharpe Ratio y PBO/CSCV.
Umbral t>3 para factores nuevos: Harvey, Liu & Zhu (2016), ya citado en
`HIPOTESIS_CONGELADA.md`.

**Convención de unidades, importante**: la fórmula real de PSR opera sobre el
Sharpe estimado a partir de exactamente `n` observaciones A ESA frecuencia --
no sobre un Sharpe anualizado combinado con una `n` de otra frecuencia. El
resto de GABI reporta Sharpe siempre ANUALIZADO (la convención más legible),
así que las funciones `*_annualized` de este módulo hacen esa conversión por
ti (`sharpe_periodo = sharpe_anualizado / sqrt(periods_per_year)`) antes de
aplicar la fórmula -- documentado en cada una, para no colar un error de
escala silencioso."""
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats

EULER_MASCHERONI = 0.5772156649015329


def probabilistic_sharpe_ratio(sharpe: float, n: int, skew: float = 0.0,
                               kurtosis: float = 3.0, benchmark_sharpe: float = 0.0) -> float:
    """PSR(SR*) = Φ( (SR - SR*) · √(n-1) / √(1 - skew·SR + (kurtosis-1)/4 · SR²) ).

    `sharpe`/`n`/`benchmark_sharpe` deben ser coherentes entre sí (mismo
    periodo/frecuencia que las `n` observaciones) -- usa
    `probabilistic_sharpe_ratio_annualized` si tienes un Sharpe anualizado.
    `kurtosis` en convención NO excedente (normal = 3, no 0 -- cuidado si
    mezclas con `scipy.stats.kurtosis`, que por defecto da la excedente).
    Con skew=0/kurtosis=3 (retornos normales) se reduce exactamente a
    `Φ((SR-SR*)·√(n-1) / √(1+0.5·SR²))`, la misma aproximación que ya usa
    `multifactor_backtest.sharpe_standard_error` -- comprobado con un test
    cruzado entre los dos módulos."""
    if n <= 1:
        raise ValueError("n debe ser mayor que 1.")
    denom = 1 - skew * sharpe + (kurtosis - 1) / 4 * sharpe ** 2
    if denom <= 0:
        raise ValueError("Combinación de skew/kurtosis/sharpe no válida (denominador <= 0).")
    z = (sharpe - benchmark_sharpe) * np.sqrt(n - 1) / np.sqrt(denom)
    return float(stats.norm.cdf(z))


def probabilistic_sharpe_ratio_annualized(annualized_sharpe: float, n: int, periods_per_year: float,
                                          skew: float = 0.0, kurtosis: float = 3.0,
                                          benchmark_sharpe: float = 0.0) -> float:
    """Como `probabilistic_sharpe_ratio`, pero recibiendo el Sharpe (y el
    benchmark) en la convención ANUALIZADA que usa el resto de GABI --
    convierte a nivel de periodo internamente antes de aplicar la fórmula."""
    period_sharpe = annualized_sharpe / np.sqrt(periods_per_year)
    period_benchmark = benchmark_sharpe / np.sqrt(periods_per_year)
    return probabilistic_sharpe_ratio(period_sharpe, n, skew, kurtosis, period_benchmark)


def probabilistic_sharpe_ratio_from_returns(returns: pd.Series, periods_per_year: float,
                                            risk_free_rate: float = 0.0,
                                            benchmark_sharpe: float = 0.0) -> dict:
    """PSR EXACTO (no aproximación normal) a partir de una serie de retornos
    real: calcula Sharpe anualizado, skew y kurtosis reales de esa serie
    (`scipy.stats.kurtosis(..., fisher=False)` -- convención NO excedente,
    para que encaje con `probabilistic_sharpe_ratio`) y `n` = nº de
    observaciones. Solo posible cuando se guardó la serie de retornos
    completa del experimento (`returns_json` en `research_lab.py`) -- para
    experimentos que solo tienen el Sharpe resumen, usa
    `probabilistic_sharpe_ratio_annualized` con skew=0/kurtosis=3 como
    aproximación."""
    returns = returns.dropna()
    n = len(returns)
    if n <= 1:
        raise ValueError("Hacen falta al menos 2 observaciones.")
    period_rf = (1 + risk_free_rate) ** (1 / periods_per_year) - 1
    excess = returns - period_rf
    period_sharpe = float(excess.mean() / excess.std(ddof=1)) if excess.std(ddof=1) else 0.0
    annualized_sharpe = period_sharpe * np.sqrt(periods_per_year)
    skew = float(stats.skew(returns))
    kurtosis = float(stats.kurtosis(returns, fisher=False))
    psr = probabilistic_sharpe_ratio(period_sharpe, n, skew, kurtosis, benchmark_sharpe / np.sqrt(periods_per_year))
    return {"psr": psr, "sharpe_anualizado": annualized_sharpe, "skew": skew, "kurtosis": kurtosis, "n": n}


def expected_max_sharpe(trial_sharpes: list) -> float:
    """SR*₀: el Sharpe MÁXIMO esperado por puro azar entre N intentos SIN
    ninguna ventaja real, a partir de la varianza de los Sharpe de esos N
    intentos (fórmula de valores extremos). `trial_sharpes` puede estar en
    cualquier unidad consistente (anualizada o por periodo) -- el resultado
    queda en esa misma unidad. Exige N >= 2 (no se puede estimar varianza
    entre intentos con un único intento)."""
    n = len(trial_sharpes)
    if n < 2:
        raise ValueError("Hacen falta al menos 2 intentos para estimar la varianza entre ellos.")
    variance = float(np.var(trial_sharpes, ddof=1))
    if variance <= 0:
        return float(np.mean(trial_sharpes))
    gamma = EULER_MASCHERONI
    z1 = stats.norm.ppf(1 - 1 / n)
    z2 = stats.norm.ppf(1 - 1 / (n * np.e))
    return float(np.sqrt(variance) * ((1 - gamma) * z1 + gamma * z2))


def deflated_sharpe_ratio(selected_sharpe: float, trial_sharpes: list, n_obs: int,
                          periods_per_year: float, skew: float = 0.0, kurtosis: float = 3.0) -> dict:
    """DSR: el PSR del Sharpe seleccionado usando como listón de comparación
    el Sharpe máximo esperable por azar entre los `trial_sharpes`
    (`expected_max_sharpe`) en vez de 0 -- corrige por *multiple testing*:
    cuantas más configuraciones se prueban, más alto sale ese listón por
    pura casualidad, y un Sharpe que parecía "claramente positivo" contra 0
    puede no serlo tanto contra "el mejor de N intentos aleatorios".

    `selected_sharpe`/`trial_sharpes` en Sharpe ANUALIZADO (la convención
    del resto de GABI) -- `n_obs`/`periods_per_year` son los del experimento
    SELECCIONADO (los que definen su propia distribución muestral).

    **Aproximación práctica** cuando los intentos mezclan frecuencias de
    rebalanceo distintas (ej. trimestral vs anual, con distinta `n` cada
    uno): se trabaja en Sharpe anualizado como unidad común en vez de
    armonizar cada intento a su propia `n` -- una simplificación habitual en
    la práctica, no el tratamiento exacto de la fórmula original (que asume
    una única frecuencia común para toda la familia de intentos). Para un
    tratamiento exacto, compara solo experimentos de la misma frecuencia, o
    usa `pbo_cscv` sobre curvas diarias, que sí da una rejilla temporal
    común real entre frecuencias distintas."""
    sr0 = expected_max_sharpe(trial_sharpes)
    dsr = probabilistic_sharpe_ratio_annualized(selected_sharpe, n_obs, periods_per_year,
                                                skew, kurtosis, benchmark_sharpe=sr0)
    return {"dsr": dsr, "sr0_benchmark": sr0, "n_trials": len(trial_sharpes), "selected_sharpe": selected_sharpe}


def bootstrap_sharpe_ci(returns: pd.Series, periods_per_year: float, risk_free_rate: float = 0.0,
                        n_boot: int = 2000, block_size: int = None, ci: float = 0.95,
                        seed: int = None) -> dict:
    """Intervalo de confianza del Sharpe anualizado por bootstrap circular
    por bloques (preserva autocorrelación de una serie temporal real, a
    diferencia de remuestrear cada observación de forma independiente).
    `block_size` por defecto ~√n. Más robusto que la aproximación normal de
    `sharpe_standard_error`/`probabilistic_sharpe_ratio`, a costa de no dar
    una fórmula cerrada."""
    returns = returns.dropna()
    n = len(returns)
    if n < 30:
        raise ValueError("Hacen falta al menos 30 observaciones para un bootstrap razonable.")
    if block_size is None:
        block_size = max(2, int(round(np.sqrt(n))))
    rng = np.random.default_rng(seed)
    values = returns.to_numpy()
    period_rf = (1 + risk_free_rate) ** (1 / periods_per_year) - 1
    sharpes = []
    for _ in range(n_boot):
        sample = np.empty(0)
        while len(sample) < n:
            start = rng.integers(0, n)
            idx = (np.arange(start, start + block_size) % n)
            sample = np.concatenate([sample, values[idx]])
        sample = sample[:n]
        vol = sample.std(ddof=1)
        if not vol:
            continue
        sharpes.append(float((sample.mean() - period_rf) / vol * np.sqrt(periods_per_year)))
    sharpes = np.array(sharpes)
    alpha = 1 - ci
    lower, upper = np.percentile(sharpes, [alpha / 2 * 100, (1 - alpha / 2) * 100])
    return {"point_estimate": float(np.mean(sharpes)), "lower": float(lower), "upper": float(upper),
            "ci": ci, "n_boot": len(sharpes)}


def _default_metric(series: pd.Series) -> float:
    std = series.std(ddof=1)
    return float(series.mean() / std) if std else -np.inf


def pbo_cscv(returns_matrix: pd.DataFrame, n_splits: int = 16, metric=None) -> dict:
    """PBO (Probability of Backtest Overfitting) vía CSCV (Combinatorially
    Symmetric Cross-Validation, Bailey/Borwein/López de Prado/Zhu 2015).

    `returns_matrix`: filas = fechas (rejilla temporal COMÚN a todas las
    variantes -- usa retornos DIARIOS, ej. `nav_curve.pct_change()` de varios
    experimentos V2 sobre el mismo rango, no retornos por periodo de
    rebalanceo, que difieren en `n` entre frecuencias distintas), columnas =
    variantes/estrategias a comparar. `metric` por defecto: Sharpe simple
    (media/desviación) sin anualizar -- no importa la escala para el PBO
    (es un ranking relativo entre columnas, no un valor absoluto).

    Divide las fechas en `n_splits` bloques contiguos (por defecto 16,
    convención habitual en la literatura); para cada una de las C(n_splits,
    n_splits/2) formas de elegir la mitad como in-sample (IS) y la otra
    mitad como out-of-sample (OOS): encuentra la variante con MEJOR
    rendimiento IS, mira en qué percentil de rendimiento OOS queda esa misma
    variante. PBO = fracción de combinaciones en las que la mejor-IS queda
    por DEBAJO de la mediana OOS -- si elegir "la mejor" dentro de muestra no
    aporta nada fuera de muestra, la elección era ruido, no señal."""
    if metric is None:
        metric = _default_metric
    if n_splits % 2 != 0:
        raise ValueError("n_splits debe ser par.")
    clean = returns_matrix.dropna(how="any")
    t, n_strategies = clean.shape
    if n_strategies < 2:
        raise ValueError("Hacen falta al menos 2 variantes para comparar.")
    if t < n_splits:
        raise ValueError("No hay suficientes observaciones para tantos bloques.")
    chunks = np.array_split(np.arange(t), n_splits)
    logits = []
    for is_combo in combinations(range(n_splits), n_splits // 2):
        is_rows = np.concatenate([chunks[i] for i in is_combo])
        oos_combo = [i for i in range(n_splits) if i not in is_combo]
        oos_rows = np.concatenate([chunks[i] for i in oos_combo])
        is_perf = clean.iloc[is_rows].apply(metric)
        oos_perf = clean.iloc[oos_rows].apply(metric)
        best_is = is_perf.idxmax()
        oos_rank = oos_perf.rank(method="average")[best_is]
        omega = oos_rank / (n_strategies + 1)
        omega = min(max(omega, 1e-6), 1 - 1e-6)
        logits.append(float(np.log(omega / (1 - omega))))
    logits = np.array(logits)
    pbo = float(np.mean(logits <= 0))
    return {"pbo": pbo, "n_combinations": len(logits), "logits": logits.tolist()}
