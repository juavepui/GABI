"""Investor profile, contributions in EUR and flow-adjusted performance (#244).

The same euros on the same days buy the portfolio and the benchmark, so the
comparison only differs in what was bought. Prices are total return (dividends
reinvested in the series), so dividends are not added again. A real vehicle
(an accumulating ETF) is priced net of its TER; only a theoretical index takes
an explicit annual cost, so fees are never counted twice. The exchange rate is
one dated series in vehicle currency per euro (``EURUSD=X`` for USD).

Performance separates skill from experience: the unitised NAV gives the
time-weighted return and a drawdown that new money cannot hide; XIRR and final
wealth describe what the investor lived. The loss tolerance is a review
threshold, never a guarantee or an automatic sale. Nothing here downloads: a
missing price or rate leaves the contribution pending and is reported.
"""

import calendar
import math
from dataclasses import dataclass
from datetime import date

import pandas as pd

PROFILE_VERSION = "investor-profile-v1"
CURRENCIES = ("EUR", "USD")
XIRR_BOUNDS = (-0.99, 10.0)


@dataclass(frozen=True)
class Profile:
    initial_eur: float
    monthly_eur: float
    horizon_months: int
    loss_tolerance: float
    capital_needed_by: date | None = None
    tax_residence: str | None = None
    # The investor's broker: applied identically to every vehicle the contributions buy.
    commission_fixed_eur: float = 0.0
    commission_pct: float = 0.0
    fx_cost_pct: float = 0.0
    min_order_eur: float = 0.0
    fractional: bool = True
    version: str = PROFILE_VERSION


@dataclass(frozen=True)
class Vehicle:
    """What the euros buy: a tradable vehicle or a theoretical index with its declared costs."""

    symbol: str
    currency: str = "USD"
    fractional: bool = True
    commission_fixed_eur: float = 0.0
    commission_pct: float = 0.0
    fx_cost_pct: float = 0.0
    min_order_eur: float = 0.0
    annual_cost_pct: float = 0.0  # Only for a theoretical index; an ETF price is already net of TER.
    theoretical: bool = False


def validate_profile(raw: dict, today: date) -> Profile:
    """The stored profile, or ValueError with the reason in Spanish."""
    try:
        initial = float(raw["initial_eur"])
        monthly = float(raw.get("monthly_eur") or 0)
        horizon = int(raw["horizon_months"])
        tolerance = float(raw["loss_tolerance"])
        needed = raw.get("capital_needed_by")
        needed = None if needed in (None, "") else (
            needed if isinstance(needed, date) else date.fromisoformat(str(needed).strip()))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Capital inicial, aportación, horizonte, tolerancia y fecha deben ser válidos.") from exc
    if not (0 <= initial <= 1e9 and 0 <= monthly <= 1e8) or initial + monthly <= 0:
        raise ValueError("El capital inicial y la aportación no pueden ser negativos y alguno debe ser positivo.")
    if not 1 <= horizon <= 600:
        raise ValueError("El horizonte debe estar entre 1 y 600 meses.")
    if not 0 < tolerance < 1:
        raise ValueError("La tolerancia de pérdida debe estar entre 0 % y 100 %.")
    if needed is not None and needed <= today:
        raise ValueError("La fecha en que se necesita el dinero debe ser futura.")
    residence = str(raw.get("tax_residence") or "").strip().upper()[:2] or None
    try:
        costs = {key: float(raw.get(key) or 0) for key in
                 ("commission_fixed_eur", "commission_pct", "fx_cost_pct", "min_order_eur")}
    except (TypeError, ValueError) as exc:
        raise ValueError("Los costes del bróker deben ser números.") from exc
    if not (0 <= costs["commission_fixed_eur"] <= 1000 and 0 <= costs["min_order_eur"] <= 1e6
            and 0 <= costs["commission_pct"] < 0.1 and 0 <= costs["fx_cost_pct"] < 0.1):
        raise ValueError("Los costes del bróker deben ser no negativos y los porcentajes menores del 10 %.")
    return Profile(initial, monthly, horizon, tolerance, needed, residence,
                   commission_fixed_eur=costs["commission_fixed_eur"], commission_pct=costs["commission_pct"],
                   fx_cost_pct=costs["fx_cost_pct"], min_order_eur=costs["min_order_eur"],
                   fractional=bool(raw.get("fractional", True)))


