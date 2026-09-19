"""Portfolio Lab V2: compara, sin declarar ganador de antemano, seis formas
de repartir el capital entre las MISMAS candidatas del ranking -- Equal
Weight, Inverse Volatility, Minimum Variance, Score-weighted, Score + risk
constrained, y Risk Parity -- con rentabilidad, volatilidad, drawdown,
turnover, coste, concentración, contribution-to-risk y tracking error frente
al SPY para cada uno, más stress tests que NO pretenden ser pronósticos.

Reutiliza `decision_engine._risk_weights` (Minimum Variance) y el patrón de
`decision_engine._risk_weights_constrained` (límites dentro del solver de
PyPortfolioOpt) en vez de reimplementar la optimización, y
`portfolio_backtest._rebalance_to_weights`/`_daily_segment`/`buy_and_hold_curve`
para la contabilidad real de cartera -- lo único nuevo aquí es CÓMO se
calculan los pesos objetivo de cada esquema, no cómo se ejecutan ni se mide
el resultado.

**Reconstruir el ranking point-in-time es el paso caro del bucle, y es el
MISMO para los 6 esquemas en un periodo dado** -- se hace una sola vez por
fecha y los 6 esquemas se calculan sobre esas mismas candidatas (optimizar
sobre ~20-50 valores es cuestión de milisegundos), así que el coste total es
aproximadamente el de un solo backtest V2, no seis."""
from datetime import date

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from . import broker_costs, decision_engine, edgar, portfolio_metrics, screener_asof, storage, universe
from . import multifactor_backtest as v1
from . import portfolio_backtest as v2

_CALENDAR = "XNYS"

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


def _weights_min_variance(picks: list, histories: dict) -> dict:
    """Minimum Variance clásico, SIN límites de posición/sector -- reutiliza
    directamente `decision_engine._risk_weights`, no se reimplementa."""
    try:
        weights, _method = decision_engine._risk_weights(histories, picks)
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


_WEIGHT_FUNCS = {
    "equal_weight": lambda picks, scores, histories, sector_by_symbol, pos_cap, sec_cap: _weights_equal(picks),
    "inverse_vol": lambda picks, scores, histories, sector_by_symbol, pos_cap, sec_cap: _weights_inverse_vol(picks, histories),
    "min_variance": lambda picks, scores, histories, sector_by_symbol, pos_cap, sec_cap: _weights_min_variance(picks, histories),
    "score_weighted": lambda picks, scores, histories, sector_by_symbol, pos_cap, sec_cap: _weights_score(picks, scores),
    "score_constrained": lambda picks, scores, histories, sector_by_symbol, pos_cap, sec_cap:
        _weights_score_constrained(picks, scores, histories, pos_cap, sec_cap, sector_by_symbol),
    "risk_parity": lambda picks, scores, histories, sector_by_symbol, pos_cap, sec_cap: _weights_risk_parity(picks, histories),
}


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

def compute_betas(symbols: list, histories: dict, spy_history: pd.DataFrame) -> dict:
    spy_returns = spy_history["adj_close"].pct_change().dropna() if not spy_history.empty else pd.Series(dtype=float)
    betas = {}
    for s in symbols:
        h = histories.get(s, pd.DataFrame())
        if h.empty or "adj_close" not in h or spy_returns.empty:
            betas[s] = 1.0
            continue
        returns = h["adj_close"].pct_change().dropna()
        beta = portfolio_metrics.beta_vs_benchmark(returns, spy_returns)
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


# --- Bucle principal ---

