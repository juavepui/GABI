"""Portfolio Lab engine: the six schemes rebalanced over the same point-in-time candidates.

The ranking, prices, filings and the V1/V2 accounting are injected (``PortfolioLabSources``);
the weighting rules live in ``domain.research.portfolio_lab``. Same loop as the original
module, so the cost of the six schemes is roughly that of one V2 backtest.
"""
from datetime import date
from typing import Any, Protocol

import exchange_calendars as xcals
import pandas as pd

from gabi.domain.research import portfolio_lab as rules

CALENDAR = "XNYS"


class PortfolioLabSources(Protocol):
    valid_modes: tuple[str, ...]
    max_days_without_filing: int

    def membership(self, as_of: str) -> dict: ...
    def sample(self, symbols: list[str], max_symbols: int | None) -> list[str]: ...
    def ranking(self, as_of: str, symbols: list[str]) -> pd.DataFrame: ...
    def prices(self, symbols: list[str]) -> dict[str, pd.DataFrame]: ...
    def last_filed(self, symbols: list[str], as_of: str) -> dict[str, str]: ...
    def daily_segment(self, cash: float, shares: dict, entry, exit_session, sessions) -> pd.Series: ...
    def rebalance(self, cash: float, shares: dict, weights: dict, prices: dict, commission_usd: float,
                  spread_bps: float) -> dict: ...
    def buy_and_hold(self, symbol: str, start: str, end: str, *, initial_capital: float, commission_usd: float,
                     spread_bps: float) -> pd.Series: ...
    def daily_risk(self, nav: pd.Series) -> dict: ...
    def tracking_error(self, returns: pd.Series, benchmark: pd.Series): ...
    def min_variance(self, histories: dict, picks: list[str]) -> tuple[dict, str]: ...
    def beta(self, returns: pd.Series, benchmark: pd.Series): ...


