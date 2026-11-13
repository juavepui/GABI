"""Portfolio Lab V2: compara, sin declarar ganador de antemano, seis formas
de repartir el capital entre las MISMAS candidatas del ranking -- Equal
Weight, Inverse Volatility, Minimum Variance, Score-weighted, Score + risk
constrained, y Risk Parity -- con rentabilidad, volatilidad, drawdown,
turnover, coste, concentración, contribution-to-risk y tracking error frente
al SPY para cada uno, más stress tests que NO pretenden ser pronósticos.

Este módulo contiene solo las reglas puras: CÓMO se calculan los pesos objetivo
de cada esquema, la concentración, la contribución al riesgo y los stress tests.
Minimum Variance y la beta usan las fórmulas existentes de GABI, inyectadas; la
ejecución y la medición del resultado están en
``application.research.portfolio_lab_engine``.
"""
import numpy as np
import pandas as pd

SCHEMES = ("equal_weight", "inverse_vol", "min_variance", "score_weighted", "score_constrained", "risk_parity")
SCHEME_LABELS = {
    "equal_weight": "Equal Weight", "inverse_vol": "Inverse Volatility",
    "min_variance": "Minimum Variance", "score_weighted": "Score-weighted",
    "score_constrained": "Score + risk constrained", "risk_parity": "Risk Parity",
}

# Heurísticas de sensibilidad por sector para Rates/USD -- NO calibradas con
# datos reales (GABI no tiene duración ni exposición a divisa por empresa
# cacheada). Valores orientativos de manual, documentados como tales en la
# UI. Por cada 100pb de subida de tipos / cada 10% de apreciación del USD.
RATE_SENSITIVITY_BY_SECTOR = {
    "Information Technology": -0.08, "Communication Services": -0.06,
    "Consumer Discretionary": -0.05, "Real Estate": -0.10, "Utilities": -0.07,
    "Financials": 0.04, "Energy": -0.01, "Materials": -0.02,
    "Industrials": -0.03, "Health Care": -0.02, "Consumer Staples": -0.01,
}
USD_SENSITIVITY_BY_SECTOR = {
    "Information Technology": -0.04, "Materials": -0.05, "Energy": -0.03,
    "Industrials": -0.04, "Health Care": -0.02, "Communication Services": -0.02,
    "Consumer Discretionary": -0.02, "Financials": -0.01, "Utilities": 0.0,
    "Real Estate": 0.0, "Consumer Staples": -0.01,
}
SCENARIOS = ("sp500_-10", "sp500_-20", "tech_-25", "vol_x2", "rates_+100bp", "usd_+10", "usd_-10")
SCENARIO_LABELS = {
    "sp500_-10": "S&P 500 −10%", "sp500_-20": "S&P 500 −20%", "tech_-25": "Tecnología −25%",
    "vol_x2": "Volatilidad ×2", "rates_+100bp": "Tipos +100pb", "usd_+10": "USD +10%", "usd_-10": "USD −10%",
}
SCENARIO_GROUND = {  # "real" = beta/sector calculados de precios reales; "heuristic" = tabla sin calibrar
    "sp500_-10": "real", "sp500_-20": "real", "tech_-25": "real", "vol_x2": "real",
    "rates_+100bp": "heuristic", "usd_+10": "heuristic", "usd_-10": "heuristic",
}


# --- Esquemas de ponderación ---

def _weights_equal(picks: list) -> dict:
    n = len(picks)
    return {s: 1.0 / n for s in picks} if n else {}


def _weights_inverse_vol(picks: list, histories: dict) -> dict:
    if len(picks) == 1:
        return {picks[0]: 1.0}
    try:
        prices = pd.concat({s: histories[s]["adj_close"].tail(252) for s in picks}, axis=1).dropna()
        if len(prices) < 20:
            raise ValueError("historial insuficiente")
        vol = prices.pct_change().dropna().std()
        if (vol <= 0).any() or vol.isna().any():
            raise ValueError("volatilidad inválida")
        inv = 1 / vol
        return (inv / inv.sum()).to_dict()
    except Exception:
        return _weights_equal(picks)


def _weights_min_variance(picks: list, histories: dict, min_variance) -> dict:
    """Minimum Variance clásico, SIN límites de posición/sector -- ``min_variance`` es
    `decision_engine._risk_weights` (inyectado), no se reimplementa."""
    try:
        weights, _method = min_variance(histories, picks)
        return weights
    except Exception:
        return _weights_equal(picks)


def _weights_score(picks: list, scores: pd.Series) -> dict:
    values = scores.reindex(picks).astype(float).clip(lower=0.01)
    total = values.sum()
    return (values / total).to_dict() if total > 0 else _weights_equal(picks)


