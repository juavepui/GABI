"""V2/V3 comparison over the same signals and data (#249).

V2 decides each rebalance (historical universe, point-in-time ranking, rotation);
V3 executes those same equal-weight targets with its own accounting: signal at
the close, execution at the next open at nominal prices, costs within the cash,
splits and dividends as events and explicit exits. The difference between the
two is the engine's, not the strategy's: this is an engineering diagnostic and
inherits no evidence (ADR 0008).

Prices are read per rebalance window, as V2 reads them, for the symbols held on
entry and the new targets; overlapping bars keep the later window's series.
"""

import math
from collections.abc import Callable
from datetime import date

import pandas as pd

from gabi.application.errors import QueryError
from gabi.application.research import backtest_v3_data
from gabi.application.research.backtest_market import BacktestMarket, NoCoveredPeriods
from gabi.application.research.backtests import normalize_backtest
from gabi.application.research.historical import _json_value
from gabi.domain.portfolio import backtest as v2_rules
from gabi.domain.portfolio import backtest_v3 as v3

# Same costs as V2's defaults (1 $ per order, 10 bp full spread) and no liquidity cap:
# isolates execution timing, nominal prices and self-financing from the cost model.
V2_EQUIVALENT = v3.Costs(commission_fixed=1.0, spread_bps=10.0, participation=1.0, cost_reserve=0.0)
SCENARIOS = {"v2_equivalent": V2_EQUIVALENT, "base": v3.BASE, "stress": v3.STRESS}
EXIT_KINDS = {"cash_merger", "delisting", "bankruptcy"}


def _symbols(text: str) -> list[str]:
    return [symbol.strip() for symbol in str(text or "").split(",") if symbol.strip()]


def plan(market: BacktestMarket, periods: pd.DataFrame, top_n: int) -> list[dict]:
    """V2's executed rebalances as V3 targets, each with the window until the next one."""
    calendar = market.calendar
    rows = []
    for row in periods.itertuples(index=False):
        picks = sorted(set(_symbols(row.held)) | set(_symbols(row.bought)))
        signal = calendar.date_to_session(pd.Timestamp(row.fecha), direction="previous")
        rows.append({"as_of": row.fecha, "signal": signal.date(), "until": pd.Timestamp(row.hasta).date(),
                     "weights": {symbol: 1.0 / top_n for symbol in picks}})
    for index, row in enumerate(rows):
        row["end"] = rows[index + 1]["signal"] if index + 1 < len(rows) else row["until"]
        row["symbols"] = sorted(set(row["weights"]) | set(rows[index - 1]["weights"] if index else ()))
    return rows


def inputs(market: BacktestMarket, rows: list[dict], splits: Callable[[list[str]], dict[str, pd.Series]],
           benchmark: str) -> tuple[list[date], backtest_v3_data.V3Data]:
    calendar = market.calendar
    sessions = [day.date() for day in calendar.sessions_in_range(pd.Timestamp(rows[0]["signal"]),
                                                                  pd.Timestamp(rows[-1]["end"]))]
    bars: dict[str, dict[date, v3.Bar]] = {}
    events: dict[tuple, v3.Event] = {}
    anomalies: list[dict] = []
    missing: set[str] = set()
    exits: list[dict] = []
    bases: dict[str, str] = {}
    windows = [(row["as_of"], row["signal"], row["end"], row["symbols"]) for row in rows]
    windows.append((rows[0]["as_of"], sessions[0], sessions[-1], [benchmark]))
    for as_of, start, end, symbols in windows:
        frames = market.prices(symbols, as_of)
        window = [day for day in sessions if start <= day <= end]

        def terminal_event(symbol: str, frame: pd.DataFrame, start=start, end=end) -> dict | None:
            owner = frame.attrs.get("entity_id")
            if not owner:
                return None
            return market.exit_value(frame, owner, pd.Timestamp(start), pd.Timestamp(end)).get("event")

        data = backtest_v3_data.load(frames, splits, start=start, end=end, sessions=window,
                                     terminal_event=terminal_event)
        for symbol, series in data.bars.items():
            bars.setdefault(symbol, {}).update(series)
        for event in data.events:
            events[(event.kind, event.symbol, event.day)] = event
        anomalies += data.anomalies
        missing |= set(data.missing)
        exits += data.exits
        bases |= data.bases
    # An exit is real only if no later window prices the symbol from its day on.
    real = {key: event for key, event in events.items()
            if event.kind not in EXIT_KINDS or not any(day >= event.day for day in bars.get(event.symbol, {}))}
    exits = [record for record in exits if (record["symbol"], date.fromisoformat(record["day"])) in
             {(event.symbol, event.day) for event in real.values() if event.kind in EXIT_KINDS}]
    unique_anomalies = list({(item["symbol"], item["day"]): item for item in anomalies}.values())
    priced = {symbol for symbol, series in bars.items() if series}
    return sessions, backtest_v3_data.V3Data(bars, list(real.values()), unique_anomalies,
                                             sorted(missing - priced), bases, exits)