def broker_vehicle(profile: Profile, symbol: str, currency: str, *, annual_cost_pct: float = 0.0,
                   theoretical: bool = False) -> Vehicle:
    """``symbol`` bought through the investor's broker, so portfolio and benchmark pay the same costs."""
    return Vehicle(symbol, currency, profile.fractional, profile.commission_fixed_eur, profile.commission_pct,
                   profile.fx_cost_pct, profile.min_order_eur, annual_cost_pct, theoretical)


def capital_need_before_horizon(profile: Profile, start: date) -> bool | None:
    """True if the money is needed before the evaluation horizon ends; None when the date is unknown."""
    if profile.capital_needed_by is None:
        return None
    return profile.capital_needed_by < add_months(start, profile.horizon_months)


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def schedule(profile: Profile, start: date, end: date) -> list[tuple[date, float]]:
    """The initial capital on ``start`` and the monthly contribution on the same day of each later month."""
    flows = [(start, profile.initial_eur)] if profile.initial_eur > 0 else []
    month = 1
    while profile.monthly_eur > 0 and (day := add_months(start, month)) <= end:
        flows.append((day, profile.monthly_eur))
        month += 1
    return flows


def _session_on_or_after(series: pd.Series, day: pd.Timestamp) -> pd.Timestamp | None:
    later = series.index[series.index >= day]
    return later[0] if len(later) else None


def simulate(flows: list[tuple[date, float]], prices: pd.Series, vehicle: Vehicle,
             fx_per_eur: pd.Series | None = None) -> dict:
    """Daily EUR wealth of buying ``vehicle`` with ``flows`` (date, euros) at total-return ``prices``.

    A contribution executes at the first session on or after its date with price
    and rate; euros below the minimum order wait and accumulate. Whole shares
    leave the remainder as cash in the vehicle currency. Costs are deducted from
    the contribution, never from returns. Returns the daily frame, total costs
    and the contributions still pending at the end of the series."""
    if vehicle.currency not in CURRENCIES:
        raise ValueError(f"Divisa no admitida: {vehicle.currency}.")
    prices = prices.dropna().sort_index()
    prices = prices[prices > 0]
    if vehicle.currency != "EUR":
        if fx_per_eur is None:
            raise ValueError(f"Falta el cambio EUR/{vehicle.currency}.")
        fx = fx_per_eur.dropna().sort_index()
        fx = fx[fx > 0].reindex(prices.index).ffill(limit=5)
    else:
        fx = pd.Series(1.0, index=prices.index)
    sessions = fx.dropna().index
    if sessions.empty:
        raise ValueError(f"No hay sesiones con precio y cambio para {vehicle.symbol}.")
    pending_eur, cash_quote, units, contributed, costs = 0.0, 0.0, 0.0, 0.0, 0.0
    queue = sorted((pd.Timestamp(day), float(amount)) for day, amount in flows if amount > 0)
    rows, previous = [], None
    for session in sessions:
        price, rate = float(prices[session]), float(fx[session])
        if previous is not None and vehicle.annual_cost_pct:
            units *= (1 - vehicle.annual_cost_pct) ** ((session - previous).days / 365)
        flow = 0.0
        while queue and queue[0][0] <= session:
            flow += queue.pop(0)[1]
        pending_eur += flow
        contributed += flow
        if pending_eur > 0 and pending_eur >= vehicle.min_order_eur:
            commission = vehicle.commission_fixed_eur + pending_eur * vehicle.commission_pct
            net_eur = max(pending_eur - commission, 0.0)
            fx_cost = net_eur * vehicle.fx_cost_pct if vehicle.currency != "EUR" else 0.0
            cash_quote += (net_eur - fx_cost) * rate
            costs += pending_eur - net_eur + fx_cost
            pending_eur = 0.0
            bought = cash_quote / price if vehicle.fractional else math.floor(cash_quote / price + 1e-9)
            units += bought
            cash_quote -= bought * price
        value = pending_eur + (units * price + cash_quote) / rate
        rows.append({"date": session, "flow_eur": flow, "contributed_eur": contributed, "units": units,
                     "price": price, "fx_per_eur": rate, "value_eur": value})
        previous = session
    frame = pd.DataFrame(rows).set_index("date")
    unexecuted = [(day.date(), amount) for day, amount in queue]
    return {"vehicle": vehicle.symbol, "theoretical": vehicle.theoretical, "daily": frame, "costs_eur": costs,
            "pending": unexecuted, "pending_eur": pending_eur}


