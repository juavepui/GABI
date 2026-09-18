"""Reconstruye el ranking del screener tal y como se habría visto en una
fecha pasada — la pieza 2 del plan point-in-time ("Fase 2: screener sobre
fecha arbitraria"). Todo anclado a esa fecha, sin usar ningún dato de "ahora":

  - Universo: universe.get_sp500_constituents_asof (evita sesgo de supervivencia).
  - Fundamentales/múltiplos: SEC EDGAR reconstruido con edgar.compute_edgar_metrics_as_of
    + precio y nº de acciones de esa fecha — nunca yfinance, que no guarda histórico.
  - Momentum y riesgo: los mismos technicals.py/risk.py de siempre, pero con
    el histórico de precios TRUNCADO a esa fecha (ya son point-in-time
    correctos en sí mismos, solo había que no dejarles ver el futuro).

No hace ninguna llamada de red: requiere que los símbolos del universo de esa
fecha ya se hayan descargado antes (precios + SEC EDGAR) desde ⚙️ Configuración.
Si un símbolo no tiene datos suficientes, aparece con métricas en blanco en
vez de romper el resto — igual que ya se hace en el screener "en vivo".
"""
import pandas as pd

from . import edgar, entity_master, risk, scoring, storage, technicals, universe


def _classic_metrics_as_of(symbol: str, as_of_date: str) -> dict:
    """Fundamentales + múltiplos clásicos (ROIC, deuda neta/EBITDA, crecimiento
    de FCF, márgenes, PER/P-VC/P-Ventas/EV-EBITDA) reconstruidos con lo que se
    conocía en as_of_date."""
    m = edgar.compute_edgar_metrics_as_of(symbol, as_of_date)
    price = storage.get_price_as_of(symbol, as_of_date) if storage.has_verified_price_as_of(symbol, as_of_date) else None
    shares = edgar.get_shares_outstanding_as_of(symbol, as_of_date)

    # yfinance devuelve el precio siempre ajustado por splits (con o sin
    # auto_adjust) — para que la capitalización cuadre con el nº de acciones
    # REAL de esa fecha (SEC EDGAR, sin ajustar), hay que deshacer los splits
    # ocurridos DESPUÉS de as_of_date multiplicando por su factor acumulado.
    # Sin esto, la capitalización de fechas anteriores a un split posterior
    # sale mal por un factor entero (comprobado con datos reales: ~4 veces
    # por debajo en un caso con Apple, que tuvo un split 4:1 en 2020).
    price_asof_unadjusted = None
    if price is not None:
        split_factor = storage.get_split_factor_since(symbol, as_of_date)
        price_asof_unadjusted = price * split_factor

    market_cap = price_asof_unadjusted * shares if price_asof_unadjusted and shares else None
    revenue = m.get("latest_revenue")
    net_income = m.get("latest_net_income")
    equity = m.get("latest_equity")
    debt = m.get("latest_debt")
    cash = m.get("latest_cash")
    ebitda = m.get("latest_ebitda")

    pe = (market_cap / net_income) if market_cap and net_income and net_income > 0 else None
    pb = (market_cap / equity) if market_cap and equity and equity > 0 else None
    ps = (market_cap / revenue) if market_cap and revenue and revenue > 0 else None
    enterprise_value = (market_cap + (debt or 0) - (cash or 0)) if market_cap is not None else None
    ev_ebitda = (enterprise_value / ebitda) if enterprise_value and ebitda and ebitda > 0 else None
    debt_to_equity = (debt / equity * 100) if debt is not None and equity and equity > 0 else None

    return {
        # Precio nominal (sin ajustar por splits posteriores) — el que de
        # verdad se habría visto en pantalla ese día, no el retroajustado
        # que usan momentum/riesgo internamente para que los retornos cuadren.
        "price": price_asof_unadjusted, "shares_outstanding": shares, "market_cap": market_cap,
        "pe": pe, "pb": pb, "ps": ps, "ev_ebitda": ev_ebitda,
        "roic": m.get("roic"),
        "gross_margin": m.get("gross_margin"),
        "operating_margin": m.get("operating_margin"),
        "profit_margin": m.get("profit_margin"),
        "revenue_growth_yoy": m.get("revenue_growth_yoy"),
        "earnings_growth_yoy": m.get("earnings_growth_yoy"),
        "revenue_cagr_3y": m.get("revenue_cagr_3y"),
        "fcf_cagr_3y": m.get("fcf_cagr_3y"),
        "debt_to_equity": debt_to_equity,
        "net_debt_to_ebitda": m.get("net_debt_to_ebitda"),
        "fundamentals_period_end": m.get("latest_period_end"),
    }


