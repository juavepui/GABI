"""Exploratory evaluation of NSI-v1 (#252), exactly as preregistered in ``docs/research/nsi-v1/preregistro.json``.

Over the observed history (signals in July 2011–2024, last window ending on the
2025 signal, inside the observed period), each configuration selects once a year
with :mod:`nsi_portfolio`, weights with the #248 limits and runs in the V3 engine
with a euro account: 11,000 € initial and 700 € a month, converted to dollars at
the day's rate net of the broker's deposit conversion cost and, by amendment 1,
invested at the next open in the current selection, 15 % dividend
withholding, and the same calendar, flows and accounting for the S&P 500 (SPY).
Results are measured in euros, time-weighted. The comparators are the equally
weighted universe with data and the FF5+UMD regression.

This reuses observed history: its result can never count as independent evidence.
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import date

import pandas as pd

from gabi.application.research import backtest_v3_comparison as comparison
from gabi.application.research import policy_validation
from gabi.application.research.backtest_market import BacktestMarket
from gabi.application.research.reservations import require_observed_period
from gabi.domain.portfolio import backtest_v3 as v3
from gabi.domain.portfolio import risk_policy
from gabi.domain.portfolio.broker_costs import DEPOSIT_FX_PCT_BANK_TRANSFER
from gabi.domain.research import net_issuance, nsi_portfolio
from gabi.domain.research import nsi_statistics as stats

CONFIGURATIONS = {"primary": (20, "BASE"), "stress": (20, "STRESS"), "top30": (30, "BASE")}
COSTS = {"BASE": v3.BASE, "STRESS": v3.STRESS}
INITIAL_EUR, MONTHLY_EUR = 11_000.0, 700.0
WITHHOLDING = 0.15
FX_COST = DEPOSIT_FX_PCT_BANK_TRANSFER / 100  # The owner's broker, verified on its conversions.
BENCHMARK = "SPY"
WINDOWS = (("2011-07-01", "2016-06-30"), ("2016-07-01", "2021-06-30"), ("2021-07-01", "2025-07-01"))


def selections(signals: list[date], members: dict[date, dict[str, str | None]], *, facts: Callable[[str], dict],
               sic: Callable[[str], int | None], top_n: int) -> list[dict]:
    """One row per yearly window: the preregistered selection at its signal, held names carried over."""
    rows: list[dict] = []
    held: set[str] = set()
    for signal, end in zip(signals[:-1], signals[1:], strict=True):
        issuers = {symbol: cik for symbol, cik in members[signal].items() if cik}
        values = {}
        for symbol, cik in issuers.items():
            value = net_issuance.issuance(facts(cik), signal)
            if value.state == "computed" and value.value is not None:
                values[symbol] = value.value
        chosen = nsi_portfolio.select(values, {symbol: sic(issuers[symbol]) for symbol in values}, held,
                                      top_n=top_n)
        rows.append({"as_of": signal.isoformat(), "signal": signal, "end": end, "selected": chosen["selected"],
                     "symbols": sorted(set(chosen["selected"]) | held), "issuers": issuers, "ranked": len(values),
                     "kept": len(chosen["kept"]), "capped_by_division": len(chosen["capped_by_division"])})
        held = set(chosen["selected"])
    return rows


def weights(row: dict, top_n: int, sectors: dict[str, str | None], policy: risk_policy.Policy) -> tuple[dict, bool]:
    """#248 limits over a Top-N whose empty slots stay in cash.

    Each empty slot takes part as its own issuer and sector, so every name starts
    at 1/top_n and the caps act on the real names only; the slots' weight is cash."""
    selected = row["selected"]
    if not selected:
        return {}, False
    slots = [f"__cash_{index}" for index in range(max(top_n - len(selected), 0))]
    limited = risk_policy.apply_limits(selected + slots,
                                       {**{symbol: row["issuers"][symbol] for symbol in selected},
                                        **{slot: slot for slot in slots}},
                                       {**sectors, **{slot: slot for slot in slots}}, policy)
    real = {symbol: weight for symbol, weight in limited["weights"].items() if symbol in selected}
    return real, bool(set(limited["capped"]) & set(selected))


def with_contributions(row: dict, target: dict[str, float], flows: dict[date, float]) -> list[v3.Rebalance]:
    """Amendment 1 (2026-11-01, before any return): each contribution day inside the window re-targets the
    window's selection, so the contribution is invested at the next open instead of waiting for July."""
    days = sorted(day for day in flows if row["signal"] < day < row["end"])
    return [v3.Rebalance(row["signal"], target), *(v3.Rebalance(day, target) for day in days)]