def _weights_score_constrained(picks: list, scores: pd.Series, histories: dict,
                               position_cap: float, sector_cap: float, sector_by_symbol: dict) -> dict:
    """Score como proxy de retorno esperado, maximizando utilidad
    media-varianza sujeta a límites de posición/sector dentro del propio
    solver -- mismo patrón que `decision_engine._risk_weights_constrained`,
    con `ef.max_quadratic_utility()` en vez de `ef.min_volatility()`."""
    if len(picks) == 1:
        return {picks[0]: 1.0}
    try:
        prices = pd.concat({s: histories[s]["adj_close"].tail(252) for s in picks}, axis=1).dropna()
        if len(prices) < 126:
            raise ValueError("historial insuficiente")
        from pypfopt import EfficientFrontier, risk_models
        cov = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
        mu = scores.reindex(picks).astype(float)
        mu = mu / mu.sum()
        ef = EfficientFrontier(mu, cov, weight_bounds=(0, position_cap))
        sectors = {s: sector_by_symbol.get(s, "Desconocido") for s in picks}
        upper = {sec: sector_cap for sec in set(sectors.values())}
        lower = {sec: 0.0 for sec in set(sectors.values())}
        ef.add_sector_constraints(sectors, lower, upper)
        ef.max_quadratic_utility(risk_aversion=1)
        weights = {s: max(0.0, float(w)) for s, w in ef.clean_weights(cutoff=0, rounding=8).items()}
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("sin pesos válidos")
        return {s: w / total for s, w in weights.items()}
    except Exception:
        return _weights_score(picks, scores)


def _weights_risk_parity(picks: list, histories: dict) -> dict:
    """Equal Risk Contribution: cada posición aporta la MISMA fracción del
    riesgo total de la cartera -- no el mismo peso en $ (eso es Equal
    Weight) ni la misma volatilidad individual (eso es Inverse Volatility).
    Sin fórmula cerrada salvo para 2 activos -- se resuelve numéricamente
    minimizando la dispersión entre las `contribution_to_risk` de cada
    posición con `scipy.optimize.minimize` (SLSQP).

    NOTA: `pypfopt.hierarchical_portfolio.HRPOpt` (la implementación de
    referencia de López de Prado) está rota con la versión de scipy
    instalada en este entorno -- comprobado:
    `AttributeError: module 'scipy.cluster.hierarchy' has no attribute
    '_LINKAGE_METHODS'` -- por eso se resuelve a mano en vez de usar esa
    clase."""
    if len(picks) == 1:
        return {picks[0]: 1.0}
    try:
        prices = pd.concat({s: histories[s]["adj_close"].tail(252) for s in picks}, axis=1).dropna()
        if len(prices) < 60:
            raise ValueError("historial insuficiente")
        from pypfopt import risk_models
        cov = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
        symbols = list(prices.columns)
        cov_matrix = cov.loc[symbols, symbols].to_numpy()
        n = len(symbols)

        def _risk_contrib_error(w):
            port_var = w @ cov_matrix @ w
            if port_var <= 0:
                return 1e6
            marginal = cov_matrix @ w
            contrib = w * marginal / port_var
            return float(np.sum((contrib - 1.0 / n) ** 2))

        from scipy.optimize import minimize
        result = minimize(
            _risk_contrib_error, np.full(n, 1.0 / n), method="SLSQP",
            bounds=[(1e-6, 1.0)] * n, constraints=[{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}],
            options={"maxiter": 500, "ftol": 1e-12},
        )
        if not result.success:
            raise ValueError(f"optimizador no convergió: {result.message}")
        weights = {s: max(0.0, float(w)) for s, w in zip(symbols, result.x)}
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("sin pesos válidos")
        return {s: w / total for s, w in weights.items()}
    except Exception:
        return _weights_equal(picks)


def weights(scheme: str, picks: list, scores: pd.Series, histories: dict, sector_by_symbol: dict,
            position_cap: float, sector_cap: float, min_variance) -> dict:
    """Pesos objetivo de ``scheme`` sobre las mismas candidatas; ``min_variance(histories, picks)``
    devuelve (pesos, método) como `decision_engine._risk_weights`."""
    if scheme == "equal_weight":
        return _weights_equal(picks)
    if scheme == "inverse_vol":
        return _weights_inverse_vol(picks, histories)
    if scheme == "min_variance":
        return _weights_min_variance(picks, histories, min_variance)
    if scheme == "score_weighted":
        return _weights_score(picks, scores)
    if scheme == "score_constrained":
        return _weights_score_constrained(picks, scores, histories, position_cap, sector_cap, sector_by_symbol)
    if scheme == "risk_parity":
        return _weights_risk_parity(picks, histories)
    raise ValueError(f"Esquema desconocido: {scheme}")