def unitised_nav(values: pd.Series, flows: pd.Series) -> pd.Series:
    """Unit value with external flows entering at the day's close: the basis of TWR and drawdown."""
    nav, units, previous = [], 0.0, 1.0
    for day, value in values.items():
        flow = float(flows.get(day, 0.0))
        if units <= 0:
            unit_value = previous
        else:
            unit_value = (float(value) - flow) / units
        units += flow / unit_value if unit_value > 0 else 0.0
        nav.append(unit_value)
        previous = unit_value
    return pd.Series(nav, index=values.index, dtype=float)


def xirr(flows: list[tuple[date, float]], final_day: date, final_value: float) -> float | None:
    """Money-weighted annual return of contributions (outflows) against the final wealth."""
    cash = [(day, -amount) for day, amount in flows if amount] + [(final_day, final_value)]
    if not flows or final_value < 0 or (final_day - min(day for day, _ in cash)).days <= 0:
        return None
    first = min(day for day, _ in cash)

    def npv(rate: float) -> float:
        return sum(amount / (1 + rate) ** ((day - first).days / 365) for day, amount in cash)

    low, high = XIRR_BOUNDS
    f_low, f_high = npv(low), npv(high)
    if f_low * f_high > 0:
        return None
    for _ in range(200):
        middle = (low + high) / 2
        f_middle = npv(middle)
        if f_low * f_middle <= 0:
            high = middle
        else:
            low, f_low = middle, f_middle
    return (low + high) / 2


def performance(result: dict, profile: Profile, executed_flows: list[tuple[date, float]] | None = None) -> dict:
    """Skill (TWR, unitised drawdown) and experience (XIRR, wealth, loss over contributions, euros at risk)."""
    daily = result["daily"]
    invested = daily[daily["contributed_eur"] > 0]
    if invested.empty:
        return {"status": "no_contributions"}
    nav = unitised_nav(invested["value_eur"], invested["flow_eur"])
    drawdown = nav / nav.cummax() - 1
    gain = invested["value_eur"] - invested["contributed_eur"]
    loss_on_contributions = gain / invested["contributed_eur"]
    years = (invested.index[-1] - invested.index[0]).days / 365
    twr = float(nav.iloc[-1] / nav.iloc[0] - 1)
    flows = executed_flows or [(day.date(), float(flow)) for day, flow in invested["flow_eur"].items() if flow]
    breach = drawdown[drawdown <= -profile.loss_tolerance]
    return {
        "status": "ok",
        "start": invested.index[0].date(), "end": invested.index[-1].date(),
        "contributed_eur": float(invested["contributed_eur"].iloc[-1]),
        "final_value_eur": float(invested["value_eur"].iloc[-1]),
        "costs_eur": float(result["costs_eur"]),
        "pending_eur": float(result["pending_eur"]),
        "twr": twr,
        "twr_annualised": (1 + twr) ** (1 / years) - 1 if years >= 1 else None,
        "xirr": xirr(flows, invested.index[-1].date(), float(invested["value_eur"].iloc[-1])),
        "max_drawdown": float(drawdown.min()),
        "current_drawdown": float(drawdown.iloc[-1]),
        "max_loss_on_contributions": float(min(loss_on_contributions.min(), 0.0)),
        "max_euros_lost": float(min(gain.min(), 0.0)),
        "euros_at_risk_at_tolerance": float(invested["value_eur"].iloc[-1] * profile.loss_tolerance),
        # A review threshold: GABI never sells automatically.
        "review_threshold_reached_on": breach.index[0].date() if not breach.empty else None,
    }