def run_portfolio_lab(
    start: str, end: str, sources: PortfolioLabSources, today: date, *, commission_usd: float, months: int = 3,
    max_symbols: int | None = None, mode: str = "validation", top_n: int = 20, initial_capital: float = 100_000.0,
    spread_bps: float = 10.0, schemes=rules.SCHEMES, score_max_position_pct: float = 0.20,
    score_max_sector_pct: float = 0.35, min_coverage: float = .7, min_universe_coverage: float = .5,
) -> dict:
    if mode not in sources.valid_modes:
        raise ValueError(f"mode debe ser uno de {sources.valid_modes}.")
    if mode == "validation" and max_symbols is not None:
        raise ValueError("mode='validation' no permite muestreo (max_symbols debe ser None).")
    if mode == "fast_dev" and max_symbols is None:
        raise ValueError("mode='fast_dev' necesita max_symbols.")
    unknown = set(schemes) - set(rules.SCHEMES)
    if unknown:
        raise ValueError(f"Esquemas desconocidos: {unknown}")
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    if start_ts >= end_ts or end_ts > pd.Timestamp(today):
        raise ValueError("El intervalo debe terminar después del inicio y no superar hoy.")

    calendar = xcals.get_calendar(CALENDAR)
    boundaries = []
    current = start_ts
    while current + pd.DateOffset(months=months) <= end_ts:
        boundaries.append(current)
        current += pd.DateOffset(months=months)
    if len(boundaries) < 2:
        raise ValueError("El intervalo no contiene ningún rebalanceo completo.")

    portfolios: dict[str, dict[str, Any]] = {s: {"cash": float(initial_capital), "shares": {}} for s in schemes}
    rows: dict[str, list[dict]] = {s: [] for s in schemes}
    nav_pieces: dict[str, list[pd.Series]] = {s: [] for s in schemes}
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
            if exit_session > pd.Timestamp(today):
                raise ValueError(f"El periodo iniciado en {as_of.date()} aún no tiene salida.")
            membership = sources.membership(as_of_str)
            if not membership["is_exact"]:
                raise ValueError(membership["note"])
            symbols = sources.sample(membership["symbols"], max_symbols)
            ranked = sources.ranking(as_of_str, symbols)
            eligible = ranked[ranked["composite_score"].notna() & (ranked["score_coverage"] >= min_coverage)]
            if len(eligible) / len(symbols) < min_universe_coverage:
                raise ValueError(f"cobertura insuficiente del universo ({len(eligible)}/{len(symbols)})")
            picks = eligible.index.tolist()[:top_n]
            if len(picks) < top_n:
                raise ValueError(f"solo {len(picks)}/{top_n} candidatas con cobertura suficiente")

            held_symbols: set[str] = set().union(*(set(p["shares"].keys()) for p in portfolios.values()))
            needed = sorted(held_symbols | set(picks) | {"SPY"})
            histories = sources.prices(needed)
            # Point-in-time: nada de lo que vean las funciones de peso (volatilidad,
            # covarianza...) puede incluir precios posteriores a la fecha de entrada
            # de este rebalanceo -- sin este corte, `.tail(252)` de cada función de
            # peso tomaría los últimos 252 días en CACHÉ (hasta hoy), no los 252
            # anteriores a `as_of`, un look-ahead real detectado con datos reales
            # durante el desarrollo (comprobado: un backtest de 2019 estaba usando
            # precios de 2025-2026 para construir la covarianza).
            histories = {s: (h[h.index <= entry_session] if not h.empty else h) for s, h in histories.items()}
            last_filed = sources.last_filed(needed, exit_session.date().isoformat())
            missing, recycled, entry_price = [], [], {}
            for s in needed:
                h = histories.get(s, pd.DataFrame())
                if (h.empty or entry_session not in h.index or pd.isna(h.loc[entry_session, "adj_close"])
                        or h.loc[entry_session, "adj_close"] <= 0):
                    missing.append(s)
                    continue
                if s in last_filed:
                    gap_days = (exit_session - pd.Timestamp(last_filed[s])).days
                    if gap_days > sources.max_days_without_filing:
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
                nav_pieces[scheme].append(sources.daily_segment(portfolios[scheme]["cash"], portfolios[scheme]["shares"],
                                                            entry_session, exit_session, sessions))
            continue

        for scheme in schemes:
            weights = rules.weights(scheme, picks, scores, histories, sector_by_symbol,
                                    score_max_position_pct, score_max_sector_pct, sources.min_variance)
            result = sources.rebalance(portfolios[scheme]["cash"], portfolios[scheme]["shares"], weights,
                                              entry_price, commission_usd, spread_bps)
            portfolios[scheme]["cash"] = result["cash"]
            rows[scheme].append({"fecha": as_of_str, "hasta": exit_session.date().isoformat(),
                                 "turnover_pct": result["turnover_pct"], "comision_pagada": result["comision_pagada"]})
            nav_pieces[scheme].append(sources.daily_segment(portfolios[scheme]["cash"], portfolios[scheme]["shares"],
                                                        entry_session, exit_session, sessions))
            last_weights[scheme] = weights
        last_cov = cov
        last_sector_by_symbol = sector_by_symbol
        last_betas = rules.compute_betas(picks, histories, histories.get("SPY", pd.DataFrame()), sources.beta)

    if not any(rows[s] for s in schemes):
        raise ValueError("Ningún periodo del rango tiene datos suficientes — "
                         f"se saltaron los {len(skipped)} periodos por falta de cobertura.")

    first_nav_date = min(pd.concat(nav_pieces[s]).index.min() for s in schemes if nav_pieces[s])
    last_nav_date = max(pd.concat(nav_pieces[s]).index.max() for s in schemes if nav_pieces[s])
    nav_curve_spy = sources.buy_and_hold("SPY", first_nav_date.date().isoformat(), last_nav_date.date().isoformat(),
                                          initial_capital=initial_capital, commission_usd=commission_usd,
                                          spread_bps=spread_bps)
    returns_spy = nav_curve_spy.pct_change().dropna()

    results = {}
    for scheme in schemes:
        nav = pd.concat(nav_pieces[scheme]).sort_index()
        nav = nav[~nav.index.duplicated(keep="last")]
        daily = sources.daily_risk(nav)
        returns = nav.pct_change().dropna()
        periods = pd.DataFrame(rows[scheme])
        weights = last_weights.get(scheme, {})
        contrib = rules.contribution_to_risk(weights, last_cov) if last_cov is not None else {}
        top3 = sum(sorted(contrib.values(), reverse=True)[:3]) if contrib else None
        results[scheme] = {
            "label": rules.SCHEME_LABELS[scheme], "periods": periods, "nav_curve": nav, "daily": daily,
            "turnover_medio": float(periods["turnover_pct"].mean()) if not periods.empty else None,
            "comision_total": float(periods["comision_pagada"].sum()) if not periods.empty else 0.0,
            "tracking_error": sources.tracking_error(returns, returns_spy),
            "hhi": rules.concentration_hhi(weights), "top3_contribution_to_risk": top3,
            "last_weights": weights, "contribution_to_risk": contrib,
        }

    scenarios_result = {}
    for scheme in schemes:
        weights = last_weights.get(scheme, {})
        scenarios_result[scheme] = {
            sc: rules.apply_scenario(weights, sc, betas=last_betas, sector_by_symbol=last_sector_by_symbol, cov=last_cov)
            for sc in rules.SCENARIOS
        }

    return {"schemes": results, "scenarios": scenarios_result, "nav_curve_spy": nav_curve_spy,
           "skipped": skipped, "mode": mode}