def _price_history_as_of(symbol: str, as_of_date: pd.Timestamp) -> pd.DataFrame:
    df = storage.get_prices(symbol)
    if df.empty:
        return df
    df = df[df.index <= as_of_date]
    # Las filas antiguas del caché se descargaron con auto_adjust=True y no
    # sirven para múltiplos históricos ni para un histórico técnico coherente.
    if "adj_close" not in df or df.empty or pd.isna(df["adj_close"].iloc[-1]):
        return df.iloc[0:0]
    return df[df["adj_close"].notna()]


def build_ranking_as_of(as_of_date: str, weights: dict = None, symbols: list = None) -> dict:
    """Reconstruye el ranking completo para as_of_date (YYYY-MM-DD).

    symbols=None (por defecto) usa el universo histórico reconstruido para
    esa fecha; pasar una lista explícita de símbolos la usa tal cual (útil
    para probar con un subconjunto pequeño antes de lanzar las ~500 del
    S&P 500, cada una con varias consultas a edgar_facts).

    Devuelve {"table": DataFrame, "universe_info": {...}}. universe_info trae
    is_exact/source_date/note de universe.get_sp500_constituents_asof (o un
    aviso genérico si se pasó `symbols` explícitamente).
    """
    if symbols is None:
        universe_info = universe.get_sp500_constituents_asof(as_of_date)
        symbols = universe_info["symbols"]
    else:
        universe_info = {
            "symbols": symbols, "source_date": None, "is_exact": None,
            "note": "Universo pasado explícitamente (no reconstruido a partir del histórico).",
        }

    as_of_ts = pd.Timestamp(as_of_date)
    bench_df = _price_history_as_of("SPY", as_of_ts)

    rows = []
    for sym in symbols:
        classic = _classic_metrics_as_of(sym, as_of_date)
        price_df = _price_history_as_of(sym, as_of_ts)

        t = technicals.compute_technicals(price_df, bench_df) if not price_df.empty else {}
        r = risk.compute_risk_metrics(price_df, bench_df) if not price_df.empty else {}

        # 'classic' se aplica el último a propósito: tanto classic como
        # technicals.compute_technicals devuelven una clave 'price', y la de
        # classic (corregida por splits posteriores, ver más arriba) es la
        # que debe quedar — la de technicals es el cierre tal cual, sin esa
        # corrección, pensado para el screener "en vivo" donde no aplica.
        row = {"symbol": sym}
        row.update(t)
        row.update(r)
        row.update(classic)
        rows.append(row)

    df = pd.DataFrame(rows).set_index("symbol")
    if df.empty:
        return {"table": df, "universe_info": universe_info}

    # No hay fuente gratuita de sector/nombre HISTÓRICO -- entity_master
    # guarda una foto con fecha cada vez que se refresca el universo en vivo
    # (screener.get_universe(force_refresh=True)) para acumular historial
    # real a partir de ahora. get_sector_asof usa la foto real más cercana a
    # as_of_date si existe (point-in-time correcto), o si no, la más antigua
    # disponible como aproximación explícita (sector_is_approximate=True) --
    # hoy en día, con poco historial de fotos acumulado, esa es la rama que
    # se usa para la mayoría de fechas de un backtest. Un símbolo sin
    # ninguna foto (deslistado antes de que existiera este mecanismo) sigue
    # sin sector -> scoring.py cae automáticamente al percentil global para
    # esas filas en vez de romper, igual que antes.
    snapshots = entity_master.get_sector_asof(list(df.index), as_of_date)
    df["sector"] = [snapshots[s]["sector"] for s in df.index]
    df["name"] = [snapshots[s]["name"] for s in df.index]
    df["sector_is_approximate"] = [snapshots[s]["is_approximate"] for s in df.index]

    df = scoring.build_scores(df, weights=weights)
    df["confidence"] = scoring.compute_confidence(df, weights=weights)
    return {"table": df, "universe_info": universe_info}