def compare(portfolio: dict, benchmark: dict) -> dict:
    """Differences between two performances computed from the same contributions."""
    if portfolio.get("status") != "ok" or benchmark.get("status") != "ok":
        return {"status": "incomplete"}
    if abs(portfolio["contributed_eur"] - benchmark["contributed_eur"]) > 0.01:
        raise ValueError("La cartera y el benchmark deben recibir las mismas aportaciones.")

    def difference(key: str) -> float | None:
        a, b = portfolio.get(key), benchmark.get(key)
        return None if a is None or b is None else a - b

    return {"status": "ok", "wealth_difference_eur": difference("final_value_eur"),
            "twr_difference": difference("twr"), "xirr_difference": difference("xirr"),
            "max_drawdown_difference": difference("max_drawdown")}


def _at_or_before(series: pd.Series, day: pd.Timestamp, lookback_days: int = 7) -> float | None:
    if series.empty:
        return None
    recent = series[(series.index <= day) & (series.index >= day - pd.Timedelta(days=lookback_days))]
    return float(recent.iloc[-1]) if not recent.empty else None


def lots_history(lots: list[dict], adjusted: dict[str, pd.Series], euros_per_unit: dict[str, pd.Series],
                 sessions: pd.DatetimeIndex) -> dict:
    """Daily EUR value of real purchase lots, as a simulation result for ``performance``.

    Each lot is a contribution of its cost with commission, converted with the
    rate the broker applied or else the cached rate of its date. Its value
    follows the adjusted close from the purchase (total return, like the
    benchmark) and the cached rate of each session. A lot without the price or
    rate of its purchase is excluded and reported, so that the same flows can buy
    the benchmark."""
    sessions = sessions.sort_values()
    total = pd.Series(0.0, index=sessions)
    flows = pd.Series(0.0, index=sessions)
    commissions, excluded, executed = 0.0, [], []
    by_currency: dict[str, pd.Series] = {}
    for lot in lots:
        symbol, currency = lot["symbol"], lot["currency"]
        bought = pd.Timestamp(lot["purchase_date"])
        prices = adjusted.get(symbol, pd.Series(dtype=float)).dropna()
        rates = pd.Series(1.0, index=sessions) if currency == "EUR" \
            else euros_per_unit.get(currency, pd.Series(dtype=float)).dropna()
        price_then = _at_or_before(prices, bought)
        rate_then = lot.get("fx_rate") or (1.0 if currency == "EUR" else _at_or_before(rates, bought))
        later = sessions[sessions >= bought]
        reason = ("missing_price" if price_then is None else "missing_fx" if rate_then is None
                  else "after_last_session" if later.empty else None)
        if reason:
            excluded.append({"id": lot.get("id"), "symbol": symbol, "purchase_date": lot["purchase_date"],
                             "reason": reason})
            continue
        assert price_then is not None and rate_then is not None
        cost_eur = (lot["shares"] * lot["price"] + lot["commission"]) * rate_then
        commissions += lot["commission"] * rate_then
        first = later[0]
        path = prices.reindex(sessions).ffill(limit=5) / price_then
        fx_path = rates.reindex(sessions).ffill(limit=5)
        value = lot["shares"] * lot["price"] * path * fx_path
        value[sessions < first] = 0.0
        total = total + value  # A missing price or rate after the purchase leaves the session incomplete.
        by_currency[currency] = by_currency.get(currency, pd.Series(0.0, index=sessions)) + value
        flows[first] += cost_eur
        executed.append((first.date(), cost_eur))
    invested = flows.cumsum()
    frame = pd.DataFrame({"flow_eur": flows, "contributed_eur": invested, "value_eur": total})
    incomplete = frame.index[frame["value_eur"].isna()]
    frame = frame[(frame["contributed_eur"] > 0) & frame["value_eur"].notna()].copy()
    # A flow on a dropped session enters on the next complete one.
    frame["flow_eur"] = frame["contributed_eur"].diff().fillna(frame["contributed_eur"])
    last = frame.index[-1] if not frame.empty else None
    value_by_currency = {currency: float(values[last]) for currency, values in by_currency.items()}         if last is not None else {}
    return {"daily": frame, "costs_eur": commissions, "pending": [], "pending_eur": 0.0, "flows": executed,
            "excluded": excluded, "incomplete_sessions": len(incomplete), "value_by_currency": value_by_currency}


