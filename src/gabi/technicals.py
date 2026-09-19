"""Indicadores técnicos: medias móviles, RSI, momentum y fuerza relativa."""
import numpy as np
import pandas as pd

from . import config


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def _rsi(series: pd.Series, period: int = config.RSI_PERIOD) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100)
    return rsi.mask((avg_loss == 0) & (avg_gain == 0), 50)


def _pct_change_n(series: pd.Series, n: int):
    if len(series) <= n:
        return None
    past = series.iloc[-n - 1]
    now = series.iloc[-1]
    if pd.isna(past) or past == 0:
        return None
    return float(now / past - 1)


def _return_price(price_df: pd.DataFrame) -> pd.Series:
    """Prioriza `adj_close` (ajustado por splits Y dividendos) sobre `close`
    (solo splits, vía yfinance) para que momentum/medias/RSI midan lo mismo
    que retorno real -- si no, una acción de alto dividendo (REIT, utility)
    puntúa peor en momentum solo por repartir caja, no por precio. Mismo
    criterio que ya usa `risk._return_price` para Sharpe/Sortino/drawdown.
    Cae a `close` si el símbolo tiene caché antiguo sin `adj_close` completo
    -- todo o nada, para no mezclar ajustado y sin ajustar en la misma serie."""
    column = "adj_close" if "adj_close" in price_df and price_df["adj_close"].notna().all() else "close"
    return price_df[column]


EMPTY_RESULT = {
    "price": None, "sma50": None, "sma200": None,
    "price_vs_sma50": None, "price_vs_sma200": None,
    "golden_cross_recent": None, "rsi14": None,
    "momentum_6m": None, "momentum_12m": None, "rel_strength_6m": None,
}


def compute_technicals(price_df: pd.DataFrame, benchmark_df: pd.DataFrame = None) -> dict:
    """price_df: DataFrame indexado por fecha (ascendente) con columna 'close'
    (y opcionalmente 'adj_close', preferida para todo lo que no sea el precio
    nominal mostrado -- ver `_return_price`)."""
    if price_df is None or price_df.empty or "close" not in price_df:
        return dict(EMPTY_RESULT)

    nominal_close = price_df["close"].dropna()
    if nominal_close.empty:
        return dict(EMPTY_RESULT)

    close = _return_price(price_df).dropna()
    if close.empty:
        return dict(EMPTY_RESULT)

    result = dict(EMPTY_RESULT)
    result["price"] = float(nominal_close.iloc[-1])
    price = close.iloc[-1]  # base ajustada -- misma serie que sma50/sma200, para que el ratio no salte por un dividendo

    sma50 = _sma(close, config.SMA_SHORT)
    sma200 = _sma(close, config.SMA_LONG)

    if pd.notna(sma50.iloc[-1]):
        result["sma50"] = float(sma50.iloc[-1])
        result["price_vs_sma50"] = float(price / sma50.iloc[-1] - 1)
    if pd.notna(sma200.iloc[-1]):
        result["sma200"] = float(sma200.iloc[-1])
        result["price_vs_sma200"] = float(price / sma200.iloc[-1] - 1)

    if pd.notna(sma50.iloc[-1]) and pd.notna(sma200.iloc[-1]):
        diff = (sma50 - sma200).tail(20).dropna()
        if len(diff) >= 2:
            result["golden_cross_recent"] = bool(diff.iloc[0] < 0 and diff.iloc[-1] > 0)
        else:
            result["golden_cross_recent"] = False

    rsi = _rsi(close)
    if pd.notna(rsi.iloc[-1]):
        result["rsi14"] = float(rsi.iloc[-1])

    result["momentum_6m"] = _pct_change_n(close, config.MOMENTUM_SHORT_DAYS)
    result["momentum_12m"] = _pct_change_n(close, config.MOMENTUM_LONG_DAYS)

    if benchmark_df is not None and not benchmark_df.empty and "close" in benchmark_df:
        bench_close = _return_price(benchmark_df).dropna()
        bench_mom_6m = _pct_change_n(bench_close, config.MOMENTUM_SHORT_DAYS)
        if result["momentum_6m"] is not None and bench_mom_6m is not None:
            result["rel_strength_6m"] = result["momentum_6m"] - bench_mom_6m

    return result