def _rates(sessions: list[date], euros_per_dollar: pd.Series) -> pd.Series:
    rates = euros_per_dollar.sort_index()
    rates.index = pd.to_datetime(rates.index)
    days = pd.to_datetime(pd.Series(sessions))
    aligned = rates.reindex(rates.index.union(days)).ffill().reindex(days)
    if aligned.isna().any():
        missing = days[aligned.isna().to_numpy()].dt.date.iloc[0]
        raise ValueError(f"Falta el cambio USDEUR=X el {missing}: actualiza el benchmark antes de evaluar.")
    return pd.Series(aligned.to_numpy(dtype=float), index=days)


def _account(sessions: list[date], rates: pd.Series) -> tuple[float, dict[date, float], pd.Series]:
    """Initial dollars, dollar flows and the euro flows they come from (gross, before conversion cost)."""
    rate = {day.date(): value for day, value in rates.items()}
    euros = policy_validation.monthly_flows(sessions, MONTHLY_EUR)
    initial = INITIAL_EUR * (1 - FX_COST) / rate[sessions[0]]
    dollars = {day: amount * (1 - FX_COST) / rate[day] for day, amount in euros.items()}
    flows_eur = pd.Series({pd.Timestamp(day): amount for day, amount in euros.items()}, dtype=float)
    return initial, dollars, flows_eur


def _measure(result: dict, rates: pd.Series, flows_eur: pd.Series, risk_free_rate: float) -> dict:
    usd = comparison._curve(result)
    eur = usd * rates.reindex(usd.index).to_numpy()
    flows = flows_eur.reindex(eur.index, fill_value=0.0)
    index_eur = comparison.time_weighted(eur, flows)
    index_usd = comparison.time_weighted(usd, comparison._flows(result))
    cash = [row["cash"] / row["nav"] for row in result["daily"] if row["nav"] > 0]
    return {"metrics_eur": comparison.metrics(eur, risk_free_rate, flows), "index_eur": index_eur,
            "index_usd": index_usd, "turnover_yearly": comparison._turnover(result, usd),
            "costs_usd": result["commissions"] + result["execution_costs"], "dividends_usd": result["dividends"],
            "trades": len(result["trades"]), "blocked_orders": len(result["blocked"]),
            "stale_days": len(result["stale"]), "average_cash_share": sum(cash) / len(cash) if cash else None,
            "identity_error": result["identity_error"], "min_cash": result["min_cash"]}


def _windows(strategy: pd.Series, benchmark: pd.Series) -> list[dict]:
    excess = stats.monthly(strategy) - stats.monthly(benchmark)
    rows = []
    for start, end in WINDOWS:
        part = excess[(excess.index >= pd.Timestamp(start)) & (excess.index <= pd.Timestamp(end))]
        rows.append({"start": start, "end": end, **stats.lower_bound(part)})
    return rows