# Declared shocks, not forecasts: market in local currency, the euro against the dollar and an opening gap.
SCENARIOS = (
    ("market_-10", "Mercado −10 %", -0.10, 0.0),
    ("market_-20", "Mercado −20 %", -0.20, 0.0),
    ("market_-35", "Mercado −35 %, como en 2020", -0.35, 0.0),
    ("euro_+10", "El euro sube un 10 % frente al dólar", 0.0, 0.10),
    ("euro_-10", "El euro baja un 10 % frente al dólar", 0.0, -0.10),
    ("market_-20_euro_+10", "Mercado −20 % y euro +10 %", -0.20, 0.10),
    ("gap_-7", "Apertura con hueco del −7 %: no se puede vender antes del hueco", -0.07, 0.0),
)


def scenarios(value_eur: float, usd_share: float, loss_tolerance: float) -> list[dict]:
    """Instant EUR effect of each declared shock on ``value_eur`` with ``usd_share`` exposed to the dollar.

    A dollar asset loses ``1 − 1/(1 + e)`` in euros when the euro rises by ``e``.
    Exceeding the tolerance is a reason to review the plan, never an automatic sale."""
    if not 0 <= usd_share <= 1:
        raise ValueError("La exposición al dólar debe estar entre 0 y 1.")
    rows = []
    for key, label, market, euro in SCENARIOS:
        currency = (1 - usd_share) + usd_share / (1 + euro)
        change = (1 + market) * currency - 1
        rows.append({"id": key, "label": label, "market": market, "euro": euro, "change": change,
                     "change_eur": value_eur * change, "value_eur": value_eur * (1 + change),
                     "exceeds_tolerance": change <= -loss_tolerance})
    return rows


def combine(first: dict, second: dict) -> dict:
    """Two simulation results held together, as a ``performance`` input.

    On a session missing from one side, that side keeps its last value (a lot
    history drops incomplete sessions)."""
    a, b = first["daily"], second["daily"]
    days = a.index.union(b.index)

    def side(frame: pd.DataFrame, column: str) -> pd.Series:
        return frame[column].reindex(days).ffill().fillna(0.0)

    frame = pd.DataFrame({"contributed_eur": side(a, "contributed_eur") + side(b, "contributed_eur"),
                          "value_eur": side(a, "value_eur") + side(b, "value_eur")})
    frame = frame[frame["contributed_eur"] > 0].copy()
    frame["flow_eur"] = frame["contributed_eur"].diff().fillna(frame["contributed_eur"])
    return {"daily": frame, "costs_eur": first["costs_eur"] + second["costs_eur"],
            "pending": [*first["pending"], *second["pending"]],
            "pending_eur": first["pending_eur"] + second["pending_eur"]}
