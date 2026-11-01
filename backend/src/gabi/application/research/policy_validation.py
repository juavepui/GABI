"""Economic validation of the investable policy of #248 with the V3 engine (#249).

On the same V2 signals and V3 inputs as the engine comparison, two allocations
of each rebalance's selection are executed:

- ``equal_weight``: the Top-N in equal weights, as the models do;
- ``limits``: the same selection through ``risk_policy.apply_limits`` (issuer and
  sector caps; what cannot be placed stays in cash, never leverage).

Each runs with a large account and with the small one #248 is about (initial
capital plus monthly contributions, a minimum order that keeps the fixed
commission under the policy's maximum cost share). The contributions wait in
cash until the next rebalance; the benchmark invests each one at the next
open. With contributions, returns and drawdowns are time-weighted.

The number of positions is the model's and is not optimised. Sectors are the
ones the point-in-time ranking used (an explicit approximation where there is
no historical snapshot); the issuer is the entity that owned the ticker.
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import date

from gabi.application.research import backtest_v3_comparison as comparison
from gabi.application.research.backtest_market import BacktestMarket
from gabi.application.research.backtest_v3_data import V3Data
from gabi.domain.portfolio import backtest_v3 as v3
from gabi.domain.portfolio import risk_policy

LARGE = {"initial": 100_000.0, "monthly": 0.0}
SMALL = {"initial": 11_000.0, "monthly": 700.0}  # #248: 11.000 and 700 a month, here in dollars.


def monthly_flows(sessions: list[date], amount: float) -> dict[date, float]:
    """``amount`` on the first session of every month after the first one."""
    if not amount:
        return {}
    firsts: dict[tuple[int, int], date] = {}
    for day in sessions:
        firsts.setdefault((day.year, day.month), day)
    return {day: amount for day in sorted(firsts.values())[1:]}


def allocations(market: BacktestMarket, rows: list[dict],
                sectors: Callable[[list[str], str], dict[str, str | None]],
                policy: risk_policy.Policy) -> tuple[dict[str, list[v3.Rebalance]], list[dict]]:
    equal, limited, notes = [], [], []
    for row in rows:
        symbols = sorted(row["weights"])
        issuers = {symbol: market.owner(symbol, row["as_of"]) or symbol for symbol in symbols}
        sector_of = sectors(symbols, row["as_of"])
        result = risk_policy.apply_limits(symbols, issuers, sector_of, policy)
        equal.append(v3.Rebalance(row["signal"], row["weights"]))
        limited.append(v3.Rebalance(row["signal"], result["weights"]))
        notes.append({"as_of": row["as_of"], "capped": result["capped"], "cash": result["cash"],
                      "unknown_sector": sorted(symbol for symbol in symbols if not sector_of.get(symbol))})
    return {"equal_weight": equal, "limits": limited}, notes


def validate(market: BacktestMarket, prepared: tuple[list[dict], list[date], V3Data], *,
             sectors: Callable[[list[str], str], dict[str, str | None]],
             policy: risk_policy.Policy | None = None, costs: v3.Costs = v3.BASE, benchmark: str = "SPY",
             accounts: dict[str, dict] | None = None) -> dict:
    policy = policy or risk_policy.Policy()
    rows, sessions, data = prepared
    plans, notes = allocations(market, rows, sectors, policy)
    results: dict[str, dict] = {}
    for account, setup in (accounts or {"large": LARGE, "small": SMALL}).items():
        flows = monthly_flows(sessions, setup["monthly"])
        # The fixed commission stays under the policy's maximum cost share of each order.
        account_costs = replace(costs, min_order=max(costs.min_order, costs.commission_fixed / policy.max_cost_share))
        reference = v3.benchmark(benchmark, sessions, data.bars, costs=account_costs, initial_cash=setup["initial"],
                                 flows=flows, events=data.events)
        reference_metrics = comparison.metrics(comparison._curve(reference), market.risk_free_rate,
                                               comparison._flows(reference))
        results[account] = {"setup": setup, "costs": account_costs.__dict__, "benchmark": reference_metrics}
        for name, rebalances in plans.items():
            run = v3.run(sessions, data.bars, rebalances=rebalances, costs=account_costs,
                         initial_cash=setup["initial"], flows=flows, events=data.events)
            curve, flow = comparison._curve(run), comparison._flows(run)
            result = comparison.metrics(curve, market.risk_free_rate, flow)
            cash_share = [row["cash"] / row["nav"] for row in run["daily"] if row["nav"] > 0]
            results[account][name] = {
                "metrics": result, "excess_cagr": result["cagr"] - reference_metrics["cagr"],
                "max_drawdown_vs_benchmark": result["max_drawdown"] - reference_metrics["max_drawdown"],
                "turnover_yearly": comparison._turnover(run, curve), "trades": len(run["trades"]),
                "costs": run["commissions"] + run["execution_costs"], "commissions": run["commissions"],
                "average_cash_share": sum(cash_share) / len(cash_share) if cash_share else None,
                "min_cash": run["min_cash"], "identity_error": run["identity_error"],
            }
    capped = [note for note in notes if note["capped"]]
    return {"policy": risk_policy.stored(policy), "rebalances": len(rows), "accounts": results,
            "rebalances_capped": len(capped), "average_limit_cash": sum(note["cash"] for note in notes) / len(notes),
            "unknown_sector_rows": sum(bool(note["unknown_sector"]) for note in notes), "allocation_notes": notes}