def metrics(curve: pd.Series, risk_free_rate: float, flows: pd.Series | None = None) -> dict:
    """Return, drawdown and risk of a NAV curve; with flows, of its time-weighted index."""
    curve = curve.dropna()
    index = curve if flows is None else time_weighted(curve, flows)
    risk = v2_rules.daily_risk_metrics(index, risk_free_rate=risk_free_rate)
    years = max((index.index[-1] - index.index[0]).days / 365.25, 1e-9)
    cagr = (index.iloc[-1] / index.iloc[0]) ** (1 / years) - 1 if index.iloc[0] > 0 else math.nan
    result = {"start": curve.index[0].date().isoformat(), "end": curve.index[-1].date().isoformat(),
              "initial": float(curve.iloc[0]), "final": float(curve.iloc[-1]), "cagr": float(cagr),
              "max_drawdown": float((index / index.cummax() - 1).min()), "risk": risk}
    if flows is not None:
        result["contributed"] = float(curve.iloc[0] + flows.iloc[1:].sum())
    return result


def time_weighted(curve: pd.Series, flows: pd.Series) -> pd.Series:
    """Index of the NAV net of contributions: each day's flow arrives before its valuation."""
    flows = flows.reindex(curve.index, fill_value=0.0)
    returns = ((curve - flows) / curve.shift()).fillna(1.0)
    return returns.where(curve.shift() > 0, 1.0).cumprod()


def _curve(result: dict) -> pd.Series:
    return pd.Series({pd.Timestamp(row["day"]): row["nav"] for row in result["daily"]}, dtype=float)


def _flows(result: dict) -> pd.Series:
    return pd.Series({pd.Timestamp(row["day"]): row["flow"] for row in result["daily"]}, dtype=float)


def _turnover(result: dict, curve: pd.Series) -> float:
    """Average yearly traded notional over the average NAV."""
    traded = sum(trade["notional"] for trade in result["trades"])
    years = max((curve.index[-1] - curve.index[0]).days / 365.25, 1e-9)
    return float(traded / curve.mean() / years) if curve.mean() > 0 else math.nan


def prepare(market: BacktestMarket, v2_result: dict, *, top_n: int,
            splits: Callable[[list[str]], dict[str, pd.Series]], benchmark: str = "SPY"
            ) -> tuple[list[dict], list[date], backtest_v3_data.V3Data]:
    """V2's signals and V3's inputs for them, read once for every comparison."""
    periods = v2_result["periods"]
    if periods is None or periods.empty:
        raise ValueError("V2 no ejecutó ningún rebalanceo: no hay señales que comparar.")
    rows = plan(market, periods, top_n)
    sessions, data = inputs(market, rows, splits, benchmark)
    if not data.bars.get(benchmark):
        raise ValueError(f"Faltan precios de {benchmark} para el benchmark de V3.")
    return rows, sessions, data


