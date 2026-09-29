"""Métricas de riesgo por empresa: volatilidad, máximo drawdown, Sharpe,
Sortino, beta y alpha — el equivalente a nivel de una sola empresa de lo que
muestran las plataformas de análisis de carteras (Sharpe, Sortino, beta...).

Todo se calcula a partir del histórico de precios que GABI ya tiene cacheado
(precio de la empresa + del benchmark SPY): no requiere ninguna fuente de
datos nueva."""
import numpy as np
import pandas as pd

from . import config

TRADING_DAYS_PER_YEAR = 252

EMPTY_RESULT = {
    "volatility": None, "max_drawdown": None, "sharpe_ratio": None, "sortino_ratio": None,
    "beta_calc": None, "alpha": None, "win_rate_monthly": None,
}


def _daily_returns(price_df: pd.DataFrame) -> pd.Series:
    if price_df is None or price_df.empty or "close" not in price_df:
        return pd.Series(dtype=float)
    return _return_price(price_df).pct_change().dropna()


def _return_price(price_df: pd.DataFrame) -> pd.Series:
    column = "adj_close" if "adj_close" in price_df and price_df["adj_close"].notna().all() else "close"
    return price_df[column]


def _annualized_return(returns: pd.Series):
    if returns.empty:
        return None
    total_return = (1 + returns).prod() - 1
    years = len(returns) / TRADING_DAYS_PER_YEAR
    if years <= 0:
        return None
    base = 1 + total_return
    if base <= 0:
        return None  # pérdida total; (base)**(1/years) no está definida con exponente fraccionario
    return base ** (1 / years) - 1


def _annualized_volatility(returns: pd.Series):
    if returns.empty:
        return None
    return float(returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR))


def _max_drawdown(price_df: pd.DataFrame):
    if price_df is None or price_df.empty or "close" not in price_df:
        return None
    close = _return_price(price_df).dropna()
    if close.empty:
        return None
    running_max = close.cummax()
    drawdown = close / running_max - 1
    return float(drawdown.min())  # valor negativo, ej. -0.35 = -35%


def _beta_vs_benchmark(returns: pd.Series, bench_returns: pd.Series):
    aligned = pd.concat([returns, bench_returns], axis=1, join="inner").dropna()
    if len(aligned) < 30:
        return None
    stock_r, bench_r = aligned.iloc[:, 0], aligned.iloc[:, 1]
    bench_var = bench_r.var()
    if not bench_var:
        return None
    return float(stock_r.cov(bench_r) / bench_var)


def _sharpe_ratio(returns: pd.Series, risk_free_rate: float):
    ann_return = _annualized_return(returns)
    ann_vol = _annualized_volatility(returns)
    if ann_return is None or not ann_vol:
        return None
    return (ann_return - risk_free_rate) / ann_vol


def _sortino_ratio(returns: pd.Series, risk_free_rate: float):
    ann_return = _annualized_return(returns)
    if ann_return is None or returns.empty:
        return None
    daily_target = (1 + risk_free_rate) ** (1 / TRADING_DAYS_PER_YEAR) - 1
    shortfall = np.minimum(returns - daily_target, 0)
    downside_dev = float(np.sqrt(np.mean(np.square(shortfall))) * np.sqrt(TRADING_DAYS_PER_YEAR))
    if not downside_dev:
        return None
    return (ann_return - risk_free_rate) / downside_dev


def _monthly_win_rate(price_df: pd.DataFrame):
    if price_df is None or price_df.empty or "close" not in price_df:
        return None
    monthly = _return_price(price_df).resample("ME").last().dropna()
    monthly_returns = monthly.pct_change().dropna()
    if monthly_returns.empty:
        return None
    return float((monthly_returns > 0).mean())


def compute_risk_metrics(price_df: pd.DataFrame, benchmark_df: pd.DataFrame = None, risk_free_rate: float = None) -> dict:
    risk_free_rate = config.RISK_FREE_RATE if risk_free_rate is None else risk_free_rate
    result = dict(EMPTY_RESULT)

    returns = _daily_returns(price_df)
    if returns.empty:
        return result

    result["volatility"] = _annualized_volatility(returns)
    result["max_drawdown"] = _max_drawdown(price_df)
    result["sharpe_ratio"] = _sharpe_ratio(returns, risk_free_rate)
    result["sortino_ratio"] = _sortino_ratio(returns, risk_free_rate)
    result["win_rate_monthly"] = _monthly_win_rate(price_df)

    if benchmark_df is not None:
        bench_returns = _daily_returns(benchmark_df)
        beta = _beta_vs_benchmark(returns, bench_returns)
        result["beta_calc"] = beta
        if beta is not None:
            stock_ann = _annualized_return(returns)
            bench_ann = _annualized_return(bench_returns)
            if stock_ann is not None and bench_ann is not None:
                result["alpha"] = stock_ann - (risk_free_rate + beta * (bench_ann - risk_free_rate))

    return result
