"""Historical metric coverage from explicit facts, prices and policy."""
import math
from dataclasses import dataclass

import pandas as pd

from gabi.domain.market import risk, sec_facts, technicals
from gabi.domain.market.scoring import MIN_SCORE_COVERAGE, SCORE_METRICS

BLOCKS = tuple((block, tuple(metrics)) for block, metrics in SCORE_METRICS.items())
METRICS = tuple(metric for _, metrics in BLOCKS for metric in metrics)


@dataclass(frozen=True)
class CoverageParameters:
    blocks: tuple[tuple[str, tuple[str, ...]], ...] = BLOCKS
    metrics: tuple[str, ...] = METRICS
    min_score_coverage: float = MIN_SCORE_COVERAGE
    technical: technicals.TechnicalParameters = technicals.TechnicalParameters()
    fiscal_alignment: bool = False
    alignment_tolerance_days: int = sec_facts.ALIGNMENT_TOLERANCE_DAYS
    shares_tags: tuple[str, ...] = tuple(sec_facts.SHARES_TAGS)


def fact_structure(frame: pd.DataFrame, as_of: str) -> dict:
    if frame.empty:
        return {"facts": {"us-gaap": {}}}
    frame = frame[(frame.filed_date <= as_of) & (frame.end_date <= as_of)].sort_values(["filed_date", "end_date", "accn"])
    result: dict = {}
    for row in frame.itertuples(index=False):
        entries = result.setdefault(row.tag, {"units": {}})["units"].setdefault(row.unit, [])
        entries.append(dict(start=row.start_date or None, end=row.end_date, val=row.val,
                            form=row.form, fp=row.fp, fy=row.fy, filed=row.filed_date, accn=row.accn))
    return {"facts": {"us-gaap": result}}


def finite(value) -> bool:
    return value is not None and not pd.isna(value) and math.isfinite(float(value))


def metric_row(facts: pd.DataFrame, prices: pd.DataFrame, benchmark: pd.DataFrame,
               as_of: str, *, nominal_price: float | None, parameters: CoverageParameters = CoverageParameters()) -> dict:
    """Same 13 ingredients/formulas as GABI; undefined ratios remain missing."""
    result = dict.fromkeys(parameters.metrics)
    facts = facts[(facts.filed_date <= as_of) & (facts.end_date <= as_of)] if not facts.empty else facts
    m = sec_facts.compute_edgar_metrics(fact_structure(facts, as_of), fiscal_alignment=parameters.fiscal_alignment,
                                       tolerance_days=parameters.alignment_tolerance_days)
    shares = facts[(facts.tag.isin(parameters.shares_tags)) & (facts.unit == "shares")] if not facts.empty else facts
    count = float(shares.sort_values(["filed_date", "end_date"]).iloc[-1].val) if not shares.empty else None
    cap = nominal_price * count if nominal_price and count and count > 0 else None
    ni, equity, ebitda = (m.get(k) for k in ["latest_net_income", "latest_equity", "latest_ebitda"])
    debt, cash = m.get("latest_debt"), m.get("latest_cash")
    result["pe"] = cap / ni if cap and ni and ni > 0 else None
    result["pb"] = cap / equity if cap and equity and equity > 0 else None
    ev = cap + (debt or 0) - (cash or 0) if cap else None
    result["ev_ebitda"] = ev / ebitda if ev and ebitda and ebitda > 0 else None
    result["debt_to_equity"] = debt / equity * 100 if debt is not None and equity and equity > 0 else None
    for key in dict(parameters.blocks)["quality"]:
        result[key] = m.get(key)
    prices = prices.loc[:as_of]
    benchmark = benchmark.loc[:as_of]
    if not prices.empty:
        close = prices.adj_close
        result["momentum_12m"] = technicals._pct_change_n(close, parameters.technical.momentum_long_days)
        short = technicals._pct_change_n(close, parameters.technical.momentum_short_days)
        bench = technicals._pct_change_n(benchmark.adj_close, parameters.technical.momentum_short_days) if not benchmark.empty else None
        result["rel_strength_6m"] = short - bench if short is not None and bench is not None else None
        if len(close) >= parameters.technical.sma_long:
            result["price_vs_sma200"] = float(close.iloc[-1] / close.tail(parameters.technical.sma_long).mean() - 1)
        result["volatility"] = risk._annualized_volatility(close.pct_change(fill_method=None).dropna())
        result["max_drawdown"] = risk._max_drawdown(prices)
    return result


def availability(metrics: dict, *, parameters: CoverageParameters = CoverageParameters()) -> tuple[int, bool]:
    count = sum(finite(metrics.get(m)) for m in parameters.metrics)
    core = all(any(finite(metrics.get(m)) for m in dict(parameters.blocks)[b]) for b in ["value", "quality", "momentum"])
    return count, bool(count / len(parameters.metrics) >= parameters.min_score_coverage and core)


def compare_prices(yahoo: pd.DataFrame, archive: pd.DataFrame) -> dict:
    """Compare returns, not differently adjusted price levels. Not identity proof."""
    aligned = pd.concat([yahoo.adj_close.rename("yahoo"), archive.adj_close.rename("archive")], axis=1, sort=True).dropna()
    returns = aligned.pct_change(fill_method=None).dropna()
    if len(returns) < 60:
        return {"overlap_returns": len(returns), "status": "insufficient_overlap", "p99_return_difference": None}
    difference = (returns.yahoo - returns.archive).abs()
    q = float(difference.quantile(0.99))
    return {"overlap_returns": len(returns), "status": "consistent_overlap" if q <= 0.005 else "disagreement",
            "p99_return_difference": q, "max_return_difference": float(difference.max())}