# --- Concentración y contribution-to-risk ---

def concentration_hhi(weights: dict) -> float:
    """Índice Herfindahl-Hirschman: Σwᵢ² -- 1/N = perfectamente equiponderado
    (HHI mínimo posible con N posiciones), 1.0 = todo en una sola posición."""
    return float(sum(w ** 2 for w in weights.values())) if weights else 0.0


def contribution_to_risk(weights: dict, cov: pd.DataFrame) -> dict:
    """Fracción de la VARIANZA total de la cartera atribuible a cada
    posición: wᵢ·(Σw)ᵢ / w'Σw -- suma 1. Responde directamente a "¿qué % del
    riesgo viene de estas 3 posiciones?", no solo "¿qué % del capital?"."""
    symbols = [s for s in weights if s in cov.index]
    if not symbols:
        return {}
    w = np.array([weights[s] for s in symbols])
    cov_matrix = cov.loc[symbols, symbols].to_numpy()
    portfolio_var = float(w @ cov_matrix @ w)
    if portfolio_var <= 0:
        return {s: 0.0 for s in symbols}
    marginal = cov_matrix @ w
    contrib = w * marginal / portfolio_var
    return dict(zip(symbols, contrib.tolist()))


# --- Stress tests (NO son pronósticos) ---

def compute_betas(symbols: list, histories: dict, spy_history: pd.DataFrame, beta_vs_benchmark) -> dict:
    """``beta_vs_benchmark(returns, spy_returns)`` es la de `portfolio_metrics` (inyectada); 1.0 si falta."""
    spy_returns = spy_history["adj_close"].pct_change().dropna() if not spy_history.empty else pd.Series(dtype=float)
    betas = {}
    for s in symbols:
        h = histories.get(s, pd.DataFrame())
        if h.empty or "adj_close" not in h or spy_returns.empty:
            betas[s] = 1.0
            continue
        returns = h["adj_close"].pct_change().dropna()
        beta = beta_vs_benchmark(returns, spy_returns)
        betas[s] = beta if beta is not None else 1.0
    return betas


def apply_scenario(weights: dict, scenario: str, betas: dict = None,
                   sector_by_symbol: dict = None, cov: pd.DataFrame = None) -> dict:
    """Un stress test, no una predicción -- shocks arbitrarios aplicados con
    supuestos simples y explícitos (beta/sector reales para
    S&P/Tech/Volatilidad, heurística de manual sin calibrar para
    Tipos/USD, ver `SCENARIO_GROUND`)."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Escenario desconocido: {scenario}")
    betas = betas or {}
    sector_by_symbol = sector_by_symbol or {}

    if scenario in ("sp500_-10", "sp500_-20"):
        shock = -0.10 if scenario == "sp500_-10" else -0.20
        impact = sum(weights[s] * betas.get(s, 1.0) * shock for s in weights)
        return {"tipo": "retorno", "impacto_pct": impact, "base": SCENARIO_GROUND[scenario]}

    if scenario == "tech_-25":
        impact = sum(weights[s] * -0.25 for s in weights if sector_by_symbol.get(s) == "Information Technology")
        return {"tipo": "retorno", "impacto_pct": impact, "base": SCENARIO_GROUND[scenario]}

    if scenario == "vol_x2":
        if cov is None:
            raise ValueError("vol_x2 necesita la matriz de covarianza.")
        symbols = [s for s in weights if s in cov.index]
        w = np.array([weights[s] for s in symbols])
        cov_matrix = cov.loc[symbols, symbols].to_numpy()
        base_var = float(w @ cov_matrix @ w)
        base_vol = float(np.sqrt(max(base_var, 0) * 252))
        scenario_vol = float(np.sqrt(max(base_var, 0) * 4 * 252))
        return {"tipo": "volatilidad", "vol_base": base_vol, "vol_escenario": scenario_vol,
               "base": SCENARIO_GROUND[scenario]}

    if scenario == "rates_+100bp":
        impact = sum(weights[s] * RATE_SENSITIVITY_BY_SECTOR.get(sector_by_symbol.get(s, ""), 0.0) for s in weights)
        return {"tipo": "retorno", "impacto_pct": impact, "base": SCENARIO_GROUND[scenario]}

    sign = 1 if scenario == "usd_+10" else -1
    impact = sum(weights[s] * USD_SENSITIVITY_BY_SECTOR.get(sector_by_symbol.get(s, ""), 0.0) * sign
                for s in weights)
    return {"tipo": "retorno", "impacto_pct": impact, "base": SCENARIO_GROUND[scenario]}