def run_portfolio_lab(
    start: str, end: str, months: int = 3, max_symbols: int | None = None, mode: str = "validation",
    top_n: int = 20, initial_capital: float = 100_000.0, commission_usd: float = broker_costs.STOCK_FEE_USD,
    spread_bps: float = 10.0, schemes=SCHEMES, score_max_position_pct: float = 0.20,
    score_max_sector_pct: float = 0.35, min_coverage: float = .7, min_universe_coverage: float = .5,
) -> dict:
    if mode not in v2.VALID_MODES:
        raise ValueError(f"mode debe ser uno de {v2.VALID_MODES}.")
    if mode == "validation" and max_symbols is not None:
        raise ValueError("mode='validation' no permite muestreo (max_symbols debe ser None).")
    if mode == "fast_dev" and max_symbols is None:
        raise ValueError("mode='fast_dev' necesita max_symbols.")
    unknown = set(schemes) - set(SCHEMES)
    if unknown:
        raise ValueError(f"Esquemas desconocidos: {unknown}")
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    if start_ts >= end_ts or end_ts > pd.Timestamp(date.today()):
        raise ValueError("El intervalo debe terminar después del inicio y no superar hoy.")

    calendar = xcals.get_calendar(_CALENDAR)
    boundaries = []
    current = start_ts
    while current + pd.DateOffset(months=months) <= end_ts:
        boundaries.append(current)
        current += pd.DateOffset(months=months)
    if len(boundaries) < 2:
        raise ValueError("El intervalo no contiene ningún rebalanceo completo.")

    portfolios = {s: {"cash": float(initial_capital), "shares": {}} for s in schemes}
    rows = {s: [] for s in schemes}
    nav_pieces = {s: [] for s in schemes}
    skipped = []
    last_weights, last_cov, last_sector_by_symbol, last_betas = {}, None, {}, {}

    for i in range(len(boundaries) - 1):
        as_of = boundaries[i]
        as_of_str = as_of.date().isoformat()
        signal_session = calendar.date_to_session(as_of, direction="previous")
        entry_session = calendar.next_session(signal_session)
        exit_session = calendar.date_to_session(boundaries[i + 1], direction="next")
        sessions = calendar.sessions_in_range(entry_session, exit_session)

        try:
            if exit_session > pd.Timestamp(date.today()):
                raise ValueError(f"El periodo iniciado en {as_of.date()} aún no tiene salida.")
            membership = universe.get_sp500_constituents_asof(as_of_str)
            if not membership["is_exact"]:
                raise ValueError(membership["note"])
            symbols = v1._sample_symbols(membership["symbols"], max_symbols)
            ranked = screener_asof.build_ranking_as_of(as_of_str, symbols=symbols)["table"]
            eligible = ranked[ranked["composite_score"].notna() & (ranked["score_coverage"] >= min_coverage)]
            if len(eligible) / len(symbols) < min_universe_coverage:
                raise ValueError(f"cobertura insuficiente del universo ({len(eligible)}/{len(symbols)})")
            picks = eligible.index.tolist()[:top_n]
            if len(picks) < top_n:
                raise ValueError(f"solo {len(picks)}/{top_n} candidatas con cobertura suficiente")

            held_symbols = set().union(*(set(p["shares"].keys()) for p in portfolios.values()))
            needed = sorted(held_symbols | set(picks) | {"SPY"})
            histories = storage.get_prices_multi(needed)
            # Point-in-time: nada de lo que vean las funciones de peso (volatilidad,
            # covarianza...) puede incluir precios posteriores a la fecha de entrada
            # de este rebalanceo -- sin este corte, `.tail(252)` de cada función de
            # peso tomaría los últimos 252 días en CACHÉ (hasta hoy), no los 252
            # anteriores a `as_of`, un look-ahead real detectado con datos reales
            # durante el desarrollo (comprobado: un backtest de 2019 estaba usando
            # precios de 2025-2026 para construir la covarianza).
            histories = {s: (h[h.index <= entry_session] if not h.empty else h) for s, h in histories.items()}
            last_filed = edgar.get_last_filed_dates(needed, as_of=exit_session.date().isoformat())
            missing, recycled, entry_price = [], [], {}
            for s in needed:
                h = histories.get(s, pd.DataFrame())
                if (h.empty or entry_session not in h.index or pd.isna(h.loc[entry_session, "adj_close"])
                        or h.loc[entry_session, "adj_close"] <= 0):
                    missing.append(s)
                    continue
                if s in last_filed:
                    gap_days = (exit_session - pd.Timestamp(last_filed[s])).days
                    if gap_days > v1._MAX_DAYS_WITHOUT_FILING:
                        recycled.append(s)
                        continue
                entry_price[s] = float(h.loc[entry_session, "adj_close"])
            if missing:
                raise ValueError(f"Faltan precios ajustados en entrada ({entry_session.date()}): "
                                 f"{', '.join(missing)}")
            if recycled:
                raise ValueError(f"Ticker probablemente reciclado en {exit_session.date()}: "
                                 f"{', '.join(recycled)}")

            scores = eligible.loc[picks, "composite_score"]
            sector_by_symbol = {s: (eligible.loc[s, "sector"] if "sector" in eligible.columns else None) or "Desconocido"
                                for s in picks}
            price_panel = pd.concat({s: histories[s]["adj_close"].tail(252) for s in picks}, axis=1).dropna()
            from pypfopt import risk_models
            cov = (risk_models.CovarianceShrinkage(price_panel).ledoit_wolf()
                  if len(price_panel) >= 20 and len(picks) > 1 else None)
        except (ValueError, RuntimeError) as exc:
            skipped.append({"fecha": as_of_str, "motivo": str(exc)})
            for scheme in schemes:
                nav_pieces[scheme].append(v2._daily_segment(portfolios[scheme]["cash"], portfolios[scheme]["shares"],
                                                            entry_session, exit_session, sessions))
            continue

        for scheme in schemes:
            weights = _WEIGHT_FUNCS[scheme](picks, scores, histories, sector_by_symbol,
                                            score_max_position_pct, score_max_sector_pct)
            result = v2._rebalance_to_weights(portfolios[scheme]["cash"], portfolios[scheme]["shares"], weights,
                                              entry_price, commission_usd, spread_bps)
            portfolios[scheme]["cash"] = result["cash"]
            rows[scheme].append({"fecha": as_of_str, "hasta": exit_session.date().isoformat(),
                                 "turnover_pct": result["turnover_pct"], "comision_pagada": result["comision_pagada"]})
            nav_pieces[scheme].append(v2._daily_segment(portfolios[scheme]["cash"], portfolios[scheme]["shares"],
                                                        entry_session, exit_session, sessions))
            last_weights[scheme] = weights
        last_cov = cov
        last_sector_by_symbol = sector_by_symbol
        last_betas = compute_betas(picks, histories, histories.get("SPY", pd.DataFrame()))

    if not any(rows[s] for s in schemes):
        raise ValueError("Ningún periodo del rango tiene datos suficientes — "
                         f"se saltaron los {len(skipped)} periodos por falta de cobertura.")

    first_nav_date = min(pd.concat(nav_pieces[s]).index.min() for s in schemes if nav_pieces[s])
    last_nav_date = max(pd.concat(nav_pieces[s]).index.max() for s in schemes if nav_pieces[s])
    nav_curve_spy = v2.buy_and_hold_curve("SPY", first_nav_date.date().isoformat(), last_nav_date.date().isoformat(),
                                          initial_capital=initial_capital, commission_usd=commission_usd,
                                          spread_bps=spread_bps)
    returns_spy = nav_curve_spy.pct_change().dropna()

    results = {}
    for scheme in schemes:
        nav = pd.concat(nav_pieces[scheme]).sort_index()
        nav = nav[~nav.index.duplicated(keep="last")]
        daily = v1.daily_risk_metrics(nav)
        returns = nav.pct_change().dropna()
        periods = pd.DataFrame(rows[scheme])
        weights = last_weights.get(scheme, {})
        contrib = contribution_to_risk(weights, last_cov) if last_cov is not None else {}
        top3 = sum(sorted(contrib.values(), reverse=True)[:3]) if contrib else None
        results[scheme] = {
            "label": SCHEME_LABELS[scheme], "periods": periods, "nav_curve": nav, "daily": daily,
            "turnover_medio": float(periods["turnover_pct"].mean()) if not periods.empty else None,
            "comision_total": float(periods["comision_pagada"].sum()) if not periods.empty else 0.0,
            "tracking_error": portfolio_metrics.tracking_error(returns, returns_spy),
            "hhi": concentration_hhi(weights), "top3_contribution_to_risk": top3,
            "last_weights": weights, "contribution_to_risk": contrib,
        }

    scenarios_result = {}
    for scheme in schemes:
        weights = last_weights.get(scheme, {})
        scenarios_result[scheme] = {
            sc: apply_scenario(weights, sc, betas=last_betas, sector_by_symbol=last_sector_by_symbol, cov=last_cov)
            for sc in SCENARIOS
        }

    return {"schemes": results, "scenarios": scenarios_result, "nav_curve_spy": nav_curve_spy,
           "skipped": skipped, "mode": mode}