def compare(market: BacktestMarket, v2_result: dict, *, top_n: int, splits: Callable[[list[str]], dict[str, pd.Series]],
            benchmark: str = "SPY", scenarios: dict[str, v3.Costs] | None = None,
            prepared: tuple[list[dict], list[date], backtest_v3_data.V3Data] | None = None) -> dict:
    rows, sessions, data = prepared or prepare(market, v2_result, top_n=top_n, splits=splits, benchmark=benchmark)
    initial = float(v2_result["initial_capital"])
    rebalances = [v3.Rebalance(row["signal"], row["weights"]) for row in rows]
    engines = {}
    for name, costs in (scenarios or SCENARIOS).items():
        result = v3.run(sessions, data.bars, rebalances=rebalances, costs=costs, initial_cash=initial,
                        events=data.events)
        reference = v3.benchmark(benchmark, sessions, data.bars, costs=costs, initial_cash=initial, events=data.events)
        curve, reference_curve = _curve(result), _curve(reference)
        engines[name] = {
            "costs": costs.__dict__, "metrics": metrics(curve, market.risk_free_rate),
            "benchmark": metrics(reference_curve, market.risk_free_rate),
            "excess_cagr": metrics(curve, market.risk_free_rate)["cagr"]
            - metrics(reference_curve, market.risk_free_rate)["cagr"],
            "turnover_yearly": _turnover(result, curve), "commissions": result["commissions"],
            "execution_costs": result["execution_costs"], "dividends": result["dividends"],
            "trades": len(result["trades"]), "partial_trades": sum(trade["partial"] for trade in result["trades"]),
            "blocked_orders": len(result["blocked"]), "stale_days": len(result["stale"]),
            "min_cash": result["min_cash"], "identity_error": result["identity_error"],
        }
    v2_curve, v2_benchmark = v2_result["nav_curve"], v2_result["nav_curve_spy"]
    v2_metrics, v2_reference = (metrics(v2_curve, market.risk_free_rate),
                                metrics(v2_benchmark, market.risk_free_rate))
    return {
        "version": v3.VERSION, "rebalances": len(rows), "sessions": len(sessions),
        "v2": {"metrics": v2_metrics, "benchmark": v2_reference,
               "excess_cagr": v2_metrics["cagr"] - v2_reference["cagr"],
               "commissions": float(v2_result["comision_total"]), "spread": float(v2_result["spread_total"]),
               "strict": bool(v2_result.get("strict_result", True)), "skipped": len(v2_result.get("skipped", []))},
        "v3": engines,
        "data": {"missing": data.missing, "anomalies": data.anomalies, "exits": data.exits, "strict": data.strict,
                 "bases": {basis: sum(value == basis for value in data.bases.values())
                           for basis in sorted(set(data.bases.values()))}},
    }


KIND = "backtest_v3_comparison"
MAX_ROWS = 500  # Each listed detail (missing series, anomalies, exits, allocation notes) is bounded.


def build(start: str, end: str, options: dict, run: Callable[[str, str, dict], dict]) -> dict:
    """The comparison job: V2's options and observed period, an engine diagnostic artifact.

    The dates go through the same check as a V2 backtest, so no run reads a
    reserved period, whatever calls it."""
    options = normalize_backtest("backtest_v2", start, end, options)
    try:
        result = run(start, end, options)
    except NoCoveredPeriods as exc:
        raise QueryError("no_covered_periods", str(exc), 422) from exc
    truncated = []
    for section, key in (("data", "missing"), ("data", "anomalies"), ("data", "exits"),
                         ("policy_248", "allocation_notes")):
        rows = result.get(section, {}).get(key)
        if isinstance(rows, list) and len(rows) > MAX_ROWS:
            result[section][key] = rows[:MAX_ROWS]
            truncated.append(f"{section}.{key}")
    artifact = {"kind": KIND, "status": "ENGINE_DIAGNOSTIC", "independent_advantage_demonstrated": False,
                "start": start, "end": end, "options": options, "truncated": truncated,
                **{key: value for key, value in result.items() if key not in {"kind", "status"}}}
    return _json_value(artifact)  # type: ignore[return-value]