def evaluate(signals: list[date], members: dict[date, dict[str, str | None]], *, market: BacktestMarket,
             facts: Callable[[str], dict], sic: Callable[[str], int | None],
             sectors: Callable[[list[str], str], dict[str, str | None]],
             splits: Callable[[list[str]], dict[str, pd.Series]], euros_per_dollar: pd.Series,
             factors: pd.DataFrame, progress: Callable[[str], None] = lambda message: None) -> dict:
    signals = sorted(signals)
    require_observed_period(signals[0].isoformat(), signals[-1].isoformat())
    policy = risk_policy.Policy()
    results: dict[str, dict] = {}
    prepared: dict[int, tuple] = {}
    for name, (top_n, scenario) in CONFIGURATIONS.items():
        if top_n not in prepared:
            progress(f"Selección Top-{top_n}")
            rows = selections(signals, members, facts=facts, sic=sic, top_n=top_n)
            progress(f"Datos V3 Top-{top_n}")
            sessions, data = comparison.inputs(market, rows, splits, BENCHMARK)
            prepared[top_n] = (rows, sessions, data)
        rows, sessions, data = prepared[top_n]
        rates = _rates(sessions, euros_per_dollar)
        initial, dollars, flows_eur = _account(sessions, rates)
        costs = replace(COSTS[scenario], dividend_withholding=WITHHOLDING,
                        min_order=max(COSTS[scenario].min_order,
                                      COSTS[scenario].commission_fixed / policy.max_cost_share))
        plan, capped = [], 0
        for row in rows:
            target, limited = weights(row, top_n, sectors(row["selected"], row["as_of"]), policy)
            plan += with_contributions(row, target, dollars)
            capped += limited
        progress(f"Motor V3 {name}")
        run = v3.run(sessions, data.bars, rebalances=plan, costs=costs, initial_cash=initial, flows=dollars,
                     events=data.events)
        reference = v3.benchmark(BENCHMARK, sessions, data.bars, costs=costs, initial_cash=initial, flows=dollars,
                                 events=data.events)
        strategy = _measure(run, rates, flows_eur, market.risk_free_rate)
        bench = _measure(reference, rates, flows_eur, market.risk_free_rate)
        windows = _windows(strategy["index_eur"], bench["index_eur"])
        overall = stats.lower_bound(stats.monthly(strategy["index_eur"]) - stats.monthly(bench["index_eur"]))
        alpha = stats.factor_alpha(stats.monthly(strategy["index_usd"]), factors)
        excess = strategy["metrics_eur"]["cagr"] - bench["metrics_eur"]["cagr"]
        volatility = (strategy["index_eur"].pct_change().std() / bench["index_eur"].pct_change().std())
        results[name] = {
            "top_n": top_n, "costs": scenario, "strategy": _public(strategy), "benchmark": _public(bench),
            "net_excess_cagr_eur": excess, "overall": overall, "windows": windows, "alpha_ff5_umd": alpha,
            "risk": {"volatility_ratio": float(volatility), "volatility_ok": bool(volatility <= 1.10),
                     "drawdown_vs_index": strategy["metrics_eur"]["max_drawdown"] - bench["metrics_eur"]["max_drawdown"],
                     "drawdown_ok": bool(strategy["metrics_eur"]["max_drawdown"]
                                         - bench["metrics_eur"]["max_drawdown"] >= -0.05)},
            "rebalances_capped_by_policy": capped,
            "decision": stats.decide(excess, [row["lower_bound_annual"] for row in windows], alpha),
        }
    results["primary"]["decision"]["applies"] = True
    for name in ("stress", "top30"):
        results[name]["decision"]["applies"] = False  # Sensitivities: reported, not decisive.
    progress("Equiponderado del universo")
    rows, sessions, data = prepared[20]
    comparator = _equal_weight(signals, members, rows, market, splits, facts, euros_per_dollar)
    return {"version": net_issuance.VERSION, "returns_read": True, "exploratory": True,
            "independent_evidence": False, "signals": [day.isoformat() for day in signals],
            "selections": [{key: row[key] for key in ("as_of", "selected", "ranked", "kept", "capped_by_division")}
                           for row in prepared[20][0]],
            "configurations": results, "equal_weight_universe": comparator,
            "data": {"missing": data.missing, "exits": data.exits, "anomalies": len(data.anomalies),
                     "strict": data.strict, "bases": _count(data.bases)},
            "decision": results["primary"]["decision"],
            "amendments": [{"id": 1, "date": "2026-11-01", "ref": "docs/research/nsi-v1/enmienda-1.json",
                            "rule": "cada aportación se invierte en la apertura siguiente en la selección vigente"}],
            "assumptions": {"fx_deposit_cost": FX_COST, "dividend_withholding": WITHHOLDING,
                            "initial_conversion_cost_outside_metrics": True,
                            "alpha_rule": "intervalo del 95 % del alfa anual contiene el cero",
                            "sic": "SIC actual de submissions, no fechado",
                            "sectors_for_policy": "sector point-in-time de entity_master (GICS)"}}


def _count(bases: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for basis in bases.values():
        counts[basis] = counts.get(basis, 0) + 1
    return counts


def _public(measured: dict) -> dict:
    return {key: value for key, value in measured.items() if key not in {"index_eur", "index_usd"}}


def _equal_weight(signals: list[date], members: dict[date, dict[str, str | None]], rows: list[dict],
                  market: BacktestMarket, splits: Callable[[list[str]], dict[str, pd.Series]],
                  facts: Callable[[str], dict], euros_per_dollar: pd.Series) -> dict:
    """Every member with an issuance value, equally weighted, rebalanced on the same dates and costs (BASE)."""
    universe_rows: list[dict] = []
    held: set[str] = set()
    for row in rows:
        signal = row["signal"]
        names = [symbol for symbol, cik in members[signal].items()
                 if cik and net_issuance.issuance(facts(cik), signal).state == "computed"]
        universe_rows.append({"as_of": row["as_of"], "signal": signal, "end": row["end"],
                              "symbols": sorted(set(names) | held), "selected": names})
        held = set(names)
    sessions, data = comparison.inputs(market, universe_rows, splits, BENCHMARK)
    rates = _rates(sessions, euros_per_dollar)
    initial, dollars, flows_eur = _account(sessions, rates)
    costs = replace(v3.BASE, dividend_withholding=WITHHOLDING)
    plan = [rebalance for row in universe_rows if row["selected"] for rebalance in with_contributions(
        row, {symbol: 1 / len(row["selected"]) for symbol in row["selected"]}, dollars)]
    run = v3.run(sessions, data.bars, rebalances=plan, costs=costs, initial_cash=initial, flows=dollars,
                 events=data.events)
    measured = _measure(run, rates, flows_eur, market.risk_free_rate)
    return {**_public(measured), "missing_series": len(data.missing), "note": "comparador; no decide"}
